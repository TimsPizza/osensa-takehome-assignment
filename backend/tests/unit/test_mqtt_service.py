import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from app.config import Settings
from app.models import FoodReady, OrderFailed, OrderRequested, OrderStatusUpdate
from app.mqtt_service import MqttOrderService
from app.order_state import (
    FoodPrepared,
    OrderStatus,
    ProcessingStarted,
    PublishConfirmed,
)
from app.protocol import (
    MQTT_QOS,
    ORDER_REQUESTED_TOPIC,
    ORDER_STATUS_CHANGED_TOPIC,
    decode_order_status_changed,
)

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
                status="food_ready",
                occurredAt=READY_AT,
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
            status="food_ready",
            occurredAt=READY_AT,
            readyAt=READY_AT,
        )


class RecordingClient:
    def __init__(self, expected_messages: int) -> None:
        self.published: list[tuple[str, bytes, int, bool]] = []
        self.expected_messages = expected_messages
        self.all_published = asyncio.Event()

    async def publish(
        self,
        topic: str,
        payload: bytes,
        qos: int,
        retain: bool,
    ) -> None:
        self.published.append((topic, payload, qos, retain))
        if len(self.published) == self.expected_messages:
            self.all_published.set()


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


def drain_status_updates(service: MqttOrderService) -> tuple[OrderStatusUpdate, ...]:
    updates: list[OrderStatusUpdate] = []
    while not service._status_updates.empty():
        updates.append(service._status_updates.get_nowait())
        service._status_updates.task_done()
    return tuple(updates)


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
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)
        ready_orders = tuple(
            service._registry.get(order_id)
            for order_id in (FIRST_ORDER_ID, SECOND_ORDER_ID, THIRD_ORDER_ID)
        )

        assert processor.max_active == 2
        assert all(
            order is not None and order.status is OrderStatus.FOOD_READY for order in ready_orders
        )
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
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)
        ready_order = service._registry.get(FIRST_ORDER_ID)

        assert ready_order is not None
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
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)
        ready_order = service._registry.get(FIRST_ORDER_ID)

        assert ready_order is not None
        assert ready_order.order.table_id == 1
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
        status="food_ready",
        occurredAt=READY_AT,
        readyAt=READY_AT,
    )
    service._registry.register(order)
    service._registry.apply(order.order_id, ProcessingStarted())
    service._registry.apply(order.order_id, FoodPrepared(food))
    service._registry.apply(order.order_id, PublishConfirmed())

    await service._handle_message(message)

    update = await asyncio.wait_for(service._status_updates.get(), timeout=1)
    service._status_updates.task_done()
    assert isinstance(update, FoodReady)
    assert update is food
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
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)
        updates = drain_status_updates(service)
        ready_orders = tuple(
            service._registry.get(order_id) for order_id in (FIRST_ORDER_ID, SECOND_ORDER_ID)
        )
        failed_update = next(
            update
            for update in updates
            if update.order_id == THIRD_ORDER_ID and isinstance(update, OrderFailed)
        )

        assert {state.order.order_id for state in ready_orders if state is not None} == {
            FIRST_ORDER_ID,
            SECOND_ORDER_ID,
        }
        assert failed_update.code == "service_overloaded"
        assert failed_update.retryable is True
        assert "processing queue is full" not in failed_update.message
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

        await asyncio.wait_for(service._processing_queue.join(), timeout=1)
        updates = drain_status_updates(service)

        failed_order = service._registry.get(FIRST_ORDER_ID)
        ready_order = service._registry.get(SECOND_ORDER_ID)
        failed_update = next(
            update
            for update in updates
            if update.order_id == FIRST_ORDER_ID and isinstance(update, OrderFailed)
        )
        assert failed_order is not None
        assert failed_order.status is OrderStatus.FAILED
        assert failed_order.failure_reason == "RuntimeError: kitchen unavailable"
        assert failed_update.code == "processing_failed"
        assert failed_update.retryable is True
        assert "RuntimeError" not in failed_update.message
        assert "kitchen unavailable" not in failed_update.message
        assert ready_order is not None
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

        updates = drain_status_updates(service)
        final_states = tuple(service._registry.get(order_id) for order_id in order_ids)
        final_counts = Counter(state.status for state in final_states if state is not None)
        ready_order_ids = {update.order_id for update in updates if isinstance(update, FoodReady)}
        update_counts = Counter(update.status for update in updates)

        assert final_counts == {
            OrderStatus.FOOD_READY: accepted_count,
            OrderStatus.FAILED: rejected_count,
        }
        assert update_counts == {
            "queued": accepted_count,
            "processing": accepted_count,
            "food_ready": accepted_count,
            "failed": rejected_count,
        }
        assert ready_order_ids == set(order_ids[:accepted_count])
        assert processor.calls == accepted_count
        assert processor.max_active == worker_count
        assert service._processing_queue.empty()
        assert service._status_updates.empty()


async def test_publisher_emits_ordered_status_union_and_confirms_ready_food() -> None:
    processor = GatedProcessor(expected_concurrency=1)
    processor.release.set()
    service = MqttOrderService(
        make_settings(),
        processor,
        max_concurrent_orders=1,
        max_queued_orders=1,
    )

    async with running_workers(service, count=1):
        await service._handle_message(make_message(FIRST_ORDER_ID, 1))
        await asyncio.wait_for(service._processing_queue.join(), timeout=1)

    ready_order = service._registry.get(FIRST_ORDER_ID)
    assert ready_order is not None
    assert ready_order.status is OrderStatus.FOOD_READY

    client = RecordingClient(expected_messages=3)
    publisher = asyncio.create_task(service._publish_status_updates(client))  # type: ignore[arg-type]
    try:
        await asyncio.wait_for(client.all_published.wait(), timeout=1)
    finally:
        publisher.cancel()
        await asyncio.gather(publisher, return_exceptions=True)

    updates = [
        decode_order_status_changed(payload) for _topic, payload, _qos, _retain in client.published
    ]
    published_order = service._registry.get(FIRST_ORDER_ID)

    assert [update.status for update in updates] == [
        "queued",
        "processing",
        "food_ready",
    ]
    assert all(
        topic == ORDER_STATUS_CHANGED_TOPIC and qos == MQTT_QOS and retain is False
        for topic, _payload, qos, retain in client.published
    )
    assert published_order is not None
    assert published_order.status is OrderStatus.PUBLISHED
    assert service._status_updates.empty()
    assert service._pending_update is None
