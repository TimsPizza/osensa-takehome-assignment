from datetime import datetime
from uuid import UUID

from app.models import (
    KitchenPressureSnapshot,
    KitchenWorkerIdle,
    KitchenWorkerProcessing,
    KitchenWorkerState,
    OrderRequested,
)


class KitchenPressureProjection:
    """Track the bounded queue and worker pool as a public, immutable snapshot."""

    def __init__(
        self,
        *,
        service_instance_id: UUID,
        worker_count: int,
        queue_capacity: int,
    ) -> None:
        if worker_count < 1 or worker_count > 64:
            raise ValueError("worker_count must be between 1 and 64")
        if queue_capacity < 1 or queue_capacity > 10_000:
            raise ValueError("queue_capacity must be between 1 and 10000")

        self._service_instance_id = service_instance_id
        self._queue_capacity = queue_capacity
        self._workers: dict[int, OrderRequested | None] = {
            worker_id: None for worker_id in range(1, worker_count + 1)
        }
        self._revision = 0
        self._last_signature: tuple[int, tuple[UUID | None, ...]] | None = None
        self._last_snapshot: KitchenPressureSnapshot | None = None

    def initialize(self, generated_at: datetime) -> KitchenPressureSnapshot:
        """Create the retained baseline published before orders are accepted."""
        self._revision = 0
        return self._build_snapshot(queued_orders=0, generated_at=generated_at)

    def worker_started(self, worker_id: int, order: OrderRequested) -> None:
        current = self._worker(worker_id)
        if current is not None:
            raise RuntimeError(f"worker {worker_id} is already processing an order")
        self._workers[worker_id] = order

    def worker_stopped(self, worker_id: int) -> None:
        self._worker(worker_id)
        self._workers[worker_id] = None

    def capture(
        self,
        *,
        queued_orders: int,
        generated_at: datetime,
    ) -> KitchenPressureSnapshot:
        if queued_orders < 0 or queued_orders > self._queue_capacity:
            raise ValueError("queued_orders must be within the configured queue capacity")

        signature = self._signature(queued_orders)
        if signature == self._last_signature and self._last_snapshot is not None:
            return self._last_snapshot

        self._revision += 1
        return self._build_snapshot(
            queued_orders=queued_orders,
            generated_at=generated_at,
        )

    def _worker(self, worker_id: int) -> OrderRequested | None:
        try:
            return self._workers[worker_id]
        except KeyError as error:
            raise ValueError(f"unknown worker_id: {worker_id}") from error

    def _signature(self, queued_orders: int) -> tuple[int, tuple[UUID | None, ...]]:
        return (
            queued_orders,
            tuple(
                order.order_id if order is not None else None
                for order in self._workers.values()
            ),
        )

    def _build_snapshot(
        self,
        *,
        queued_orders: int,
        generated_at: datetime,
    ) -> KitchenPressureSnapshot:
        workers: tuple[KitchenWorkerState, ...] = tuple(
            KitchenWorkerIdle(workerId=worker_id, status="idle")
            if order is None
            else KitchenWorkerProcessing(
                workerId=worker_id,
                status="processing",
                orderId=order.order_id,
                tableId=order.table_id,
                foodName=order.food_name,
            )
            for worker_id, order in self._workers.items()
        )
        snapshot = KitchenPressureSnapshot(
            schemaVersion=1,
            serviceInstanceId=self._service_instance_id,
            revision=self._revision,
            generatedAt=generated_at,
            queuedOrders=queued_orders,
            queueCapacity=self._queue_capacity,
            workers=workers,
        )
        self._last_signature = self._signature(queued_orders)
        self._last_snapshot = snapshot
        return snapshot
