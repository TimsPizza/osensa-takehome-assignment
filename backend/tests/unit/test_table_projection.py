from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models import OrderQueued
from app.table_projection import MAX_SNAPSHOT_ORDERS, TableSnapshotProjection

SERVICE_INSTANCE_ID = UUID("1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54")
STARTED_AT = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def queued_update(number: int, *, table_id: int = 1) -> OrderQueued:
    return OrderQueued(
        schemaVersion=1,
        orderId=UUID(int=number),
        tableId=table_id,
        foodName=f"Order {number}",
        status="queued",
        occurredAt=STARTED_AT + timedelta(seconds=number),
    )


def test_initial_snapshots_are_empty_and_identify_the_service_instance() -> None:
    projection = TableSnapshotProjection(service_instance_id=SERVICE_INSTANCE_ID)

    snapshots = projection.initialize(STARTED_AT)

    assert [snapshot.table_id for snapshot in snapshots] == [1, 2, 3, 4]
    assert all(snapshot.service_instance_id == SERVICE_INSTANCE_ID for snapshot in snapshots)
    assert all(snapshot.revision == 0 for snapshot in snapshots)
    assert all(snapshot.orders == () for snapshot in snapshots)


def test_projection_is_table_scoped_newest_first_and_idempotent() -> None:
    projection = TableSnapshotProjection(service_instance_id=SERVICE_INSTANCE_ID)
    first = queued_update(1, table_id=1)
    second = queued_update(2, table_id=2)

    first_snapshot = projection.apply(first, generated_at=STARTED_AT)
    second_snapshot = projection.apply(second, generated_at=STARTED_AT)
    duplicate_snapshot = projection.apply(first, generated_at=STARTED_AT + timedelta(minutes=1))

    assert first_snapshot.revision == 1
    assert first_snapshot.orders == (first,)
    assert second_snapshot.revision == 1
    assert second_snapshot.orders == (second,)
    assert duplicate_snapshot == first_snapshot


def test_projection_keeps_only_the_ten_most_recent_orders_per_table() -> None:
    projection = TableSnapshotProjection(service_instance_id=SERVICE_INSTANCE_ID)
    snapshot = None

    for number in range(1, MAX_SNAPSHOT_ORDERS + 3):
        snapshot = projection.apply(
            queued_update(number),
            generated_at=STARTED_AT + timedelta(seconds=number),
        )

    assert snapshot is not None
    assert snapshot.revision == MAX_SNAPSHOT_ORDERS + 2
    assert [order.order_id.int for order in snapshot.orders] == list(
        range(MAX_SNAPSHOT_ORDERS + 2, 2, -1)
    )
