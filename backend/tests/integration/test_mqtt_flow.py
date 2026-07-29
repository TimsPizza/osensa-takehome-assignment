import asyncio
import json
import os
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

import aiomqtt
import pytest

from app.models import (
    FoodReady,
    KitchenPressureSnapshot,
    OrderFailed,
    OrderRequested,
    TableSnapshot,
)
from app.protocol import (
    KITCHEN_PRESSURE_TOPIC,
    MQTT_QOS,
    ORDER_REQUESTED_TOPIC,
    ORDER_STATUS_CHANGED_TOPIC,
    decode_kitchen_pressure,
    decode_order_status_changed,
    decode_table_snapshot,
    table_snapshot_topic,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MQTT_INTEGRATION") != "1",
        reason="set RUN_MQTT_INTEGRATION=1 with the Compose stack running",
    ),
]

SUBSCRIPTION_COUNT_TOPIC = "$SYS/broker/subscriptions/count"
LOAD_TEST = pytest.mark.skipif(
    os.getenv("RUN_MQTT_LOAD") != "1",
    reason="set RUN_MQTT_LOAD=1 to run MQTT burst tests",
)


@dataclass(frozen=True, slots=True)
class ExpectedFood:
    table_id: int
    food_name: str


def order_payload(
    *,
    order_id: str,
    table_id: object = 1,
    food_name: object = "Soup",
    schema_version: object = 1,
    **extra: object,
) -> bytes:
    return json.dumps(
        {
            "schemaVersion": schema_version,
            "orderId": order_id,
            "tableId": table_id,
            "foodName": food_name,
            **extra,
        }
    ).encode()


async def wait_until_backend_is_subscribed(client: aiomqtt.Client) -> None:
    async for message in client.messages:
        if str(message.topic) != SUBSCRIPTION_COUNT_TOPIC:
            continue
        if int(message.payload) >= 3:
            return
    raise AssertionError("MQTT message stream ended before the backend subscribed")


@asynccontextmanager
async def connected_client(
    *,
    max_outgoing_calls: int = 10,
) -> AsyncIterator[aiomqtt.Client]:
    host = os.getenv("MQTT_TEST_HOST", "localhost")
    port = int(os.getenv("MQTT_TEST_PORT", "9001"))
    websocket_path = os.getenv("MQTT_TEST_WEBSOCKET_PATH", "/mqtt")

    async with aiomqtt.Client(
        hostname=host,
        port=port,
        identifier=f"integration-test-{uuid4()}",
        clean_session=True,
        transport="websockets",
        websocket_path=websocket_path,
        max_concurrent_outgoing_calls=max_outgoing_calls,
    ) as client:
        await client.subscribe(ORDER_STATUS_CHANGED_TOPIC, qos=MQTT_QOS)
        await client.subscribe(SUBSCRIPTION_COUNT_TOPIC, qos=0)
        await wait_until_backend_is_subscribed(client)
        yield client


@asynccontextmanager
async def snapshot_client(table_id: int) -> AsyncIterator[aiomqtt.Client]:
    host = os.getenv("MQTT_TEST_HOST", "localhost")
    port = int(os.getenv("MQTT_TEST_PORT", "9001"))
    websocket_path = os.getenv("MQTT_TEST_WEBSOCKET_PATH", "/mqtt")

    async with aiomqtt.Client(
        hostname=host,
        port=port,
        identifier=f"snapshot-test-{uuid4()}",
        clean_session=True,
        transport="websockets",
        websocket_path=websocket_path,
    ) as client:
        await client.subscribe(table_snapshot_topic(table_id), qos=MQTT_QOS)
        yield client


@asynccontextmanager
async def pressure_client() -> AsyncIterator[aiomqtt.Client]:
    host = os.getenv("MQTT_TEST_HOST", "localhost")
    port = int(os.getenv("MQTT_TEST_PORT", "9001"))
    websocket_path = os.getenv("MQTT_TEST_WEBSOCKET_PATH", "/mqtt")

    async with aiomqtt.Client(
        hostname=host,
        port=port,
        identifier=f"pressure-test-{uuid4()}",
        clean_session=True,
        transport="websockets",
        websocket_path=websocket_path,
    ) as client:
        await client.subscribe(KITCHEN_PRESSURE_TOPIC, qos=MQTT_QOS)
        yield client


async def publish_payload(client: aiomqtt.Client, payload: bytes) -> None:
    await client.publish(
        ORDER_REQUESTED_TOPIC,
        payload=payload,
        qos=MQTT_QOS,
        retain=False,
    )


