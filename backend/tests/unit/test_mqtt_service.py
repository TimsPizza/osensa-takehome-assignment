import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from app.config import Settings
from app.models import FoodReady, OrderRequested
from app.mqtt_service import MqttOrderService
from app.order_state import (
    FoodPrepared,
    OrderStatus,
    ProcessingStarted,
    PublishConfirmed,
)
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
        self.calls = 0
        self.max_active = 0
        self.all_started = asyncio.Event()
        self.release = asyncio.Event()
        self.expected_concurrency = expected_concurrency

    async def process(self, order: OrderRequested) -> FoodReady:
        self.calls += 1
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


class FailOnceProcessor:
    def __init__(self) -> None:
        self.calls = 0

    async def process(self, order: OrderRequested) -> FoodReady:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("kitchen unavailable")
        return FoodReady(
            schemaVersion=1,
            orderId=order.order_id,
            tableId=order.table_id,
            foodName=order.food_name,
            readyAt=READY_AT,
        )


@asynccontextmanager
async def running_workers(
    service: MqttOrderService,
    count: int,
) -> AsyncIterator[None]:
    workers = tuple(
        asyncio.create_task(
            service._consume_orders(worker_number),
            name=f"test-order-worker-{worker_number}",
        )
        for worker_number in range(1, count + 1)
    )
    try:
        yield
    finally:
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


async def test_orders_wait_queued_until_a_worker_is_available() -> None:
    processor = GatedProcessor(expected_concurrency=2)
    service = MqttOrderService(
        make_settings(),
        processor,
        max_concurrent_orders=2,
        max_queued_orders=2,
    )

    async with running_workers(service, count=2):
        await service._handle_message(make_message(FIRST_ORDER_ID, 1))
        await service._handle_message(make_message(SECOND_ORDER_ID, 2))
        await asyncio.wait_for(processor.all_started.wait(), timeout=1)

        await service._handle_message(make_message(THIRD_ORDER_ID, 3))
        third_order = service._registry.get(THIRD_ORDER_ID)

        assert processor.max_active == 2
        assert third_order is not None
        assert third_order.status is OrderStatus.QUEUED
        assert service._processing_queue.qsize() == 1

        processor.release.set()
        ready_orders = [
            await asyncio.wait_for(service._ready_orders.get(), timeout=1) for _ in range(3)
        ]
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)

        assert processor.max_active == 2
        assert all(order.status is OrderStatus.FOOD_READY for order in ready_orders)
        assert {order.food.order_id for order in ready_orders if order.food is not None} == {
            FIRST_ORDER_ID,
            SECOND_ORDER_ID,
            THIRD_ORDER_ID,
        }


async def test_duplicate_processing_order_is_not_processed_twice() -> None:
    processor = GatedProcessor(expected_concurrency=1)
    service = MqttOrderService(
        make_settings(),
        processor,
        max_concurrent_orders=2,
    )
    message = make_message(FIRST_ORDER_ID, 1)

    async with running_workers(service, count=2):
        await service._handle_message(message)
        await asyncio.wait_for(processor.all_started.wait(), timeout=1)
        await service._handle_message(message)

        assert processor.calls == 1

        processor.release.set()
        ready_order = await asyncio.wait_for(service._ready_orders.get(), timeout=1)
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)

        assert ready_order.status is OrderStatus.FOOD_READY
        assert ready_order.order.order_id == FIRST_ORDER_ID
        assert processor.calls == 1


async def test_conflicting_payload_does_not_start_another_processor() -> None:
    processor = GatedProcessor(expected_concurrency=1)
    service = MqttOrderService(
        make_settings(),
        processor,
        max_concurrent_orders=2,
    )

    async with running_workers(service, count=2):
        await service._handle_message(make_message(FIRST_ORDER_ID, 1))
        await asyncio.wait_for(processor.all_started.wait(), timeout=1)
        await service._handle_message(make_message(FIRST_ORDER_ID, 3))

        assert processor.calls == 1

        processor.release.set()
        ready_order = await asyncio.wait_for(service._ready_orders.get(), timeout=1)
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)

        assert ready_order.order.table_id == 1
        assert service._registry.get(FIRST_ORDER_ID) is ready_order
        assert processor.calls == 1


async def test_duplicate_published_order_requeues_cached_food_without_processing() -> None:
    processor = GatedProcessor(expected_concurrency=1)
    service = MqttOrderService(make_settings(), processor)
    message = make_message(FIRST_ORDER_ID, 1)
    order = OrderRequested.model_validate_json(message.payload)
    food = FoodReady(
        schemaVersion=1,
        orderId=order.order_id,
        tableId=order.table_id,
        foodName=order.food_name,
        readyAt=READY_AT,
    )
    service._registry.register(order)
    service._registry.apply(order.order_id, ProcessingStarted())
    service._registry.apply(order.order_id, FoodPrepared(food))
    service._registry.apply(order.order_id, PublishConfirmed())

    await service._handle_message(message)

    ready_order = await asyncio.wait_for(service._ready_orders.get(), timeout=1)
    assert ready_order.status is OrderStatus.FOOD_READY
    assert ready_order.food is food
    assert processor.calls == 0


