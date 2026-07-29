from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.kitchen_pressure import KitchenPressureProjection
from app.models import KitchenWorkerProcessing, OrderRequested

SERVICE_INSTANCE_ID = UUID("1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54")
NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
ORDER = OrderRequested(
    schemaVersion=1,
    orderId=UUID("3b11d31c-7d34-4dda-91e5-d64721a50463"),
    tableId=2,
    foodName="Chicken sandwich",
)


def projection() -> KitchenPressureProjection:
    return KitchenPressureProjection(
        service_instance_id=SERVICE_INSTANCE_ID,
        worker_count=2,
        queue_capacity=4,
    )


def test_initial_snapshot_exposes_idle_workers_and_queue_capacity() -> None:
    snapshot = projection().initialize(NOW)

    assert snapshot.service_instance_id == SERVICE_INSTANCE_ID
    assert snapshot.revision == 0
    assert snapshot.queued_orders == 0
    assert snapshot.queue_capacity == 4
    assert [worker.status for worker in snapshot.workers] == ["idle", "idle"]


def test_capture_tracks_busy_worker_and_queue_depth() -> None:
    pressure = projection()
    pressure.initialize(NOW)
    pressure.worker_started(2, ORDER)

    snapshot = pressure.capture(
        queued_orders=3,
        generated_at=NOW + timedelta(seconds=1),
    )
    worker = snapshot.workers[1]

    assert snapshot.revision == 1
    assert snapshot.queued_orders == 3
    assert isinstance(worker, KitchenWorkerProcessing)
    assert worker.worker_id == 2
    assert worker.order_id == ORDER.order_id
    assert worker.table_id == 2
    assert worker.food_name == "Chicken sandwich"


def test_unchanged_pressure_reuses_the_same_revision() -> None:
    pressure = projection()
    first = pressure.initialize(NOW)

    duplicate = pressure.capture(
        queued_orders=0,
        generated_at=NOW + timedelta(minutes=1),
    )

    assert duplicate is first
    assert duplicate.revision == 0


def test_worker_completion_returns_the_slot_to_idle() -> None:
    pressure = projection()
    pressure.initialize(NOW)
    pressure.worker_started(1, ORDER)
    pressure.capture(queued_orders=0, generated_at=NOW)

    pressure.worker_stopped(1)
    snapshot = pressure.capture(
        queued_orders=0,
        generated_at=NOW + timedelta(seconds=1),
    )

    assert snapshot.revision == 2
    assert snapshot.workers[0].status == "idle"


@pytest.mark.parametrize("queued_orders", [-1, 5])
def test_capture_rejects_queue_depth_outside_capacity(queued_orders: int) -> None:
    with pytest.raises(ValueError):
        projection().capture(queued_orders=queued_orders, generated_at=NOW)


def test_unknown_worker_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown worker_id"):
        projection().worker_started(3, ORDER)
