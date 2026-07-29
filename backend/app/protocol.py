from app.models import (
    KitchenPressureSnapshot,
    OrderRequested,
    OrderStatusChanged,
    OrderStatusUpdate,
    TableSnapshot,
)

TABLE_IDS = (1, 2, 3, 4)
ORDER_REQUESTED_TOPIC_FILTER = "restaurant/v1/table/+/order/requested"
ORDER_STATUS_CHANGED_TOPIC_FILTER = "restaurant/v1/table/+/order/status-changed"
TABLE_SNAPSHOT_TOPIC_FILTER = "restaurant/v1/table/+/snapshot"
KITCHEN_PRESSURE_TOPIC = "restaurant/v1/kitchen/pressure"
MQTT_QOS = 1


def decode_order_requested(payload: bytes) -> OrderRequested:
    """Validate an untrusted MQTT payload against the wire contract."""
    return OrderRequested.model_validate_json(payload)


def decode_order_status_changed(payload: bytes) -> OrderStatusUpdate:
    """Validate a public order status event from its discriminated wire union."""
    return OrderStatusChanged.model_validate_json(payload).root


def encode_order_status_changed(update: OrderStatusUpdate) -> bytes:
    """Serialize one public order status variant with its wire aliases."""
    return OrderStatusChanged(root=update).model_dump_json().encode()


def order_requested_topic(table_id: int) -> str:
    _validate_table_id(table_id)
    return f"restaurant/v1/table/{table_id}/order/requested"


def order_status_changed_topic(table_id: int) -> str:
    _validate_table_id(table_id)
    return f"restaurant/v1/table/{table_id}/order/status-changed"


def table_snapshot_topic(table_id: int) -> str:
    _validate_table_id(table_id)
    return f"restaurant/v1/table/{table_id}/snapshot"


def table_id_from_order_requested_topic(topic: str) -> int | None:
    return _table_id_from_topic(topic, suffix=("order", "requested"))


def table_id_from_order_status_changed_topic(topic: str) -> int | None:
    return _table_id_from_topic(topic, suffix=("order", "status-changed"))


def _table_id_from_topic(topic: str, *, suffix: tuple[str, ...]) -> int | None:
    segments = topic.split("/")
    expected_length = 4 + len(suffix)
    if (
        len(segments) != expected_length
        or segments[:3] != ["restaurant", "v1", "table"]
        or tuple(segments[4:]) != suffix
    ):
        return None

    try:
        table_id = int(segments[3])
    except ValueError:
        return None
    return table_id if table_id in TABLE_IDS else None


def _validate_table_id(table_id: int) -> None:
    if table_id not in TABLE_IDS:
        raise ValueError("table_id must be between 1 and 4")


def decode_table_snapshot(payload: bytes) -> TableSnapshot:
    """Validate a retained table snapshot from the public MQTT boundary."""
    return TableSnapshot.model_validate_json(payload)


def encode_table_snapshot(snapshot: TableSnapshot) -> bytes:
    """Serialize an authoritative table snapshot with its wire aliases."""
    return snapshot.model_dump_json().encode()


def decode_kitchen_pressure(payload: bytes) -> KitchenPressureSnapshot:
    """Validate the retained kitchen pressure snapshot."""
    return KitchenPressureSnapshot.model_validate_json(payload)


def encode_kitchen_pressure(snapshot: KitchenPressureSnapshot) -> bytes:
    """Serialize queue and worker-pool pressure for public monitoring."""
    return snapshot.model_dump_json().encode()
