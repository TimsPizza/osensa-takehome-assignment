import { describe, expect, it } from 'vitest';

import type { OrderStatusChanged } from '$lib/generated/contracts';
import { RestaurantMqttClient } from '$lib/mqtt-client';
import { createRandomOrders } from '$lib/random-orders';

const runIntegration = import.meta.env.VITE_RUN_MQTT_INTEGRATION === '1';

describe.skipIf(!runIntegration)('frontend MQTT integration', () => {
	it('publishes an order and receives its complete lifecycle', async () => {
		const orderId = crypto.randomUUID();
		const statuses: OrderStatusChanged[] = [];
		let resolveConnected: (() => void) | undefined;
		let resolveReady: (() => void) | undefined;
		let rejectFlow: ((error: Error) => void) | undefined;

		const connected = new Promise<void>((resolve) => {
			resolveConnected = resolve;
		});
		const ready = new Promise<void>((resolve) => {
			resolveReady = resolve;
		});
		const flowFailure = new Promise<never>((_resolve, reject) => {
			rejectFlow = reject;
		});

		const client = new RestaurantMqttClient(
			import.meta.env.VITE_MQTT_URL ?? 'ws://localhost:9001/mqtt',
			{
				onConnectionChange: (state) => {
					if (state === 'connected') resolveConnected?.();
				},
				onOrderStatus: (status) => {
					if (status.orderId !== orderId) return;
					statuses.push(status);
					if (status.status === 'food_ready') resolveReady?.();
					if (status.status === 'failed') {
						rejectFlow?.(new Error(`${status.code}: ${status.message}`));
					}
				},
				onError: (message) => rejectFlow?.(new Error(message))
			}
		);

		try {
			client.connect();
			await withTimeout(
				Promise.race([connected, flowFailure]),
				5_000,
				'frontend MQTT connection timed out'
			);
			await client.publishOrder({
				schemaVersion: 1,
				orderId,
				tableId: 3,
				foodName: 'Frontend integration soup'
			});
			await withTimeout(Promise.race([ready, flowFailure]), 10_000, 'order lifecycle timed out');
		} finally {
			await client.disconnect();
		}

		expect(statuses.map((status) => status.status)).toEqual(['queued', 'processing', 'food_ready']);
		expect(statuses.at(-1)).toMatchObject({
			orderId,
			tableId: 3,
			foodName: 'Frontend integration soup',
			status: 'food_ready'
		});
	}, 15_000);

	it('publishes ten random orders concurrently and receives every terminal state', async () => {
		const batch = createRandomOrders(2);
		const expectedOrderIds = new Set(batch.map((order) => order.orderId));
		const statuses = new Map<string, string[]>();
		const readyOrderIds = new Set<string>();
		let resolveConnected: (() => void) | undefined;
		let resolveAllReady: (() => void) | undefined;
		let rejectFlow: ((error: Error) => void) | undefined;

		const connected = new Promise<void>((resolve) => {
			resolveConnected = resolve;
		});
		const allReady = new Promise<void>((resolve) => {
			resolveAllReady = resolve;
		});
		const flowFailure = new Promise<never>((_resolve, reject) => {
			rejectFlow = reject;
		});

		const client = new RestaurantMqttClient(
			import.meta.env.VITE_MQTT_URL ?? 'ws://localhost:9001/mqtt',
			{
				onConnectionChange: (state) => {
					if (state === 'connected') resolveConnected?.();
				},
				onOrderStatus: (status) => {
					if (!expectedOrderIds.has(status.orderId)) return;
					const orderStatuses = statuses.get(status.orderId) ?? [];
					orderStatuses.push(status.status);
					statuses.set(status.orderId, orderStatuses);
					if (status.status === 'failed') {
						rejectFlow?.(new Error(`${status.code}: ${status.message}`));
					}
					if (status.status === 'food_ready') {
						readyOrderIds.add(status.orderId);
						if (readyOrderIds.size === batch.length) resolveAllReady?.();
					}
				},
				onError: (message) => rejectFlow?.(new Error(message))
			}
		);

		try {
			client.connect();
			await withTimeout(
				Promise.race([connected, flowFailure]),
				5_000,
				'frontend MQTT connection timed out'
			);
			await Promise.all(batch.map((order) => client.publishOrder(order)));
			await withTimeout(
				Promise.race([allReady, flowFailure]),
				15_000,
				'random order batch timed out'
			);
		} finally {
			await client.disconnect();
		}

		expect(readyOrderIds).toEqual(expectedOrderIds);
		expect(
			[...statuses.values()].every(
				(orderStatuses) => orderStatuses.join(',') === 'queued,processing,food_ready'
			)
		).toBe(true);
	}, 20_000);
});

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
	let timeout: ReturnType<typeof setTimeout> | undefined;
	const expired = new Promise<never>((_resolve, reject) => {
		timeout = setTimeout(() => reject(new Error(message)), timeoutMs);
	});

	try {
		return await Promise.race([promise, expired]);
	} finally {
		clearTimeout(timeout);
	}
}
