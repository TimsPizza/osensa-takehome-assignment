import asyncio
import logging
from typing import Protocol
from uuid import UUID

import aiomqtt
from pydantic import ValidationError

from app.config import Settings
from app.models import FoodReady, OrderRequested
from app.order_processor import OrderProcessor
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
    FOOD_READY_TOPIC,
    MQTT_QOS,
    ORDER_REQUESTED_TOPIC,
    decode_order_requested,
    encode_food_ready,
)

LOGGER = logging.getLogger(__name__)


class Processor(Protocol):
    async def process(self, order: OrderRequested) -> FoodReady: ...


class MqttOrderService:
    def __init__(
        self,
        settings: Settings,
        processor: Processor | None = None,
        registry: OrderRegistry | None = None,
        *,
        max_concurrent_orders: int = 8,
        max_queued_orders: int = 256,
    ) -> None:
        if max_concurrent_orders < 1:
            raise ValueError("max_concurrent_orders must be greater than zero")
        if max_queued_orders < 1:
            raise ValueError("max_queued_orders must be greater than zero")

        self._settings = settings
        self._processor = processor if processor is not None else OrderProcessor()
        self._registry = registry if registry is not None else OrderRegistry()
        self._worker_count = max_concurrent_orders
        self._processing_queue: asyncio.Queue[UUID] = asyncio.Queue(
            maxsize=max_queued_orders,
        )
        self._ready_orders: asyncio.Queue[OrderState] = asyncio.Queue(
            maxsize=max_concurrent_orders + max_queued_orders,
        )
        self._pending_order: OrderState | None = None

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
            max_queued_incoming_messages=100,
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

    async def _run_connected(self, client: aiomqtt.Client) -> None:
        connection_tasks = {
            asyncio.create_task(
                self._receive_orders(client),
                name="mqtt-order-receiver",
            ),
            asyncio.create_task(
                self._publish_ready_food(client),
                name="mqtt-food-publisher",
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
            await self._ready_orders.put(registration.state)
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
            LOGGER.warning(
                "order_queue_admission_failed order_id=%s table_id=%d status=%s",
                order.order_id,
                order.table_id,
                failed_order.status,
            )
            return

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
                await self._process_order(processing_order, worker_number)
            finally:
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
        await self._ready_orders.put(ready_order)
        LOGGER.info(
            "order_processing_finished order_id=%s table_id=%d status=%s worker=%d",
            food.order_id,
            food.table_id,
            ready_order.status,
            worker_number,
        )

    async def _publish_ready_food(self, client: aiomqtt.Client) -> None:
        while True:
            if self._pending_order is None:
                self._pending_order = await self._ready_orders.get()

            ready_order = self._pending_order
            food = ready_order.food
            if food is None:
                raise RuntimeError(
                    f"{ready_order.status} order {ready_order.order.order_id} has no food"
                )

            await client.publish(
                FOOD_READY_TOPIC,
                payload=encode_food_ready(food),
                qos=MQTT_QOS,
                retain=False,
            )
            published_order = self._registry.apply(
                ready_order.order.order_id,
                PublishConfirmed(),
            )
            LOGGER.info(
                "food_published order_id=%s table_id=%d topic=%s status=%s",
                food.order_id,
                food.table_id,
                FOOD_READY_TOPIC,
                published_order.status,
            )
            self._pending_order = None
