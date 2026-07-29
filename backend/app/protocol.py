from app.models import OrderRequested, OrderStatusChanged, OrderStatusUpdate

ORDER_REQUESTED_TOPIC = "restaurant/v1/order/requested"
ORDER_STATUS_CHANGED_TOPIC = "restaurant/v1/order/status-changed"
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
