from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.models import FoodReady, OrderRequested
from app.order_registry import (
    OrderNotFoundError,
    OrderRegistry,
    RegistrationAction,
)
from app.order_state import (
    FoodPrepared,
    InvalidOrderTransitionError,
    OrderEvent,
    OrderStatus,
    ProcessingFailed,
    ProcessingStarted,
    PublishConfirmed,
)

ORDER_ID = UUID("3b11d31c-7d34-4dda-91e5-d64721a50463")
UNKNOWN_ORDER_ID = UUID("4a22d42d-8e45-4eeb-a2f6-e75832b61574")
READY_AT = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)


def make_order(
    *,
    table_id: int = 2,
    food_name: str = "Chicken sandwich",
) -> OrderRequested:
    return OrderRequested(
        schemaVersion=1,
        orderId=ORDER_ID,
        tableId=table_id,
        foodName=food_name,
    )


def make_food() -> FoodReady:
    return FoodReady(
        schemaVersion=1,
        orderId=ORDER_ID,
        tableId=2,
        foodName="Chicken sandwich",
        status="food_ready",
        occurredAt=READY_AT,
        readyAt=READY_AT,
    )


def apply_events(registry: OrderRegistry, events: tuple[OrderEvent, ...]) -> None:
    for event in events:
        registry.apply(ORDER_ID, event)


def test_new_order_is_registered_for_processing() -> None:
    registry = OrderRegistry()
    order = make_order()

    result = registry.register(order)

    assert result.action is RegistrationAction.PROCESS
    assert result.state.order is order
    assert result.state.status is OrderStatus.QUEUED
    assert registry.get(ORDER_ID) is result.state
    assert len(registry) == 1


@pytest.mark.parametrize(
    "events",
    [
        (),
        (ProcessingStarted(),),
        (ProcessingStarted(), FoodPrepared(make_food())),
    ],
)
def test_duplicate_active_order_is_ignored(
    events: tuple[OrderEvent, ...],
) -> None:
    registry = OrderRegistry()
    order = make_order()
    registry.register(order)
    apply_events(registry, events)
    current = registry.get(ORDER_ID)

    result = registry.register(order)

    assert result.action is RegistrationAction.IGNORE
    assert result.state is current
    assert registry.get(ORDER_ID) is current
    assert len(registry) == 1


def test_duplicate_published_order_schedules_cached_food_for_republish() -> None:
    registry = OrderRegistry()
    order = make_order()
    registry.register(order)
    apply_events(
        registry,
        (
            ProcessingStarted(),
            FoodPrepared(make_food()),
            PublishConfirmed(),
        ),
    )
    published = registry.get(ORDER_ID)

    result = registry.register(order)

    assert published is not None
    assert published.status is OrderStatus.PUBLISHED
    assert result.action is RegistrationAction.REPUBLISH
    assert result.state.status is OrderStatus.FOOD_READY
    assert result.state.food is published.food
    assert registry.get(ORDER_ID) is result.state


def test_duplicate_failed_order_is_requeued_for_processing() -> None:
    registry = OrderRegistry()
    order = make_order()
    registry.register(order)
    apply_events(
        registry,
        (
            ProcessingStarted(),
            ProcessingFailed("kitchen unavailable"),
        ),
    )

    result = registry.register(order)

    assert result.action is RegistrationAction.PROCESS
    assert result.state.status is OrderStatus.QUEUED
    assert result.state.failure_reason is None
    assert registry.get(ORDER_ID) is result.state


@pytest.mark.parametrize(
    "conflicting_order",
    [
        make_order(table_id=3),
        make_order(food_name="Soup"),
    ],
)
def test_same_id_with_different_payload_is_rejected_without_mutation(
    conflicting_order: OrderRequested,
) -> None:
    registry = OrderRegistry()
    original = make_order()
    original_result = registry.register(original)

    result = registry.register(conflicting_order)

    assert result.action is RegistrationAction.CONFLICT
    assert result.state is original_result.state
    assert registry.get(ORDER_ID) is original_result.state
    assert len(registry) == 1


def test_apply_reduces_and_stores_the_next_state() -> None:
    registry = OrderRegistry()
    registry.register(make_order())
    queued = registry.get(ORDER_ID)

    processing = registry.apply(ORDER_ID, ProcessingStarted())

    assert queued is not None
    assert queued.status is OrderStatus.QUEUED
    assert processing.status is OrderStatus.PROCESSING
    assert processing is not queued
    assert registry.get(ORDER_ID) is processing


def test_apply_unknown_order_is_rejected() -> None:
    registry = OrderRegistry()

    with pytest.raises(OrderNotFoundError, match=str(UNKNOWN_ORDER_ID)):
        registry.apply(UNKNOWN_ORDER_ID, ProcessingStarted())


def test_failed_transition_does_not_replace_current_state() -> None:
    registry = OrderRegistry()
    registry.register(make_order())
    processing = registry.apply(ORDER_ID, ProcessingStarted())

    with pytest.raises(InvalidOrderTransitionError):
        registry.apply(ORDER_ID, ProcessingStarted())

    assert registry.get(ORDER_ID) is processing
