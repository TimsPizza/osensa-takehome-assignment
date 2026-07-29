from app.models import FoodReady, OrderRequested

ORDER_REQUESTED_TOPIC = "restaurant/v1/order/requested"
FOOD_READY_TOPIC = "restaurant/v1/food/ready"
MQTT_QOS = 1


def decode_order_requested(payload: bytes) -> OrderRequested:
    """Validate an untrusted MQTT payload against the wire contract."""
    return OrderRequested.model_validate_json(payload)


def encode_food_ready(food: FoodReady) -> bytes:
    """Serialize a validated DTO using its public camelCase aliases."""
    return food.model_dump_json().encode()
