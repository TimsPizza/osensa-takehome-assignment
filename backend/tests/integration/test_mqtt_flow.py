import asyncio
import json
import os
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ExpectedFood:
    table_id: int
    food_name: str


async def wait_until_backend_is_subscribed(client: aiomqtt.Client) -> None:
    async for message in client.messages:
        if str(message.topic) != SUBSCRIPTION_COUNT_TOPIC:
            continue
        if int(message.payload) >= 3:
            return
    raise AssertionError("MQTT message stream ended before the backend subscribed")


async def wait_for_food(
    client: aiomqtt.Client,
    expected_order_ids: set[str],
) -> dict[str, tuple[FoodReady, aiomqtt.Message]]:
    received: dict[str, tuple[FoodReady, aiomqtt.Message]] = {}

    async for message in client.messages:
        if str(message.topic) != FOOD_READY_TOPIC:
            continue
        food = FoodReady.model_validate_json(message.payload)
        order_id = str(food.order_id)
        if order_id in expected_order_ids:
            received[order_id] = (food, message)
        if received.keys() == expected_order_ids:
            return received

    raise AssertionError("MQTT message stream ended before all FOOD_READY events arrived")


async def test_concurrent_orders_round_trip_over_websockets() -> None:
    host = os.getenv("MQTT_TEST_HOST", "localhost")
    port = int(os.getenv("MQTT_TEST_PORT", "9001"))
    websocket_path = os.getenv("MQTT_TEST_WEBSOCKET_PATH", "/mqtt")
    expected = {
        str(uuid4()): ExpectedFood(table_id=1, food_name="Noodles"),
        str(uuid4()): ExpectedFood(table_id=2, food_name="Pizza"),
        str(uuid4()): ExpectedFood(table_id=3, food_name="Soup"),
        str(uuid4()): ExpectedFood(table_id=4, food_name="Tacos"),
    }

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

            for order_id, expected_food in expected.items():
                order = OrderRequested.model_validate_json(
                    json.dumps(
                        {
                            "schemaVersion": 1,
                            "orderId": order_id,
                            "tableId": expected_food.table_id,
                            "foodName": expected_food.food_name,
                        }
                    )
                )
                await client.publish(
                    ORDER_REQUESTED_TOPIC,
                    payload=order.model_dump_json().encode(),
                    qos=MQTT_QOS,
                    retain=False,
                )

            received = await wait_for_food(client, set(expected))

    assert received.keys() == expected.keys()
    for order_id, expected_food in expected.items():
        food, message = received[order_id]
        assert food.table_id == expected_food.table_id
        assert food.food_name == expected_food.food_name
        assert food.ready_at.tzinfo is not None
        assert message.qos == MQTT_QOS
        assert message.retain is False
