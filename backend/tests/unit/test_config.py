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


def test_capacity_can_be_configured_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORDER_WORKER_COUNT", "4")
    monkeypatch.setenv("ORDER_QUEUE_CAPACITY", "32")

    settings = Settings.from_env()

    assert settings.order_worker_count == 4
    assert settings.order_queue_capacity == 32


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ORDER_WORKER_COUNT", "0", "must be between 1 and 64"),
        ("ORDER_WORKER_COUNT", "65", "must be between 1 and 64"),
        ("ORDER_WORKER_COUNT", "many", "must be an integer"),
        ("ORDER_QUEUE_CAPACITY", "0", "must be between 1 and 10000"),
        ("ORDER_QUEUE_CAPACITY", "10001", "must be between 1 and 10000"),
        ("ORDER_QUEUE_CAPACITY", "large", "must be an integer"),
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
