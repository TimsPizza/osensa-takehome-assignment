import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import aiomqtt
import pytest

from app.protocol import MQTT_QOS, order_requested_topic, order_status_changed_topic

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MQTT_SECURITY") != "1",
        reason="set RUN_MQTT_SECURITY=1 with the production Mosquitto listener running",
    ),
]

REPOSITORY_ROOT = Path(__file__).parents[3]
SECRETS_DIRECTORY = REPOSITORY_ROOT / "deploy" / "secrets"


def password_for(username: str) -> str:
    env_name = f"MQTT_TEST_{username.upper().replace('-', '_')}_PASSWORD"
    value = os.getenv(env_name)
    if value:
        return value
    return (SECRETS_DIRECTORY / f"mqtt-{username}-password").read_text(encoding="utf-8")


@asynccontextmanager
async def authenticated_client(username: str) -> AsyncIterator[aiomqtt.Client]:
    async with aiomqtt.Client(
        hostname=os.getenv("MQTT_TEST_HOST", "localhost"),
        port=int(os.getenv("MQTT_TEST_PORT", "19001")),
        username=username,
        password=password_for(username),
        identifier=f"acl-test-{username}-{uuid4()}",
        clean_session=True,
        transport="websockets",
        websocket_path=os.getenv("MQTT_TEST_WEBSOCKET_PATH", "/mqtt"),
    ) as client:
        yield client


def subscription_was_denied(reason_codes: tuple[int, ...] | list[object]) -> bool:
    for reason_code in reason_codes:
        if hasattr(reason_code, "is_failure"):
            if reason_code.is_failure:  # type: ignore[union-attr]
                return True
        elif int(reason_code) >= 128:
            return True
    return False


async def expect_no_message(client: aiomqtt.Client) -> None:
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.4):
            await anext(client.messages)


async def test_anonymous_and_invalid_credentials_are_rejected() -> None:
    common = {
        "hostname": os.getenv("MQTT_TEST_HOST", "localhost"),
        "port": int(os.getenv("MQTT_TEST_PORT", "19001")),
        "transport": "websockets",
        "websocket_path": os.getenv("MQTT_TEST_WEBSOCKET_PATH", "/mqtt"),
    }

    with pytest.raises(aiomqtt.MqttError):
        async with aiomqtt.Client(identifier=f"anonymous-{uuid4()}", **common):
            pass

    with pytest.raises(aiomqtt.MqttError):
        async with aiomqtt.Client(
            identifier=f"invalid-password-{uuid4()}",
            username="table-1",
            password="not-the-password",
            **common,
        ):
            pass


async def test_table_identity_cannot_cross_table_or_forge_backend_events() -> None:
    table_one_request = order_requested_topic(1)
    table_four_request = order_requested_topic(4)
    table_one_status = order_status_changed_topic(1)

    async with authenticated_client("restaurant-backend") as backend:
        await backend.subscribe(
            [
                (table_one_request, MQTT_QOS),
                (table_four_request, MQTT_QOS),
            ],
        )

        async with authenticated_client("table-1") as table_one:
            own_status_ack = await table_one.subscribe(table_one_status, qos=MQTT_QOS)
            other_table_ack = await table_one.subscribe(
                order_status_changed_topic(4),
                qos=MQTT_QOS,
            )

            assert not subscription_was_denied(own_status_ack)
            # Mosquitto accepts the filter but applies `read` ACLs when routing
            # each publication, so authorization is proven by non-delivery.
            assert not subscription_was_denied(other_table_ack)

            await backend.publish(
                order_status_changed_topic(4),
                payload=b"other-table-status",
                qos=MQTT_QOS,
            )
            await expect_no_message(table_one)

            await table_one.publish(
                table_four_request,
                payload=b"forbidden-cross-table-request",
                qos=MQTT_QOS,
            )
            await expect_no_message(backend)

            await table_one.publish(
                table_one_request,
                payload=b"allowed-own-table-request",
                qos=MQTT_QOS,
            )
            request = await asyncio.wait_for(anext(backend.messages), timeout=1)
            assert str(request.topic) == table_one_request
            assert request.payload == b"allowed-own-table-request"

            await backend.publish(
                table_one_status,
                payload=b"allowed-backend-status",
                qos=MQTT_QOS,
            )
            status = await asyncio.wait_for(anext(table_one.messages), timeout=1)
            assert str(status.topic) == table_one_status
            assert status.payload == b"allowed-backend-status"

            await table_one.publish(
                table_one_status,
                payload=b"forbidden-forged-status",
                qos=MQTT_QOS,
            )
            await expect_no_message(table_one)


async def test_console_role_can_operate_all_tables_without_backend_write_access() -> None:
    table_four_request = order_requested_topic(4)
    table_four_status = order_status_changed_topic(4)

    async with authenticated_client("restaurant-backend") as backend:
        await backend.subscribe(table_four_request, qos=MQTT_QOS)

        async with authenticated_client("restaurant-console") as console:
            status_ack = await console.subscribe(table_four_status, qos=MQTT_QOS)
            assert not subscription_was_denied(status_ack)

            await console.publish(
                table_four_request,
                payload=b"allowed-console-request",
                qos=MQTT_QOS,
            )
            request = await asyncio.wait_for(anext(backend.messages), timeout=1)
            assert str(request.topic) == table_four_request

            await console.publish(
                table_four_status,
                payload=b"forbidden-console-status",
                qos=MQTT_QOS,
            )
            await expect_no_message(console)
