import { describe, expect, it } from 'vitest';

import { OrderRequestedSchema } from '$lib/generated/contracts';
import { createRandomOrders } from '$lib/random-orders';

describe('random order batch', () => {
	it('creates ten contract-valid orders for the selected table', () => {
		let nextId = 0;
		const orders = createRandomOrders(4, {
			random: () => 0,
			createId: () => `00000000-0000-4000-8000-${String(nextId++).padStart(12, '0')}`
		});

		expect(orders).toHaveLength(10);
		expect(new Set(orders.map((order) => order.orderId)).size).toBe(10);
		expect(orders.every((order) => order.tableId === 4)).toBe(true);
		expect(orders.every((order) => OrderRequestedSchema.safeParse(order).success)).toBe(true);
		expect(orders.every((order) => order.foodName === 'Margherita pizza')).toBe(true);
	});

	it.each([0, -1, 1.5, 501])('rejects an unsafe batch size: %s', (count) => {
		expect(() => createRandomOrders(1, { count })).toThrow(RangeError);
	});
});
