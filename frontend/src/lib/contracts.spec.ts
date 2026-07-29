import { describe, expect, it } from 'vitest';

import {
	OrderRequestedSchema,
	OrderStatusChangedSchema,
	TableSnapshotSchema
} from './generated/contracts';

const validOrder = {
	schemaVersion: 1,
	orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
	tableId: 2,
	foodName: 'Chicken sandwich'
};

const validStatus = {
	...validOrder,
	occurredAt: '2026-07-28T20:15:31Z'
};

describe('generated MQTT contracts', () => {
	it('accepts the expected order wire shape', () => {
		expect(OrderRequestedSchema.parse(validOrder)).toEqual(validOrder);
	});

	it.each([
		{ ...validOrder, tableId: 0 },
		{ ...validOrder, tableId: 5 },
		{ ...validOrder, tableId: '2' },
		{ ...validOrder, foodName: '   ' },
		{ ...validOrder, foodName: ' trailing ' },
		{ ...validOrder, unexpected: true }
	])('rejects an invalid order: %o', (order) => {
		expect(OrderRequestedSchema.safeParse(order).success).toBe(false);
	});

	it.each([
		{ ...validStatus, status: 'queued' },
		{ ...validStatus, status: 'processing' },
		{
			...validStatus,
			status: 'food_ready',
			readyAt: '2026-07-28T20:15:31Z'
		},
		{
			...validStatus,
			status: 'failed',
			code: 'processing_failed',
			message: 'The order could not be prepared.',
			retryable: true
		}
	])('accepts an order status variant: %o', (update) => {
		expect(OrderStatusChangedSchema.safeParse(update).success).toBe(true);
	});

	it.each([
		{ ...validStatus, status: 'unknown' },
		{ ...validStatus, status: 'food_ready' },
		{
			...validStatus,
			status: 'food_ready',
			readyAt: '2026-07-28T20:15:31'
		},
		{
			...validStatus,
			status: 'failed',
			code: 'raw_exception',
			message: 'unsafe',
			retryable: true
		}
	])('rejects an invalid order status variant: %o', (update) => {
		expect(OrderStatusChangedSchema.safeParse(update).success).toBe(false);
	});

	it('accepts a bounded table snapshot containing the status union', () => {
		const snapshot = {
			schemaVersion: 1,
			serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
			tableId: 2,
			revision: 4,
			generatedAt: '2026-07-28T20:15:32Z',
			orders: [{ ...validStatus, status: 'processing' }]
		};

		expect(TableSnapshotSchema.parse(snapshot)).toEqual(snapshot);
	});

	it('rejects a table snapshot with more than ten orders', () => {
		const snapshot = {
			schemaVersion: 1,
			serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
			tableId: 2,
			revision: 11,
			generatedAt: '2026-07-28T20:15:32Z',
			orders: Array.from({ length: 11 }, (_, index) => ({
				...validStatus,
				orderId: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
				status: 'queued'
			}))
		};

		expect(TableSnapshotSchema.safeParse(snapshot).success).toBe(false);
	});
});
