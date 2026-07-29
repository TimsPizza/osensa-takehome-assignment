import { describe, expect, it } from 'vitest';

import { FoodReadySchema, OrderRequestedSchema } from './generated/contracts';

const validOrder = {
	schemaVersion: 1,
	orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
	tableId: 2,
	foodName: 'Chicken sandwich'
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

	it('accepts an offset-aware ready timestamp', () => {
		expect(
			FoodReadySchema.safeParse({
				...validOrder,
				readyAt: '2026-07-28T20:15:31Z'
			}).success
		).toBe(true);
	});

	it('rejects a ready timestamp without a timezone', () => {
		expect(
			FoodReadySchema.safeParse({
				...validOrder,
				readyAt: '2026-07-28T20:15:31'
			}).success
		).toBe(false);
	});
});
