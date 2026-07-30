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

type OrderKey = tuple[int, UUID]


class RegistrationAction(StrEnum):
    PROCESS = "process"
    IGNORE = "ignore"
    DEFER_REPUBLISH = "defer_republish"
    REPUBLISH = "republish"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    action: RegistrationAction
    state: OrderState


class OrderNotFoundError(LookupError):
    """Raised when an event targets an order that is not registered."""


class OrderRegistryFullError(RuntimeError):
    """Raised when no terminal entry can be evicted for a new order."""


class OrderRegistry:
    """Own order state with idempotency scoped to a restaurant table."""

    def __init__(self, max_orders: int = 4096) -> None:
        if max_orders < 1:
            raise ValueError("max_orders must be greater than zero")
        self._max_orders = max_orders
        self._orders: dict[OrderKey, OrderState] = {}

    def __len__(self) -> int:
        return len(self._orders)

    def get(self, table_id: int, order_id: UUID) -> OrderState | None:
        return self._orders.get((table_id, order_id))

    def register(self, order: OrderRequested) -> RegistrationResult:
        key = (order.table_id, order.order_id)
        current = self._orders.get(key)
        if current is None:
            self._make_room()
            queued = OrderState(order)
            self._orders[key] = queued
            return RegistrationResult(RegistrationAction.PROCESS, queued)

        if current.order != order:
            return RegistrationResult(RegistrationAction.CONFLICT, current)

        match current.status:
            case OrderStatus.QUEUED | OrderStatus.PROCESSING:
                return RegistrationResult(RegistrationAction.IGNORE, current)

            case OrderStatus.FOOD_READY:
                return RegistrationResult(RegistrationAction.DEFER_REPUBLISH, current)

            case OrderStatus.PUBLISHED:
                ready = transition(current, RepublishRequested())
                self._orders[key] = ready
                return RegistrationResult(RegistrationAction.REPUBLISH, ready)

            case OrderStatus.FAILED:
                queued = transition(current, RetryRequested())
                self._orders[key] = queued
                return RegistrationResult(RegistrationAction.PROCESS, queued)

            case _:
                assert_never(current.status)

    def _make_room(self) -> None:
        if len(self._orders) < self._max_orders:
            return

        evictable_key = next(
            (
                key
                for key, state in self._orders.items()
                if state.status in (OrderStatus.FAILED, OrderStatus.PUBLISHED)
            ),
            None,
        )
        if evictable_key is None:
            raise OrderRegistryFullError("order registry has no evictable terminal entries")
        del self._orders[evictable_key]

    def apply(self, table_id: int, order_id: UUID, event: OrderEvent) -> OrderState:
        key = (table_id, order_id)
        current = self._orders.get(key)
        if current is None:
            raise OrderNotFoundError(
                f"order is not registered: table_id={table_id} order_id={order_id}"
            )

        next_state = transition(current, event)
        self._orders[key] = next_state
        return next_state
