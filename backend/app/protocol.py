from app.models import (
    OrderRequested,
    OrderStatusChanged,
    OrderStatusUpdate,
    TableSnapshot,
)

ORDER_REQUESTED_TOPIC = "restaurant/v1/order/requested"
ORDER_STATUS_CHANGED_TOPIC = "restaurant/v1/order/status-changed"
TABLE_SNAPSHOT_TOPIC_FILTER = "restaurant/v1/table/+/snapshot"
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


def table_snapshot_topic(table_id: int) -> str:
    if table_id not in (1, 2, 3, 4):
        raise ValueError("table_id must be between 1 and 4")
    return f"restaurant/v1/table/{table_id}/snapshot"


def decode_table_snapshot(payload: bytes) -> TableSnapshot:
    """Validate a retained table snapshot from the public MQTT boundary."""
    return TableSnapshot.model_validate_json(payload)


def encode_table_snapshot(snapshot: TableSnapshot) -> bytes:
    """Serialize an authoritative table snapshot with its wire aliases."""
    return snapshot.model_dump_json().encode()
