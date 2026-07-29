import asyncio
import logging
from datetime import UTC, datetime

import aiomqtt
from pydantic import ValidationError

from app.config import Settings
from app.models import FoodReady
from app.protocol import (
    FOOD_READY_TOPIC,
    MQTT_QOS,
    ORDER_REQUESTED_TOPIC,
    decode_order_requested,
    encode_food_ready,
)

LOGGER = logging.getLogger(__name__)


class MqttOrderService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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

                    async for message in client.messages:
                        await self._handle_message(client, message)
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

    async def _handle_message(
        self,
        client: aiomqtt.Client,
        message: aiomqtt.Message,
    ) -> None:
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
        food = FoodReady(
            schemaVersion=1,
            orderId=order.order_id,
            tableId=order.table_id,
            foodName=order.food_name,
            readyAt=datetime.now(UTC),
        )
        await client.publish(
            FOOD_READY_TOPIC,
            payload=encode_food_ready(food),
            qos=MQTT_QOS,
            retain=False,
        )
        LOGGER.info(
            "food_published order_id=%s table_id=%d topic=%s",
            food.order_id,
            food.table_id,
            FOOD_READY_TOPIC,
        )
