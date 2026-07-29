import asyncio
import logging
from typing import Protocol
from uuid import UUID, uuid4

import aiomqtt
from pydantic import ValidationError

from app.config import Settings
from app.kitchen_pressure import KitchenPressureProjection
from app.models import (
    FoodReady,
    KitchenPressureSnapshot,
    OrderFailed,
    OrderProcessing,
    OrderQueued,
    OrderRequested,
    OrderStatusUpdate,
)
from app.order_processor import Clock, OrderProcessor, utc_now
from app.order_registry import OrderRegistry, RegistrationAction
from app.order_state import (
    FoodPrepared,
    OrderState,
    ProcessingFailed,
    ProcessingStarted,
    PublishConfirmed,
    QueueAdmissionFailed,
)
from app.protocol import (
    KITCHEN_PRESSURE_TOPIC,
    MQTT_QOS,
    ORDER_REQUESTED_TOPIC,
    ORDER_STATUS_CHANGED_TOPIC,
    decode_order_requested,
    encode_kitchen_pressure,
    encode_order_status_changed,
    encode_table_snapshot,
    table_snapshot_topic,
)
from app.table_projection import TableSnapshotProjection

LOGGER = logging.getLogger(__name__)
PROCESSING_FAILED_MESSAGE = "The order could not be prepared. Please retry."
SERVICE_OVERLOADED_MESSAGE = "The order service is at capacity. Please retry."


class Processor(Protocol):
    async def process(self, order: OrderRequested) -> FoodReady: ...


