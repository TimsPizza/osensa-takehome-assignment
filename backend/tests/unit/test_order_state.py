from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.models import FoodReady, OrderRequested
from app.order_state import (
    FoodOrderMismatchError,
    FoodPrepared,
    InvalidOrderStateError,
    InvalidOrderTransitionError,
    OrderEvent,
    OrderState,
    OrderStatus,
    ProcessingFailed,
    ProcessingStarted,
    PublishConfirmed,
    QueueAdmissionFailed,
    RepublishRequested,
    RetryRequested,
    transition,
)

ORDER_ID = UUID("3b11d31c-7d34-4dda-91e5-d64721a50463")
OTHER_ORDER_ID = UUID("4a22d42d-8e45-4eeb-a2f6-e75832b61574")
READY_AT = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)


def make_order() -> OrderRequested:
    return OrderRequested(
        schemaVersion=1,
        orderId=ORDER_ID,
        tableId=2,
        foodName="Chicken sandwich",
    )


def make_food(
    *,
    order_id: UUID = ORDER_ID,
    table_id: int = 2,
    food_name: str = "Chicken sandwich",
) -> FoodReady:
    return FoodReady(
        schemaVersion=1,
        orderId=order_id,
        tableId=table_id,
        foodName=food_name,
        readyAt=READY_AT,
    )


def processing_state() -> OrderState:
    return transition(OrderState(make_order()), ProcessingStarted())


def food_ready_state() -> OrderState:
    return transition(processing_state(), FoodPrepared(make_food()))


def published_state() -> OrderState:
    return transition(food_ready_state(), PublishConfirmed())


def failed_state() -> OrderState:
    return transition(processing_state(), ProcessingFailed("kitchen unavailable"))


def test_new_order_starts_queued_without_result_or_failure() -> None:
    order = make_order()

    state = OrderState(order)

    assert state.order is order
    assert state.status is OrderStatus.QUEUED
    assert state.food is None
    assert state.failure_reason is None


def test_happy_path_returns_new_immutable_states() -> None:
    queued = OrderState(make_order())
    food = make_food()

    processing = transition(queued, ProcessingStarted())
    ready = transition(processing, FoodPrepared(food))
    published = transition(ready, PublishConfirmed())

    assert queued.status is OrderStatus.QUEUED
    assert processing.status is OrderStatus.PROCESSING
    assert ready.status is OrderStatus.FOOD_READY
    assert ready.food is food
    assert published.status is OrderStatus.PUBLISHED
    assert published.food is food
    assert len({id(queued), id(processing), id(ready), id(published)}) == 4


def test_failed_order_can_be_retried_from_the_queue() -> None:
    processing = processing_state()

    failed = transition(processing, ProcessingFailed("  kitchen unavailable  "))
    queued = transition(failed, RetryRequested())

    assert processing.status is OrderStatus.PROCESSING
    assert failed.status is OrderStatus.FAILED
    assert failed.failure_reason == "kitchen unavailable"
    assert failed.food is None
    assert queued.status is OrderStatus.QUEUED
    assert queued.failure_reason is None


def test_queued_order_can_fail_when_queue_admission_is_rejected() -> None:
    queued = OrderState(make_order())

    failed = transition(queued, QueueAdmissionFailed("  processing queue is full  "))

    assert failed.status is OrderStatus.FAILED
    assert failed.failure_reason == "processing queue is full"
    assert failed.food is None


def test_published_food_can_be_scheduled_for_republish() -> None:
    published = published_state()

    ready = transition(published, RepublishRequested())
    republished = transition(ready, PublishConfirmed())

    assert ready.status is OrderStatus.FOOD_READY
    assert ready.food is published.food
    assert republished.status is OrderStatus.PUBLISHED
    assert republished.food is published.food


@pytest.mark.parametrize(
    "event",
    [
        FoodPrepared(make_food()),
        ProcessingFailed("failed"),
        PublishConfirmed(),
        RetryRequested(),
        RepublishRequested(),
    ],
)
def test_invalid_events_are_rejected_without_changing_current_state(
    event: OrderEvent,
) -> None:
    current = OrderState(make_order())

    with pytest.raises(InvalidOrderTransitionError):
        transition(current, event)

    assert current.status is OrderStatus.QUEUED
    assert current.food is None
    assert current.failure_reason is None


def test_repeated_event_is_rejected() -> None:
    current = processing_state()

    with pytest.raises(InvalidOrderTransitionError, match="ProcessingStarted"):
        transition(current, ProcessingStarted())

    assert current.status is OrderStatus.PROCESSING


@pytest.mark.parametrize(
    ("food", "field_name"),
    [
        (make_food(order_id=OTHER_ORDER_ID), "orderId"),
        (make_food(table_id=3), "tableId"),
        (make_food(food_name="Soup"), "foodName"),
    ],
)
def test_mismatched_food_is_rejected_without_changing_current_state(
    food: FoodReady,
    field_name: str,
) -> None:
    current = processing_state()

    with pytest.raises(FoodOrderMismatchError, match=field_name):
        transition(current, FoodPrepared(food))

    assert current.status is OrderStatus.PROCESSING
    assert current.food is None


def test_empty_failure_reason_is_rejected_without_changing_current_state() -> None:
    current = processing_state()

    with pytest.raises(ValueError, match="failure reason"):
        transition(current, ProcessingFailed("   "))

    assert current.status is OrderStatus.PROCESSING
    assert current.failure_reason is None


def test_queue_admission_failure_is_only_valid_while_queued() -> None:
    current = processing_state()

    with pytest.raises(InvalidOrderTransitionError):
        transition(current, QueueAdmissionFailed("queue full"))

    assert current.status is OrderStatus.PROCESSING
    assert current.failure_reason is None


@pytest.mark.parametrize(
    "state",
    [
        OrderState(make_order()),
        processing_state(),
        food_ready_state(),
        published_state(),
        failed_state(),
    ],
)
def test_states_are_immutable(state: OrderState) -> None:
    with pytest.raises(FrozenInstanceError):
        state.status = OrderStatus.PUBLISHED  # type: ignore[misc]


@pytest.mark.parametrize(
    "state_values",
    [
        {"status": OrderStatus.FOOD_READY},
        {"status": OrderStatus.PUBLISHED},
        {"status": OrderStatus.QUEUED, "food": make_food()},
        {"status": OrderStatus.PROCESSING, "failure_reason": "failed"},
        {"status": OrderStatus.FAILED},
        {"status": OrderStatus.FAILED, "failure_reason": "   "},
    ],
)
def test_invalid_state_data_is_rejected(
    state_values: dict[str, object],
) -> None:
    with pytest.raises(InvalidOrderStateError):
        OrderState(make_order(), **state_values)  # type: ignore[arg-type]
