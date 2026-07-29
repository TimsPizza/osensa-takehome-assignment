import os
from dataclasses import dataclass
from pathlib import Path


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


def _optional_secret(name: str) -> str | None:
    value = os.getenv(name)
    file_path = os.getenv(f"{name}_FILE")
    if value is not None and file_path is not None:
        raise ValueError(f"{name} and {name}_FILE cannot both be set")
    if file_path is None:
        return value or None

    try:
        secret = Path(file_path).read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ValueError(f"{name}_FILE could not be read") from error
    if not secret:
        raise ValueError(f"{name}_FILE must not be empty")
    return secret


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
    order_registry_capacity: int = 4096
    mqtt_incoming_queue_capacity: int = 1024

    @classmethod
    def from_env(cls) -> "Settings":
        host = os.getenv("MQTT_HOST", "localhost").strip()
        websocket_path = os.getenv("MQTT_WEBSOCKET_PATH", "/mqtt").strip()
        client_id = os.getenv("MQTT_CLIENT_ID", "osensa-order-service").strip()
        username = os.getenv("MQTT_USERNAME") or None
        password = _optional_secret("MQTT_PASSWORD")
        reconnect_delay = _positive_float("MQTT_RECONNECT_DELAY_SECONDS", 1.0)
        reconnect_max_delay = _positive_float("MQTT_RECONNECT_MAX_DELAY_SECONDS", 30.0)
        worker_count = _bounded_int(
            "ORDER_WORKER_COUNT",
            8,
            minimum=1,
            maximum=64,
        )
        queue_capacity = _bounded_int(
            "ORDER_QUEUE_CAPACITY",
            256,
            minimum=1,
            maximum=10_000,
        )
        registry_capacity = _bounded_int(
            "ORDER_REGISTRY_CAPACITY",
            4096,
            minimum=1,
            maximum=100_000,
        )
        incoming_queue_capacity = _bounded_int(
            "MQTT_INCOMING_QUEUE_CAPACITY",
            1024,
            minimum=1,
            maximum=100_000,
        )

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
        if registry_capacity < worker_count + queue_capacity:
            raise ValueError(
                "ORDER_REGISTRY_CAPACITY must be at least ORDER_WORKER_COUNT + ORDER_QUEUE_CAPACITY"
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
            order_worker_count=worker_count,
            order_queue_capacity=queue_capacity,
            order_registry_capacity=registry_capacity,
            mqtt_incoming_queue_capacity=incoming_queue_capacity,
        )