async def test_full_queue_fails_new_order_without_leaving_it_queued() -> None:
    processor = GatedProcessor(expected_concurrency=1)
    service = MqttOrderService(
        make_settings(),
        processor,
        max_concurrent_orders=1,
        max_queued_orders=1,
    )

    async with running_workers(service, count=1):
        await service._handle_message(make_message(FIRST_ORDER_ID, 1))
        await asyncio.wait_for(processor.all_started.wait(), timeout=1)
        await service._handle_message(make_message(SECOND_ORDER_ID, 2))
        await service._handle_message(make_message(THIRD_ORDER_ID, 3))

        queued_order = service._registry.get(SECOND_ORDER_ID)
        rejected_order = service._registry.get(THIRD_ORDER_ID)

        assert queued_order is not None
        assert queued_order.status is OrderStatus.QUEUED
        assert rejected_order is not None
        assert rejected_order.status is OrderStatus.FAILED
        assert rejected_order.failure_reason == "processing queue is full"
        assert service._processing_queue.qsize() == 1

        processor.release.set()
        ready_orders = [
            await asyncio.wait_for(service._ready_orders.get(), timeout=1) for _ in range(2)
        ]
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)

        assert {state.order.order_id for state in ready_orders} == {
            FIRST_ORDER_ID,
            SECOND_ORDER_ID,
        }
        assert processor.calls == 2


async def test_processing_failure_does_not_stop_worker_from_consuming() -> None:
    processor = FailOnceProcessor()
    service = MqttOrderService(
        make_settings(),
        processor,
        max_concurrent_orders=1,
        max_queued_orders=2,
    )

    async with running_workers(service, count=1):
        await service._handle_message(make_message(FIRST_ORDER_ID, 1))
        await service._handle_message(make_message(SECOND_ORDER_ID, 2))

        ready_order = await asyncio.wait_for(service._ready_orders.get(), timeout=1)
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)

        failed_order = service._registry.get(FIRST_ORDER_ID)
        assert failed_order is not None
        assert failed_order.status is OrderStatus.FAILED
        assert failed_order.failure_reason == "RuntimeError: kitchen unavailable"
        assert ready_order.order.order_id == SECOND_ORDER_ID
        assert ready_order.status is OrderStatus.FOOD_READY
        assert processor.calls == 2


async def test_default_worker_pool_handles_a_saturated_burst_without_loss() -> None:
    worker_count = 8
    queue_capacity = 256
    rejected_count = 16
    accepted_count = worker_count + queue_capacity
    order_ids = tuple(UUID(int=number) for number in range(1, accepted_count + rejected_count + 1))
    processor = GatedProcessor(expected_concurrency=worker_count)
    service = MqttOrderService(make_settings(), processor)

    assert service._worker_count == worker_count
    assert service._processing_queue.maxsize == queue_capacity

    async with running_workers(service, count=worker_count):
        for index, order_id in enumerate(order_ids[:worker_count]):
            await service._handle_message(
                make_message(order_id, table_id=(index % 4) + 1),
            )
        await asyncio.wait_for(processor.all_started.wait(), timeout=1)

        for index, order_id in enumerate(
            order_ids[worker_count:],
            start=worker_count,
        ):
            await service._handle_message(
                make_message(order_id, table_id=(index % 4) + 1),
            )

        saturated_states = tuple(service._registry.get(order_id) for order_id in order_ids)
        saturated_counts = Counter(state.status for state in saturated_states if state is not None)

        assert all(state is not None for state in saturated_states)
        assert saturated_counts == {
            OrderStatus.PROCESSING: worker_count,
            OrderStatus.QUEUED: queue_capacity,
            OrderStatus.FAILED: rejected_count,
        }
        assert service._processing_queue.qsize() == queue_capacity
        assert processor.max_active == worker_count

        processor.release.set()
        await asyncio.wait_for(service._processing_queue.join(), timeout=5)

        ready_orders = tuple(service._ready_orders.get_nowait() for _ in range(accepted_count))
        final_states = tuple(service._registry.get(order_id) for order_id in order_ids)
        final_counts = Counter(state.status for state in final_states if state is not None)
        ready_order_ids = {
            state.order.order_id for state in ready_orders if state.status is OrderStatus.FOOD_READY
        }

        assert final_counts == {
            OrderStatus.FOOD_READY: accepted_count,
            OrderStatus.FAILED: rejected_count,
        }
        assert len(ready_orders) == accepted_count
        assert ready_order_ids == set(order_ids[:accepted_count])
        assert processor.calls == accepted_count
        assert processor.max_active == worker_count
        assert service._processing_queue.empty()
        assert service._ready_orders.empty()
