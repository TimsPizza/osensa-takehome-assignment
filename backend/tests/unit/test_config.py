import pytest

from app.config import Settings


def test_capacity_defaults_match_the_documented_worker_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORDER_WORKER_COUNT", raising=False)
    monkeypatch.delenv("ORDER_QUEUE_CAPACITY", raising=False)

    settings = Settings.from_env()

    assert settings.order_worker_count == 8
    assert settings.order_queue_capacity == 256
    assert settings.order_registry_capacity == 4096
    assert settings.mqtt_incoming_queue_capacity == 1024


def test_capacity_can_be_configured_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORDER_WORKER_COUNT", "4")
    monkeypatch.setenv("ORDER_QUEUE_CAPACITY", "32")

    settings = Settings.from_env()

    assert settings.order_worker_count == 4
    assert settings.order_queue_capacity == 32


def test_mqtt_password_can_be_read_from_a_secret_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    password_file = tmp_path / "mqtt-password"
    password_file.write_text("secret-from-file\n", encoding="utf-8")
    monkeypatch.setenv("MQTT_USERNAME", "restaurant-backend")
    monkeypatch.setenv("MQTT_PASSWORD_FILE", str(password_file))

    settings = Settings.from_env()

    assert settings.mqtt_username == "restaurant-backend"
    assert settings.mqtt_password == "secret-from-file"


def test_mqtt_password_rejects_ambiguous_secret_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    password_file = tmp_path / "mqtt-password"
    password_file.write_text("secret-from-file", encoding="utf-8")
    monkeypatch.setenv("MQTT_PASSWORD", "secret-from-env")
    monkeypatch.setenv("MQTT_PASSWORD_FILE", str(password_file))

    with pytest.raises(ValueError, match="cannot both be set"):
        Settings.from_env()


def test_registry_capacity_cannot_be_smaller_than_active_order_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORDER_WORKER_COUNT", "8")
    monkeypatch.setenv("ORDER_QUEUE_CAPACITY", "256")
    monkeypatch.setenv("ORDER_REGISTRY_CAPACITY", "263")

    with pytest.raises(ValueError, match="must be at least"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ORDER_WORKER_COUNT", "0", "must be between 1 and 64"),
        ("ORDER_WORKER_COUNT", "65", "must be between 1 and 64"),
        ("ORDER_WORKER_COUNT", "many", "must be an integer"),
        ("ORDER_QUEUE_CAPACITY", "0", "must be between 1 and 10000"),
        ("ORDER_QUEUE_CAPACITY", "10001", "must be between 1 and 10000"),
        ("ORDER_QUEUE_CAPACITY", "large", "must be an integer"),
        ("ORDER_REGISTRY_CAPACITY", "0", "must be between 1 and 100000"),
        ("MQTT_INCOMING_QUEUE_CAPACITY", "0", "must be between 1 and 100000"),
    ],
)
def test_invalid_capacity_configuration_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        Settings.from_env()
