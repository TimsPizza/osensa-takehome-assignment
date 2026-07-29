from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.models import OrderStatusUpdate, TableSnapshot

TABLE_IDS = (1, 2, 3, 4)
MAX_SNAPSHOT_ORDERS = 10


@dataclass(frozen=True, slots=True)
class _ProjectedOrder:
    update: OrderStatusUpdate
    sequence: int


class TableSnapshotProjection:
    """Build bounded, public table views from successfully published status events."""

    def __init__(
        self,
        *,
        service_instance_id: UUID | None = None,
        max_orders_per_table: int = MAX_SNAPSHOT_ORDERS,
    ) -> None:
        if max_orders_per_table < 1 or max_orders_per_table > MAX_SNAPSHOT_ORDERS:
            raise ValueError(f"max_orders_per_table must be between 1 and {MAX_SNAPSHOT_ORDERS}")

        self._service_instance_id = service_instance_id or uuid4()
        self._max_orders_per_table = max_orders_per_table
        self._orders: dict[int, dict[UUID, _ProjectedOrder]] = {
            table_id: {} for table_id in TABLE_IDS
        }
        self._revisions = {table_id: 0 for table_id in TABLE_IDS}
        self._snapshots: dict[int, TableSnapshot] = {}
        self._sequence = 0

    def initialize(self, generated_at: datetime) -> tuple[TableSnapshot, ...]:
        """Return authoritative empty snapshots before the service accepts orders."""
        return tuple(self._build_snapshot(table_id, generated_at) for table_id in TABLE_IDS)

    def apply(
        self,
        update: OrderStatusUpdate,
        *,
        generated_at: datetime,
    ) -> TableSnapshot:
        table_orders = self._orders[update.table_id]
        existing = table_orders.get(update.order_id)
        if existing is not None and existing.update == update:
            snapshot = self._snapshots.get(update.table_id)
            if snapshot is not None:
                return snapshot

        self._sequence += 1
        table_orders[update.order_id] = _ProjectedOrder(update, self._sequence)

        if len(table_orders) > self._max_orders_per_table:
            oldest_order_id = min(
                table_orders,
                key=lambda order_id: table_orders[order_id].sequence,
            )
            del table_orders[oldest_order_id]

        self._revisions[update.table_id] += 1
        return self._build_snapshot(update.table_id, generated_at)

    def _build_snapshot(self, table_id: int, generated_at: datetime) -> TableSnapshot:
        orders = tuple(
            projected.update
            for projected in sorted(
                self._orders[table_id].values(),
                key=lambda projected: projected.sequence,
                reverse=True,
            )
        )
        snapshot = TableSnapshot(
            schemaVersion=1,
            serviceInstanceId=self._service_instance_id,
            tableId=table_id,
            revision=self._revisions[table_id],
            generatedAt=generated_at,
            orders=orders,
        )
        self._snapshots[table_id] = snapshot
        return snapshot
