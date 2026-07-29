import { describe, expect, it } from 'vitest';

import type { OrderStatusChanged } from '$lib/generated/contracts';
import {
	addSendingOrder,
	applyOrderStatus,
	markSendFailed,
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
});
