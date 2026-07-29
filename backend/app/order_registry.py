from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never
from uuid import UUID

from app.models import OrderRequested
from app.order_state import (
    OrderEvent,
    OrderState,
    OrderStatus,
    RepublishRequested,
    RetryRequested,
    transition,
)


class RegistrationAction(StrEnum):
    PROCESS = "process"
    IGNORE = "ignore"
    REPUBLISH = "republish"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    action: RegistrationAction
    state: OrderState


class OrderNotFoundError(LookupError):
    """Raised when an event targets an order that is not registered."""


class OrderRegistry:
    """Own the current in-memory state of each order."""

    def __init__(self) -> None:
        self._orders: dict[UUID, OrderState] = {}

    def __len__(self) -> int:
        return len(self._orders)

    def get(self, order_id: UUID) -> OrderState | None:
        return self._orders.get(order_id)

    def register(self, order: OrderRequested) -> RegistrationResult:
        current = self._orders.get(order.order_id)
        if current is None:
            queued = OrderState(order)
            self._orders[order.order_id] = queued
            return RegistrationResult(RegistrationAction.PROCESS, queued)

        if current.order != order:
            return RegistrationResult(RegistrationAction.CONFLICT, current)

        match current.status:
            case OrderStatus.QUEUED | OrderStatus.PROCESSING | OrderStatus.FOOD_READY:
                return RegistrationResult(RegistrationAction.IGNORE, current)

            case OrderStatus.PUBLISHED:
                ready = transition(current, RepublishRequested())
                self._orders[order.order_id] = ready
                return RegistrationResult(RegistrationAction.REPUBLISH, ready)

            case OrderStatus.FAILED:
                queued = transition(current, RetryRequested())
                self._orders[order.order_id] = queued
                return RegistrationResult(RegistrationAction.PROCESS, queued)

            case _:
                assert_never(current.status)

    def apply(self, order_id: UUID, event: OrderEvent) -> OrderState:
        current = self._orders.get(order_id)
        if current is None:
            raise OrderNotFoundError(f"order is not registered: {order_id}")

        next_state = transition(current, event)
        self._orders[order_id] = next_state
        return next_state