class MqttOrderService:
    def __init__(
        self,
        settings: Settings,
        processor: Processor | None = None,
        registry: OrderRegistry | None = None,
        *,
        max_concurrent_orders: int | None = None,
        max_queued_orders: int | None = None,
        clock: Clock = utc_now,
    ) -> None:
        worker_count = (
            settings.order_worker_count
            if max_concurrent_orders is None
            else max_concurrent_orders
        )
        queue_capacity = (
            settings.order_queue_capacity
            if max_queued_orders is None
            else max_queued_orders
        )
        if worker_count < 1 or worker_count > 64:
            raise ValueError("max_concurrent_orders must be between 1 and 64")
        if queue_capacity < 1 or queue_capacity > 10_000:
            raise ValueError("max_queued_orders must be between 1 and 10000")

        self._settings = settings
        self._processor = processor if processor is not None else OrderProcessor()
        self._registry = registry if registry is not None else OrderRegistry()
        self._clock = clock
        self._worker_count = worker_count
        self._processing_queue: asyncio.Queue[UUID] = asyncio.Queue(
            maxsize=queue_capacity,
        )
        self._status_updates: asyncio.Queue[OrderStatusUpdate] = asyncio.Queue(
            maxsize=(worker_count + queue_capacity) * 4,
        )
        self._pending_update: OrderStatusUpdate | None = None
        self._service_instance_id = uuid4()
        self._table_projection = TableSnapshotProjection(
            service_instance_id=self._service_instance_id,
        )
        self._pressure_projection = KitchenPressureProjection(
            service_instance_id=self._service_instance_id,
            worker_count=worker_count,
            queue_capacity=queue_capacity,
        )
        self._pressure_changed = asyncio.Event()
        self._pending_pressure_snapshot: KitchenPressureSnapshot | None = None
        self._snapshots_initialized = False

    def _client(self) -> aiomqtt.Client:
        return aiomqtt.Client(
            hostname=self._settings.mqtt_host,
            port=self._settings.mqtt_port,
            username=self._settings.mqtt_username,
            password=self._settings.mqtt_password,
            identifier=self._settings.mqtt_client_id,
            clean_session=True,
            transport="websockets",
            websocket_path=self._settings.mqtt_websocket_path,
            # A bounded aiomqtt queue silently discards overflow. Admission control
            # belongs to _processing_queue, where callers receive an explicit failure.
            max_queued_incoming_messages=0,
            max_concurrent_outgoing_calls=10,
        )

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tasks:
            for worker_number in range(1, self._worker_count + 1):
                tasks.create_task(
                    self._consume_orders(worker_number),
                    name=f"order-worker-{worker_number}",
                )
            tasks.create_task(
                self._maintain_connection(),
                name="mqtt-connection-manager",
            )

    async def _maintain_connection(self) -> None:
        reconnect_delay = self._settings.reconnect_delay_seconds

        while True:
            try:
                async with self._client() as client:
                    if not self._snapshots_initialized:
                        await self._initialize_retained_snapshots(client)
                    await client.subscribe(ORDER_REQUESTED_TOPIC, qos=MQTT_QOS)
                    reconnect_delay = self._settings.reconnect_delay_seconds
                    LOGGER.info(
                        "mqtt_subscribed topic=%s qos=%d transport=websockets",
                        ORDER_REQUESTED_TOPIC,
                        MQTT_QOS,
                    )
                    await self._run_connected(client)
            except asyncio.CancelledError:
                raise
            except aiomqtt.MqttError as error:
                LOGGER.warning(
                    "mqtt_connection_lost host=%s port=%d retry_seconds=%.1f error=%s",
                    self._settings.mqtt_host,
                    self._settings.mqtt_port,
                    reconnect_delay,
                    error,
                )

            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(
                reconnect_delay * 2,
                self._settings.reconnect_max_delay_seconds,
            )

    async def _initialize_retained_snapshots(self, client: aiomqtt.Client) -> None:
        snapshots = self._table_projection.initialize(self._clock())
        for snapshot in snapshots:
            topic = table_snapshot_topic(snapshot.table_id)
            await client.publish(
                topic,
                payload=encode_table_snapshot(snapshot),
                qos=MQTT_QOS,
                retain=True,
            )
            LOGGER.info(
                "table_snapshot_initialized table_id=%d topic=%s revision=%d",
                snapshot.table_id,
                topic,
                snapshot.revision,
            )
        pressure = self._pressure_projection.initialize(self._clock())
        await client.publish(
            KITCHEN_PRESSURE_TOPIC,
            payload=encode_kitchen_pressure(pressure),
            qos=MQTT_QOS,
            retain=True,
        )
        LOGGER.info(
            "kitchen_pressure_initialized topic=%s revision=%d workers=%d "
            "queue_capacity=%d",
            KITCHEN_PRESSURE_TOPIC,
            pressure.revision,
            len(pressure.workers),
            pressure.queue_capacity,
        )
        self._snapshots_initialized = True

    async def _run_connected(self, client: aiomqtt.Client) -> None:
        connection_tasks = {
            asyncio.create_task(
                self._receive_orders(client),
                name="mqtt-order-receiver",
            ),
            asyncio.create_task(
                self._publish_status_updates(client),
                name="mqtt-status-publisher",
            ),
            asyncio.create_task(
                self._publish_pressure_updates(client),
                name="mqtt-pressure-publisher",
            ),
        }

        try:
            done, _pending = await asyncio.wait(
                connection_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
        finally:
            for task in connection_tasks:
                task.cancel()
            await asyncio.gather(*connection_tasks, return_exceptions=True)

    async def _receive_orders(self, client: aiomqtt.Client) -> None:
        async for message in client.messages:
            await self._handle_message(message)

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        if str(message.topic) != ORDER_REQUESTED_TOPIC:
            LOGGER.warning("mqtt_unexpected_topic topic=%s", message.topic)
            return

        try:
            order = decode_order_requested(message.payload)
        except ValidationError as error:
            LOGGER.warning(
                "order_rejected reason=invalid_payload errors=%s",
                error.errors(include_url=False, include_input=False),
            )
            return

        LOGGER.info(
            "order_received order_id=%s table_id=%d",
            order.order_id,
            order.table_id,
        )

        registration = self._registry.register(order)

        if registration.action is RegistrationAction.IGNORE:
            LOGGER.info(
                "order_duplicate_ignored order_id=%s status=%s",
                order.order_id,
                registration.state.status,
            )
            return

        if registration.action is RegistrationAction.CONFLICT:
            LOGGER.warning(
                "order_conflict order_id=%s existing_table_id=%d received_table_id=%d",
                order.order_id,
                registration.state.order.table_id,
                order.table_id,
            )
            return

        if registration.action is RegistrationAction.REPUBLISH:
            food = registration.state.food
            if food is None:
                raise RuntimeError(f"republished order has no food: {order.order_id}")
            self._queue_status_update(food)
            LOGGER.info(
                "order_republish_scheduled order_id=%s status=%s",
                order.order_id,
                registration.state.status,
            )
            return

        try:
            self._processing_queue.put_nowait(order.order_id)
        except asyncio.QueueFull:
            failed_order = self._registry.apply(
                order.order_id,
                QueueAdmissionFailed("processing queue is full"),
            )
            self._queue_status_update(
                OrderFailed(
                    schemaVersion=1,
                    orderId=order.order_id,
                    tableId=order.table_id,
                    foodName=order.food_name,
                    status="failed",
                    occurredAt=self._clock(),
                    code="service_overloaded",
                    message=SERVICE_OVERLOADED_MESSAGE,
                    retryable=True,
                )
            )
            LOGGER.warning(
                "order_queue_admission_failed order_id=%s table_id=%d status=%s",
                order.order_id,
                order.table_id,
                failed_order.status,
            )
            return

        self._pressure_changed.set()
        self._queue_status_update(
            OrderQueued(
                schemaVersion=1,
                orderId=order.order_id,
                tableId=order.table_id,
                foodName=order.food_name,
                status="queued",
                occurredAt=self._clock(),
            )
        )
        LOGGER.info(
            "order_queued order_id=%s table_id=%d status=%s queue_size=%d",
            order.order_id,
            order.table_id,
            registration.state.status,
            self._processing_queue.qsize(),
        )

    async def _consume_orders(self, worker_number: int) -> None:
        while True:
            order_id = await self._processing_queue.get()
            try:
                processing_order = self._registry.apply(
                    order_id,
                    ProcessingStarted(),
                )
                order = processing_order.order
                self._pressure_projection.worker_started(worker_number, order)
                self._pressure_changed.set()
                self._queue_status_update(
                    OrderProcessing(
                        schemaVersion=1,
                        orderId=order.order_id,
                        tableId=order.table_id,
                        foodName=order.food_name,
                        status="processing",
                        occurredAt=self._clock(),
                    )
                )
                await self._process_order(processing_order, worker_number)
            finally:
                self._pressure_projection.worker_stopped(worker_number)
                self._pressure_changed.set()
                self._processing_queue.task_done()

    async def _process_order(
        self,
        processing_order: OrderState,
        worker_number: int,
    ) -> None:
        order = processing_order.order

        try:
            LOGGER.info(
                "order_processing_started order_id=%s table_id=%d status=%s worker=%d",
                order.order_id,
                order.table_id,
                processing_order.status,
                worker_number,
            )
            food = await self._processor.process(order)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failure_reason = f"{type(error).__name__}: {error}"
            failed_order = self._registry.apply(
                order.order_id,
                ProcessingFailed(failure_reason),
            )
            self._queue_status_update(
                OrderFailed(
                    schemaVersion=1,
                    orderId=order.order_id,
                    tableId=order.table_id,
                    foodName=order.food_name,
                    status="failed",
                    occurredAt=self._clock(),
                    code="processing_failed",
                    message=PROCESSING_FAILED_MESSAGE,
                    retryable=True,
                )
            )
            LOGGER.exception(
                "order_processing_failed order_id=%s table_id=%d status=%s reason=%s",
                order.order_id,
                order.table_id,
                failed_order.status,
                failed_order.failure_reason,
            )
            return

        ready_order = self._registry.apply(
            order.order_id,
            FoodPrepared(food),
        )
        self._queue_status_update(food)
        LOGGER.info(
            "order_processing_finished order_id=%s table_id=%d status=%s worker=%d",
            food.order_id,
            food.table_id,
            ready_order.status,
            worker_number,
        )

    def _queue_status_update(self, update: OrderStatusUpdate) -> None:
        try:
            self._status_updates.put_nowait(update)
        except asyncio.QueueFull as error:
            LOGGER.critical(
                "order_status_queue_full order_id=%s status=%s",
                update.order_id,
                update.status,
            )
            raise RuntimeError("order status update queue is full") from error

    async def _publish_status_updates(self, client: aiomqtt.Client) -> None:
        while True:
            if self._pending_update is None:
                self._pending_update = await self._status_updates.get()

            update = self._pending_update
            await client.publish(
                ORDER_STATUS_CHANGED_TOPIC,
                payload=encode_order_status_changed(update),
                qos=MQTT_QOS,
                retain=False,
            )
            snapshot = self._table_projection.apply(
                update,
                generated_at=self._clock(),
            )
            snapshot_topic = table_snapshot_topic(update.table_id)
            await client.publish(
                snapshot_topic,
                payload=encode_table_snapshot(snapshot),
                qos=MQTT_QOS,
                retain=True,
            )

            internal_status = update.status
            if isinstance(update, FoodReady):
                published_order = self._registry.apply(
                    update.order_id,
                    PublishConfirmed(),
                )
                internal_status = published_order.status

            LOGGER.info(
                "order_status_published order_id=%s table_id=%d topic=%s "
                "snapshot_topic=%s snapshot_revision=%d public_status=%s "
                "internal_status=%s",
                update.order_id,
                update.table_id,
                ORDER_STATUS_CHANGED_TOPIC,
                snapshot_topic,
                snapshot.revision,
                update.status,
                internal_status,
            )
            self._status_updates.task_done()
            self._pending_update = None

    async def _publish_pressure_updates(self, client: aiomqtt.Client) -> None:
        while True:
            if self._pending_pressure_snapshot is None:
                await self._pressure_changed.wait()
                self._pressure_changed.clear()
                self._pending_pressure_snapshot = self._pressure_projection.capture(
                    queued_orders=self._processing_queue.qsize(),
                    generated_at=self._clock(),
                )

            snapshot = self._pending_pressure_snapshot
            await client.publish(
                KITCHEN_PRESSURE_TOPIC,
                payload=encode_kitchen_pressure(snapshot),
                qos=MQTT_QOS,
                retain=True,
            )
            LOGGER.info(
                "kitchen_pressure_published topic=%s revision=%d queued_orders=%d "
                "busy_workers=%d",
                KITCHEN_PRESSURE_TOPIC,
                snapshot.revision,
                snapshot.queued_orders,
                sum(worker.status == "processing" for worker in snapshot.workers),
            )
            self._pending_pressure_snapshot = None
