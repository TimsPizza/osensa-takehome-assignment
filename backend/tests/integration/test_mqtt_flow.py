import asyncio
import json
import os
from uuid import uuid4

import aiomqtt
import pytest

from app.models import FoodReady, OrderRequested
from app.protocol import FOOD_READY_TOPIC, MQTT_QOS, ORDER_REQUESTED_TOPIC

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MQTT_INTEGRATION") != "1",
        reason="set RUN_MQTT_INTEGRATION=1 with the Compose stack running",
    ),
]

SUBSCRIPTION_COUNT_TOPIC = "$SYS/broker/subscriptions/count"


async def wait_until_backend_is_subscribed(client: aiomqtt.Client) -> None:
    async for message in client.messages:
        if str(message.topic) != SUBSCRIPTION_COUNT_TOPIC:
            continue
        if int(message.payload) >= 3:
            return
    raise AssertionError("MQTT message stream ended before the backend subscribed")


async def wait_for_food(client: aiomqtt.Client, order_id: str) -> tuple[FoodReady, aiomqtt.Message]:
    async for message in client.messages:
        if str(message.topic) != FOOD_READY_TOPIC:
            continue
        food = FoodReady.model_validate_json(message.payload)
        if str(food.order_id) == order_id:
            return food, message
    raise AssertionError("MQTT message stream ended before FOOD_READY arrived")


async def test_order_to_food_round_trip_over_websockets() -> None:
    host = os.getenv("MQTT_TEST_HOST", "localhost")
    port = int(os.getenv("MQTT_TEST_PORT", "9001"))
    websocket_path = os.getenv("MQTT_TEST_WEBSOCKET_PATH", "/mqtt")
    order_id = str(uuid4())

    async with asyncio.timeout(15):
        async with aiomqtt.Client(
            hostname=host,
            port=port,
            identifier=f"integration-test-{uuid4()}",
            clean_session=True,
            transport="websockets",
            websocket_path=websocket_path,
        ) as client:
            await client.subscribe(FOOD_READY_TOPIC, qos=MQTT_QOS)
            await client.subscribe(SUBSCRIPTION_COUNT_TOPIC, qos=0)
            await wait_until_backend_is_subscribed(client)

            order = OrderRequested.model_validate_json(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "orderId": order_id,
                        "tableId": 3,
                        "foodName": "Noodles",
                    }
                )
            )
            await client.publish(
                ORDER_REQUESTED_TOPIC,
                payload=order.model_dump_json().encode(),
                qos=MQTT_QOS,
                retain=False,
            )

            food, message = await wait_for_food(client, order_id)

    assert food.table_id == 3
    assert food.food_name == "Noodles"
    assert food.ready_at.tzinfo is not None
    assert message.qos == MQTT_QOS
    assert message.retain is False
