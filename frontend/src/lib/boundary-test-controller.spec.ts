import { get } from 'svelte/store';
import { describe, expect, it, vi } from 'vitest';

import { BoundaryTestController } from '$lib/boundary-test-controller';
import type {
	KitchenPressureSnapshot,
	OrderRequested,
	OrderStatusChanged
} from '$lib/generated/contracts';

const occurredAt = '2026-07-29T18:00:00Z';

describe('boundary test controller', () => {
	it('tracks a random burst until every published order is terminal', async () => {
		const published: OrderRequested[] = [];
		let nextId = 1;
		const controller = new BoundaryTestController(
			async (order) => {
				published.push(order);
			},
			{
				createId: () => `00000000-0000-4000-8000-${String(nextId++).padStart(12, '0')}`,
				random: () => 0
			}
		);

		await controller.runRandomBurst(3);
		expect(get(controller.burst)).toMatchObject({
			status: 'observing',
			requested: 3,
			published: 3
		});

		for (const order of published) {
			controller.handleOrderStatus(status(order, 'queued'));
			controller.handleOrderStatus(status(order, 'food_ready', { readyAt: occurredAt }));
		}

		expect(get(controller.burst)).toMatchObject({
			status: 'completed',
			accepted: 3,
			terminal: 3,
			overloaded: 0
		});
		controller.destroy();
	});

	it('proves three duplicate publishes collapse into one lifecycle', async () => {
		const published: OrderRequested[] = [];
		const controller = new BoundaryTestController(
			async (order) => {
				published.push(order);
			},
			{
				createId: () => '3b11d31c-7d34-4dda-91e5-d64721a50463',
				random: () => 0
			}
		);

		await controller.runIdempotency();
		expect(published).toHaveLength(3);
		expect(new Set(published.map((order) => order.orderId)).size).toBe(1);

		const order = published[0];
		controller.handleOrderStatus(status(order, 'queued'));
		controller.handleOrderStatus(status(order, 'processing'));
		controller.handleOrderStatus(status(order, 'food_ready', { readyAt: occurredAt }));

		expect(get(controller.idempotency)).toMatchObject({
			status: 'passed',
			published: 3,
			rawEvents: 3,
			uniqueStatuses: ['queued', 'processing', 'food_ready']
		});
		controller.destroy();
	});

	it('adaptively fills toward the pressure target and stops at the deadline', async () => {
		let now = 0;
		const publish = vi.fn(async () => {});
		const controller = new BoundaryTestController(publish, {
			now: () => now,
			wait: async (milliseconds) => {
				now += milliseconds;
			},
			createId: (() => {
				let nextId = 1;
				return () => `00000000-0000-4000-8000-${String(nextId++).padStart(12, '0')}`;
			})(),
			random: () => 0
		});
		controller.handlePressure(pressureSnapshot());

		await controller.startSaturation({
			durationSeconds: 5,
			targetPercent: 80,
			maxOrdersPerSecond: 20
		});

		expect(publish).toHaveBeenCalledTimes(100);
		expect(get(controller.saturation)).toMatchObject({
			status: 'completed',
			published: 100,
			publishFailed: 0
		});
		controller.destroy();
	});

	it('rejects unsafe saturation controls before publishing', async () => {
		const publish = vi.fn(async () => {});
		const controller = new BoundaryTestController(publish);

		await expect(
			controller.startSaturation({
				durationSeconds: 0,
				targetPercent: 95,
				maxOrdersPerSecond: 40
			})
		).rejects.toThrow('durationSeconds');
		expect(publish).not.toHaveBeenCalled();
	});
});

function status(
	order: OrderRequested,
	state: OrderStatusChanged['status'],
	extra: Record<string, unknown> = {}
): OrderStatusChanged {
	return {
		...order,
		status: state,
		occurredAt,
		...extra
	} as OrderStatusChanged;
}

function pressureSnapshot(): KitchenPressureSnapshot {
	return {
		schemaVersion: 1,
		serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
		revision: 1,
		generatedAt: occurredAt,
		queuedOrders: 0,
		queueCapacity: 10,
		workers: [{ workerId: 1, status: 'idle' }]
	};
}