async def wait_for_food(
    client: aiomqtt.Client,
    expected_order_ids: set[str],
) -> tuple[
    dict[str, tuple[FoodReady, aiomqtt.Message]],
    dict[str, list[str]],
]:
    received: dict[str, tuple[FoodReady, aiomqtt.Message]] = {}
    statuses = {order_id: [] for order_id in expected_order_ids}

    async for message in client.messages:
        if str(message.topic) != ORDER_STATUS_CHANGED_TOPIC:
            continue
        update = decode_order_status_changed(message.payload)
        order_id = str(update.order_id)
        if order_id not in expected_order_ids:
            continue

        statuses[order_id].append(update.status)
        if isinstance(update, OrderFailed):
            raise AssertionError(f"order {order_id} failed: {update.code}")
        if isinstance(update, FoodReady):
            received[order_id] = (update, message)
        if received.keys() == expected_order_ids:
            return received, statuses

    raise AssertionError("MQTT message stream ended before all FOOD_READY events arrived")


async def wait_for_one_food(
    client: aiomqtt.Client,
    order_id: str,
) -> tuple[FoodReady, list[str]]:
    statuses: list[str] = []

    async for message in client.messages:
        if str(message.topic) != ORDER_STATUS_CHANGED_TOPIC:
            continue
        update = decode_order_status_changed(message.payload)
        if str(update.order_id) != order_id:
            continue

        statuses.append(update.status)
        if isinstance(update, OrderFailed):
            raise AssertionError(f"order {order_id} failed: {update.code}")
        if isinstance(update, FoodReady):
            return update, statuses

    raise AssertionError(f"MQTT message stream ended before order {order_id} was ready")


async def wait_for_retained_snapshot(
    client: aiomqtt.Client,
    table_id: int,
) -> tuple[TableSnapshot, aiomqtt.Message]:
    expected_topic = table_snapshot_topic(table_id)
    async for message in client.messages:
        if str(message.topic) == expected_topic:
            return decode_table_snapshot(message.payload), message

    raise AssertionError(f"MQTT message stream ended before table {table_id} snapshot arrived")


async def wait_for_pressure_cycle(
    client: aiomqtt.Client,
) -> tuple[KitchenPressureSnapshot, KitchenPressureSnapshot]:
    peak: KitchenPressureSnapshot | None = None

    async for message in client.messages:
        if str(message.topic) != KITCHEN_PRESSURE_TOPIC:
            continue
        pressure = decode_kitchen_pressure(message.payload)
        busy_workers = sum(
            worker.status == "processing" for worker in pressure.workers
        )
        if busy_workers == len(pressure.workers) and pressure.queued_orders > 0:
            peak = pressure
        if peak is not None and busy_workers == 0 and pressure.queued_orders == 0:
            return peak, pressure

    raise AssertionError("MQTT message stream ended before pressure returned to idle")


async def wait_for_full_pressure(
    client: aiomqtt.Client,
) -> KitchenPressureSnapshot:
    async for message in client.messages:
        if str(message.topic) != KITCHEN_PRESSURE_TOPIC:
            continue
        pressure = decode_kitchen_pressure(message.payload)
        if pressure.queued_orders == pressure.queue_capacity and all(
            worker.status == "processing" for worker in pressure.workers
        ):
            return pressure

    raise AssertionError("MQTT message stream ended before the queue reached capacity")


async def test_concurrent_orders_round_trip_over_websockets() -> None:
    expected = {
        str(uuid4()): ExpectedFood(table_id=1, food_name="Noodles"),
        str(uuid4()): ExpectedFood(table_id=2, food_name="Pizza"),
        str(uuid4()): ExpectedFood(table_id=3, food_name="Soup"),
        str(uuid4()): ExpectedFood(table_id=4, food_name="Tacos"),
    }

    async with asyncio.timeout(15):
        async with connected_client() as client:
            for order_id, expected_food in expected.items():
                order = OrderRequested.model_validate_json(
                    order_payload(
                        order_id=order_id,
                        table_id=expected_food.table_id,
                        food_name=expected_food.food_name,
                    )
                )
                await publish_payload(client, order.model_dump_json().encode())

            received, statuses = await wait_for_food(client, set(expected))

    assert received.keys() == expected.keys()
    for order_id, expected_food in expected.items():
        food, message = received[order_id]
        assert food.table_id == expected_food.table_id
        assert food.food_name == expected_food.food_name
        assert food.ready_at.tzinfo is not None
        assert message.qos == MQTT_QOS
        assert message.retain is False
        assert statuses[order_id] == ["queued", "processing", "food_ready"]


