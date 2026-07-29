import asyncio
import logging

from app.config import Settings
from app.logging_config import configure_logging
from app.mqtt_service import MqttOrderService

LOGGER = logging.getLogger(__name__)


async def async_main(settings: Settings) -> None:
    await MqttOrderService(settings).run()


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    LOGGER.info(
        "service_starting broker=%s:%d websocket_path=%s workers=%d queue_capacity=%d",
        settings.mqtt_host,
        settings.mqtt_port,
        settings.mqtt_websocket_path,
        settings.order_worker_count,
        settings.order_queue_capacity,
    )
    asyncio.run(async_main(settings))


if __name__ == "__main__":
    main()
