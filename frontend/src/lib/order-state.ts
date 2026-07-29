import type { OrderStatusChanged } from '$lib/generated/contracts';

export type TableId = 1 | 2 | 3 | 4;
export type OrderViewStatus = 'sending' | 'send_failed' | OrderStatusChanged['status'];

export interface OrderView {
	orderId: string;
	tableId: TableId;
	foodName: string;
	status: OrderViewStatus;
	occurredAt?: string;
	readyAt?: string;
	failureMessage?: string;
	retryable?: boolean;
}

const STATUS_RANK: Record<OrderViewStatus, number> = {
	sending: 0,
	send_failed: 0,
	queued: 1,
	processing: 2,
	food_ready: 3,
	failed: 3
};

export function addSendingOrder(
	orders: readonly OrderView[],
	order: Pick<OrderView, 'orderId' | 'tableId' | 'foodName'>
): OrderView[] {
	return [{ ...order, status: 'sending' }, ...orders];
}

export function markSendFailed(
	orders: readonly OrderView[],
	orderId: string,
	message: string
): OrderView[] {
	return orders.map((order) =>
		order.orderId === orderId && order.status === 'sending'
			? {
					...order,
					status: 'send_failed',
					failureMessage: message,
					retryable: true
				}
			: order
	);
}

export function applyOrderStatus(
	orders: readonly OrderView[],
	update: OrderStatusChanged
): OrderView[] {
	const existing = orders.find((order) => order.orderId === update.orderId);
	const next = fromStatusUpdate(update);

	if (!existing) {
		return [next, ...orders];
	}

	if (
		existing.status === 'food_ready' ||
		existing.status === 'failed' ||
		STATUS_RANK[update.status] < STATUS_RANK[existing.status]
	) {
		return [...orders];
	}

	if (existing.status === update.status && existing.occurredAt === update.occurredAt) {
		return [...orders];
	}

	return orders.map((order) => (order.orderId === update.orderId ? next : order));
}

function fromStatusUpdate(update: OrderStatusChanged): OrderView {
	return {
		orderId: update.orderId,
		tableId: update.tableId as TableId,
		foodName: update.foodName,
		status: update.status,
		occurredAt: update.occurredAt,
		...(update.status === 'food_ready' ? { readyAt: update.readyAt } : {}),
		...(update.status === 'failed'
			? {
					failureMessage: update.message,
					retryable: update.retryable
				}
			: {})
	};
}
