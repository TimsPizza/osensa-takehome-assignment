import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models import FoodReady, OrderRequested

type DelaySampler = Callable[[float, float], float]
type Sleeper = Callable[[float], Awaitable[None]]
type Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class OrderProcessor:
    """Turn one validated order into food after a non-blocking delay."""

    min_delay_seconds: float = 1.0
    max_delay_seconds: float = 5.0
    delay_sampler: DelaySampler = random.uniform
    sleeper: Sleeper = asyncio.sleep
    clock: Clock = utc_now

    def __post_init__(self) -> None:
        if self.min_delay_seconds < 0:
            raise ValueError("min_delay_seconds must be greater than or equal to zero")
        if self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError("max_delay_seconds must be greater than or equal to min_delay_seconds")

    async def process(self, order: OrderRequested) -> FoodReady:
        delay_seconds = self.delay_sampler(
            self.min_delay_seconds,
            self.max_delay_seconds,
        )
        await self.sleeper(delay_seconds)
        ready_at = self.clock()

        return FoodReady(
            schemaVersion=1,
            orderId=order.order_id,
            tableId=order.table_id,
            foodName=order.food_name,
            status="food_ready",
            occurredAt=ready_at,
            readyAt=ready_at,
        )
