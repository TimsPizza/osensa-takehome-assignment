import type { OrderRequested } from '$lib/generated/contracts';
import type { TableId } from '$lib/order-state';
import { createRandomOrders } from '$lib/random-orders';

export type PublishOrder = (order: OrderRequested) => Promise<void>;

export interface ControllerOptions {
	now?: () => number;
	wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
	createId?: () => string;
	random?: () => number;
}

export interface BoundaryTestDependencies {
	publishOrder: PublishOrder;
	now: () => number;
	wait: (milliseconds: number, signal: AbortSignal) => Promise<void>;
	createId: () => string;
	random: () => number;
}

export interface PublishBatchResult {
	published: number;
	publishFailed: number;
	failedOrderIds: string[];
}

export function resolveDependencies(
	publishOrder: PublishOrder,
	options: ControllerOptions
): BoundaryTestDependencies {
	return {
		publishOrder,
		now: options.now ?? Date.now,
		wait: options.wait ?? waitFor,
		createId: options.createId ?? (() => crypto.randomUUID()),
		random: options.random ?? Math.random
	};
}

export function createOrders(
	count: number,
	dependencies: BoundaryTestDependencies
): OrderRequested[] {
	return Array.from({ length: count }, () => {
		const tableId = (Math.floor(dependencies.random() * 4) + 1) as TableId;
		return createRandomOrders(tableId, {
			count: 1,
			random: dependencies.random,
			createId: dependencies.createId
		})[0];
	});
}

export async function publishOrders(
	orders: readonly OrderRequested[],
	publishOrder: PublishOrder
): Promise<PublishBatchResult> {
	const results = await Promise.allSettled(orders.map((order) => publishOrder(order)));
	const failedOrderIds = results.flatMap((result, index) =>
		result.status === 'rejected' ? [orders[index].orderId] : []
	);
	return {
		published: orders.length - failedOrderIds.length,
		publishFailed: failedOrderIds.length,
		failedOrderIds
	};
}

function waitFor(milliseconds: number, signal: AbortSignal): Promise<void> {
	return new Promise((resolve, reject) => {
		const handleAbort = (): void => {
			clearTimeout(timeout);
			reject(new DOMException('Test stopped', 'AbortError'));
		};
		const timeout = setTimeout(() => {
			signal.removeEventListener('abort', handleAbort);
			resolve();
		}, milliseconds);
		signal.addEventListener('abort', handleAbort, { once: true });
	});
}
