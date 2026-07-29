from dataclasses import dataclass, replace
from enum import StrEnum

from app.models import FoodReady, OrderRequested


class OrderStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    FOOD_READY = "food_ready"
    PUBLISHED = "published"
    FAILED = "failed"


class InvalidOrderTransitionError(RuntimeError):
    """Raised when an event is not valid for the current order state."""


class InvalidOrderStateError(ValueError):
    """Raised when an OrderState violates its data invariants."""


class FoodOrderMismatchError(ValueError):
    """Raised when completed food does not belong to its source order."""


@dataclass(frozen=True, slots=True)
class ProcessingStarted:
    pass


@dataclass(frozen=True, slots=True)
class FoodPrepared:
    food: FoodReady


@dataclass(frozen=True, slots=True)
class ProcessingFailed:
    reason: str


@dataclass(frozen=True, slots=True)
class PublishConfirmed:
    pass


@dataclass(frozen=True, slots=True)
class RetryRequested:
    pass


@dataclass(frozen=True, slots=True)
class RepublishRequested:
    pass


type OrderEvent = (
    ProcessingStarted
    | FoodPrepared
    | ProcessingFailed
    | PublishConfirmed
    | RetryRequested
    | RepublishRequested
)


@dataclass(frozen=True, slots=True)
class OrderState:
    """Immutable extended state for one validated order."""

    order: OrderRequested
    status: OrderStatus = OrderStatus.QUEUED
    food: FoodReady | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        has_food = self.status in {OrderStatus.FOOD_READY, OrderStatus.PUBLISHED}
        if has_food:
            if self.food is None:
                raise InvalidOrderStateError(f"{self.status.value} order must contain food")
            _validate_food_matches_order(self.order, self.food)
        elif self.food is not None:
            raise InvalidOrderStateError(f"{self.status.value} order must not contain food")

        if self.status is OrderStatus.FAILED:
            if self.failure_reason is None or not self.failure_reason.strip():
                raise InvalidOrderStateError("failed order must contain a failure reason")
        elif self.failure_reason is not None:
            raise InvalidOrderStateError(
                f"{self.status.value} order must not contain a failure reason"
            )


def transition(current: OrderState, event: OrderEvent) -> OrderState:
    """Reduce one valid state/event pair into a new immutable state."""

    match current.status, event:
        case OrderStatus.QUEUED, ProcessingStarted():
            return replace(current, status=OrderStatus.PROCESSING)

        case OrderStatus.PROCESSING, FoodPrepared(food=food):
            return replace(
                current,
                status=OrderStatus.FOOD_READY,
                food=food,
            )

        case OrderStatus.PROCESSING, ProcessingFailed(reason=reason):
            normalized_reason = reason.strip()
            if not normalized_reason:
                raise ValueError("failure reason must not be empty")
            return replace(
                current,
                status=OrderStatus.FAILED,
                failure_reason=normalized_reason,
            )

        case OrderStatus.FOOD_READY, PublishConfirmed():
            return replace(current, status=OrderStatus.PUBLISHED)

        case OrderStatus.FAILED, RetryRequested():
            return replace(
                current,
                status=OrderStatus.QUEUED,
                failure_reason=None,
            )

        case OrderStatus.PUBLISHED, RepublishRequested():
            return replace(current, status=OrderStatus.FOOD_READY)

        case _:
            raise InvalidOrderTransitionError(
                f"cannot apply {type(event).__name__} to order {current.order.order_id} "
                f"in {current.status.value}"
            )


def _validate_food_matches_order(order: OrderRequested, food: FoodReady) -> None:
    mismatched_fields = [
        field_name
        for field_name, order_value, food_value in (
            ("orderId", order.order_id, food.order_id),
            ("tableId", order.table_id, food.table_id),
            ("foodName", order.food_name, food.food_name),
        )
        if order_value != food_value
    ]
    if mismatched_fields:
        joined_fields = ", ".join(mismatched_fields)
        raise FoodOrderMismatchError(f"food does not match order {order.order_id}: {joined_fields}")
