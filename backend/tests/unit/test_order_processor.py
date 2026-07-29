import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.models import OrderRequested
from app.order_processor import OrderProcessor

ORDER_ID = UUID("3b11d31c-7d34-4dda-91e5-d64721a50463")
READY_AT = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)


def make_order() -> OrderRequested:
    return OrderRequested(
        schemaVersion=1,
        orderId=ORDER_ID,
        tableId=2,
        foodName="Chicken sandwich",
    )


async def test_process_waits_for_sampled_delay_and_preserves_order_fields() -> None:
    sampled_bounds: list[tuple[float, float]] = []
    slept_for: list[float] = []

    def sample_delay(lower: float, upper: float) -> float:
        sampled_bounds.append((lower, upper))
        return 2.75

    async def fake_sleep(delay: float) -> None:
        slept_for.append(delay)

    processor = OrderProcessor(
        min_delay_seconds=1.0,
        max_delay_seconds=5.0,
        delay_sampler=sample_delay,
        sleeper=fake_sleep,
        clock=lambda: READY_AT,
    )

    food = await processor.process(make_order())

    assert sampled_bounds == [(1.0, 5.0)]
    assert slept_for == [2.75]
    assert food.schema_version == 1
    assert food.order_id == ORDER_ID
    assert food.table_id == 2
    assert food.food_name == "Chicken sandwich"
    assert food.occurred_at == READY_AT
    assert food.ready_at == READY_AT


async def test_ready_timestamp_is_captured_after_processing_finishes() -> None:
    processing_finished = False

    async def fake_sleep(_: float) -> None:
        nonlocal processing_finished
        processing_finished = True

    def clock() -> datetime:
        assert processing_finished
        return READY_AT

    processor = OrderProcessor(
        delay_sampler=lambda _lower, _upper: 0,
        sleeper=fake_sleep,
        clock=clock,
    )

    food = await processor.process(make_order())

    assert food.occurred_at == READY_AT
    assert food.ready_at == READY_AT


@pytest.mark.parametrize(
    ("minimum", "maximum", "message"),
    [
        (-0.1, 1.0, "min_delay_seconds"),
        (2.0, 1.0, "max_delay_seconds"),
    ],
)
def test_invalid_delay_range_is_rejected(
    minimum: float,
    maximum: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        OrderProcessor(
            min_delay_seconds=minimum,
            max_delay_seconds=maximum,
        )


async def test_cancellation_is_not_swallowed() -> None:
    async def cancelled_sleep(_: float) -> None:
        raise asyncio.CancelledError

    processor = OrderProcessor(
        delay_sampler=lambda _lower, _upper: 1,
        sleeper=cancelled_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        await processor.process(make_order())
