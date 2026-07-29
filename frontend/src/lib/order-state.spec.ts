import { describe, expect, it } from 'vitest';

import type { OrderStatusChanged, TableSnapshot } from '$lib/generated/contracts';
import {
	addSendingOrder,
	applyOrderStatus,
	markSendFailed,
	replaceTableFromSnapshot,
	shouldApplyTableSnapshot,
	type OrderView
} from '$lib/order-state';

const orderId = '3b11d31c-7d34-4dda-91e5-d64721a50463';
const baseStatus = {
	schemaVersion: 1,
	orderId,
	tableId: 2,
	foodName: 'Chicken sandwich',
	occurredAt: '2026-07-29T18:00:00Z'
} as const;

describe('order view reducer', () => {
	it('adds a local sending state before the broker acknowledges an order', () => {
		const orders = addSendingOrder([], {
			orderId,
			tableId: 2,
			foodName: 'Chicken sandwich'
		});

		expect(orders).toEqual([
			{
				orderId,
				tableId: 2,
				foodName: 'Chicken sandwich',
				status: 'sending'
			}
		]);
	});

	it('moves an order through the public lifecycle', () => {
		let orders = addSendingOrder([], {
			orderId,
			tableId: 2,
			foodName: 'Chicken sandwich'
		});

		for (const update of [
			{ ...baseStatus, status: 'queued' },
			{ ...baseStatus, status: 'processing' },
			{
				...baseStatus,
				status: 'food_ready',
				readyAt: '2026-07-29T18:00:03Z'
			}
		] satisfies OrderStatusChanged[]) {
			orders = applyOrderStatus(orders, update);
		}

		expect(orders[0]).toMatchObject({
			orderId,
			status: 'food_ready',
			readyAt: '2026-07-29T18:00:03Z'
		});
	});

	it('adds updates from other connected restaurant clients', () => {
		const update = {
			...baseStatus,
			status: 'processing'
		} satisfies OrderStatusChanged;

		expect(applyOrderStatus([], update)).toEqual([
			{
				orderId,
				tableId: 2,
				foodName: 'Chicken sandwich',
				status: 'processing',
				occurredAt: baseStatus.occurredAt
			}
		]);
	});

	it('ignores duplicate and regressive QoS messages after completion', () => {
		const ready = {
			...baseStatus,
			status: 'food_ready',
			readyAt: '2026-07-29T18:00:03Z'
		} satisfies OrderStatusChanged;
		const completed = applyOrderStatus([], ready);
		const staleQueued = {
			...baseStatus,
			status: 'queued'
		} satisfies OrderStatusChanged;

		expect(applyOrderStatus(completed, ready)).toEqual(completed);
		expect(applyOrderStatus(completed, staleQueued)).toEqual(completed);
	});

	it('records local send and backend processing failures', () => {
		const sending: OrderView[] = [
			{
				orderId,
				tableId: 2,
				foodName: 'Chicken sandwich',
				status: 'sending'
			}
		];
		const sendFailed = markSendFailed(sending, orderId, 'Could not send');
		const backendFailure = {
			...baseStatus,
			status: 'failed',
			code: 'service_overloaded',
			message: 'Kitchen is full',
			retryable: true
		} satisfies OrderStatusChanged;

		expect(sendFailed[0]).toMatchObject({
			status: 'send_failed',
			failureMessage: 'Could not send',
			retryable: true
		});
		expect(applyOrderStatus(sendFailed, backendFailure)[0]).toMatchObject({
			status: 'failed',
			failureMessage: 'Kitchen is full',
			retryable: true
		});
	});

	it('replaces one table from an authoritative retained snapshot', () => {
		const oldOrder: OrderView = {
			orderId: '4a22d42d-8e45-4eeb-a2f6-e75832b61574',
			tableId: 2,
			foodName: 'Old soup',
			status: 'food_ready'
		};
		const otherTable: OrderView = {
			orderId: '5b33e53e-9f56-4ffc-b307-f86943c72685',
			tableId: 3,
			foodName: 'Other table pizza',
			status: 'processing'
		};
		const snapshot = tableSnapshot({
			orders: [
				{
					...baseStatus,
					status: 'food_ready',
					readyAt: '2026-07-29T18:00:03Z'
				}
			]
		});

		const replaced = replaceTableFromSnapshot([oldOrder, otherTable], snapshot);

		expect(replaced.map((order) => order.orderId)).toEqual([orderId, otherTable.orderId]);
		expect(replaced[0].status).toBe('food_ready');
	});

	it('preserves unsynchronized local orders when a snapshot arrives', () => {
		const sending = addSendingOrder([], {
			orderId: '4a22d42d-8e45-4eeb-a2f6-e75832b61574',
			tableId: 2,
			foodName: 'Still sending'
		});

		expect(replaceTableFromSnapshot(sending, tableSnapshot()).at(0)).toMatchObject({
			status: 'sending',
			foodName: 'Still sending'
		});
	});

	it('accepts a newer revision or a new service instance and rejects stale snapshots', () => {
		const current = {
			serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
			revision: 3
		};

		expect(shouldApplyTableSnapshot(tableSnapshot({ revision: 4 }), current)).toBe(true);
		expect(shouldApplyTableSnapshot(tableSnapshot({ revision: 3 }), current)).toBe(false);
		expect(shouldApplyTableSnapshot(tableSnapshot({ revision: 2 }), current)).toBe(false);
		expect(
			shouldApplyTableSnapshot(
				tableSnapshot({
					serviceInstanceId: 'ad0716a0-ad7e-451f-9198-a014e60bc68c',
					revision: 0
				}),
				current
			)
		).toBe(true);
	});
});

function tableSnapshot(overrides: Partial<TableSnapshot> = {}): TableSnapshot {
	return {
		schemaVersion: 1,
		serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
		tableId: 2,
		revision: 0,
		generatedAt: '2026-07-29T18:00:04Z',
		orders: [],
		...overrides
	};
}