async def test_new_client_recovers_food_completed_while_ordering_client_was_closed() -> None:
    order_id = str(uuid4())
    table_id = 4

    async with asyncio.timeout(15):
        async with connected_client() as completion_observer:
            async with connected_client() as ordering_client:
                await publish_payload(
                    ordering_client,
                    order_payload(
                        order_id=order_id,
                        table_id=table_id,
                        food_name="Offline recovery soup",
                    ),
                )

            food, statuses = await wait_for_one_food(completion_observer, order_id)

        async with snapshot_client(table_id) as new_client:
            snapshot, message = await wait_for_retained_snapshot(new_client, table_id)

    recovered = next(
        update for update in snapshot.orders if str(update.order_id) == order_id
    )
    assert statuses == ["queued", "processing", "food_ready"]
    assert food.food_name == "Offline recovery soup"
    assert isinstance(recovered, FoodReady)
    assert recovered.ready_at == food.ready_at
    assert message.qos == MQTT_QOS
    assert message.retain is True


async def test_pressure_snapshot_exposes_bounded_queue_and_worker_pool() -> None:
    orders = [
        order_payload(
            order_id=str(uuid4()),
            table_id=(index % 4) + 1,
            food_name=f"Pressure order {index:02d}",
        )
        for index in range(20)
    ]

    async with asyncio.timeout(20):
        async with pressure_client() as monitor:
            async with connected_client(max_outgoing_calls=32) as producer:
                await asyncio.gather(
                    *(publish_payload(producer, payload) for payload in orders)
                )
                peak, idle = await wait_for_pressure_cycle(monitor)

    assert peak.queue_capacity == 256
    assert peak.queued_orders <= peak.queue_capacity
    assert len(peak.workers) == 8
    assert all(worker.status == "processing" for worker in peak.workers)
    assert len({worker.worker_id for worker in peak.workers}) == 8
    assert idle.revision > peak.revision
    assert idle.queued_orders == 0
    assert all(worker.status == "idle" for worker in idle.workers)


async def test_malformed_and_invalid_orders_are_rejected_without_poisoning_flow() -> None:
    invalid_ids = [str(uuid4()) for _ in range(14)]
    malformed_payloads = [
        b"",
        b"not-json",
        b"\xff",
        b"null",
        b"[]",
        b"{}",
        order_payload(order_id="not-a-uuid"),
        order_payload(order_id=invalid_ids[0], schema_version=2),
        order_payload(order_id=invalid_ids[1], schema_version="1"),
        order_payload(order_id=invalid_ids[2], table_id=0),
        order_payload(order_id=invalid_ids[3], table_id=5),
        order_payload(order_id=invalid_ids[4], table_id="2"),
        order_payload(order_id=invalid_ids[5], table_id=True),
        order_payload(order_id=invalid_ids[6], table_id=2.0),
        order_payload(order_id=invalid_ids[7], food_name=""),
        order_payload(order_id=invalid_ids[8], food_name="   "),
        order_payload(order_id=invalid_ids[9], food_name=" leading"),
        order_payload(order_id=invalid_ids[10], food_name="trailing "),
        order_payload(order_id=invalid_ids[11], food_name="x" * 101),
        order_payload(order_id=invalid_ids[12], unexpected=True),
        json.dumps(
            {
                "schemaVersion": 1,
                "orderId": invalid_ids[13],
                "tableId": 1,
            }
        ).encode(),
    ]
    sentinel_id = str(uuid4())

    async with asyncio.timeout(15):
        async with connected_client(max_outgoing_calls=32) as client:
            await asyncio.gather(
                *(publish_payload(client, payload) for payload in malformed_payloads)
            )
            await publish_payload(
                client,
                order_payload(
                    order_id=sentinel_id,
                    table_id=4,
                    food_name="Sentinel soup",
                ),
            )

            invalid_updates = []
            sentinel_statuses = []
            async for message in client.messages:
                if str(message.topic) != ORDER_STATUS_CHANGED_TOPIC:
                    continue
                update = decode_order_status_changed(message.payload)
                update_order_id = str(update.order_id)
                if update_order_id in invalid_ids:
                    invalid_updates.append(update)
                if update_order_id != sentinel_id:
                    continue
                sentinel_statuses.append(update.status)
                if isinstance(update, FoodReady):
                    break

    assert invalid_updates == []
    assert sentinel_statuses == ["queued", "processing", "food_ready"]


async def test_duplicate_order_is_processed_once_then_republished_from_cache() -> None:
    order_id = str(uuid4())
    payload = order_payload(order_id=order_id, table_id=2, food_name="Duplicate pizza")

    async with asyncio.timeout(20):
        async with connected_client(max_outgoing_calls=32) as client:
            await asyncio.gather(*(publish_payload(client, payload) for _ in range(20)))
            first_food, first_statuses = await wait_for_one_food(client, order_id)

            await publish_payload(client, payload)
            republished_food, republished_statuses = await wait_for_one_food(client, order_id)

    assert first_statuses == ["queued", "processing", "food_ready"]
    assert republished_statuses == ["food_ready"]
    assert republished_food.ready_at == first_food.ready_at
    assert republished_food.occurred_at == first_food.occurred_at


