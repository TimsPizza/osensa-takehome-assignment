import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.models import FoodReady, OrderRequested


def order_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "orderId": str(uuid4()),
        "tableId": 2,
        "foodName": "Chicken sandwich",
    }
    payload.update(overrides)
    return payload


def validate_order(payload: dict[str, object]) -> OrderRequested:
    return OrderRequested.model_validate_json(json.dumps(payload))


def test_order_requested_accepts_the_wire_shape() -> None:
    payload = order_payload()

    order = validate_order(payload)

    assert order.schema_version == 1
    assert order.order_id == UUID(str(payload["orderId"]))
    assert order.table_id == 2
    assert order.food_name == "Chicken sandwich"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tableId", 0),
        ("tableId", 5),
        ("tableId", "2"),
        ("tableId", True),
        ("foodName", ""),
        ("foodName", "   "),
        ("foodName", " leading"),
        ("foodName", "trailing "),
        ("foodName", "x" * 101),
        ("orderId", "not-a-uuid"),
        ("schemaVersion", 2),
    ],
)
def test_order_requested_rejects_invalid_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        validate_order(order_payload(**{field: value}))


def test_order_requested_rejects_unknown_and_python_field_names() -> None:
    with pytest.raises(ValidationError):
        validate_order(order_payload(unexpected="value"))

    payload = order_payload()
    payload["order_id"] = payload.pop("orderId")
    with pytest.raises(ValidationError):
        validate_order(payload)


def test_food_ready_serializes_the_frontend_wire_shape() -> None:
    order_id = uuid4()
    food = FoodReady(
        schemaVersion=1,
        orderId=order_id,
        tableId=4,
        foodName="Soup",
        readyAt=datetime(2026, 7, 28, 20, 15, 31, tzinfo=UTC),
    )

    payload = json.loads(food.model_dump_json())

    assert payload == {
        "schemaVersion": 1,
        "orderId": str(order_id),
        "tableId": 4,
        "foodName": "Soup",
        "readyAt": "2026-07-28T20:15:31Z",
    }


def test_food_ready_requires_a_timezone() -> None:
    with pytest.raises(ValidationError):
        FoodReady(
            schemaVersion=1,
            orderId=uuid4(),
            tableId=1,
            foodName="Soup",
            readyAt=datetime(2026, 7, 28, 20, 15, 31),
        )


def test_json_schema_uses_aliases_and_forbids_extra_fields() -> None:
    schema = OrderRequested.model_json_schema(by_alias=True, mode="validation")

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"schemaVersion", "orderId", "tableId", "foodName"}
    assert "order_id" not in schema["properties"]
    assert schema["properties"]["tableId"]["minimum"] == 1
    assert schema["properties"]["tableId"]["maximum"] == 4
