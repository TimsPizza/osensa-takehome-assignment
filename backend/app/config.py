import os
from dataclasses import dataclass


def _required_port(name: str, default: int) -> int:
    return _bounded_int(name, default, minimum=1, maximum=65535)


def _bounded_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    mqtt_host: str
    mqtt_port: int
    mqtt_websocket_path: str
    mqtt_client_id: str
    mqtt_username: str | None
    mqtt_password: str | None
    reconnect_delay_seconds: float
    reconnect_max_delay_seconds: float
    log_level: str
    order_worker_count: int = 8
    order_queue_capacity: int = 256

    @classmethod
    def from_env(cls) -> "Settings":
        host = os.getenv("MQTT_HOST", "localhost").strip()
        websocket_path = os.getenv("MQTT_WEBSOCKET_PATH", "/mqtt").strip()
        client_id = os.getenv("MQTT_CLIENT_ID", "osensa-order-service").strip()
        username = os.getenv("MQTT_USERNAME") or None
        password = os.getenv("MQTT_PASSWORD") or None
        reconnect_delay = _positive_float("MQTT_RECONNECT_DELAY_SECONDS", 1.0)
        reconnect_max_delay = _positive_float("MQTT_RECONNECT_MAX_DELAY_SECONDS", 30.0)

        if not host:
            raise ValueError("MQTT_HOST must not be empty")
        if not websocket_path.startswith("/"):
            raise ValueError("MQTT_WEBSOCKET_PATH must start with '/'")
        if not client_id:
            raise ValueError("MQTT_CLIENT_ID must not be empty")
        if (username is None) != (password is None):
            raise ValueError("MQTT_USERNAME and MQTT_PASSWORD must be provided together")
        if reconnect_delay > reconnect_max_delay:
            raise ValueError(
                "MQTT_RECONNECT_DELAY_SECONDS must not exceed MQTT_RECONNECT_MAX_DELAY_SECONDS"
            )

        return cls(
            mqtt_host=host,
            mqtt_port=_required_port("MQTT_PORT", 9001),
            mqtt_websocket_path=websocket_path,
            mqtt_client_id=client_id,
            mqtt_username=username,
            mqtt_password=password,
            reconnect_delay_seconds=reconnect_delay,
            reconnect_max_delay_seconds=reconnect_max_delay,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            order_worker_count=_bounded_int(
                "ORDER_WORKER_COUNT",
                8,
                minimum=1,
                maximum=64,
            ),
            order_queue_capacity=_bounded_int(
                "ORDER_QUEUE_CAPACITY",
                256,
                minimum=1,
                maximum=10_000,
            ),
        )
