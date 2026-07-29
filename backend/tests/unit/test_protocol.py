import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import FoodReady, OrderFailed, TableSnapshot
from app.protocol import (
    decode_order_requested,
    decode_order_status_changed,
    decode_table_snapshot,
    encode_order_status_changed,
    encode_table_snapshot,
    table_snapshot_topic,
)


def test_decode_order_requested_validates_json_bytes() -> None:
    order_id = uuid4()

    order = decode_order_requested(
        json.dumps(
            {
                "schemaVersion": 1,
                "orderId": str(order_id),
                "tableId": 3,
                "foodName": "Noodles",
            }
        ).encode()
    )

    assert order.order_id == order_id
    assert order.table_id == 3
    assert order.food_name == "Noodles"


@pytest.mark.parametrize("payload", [b"", b"not-json", b"{}", b'{"tableId": 2}'])
def test_decode_order_requested_rejects_malformed_payload(payload: bytes) -> None:
    with pytest.raises(ValidationError):
        decode_order_requested(payload)


def test_encode_food_ready_status_uses_the_wire_aliases() -> None:
    order_id = uuid4()
    food = FoodReady(
        schemaVersion=1,
        orderId=order_id,
        tableId=1,
        foodName="Tacos",
        status="food_ready",
        occurredAt=datetime(2026, 7, 28, 20, 15, 31, tzinfo=UTC),
        readyAt=datetime(2026, 7, 28, 20, 15, 31, tzinfo=UTC),
    )

    payload = json.loads(encode_order_status_changed(food))

    assert payload == {
        "schemaVersion": 1,
        "orderId": str(order_id),
        "tableId": 1,
        "foodName": "Tacos",
        "status": "food_ready",
        "occurredAt": "2026-07-28T20:15:31Z",
        "readyAt": "2026-07-28T20:15:31Z",
    }


def test_decode_failed_status_selects_the_discriminated_variant() -> None:
    order_id = uuid4()

    update = decode_order_status_changed(
        json.dumps(
            {
                "schemaVersion": 1,
                "orderId": str(order_id),
                "tableId": 2,
                "foodName": "Soup",
                "status": "failed",
                "occurredAt": "2026-07-28T20:15:31Z",
                "code": "service_overloaded",
                "message": "The order service is at capacity. Please retry.",
                "retryable": True,
            }
        ).encode()
    )

    assert isinstance(update, OrderFailed)
    assert update.order_id == order_id
    assert update.code == "service_overloaded"
    assert update.retryable is True


def test_table_snapshot_round_trips_and_uses_a_table_scoped_topic() -> None:
    service_instance_id = uuid4()
    snapshot = TableSnapshot(
        schemaVersion=1,
        serviceInstanceId=service_instance_id,
        tableId=2,
        revision=3,
        generatedAt=datetime(2026, 7, 28, 20, 15, 31, tzinfo=UTC),
        orders=(),
    )

    decoded = decode_table_snapshot(encode_table_snapshot(snapshot))

    assert decoded == snapshot
    assert table_snapshot_topic(decoded.table_id) == "restaurant/v1/table/2/snapshot"


@pytest.mark.parametrize("table_id", [0, 5])
def test_table_snapshot_topic_rejects_an_unknown_table(table_id: int) -> None:
    with pytest.raises(ValueError):
        table_snapshot_topic(table_id)
