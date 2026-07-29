import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from app.config import Settings
from app.models import FoodReady, OrderRequested
from app.mqtt_service import MqttOrderService
from app.protocol import ORDER_REQUESTED_TOPIC

FIRST_ORDER_ID = UUID("3b11d31c-7d34-4dda-91e5-d64721a50463")
SECOND_ORDER_ID = UUID("4a22d42d-8e45-4eeb-a2f6-e75832b61574")
THIRD_ORDER_ID = UUID("5b33e53e-9f56-4ffc-b307-f86943c72685")
READY_AT = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)


def make_settings() -> Settings:
    return Settings(
        mqtt_host="localhost",
        mqtt_port=9001,
        mqtt_websocket_path="/mqtt",
        mqtt_client_id="test-order-service",
        mqtt_username=None,
        mqtt_password=None,
        reconnect_delay_seconds=1,
        reconnect_max_delay_seconds=30,
        log_level="INFO",
    )


def make_message(order_id: UUID, table_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        topic=ORDER_REQUESTED_TOPIC,
        payload=json.dumps(
            {
                "schemaVersion": 1,
                "orderId": str(order_id),
                "tableId": table_id,
                "foodName": f"Food for table {table_id}",
            }
        ).encode(),
    )


class GatedProcessor:
    def __init__(self, expected_concurrency: int) -> None:
        self.active = 0
        self.max_active = 0
        self.all_started = asyncio.Event()
        self.release = asyncio.Event()
        self.expected_concurrency = expected_concurrency

    async def process(self, order: OrderRequested) -> FoodReady:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.active == self.expected_concurrency:
            self.all_started.set()

        try:
            await self.release.wait()
            return FoodReady(
                schemaVersion=1,
                orderId=order.order_id,
                tableId=order.table_id,
                foodName=order.food_name,
                readyAt=READY_AT,
            )
        finally:
            self.active -= 1


async def test_orders_run_concurrently_with_bounded_backpressure() -> None:
    processor = GatedProcessor(expected_concurrency=2)
    service = MqttOrderService(
        make_settings(),
        processor,
        max_concurrent_orders=2,
    )

    await service._handle_message(make_message(FIRST_ORDER_ID, 1))
    await service._handle_message(make_message(SECOND_ORDER_ID, 2))
    await asyncio.wait_for(processor.all_started.wait(), timeout=1)

    third_order = asyncio.create_task(
        service._handle_message(make_message(THIRD_ORDER_ID, 3)),
    )
    await asyncio.sleep(0)

    assert processor.max_active == 2
    assert not third_order.done()

    processor.release.set()
    await asyncio.wait_for(third_order, timeout=1)
    ready_food = [await asyncio.wait_for(service._ready_food.get(), timeout=1) for _ in range(3)]
    await asyncio.gather(*tuple(service._processing_tasks))

    assert processor.max_active == 2
    assert {food.order_id for food in ready_food} == {
        FIRST_ORDER_ID,
        SECOND_ORDER_ID,
        THIRD_ORDER_ID,
    }