async def test_conflicting_payload_never_mutates_the_original_order() -> None:
    order_id = str(uuid4())
    original = order_payload(order_id=order_id, table_id=1, food_name="Original soup")
    conflicting = order_payload(order_id=order_id, table_id=4, food_name="Conflicting tacos")
    sentinel_id = str(uuid4())

    async with asyncio.timeout(25):
        async with connected_client() as client:
            await publish_payload(client, original)
            await publish_payload(client, conflicting)
            food, statuses = await wait_for_one_food(client, order_id)

            await publish_payload(client, conflicting)
            await publish_payload(
                client,
                order_payload(
                    order_id=sentinel_id,
                    table_id=3,
                    food_name="Conflict sentinel",
                ),
            )

            unexpected_original_updates = []
            sentinel_statuses = []
            async for message in client.messages:
                if str(message.topic) != ORDER_STATUS_CHANGED_TOPIC:
                    continue
                update = decode_order_status_changed(message.payload)
                update_order_id = str(update.order_id)
                if update_order_id == order_id:
                    unexpected_original_updates.append(update)
                if update_order_id != sentinel_id:
                    continue
                sentinel_statuses.append(update.status)
                if isinstance(update, FoodReady):
                    break

    assert food.table_id == 1
    assert food.food_name == "Original soup"
    assert statuses == ["queued", "processing", "food_ready"]
    assert unexpected_original_updates == []
    assert sentinel_statuses == ["queued", "processing", "food_ready"]


@pytest.mark.load
@LOAD_TEST
async def test_hundred_order_burst_reaches_unique_terminal_states() -> None:
    expected = {
        str(uuid4()): ExpectedFood(
            table_id=(index % 4) + 1,
            food_name=f"Load order {index:03d}",
        )
        for index in range(100)
    }

    async with asyncio.timeout(90):
        async with connected_client(max_outgoing_calls=128) as client:
            await asyncio.gather(
                *(
                    publish_payload(
                        client,
                        order_payload(
                            order_id=order_id,
                            table_id=food.table_id,
                            food_name=food.food_name,
                        ),
                    )
                    for order_id, food in expected.items()
                )
            )
            received, statuses = await wait_for_food(client, set(expected))

    assert received.keys() == expected.keys()
    assert all(
        statuses[order_id] == ["queued", "processing", "food_ready"] for order_id in expected
    )
    assert {
        order_id
        for order_id, (food, _message) in received.items()
        if food.table_id == expected[order_id].table_id
        and food.food_name == expected[order_id].food_name
    } == set(expected)


@pytest.mark.load
@LOAD_TEST
async def test_saturated_burst_reports_explicit_admission_failures() -> None:
    worker_count = 8
    queue_capacity = 256
    rejected_count = 16
    order_ids = [str(uuid4()) for _ in range(worker_count + queue_capacity + rejected_count)]

    async with asyncio.timeout(30):
        async with pressure_client() as monitor:
            full_pressure_task = asyncio.create_task(wait_for_full_pressure(monitor))
            try:
                async with connected_client(max_outgoing_calls=320) as client:
                    await asyncio.gather(
                        *(
                            publish_payload(
                                client,
                                order_payload(
                                    order_id=order_id,
                                    table_id=(index % 4) + 1,
                                    food_name=f"Saturation order {index:03d}",
                                ),
                            )
                            for index, order_id in enumerate(order_ids)
                        )
                    )

                    admissions: dict[str, str] = {}
                    failures: dict[str, OrderFailed] = {}
                    async for message in client.messages:
                        if str(message.topic) != ORDER_STATUS_CHANGED_TOPIC:
                            continue
                        update = decode_order_status_changed(message.payload)
                        update_order_id = str(update.order_id)
                        if update_order_id not in order_ids or update_order_id in admissions:
                            continue
                        if update.status == "queued":
                            admissions[update_order_id] = update.status
                        elif isinstance(update, OrderFailed):
                            admissions[update_order_id] = update.status
                            failures[update_order_id] = update
                        if len(admissions) == len(order_ids):
                            break
                full_pressure = await full_pressure_task
            finally:
                full_pressure_task.cancel()
                await asyncio.gather(full_pressure_task, return_exceptions=True)

    assert Counter(admissions.values()) == {
        "queued": worker_count + queue_capacity,
        "failed": rejected_count,
    }
    assert len(failures) == rejected_count
    assert all(
        failure.code == "service_overloaded" and failure.retryable for failure in failures.values()
    )
    assert full_pressure.queued_orders == queue_capacity
    assert len(full_pressure.workers) == worker_count
