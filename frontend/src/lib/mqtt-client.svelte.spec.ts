import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';

import { BoundaryTestController } from '$lib/boundary-test-controller';
import type { KitchenPressureSnapshot, OrderStatusChanged } from '$lib/generated/contracts';
import { RestaurantMqttClient } from '$lib/mqtt-client';
import { createRandomOrders } from '$lib/random-orders';

const runIntegration = import.meta.env.VITE_RUN_MQTT_INTEGRATION === '1';
const runLoad = import.meta.env.VITE_RUN_MQTT_LOAD === '1';

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
				onTableSnapshot: () => {},
				onKitchenPressure: () => {},
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

	it('receives retained backend queue and worker capacity', async () => {
		let resolveConnected: (() => void) | undefined;
		let resolvePressure: (() => void) | undefined;
		let pressure: KitchenPressureSnapshot | undefined;

		const connected = new Promise<void>((resolve) => {
			resolveConnected = resolve;
		});
		const pressureReceived = new Promise<void>((resolve) => {
			resolvePressure = resolve;
		});
		const client = new RestaurantMqttClient(
			import.meta.env.VITE_MQTT_URL ?? 'ws://localhost:9001/mqtt',
			{
				onConnectionChange: (state) => {
					if (state === 'connected') resolveConnected?.();
				},
				onOrderStatus: () => {},
				onTableSnapshot: () => {},
				onKitchenPressure: (snapshot) => {
					pressure = snapshot;
					resolvePressure?.();
				},
				onError: () => {}
			}
		);

		try {
			client.connect();
			await withTimeout(
				Promise.all([connected, pressureReceived]),
				5_000,
				'retained kitchen pressure timed out'
			);
		} finally {
			await client.disconnect();
		}

		expect(pressure).toMatchObject({
			queueCapacity: 256,
			queuedOrders: expect.any(Number)
		});
		expect(pressure?.workers).toHaveLength(8);
	}, 10_000);

	it('collapses three rapid publishes with the same UUID into one lifecycle', async () => {
		let resolveConnected: (() => void) | undefined;
		let resolvePassed: (() => void) | undefined;
		let rejectFlow: ((error: Error) => void) | undefined;
		const connection: { client?: RestaurantMqttClient } = {};

		const connected = new Promise<void>((resolve) => {
			resolveConnected = resolve;
		});
		const passed = new Promise<void>((resolve) => {
			resolvePassed = resolve;
		});
		const flowFailure = new Promise<never>((_resolve, reject) => {
			rejectFlow = reject;
		});
		const controller = new BoundaryTestController((order) => {
			if (!connection.client) throw new Error('MQTT client is not ready');
			return connection.client.publishOrder(order);
		});
		const unsubscribe = controller.idempotency.subscribe((run) => {
			if (run.status === 'passed') resolvePassed?.();
			if (run.status === 'failed') rejectFlow?.(new Error(run.error ?? 'Idempotency test failed'));
		});

		const client = new RestaurantMqttClient(
			import.meta.env.VITE_MQTT_URL ?? 'ws://localhost:9001/mqtt',
			{
				onConnectionChange: (state) => {
					if (state === 'connected') resolveConnected?.();
				},
				onOrderStatus: (status) => controller.handleOrderStatus(status),
				onTableSnapshot: () => {},
				onKitchenPressure: (snapshot) => controller.handlePressure(snapshot),
				onError: (message) => rejectFlow?.(new Error(message))
			}
		);
		connection.client = client;

		try {
			client.connect();
			await withTimeout(
				Promise.race([connected, flowFailure]),
				5_000,
				'frontend MQTT connection timed out'
			);
			await controller.runIdempotency();
			await withTimeout(
				Promise.race([passed, flowFailure]),
				10_000,
				'duplicate order lifecycle timed out'
			);
			expect(get(controller.idempotency)).toMatchObject({
				status: 'passed',
				published: 3,
				uniqueStatuses: ['queued', 'processing', 'food_ready']
			});
		} finally {
			unsubscribe();
			controller.destroy();
			await client.disconnect();
		}
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
				onTableSnapshot: () => {},
				onKitchenPressure: () => {},
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

	it('recovers a completed order in a brand-new clean-session client', async () => {
		const orderId = crypto.randomUUID();
		const mqttUrl = import.meta.env.VITE_MQTT_URL ?? 'ws://localhost:9001/mqtt';
		let resolveObserverConnected: (() => void) | undefined;
		let resolveOrderingConnected: (() => void) | undefined;
		let resolveReady: (() => void) | undefined;
		let resolveRecoveryConnected: (() => void) | undefined;
		let resolveRecovered: (() => void) | undefined;
		let recoveredStatus: OrderStatusChanged | undefined;
		let rejectFlow: ((error: Error) => void) | undefined;

		const observerConnected = new Promise<void>((resolve) => {
			resolveObserverConnected = resolve;
		});
		const orderingConnected = new Promise<void>((resolve) => {
			resolveOrderingConnected = resolve;
		});
		const ready = new Promise<void>((resolve) => {
			resolveReady = resolve;
		});
		const recoveryConnected = new Promise<void>((resolve) => {
			resolveRecoveryConnected = resolve;
		});
		const recovered = new Promise<void>((resolve) => {
			resolveRecovered = resolve;
		});
		const flowFailure = new Promise<never>((_resolve, reject) => {
			rejectFlow = reject;
		});

		const observer = new RestaurantMqttClient(mqttUrl, {
			onConnectionChange: (state) => {
				if (state === 'connected') resolveObserverConnected?.();
			},
			onOrderStatus: (status) => {
				if (status.orderId !== orderId) return;
				if (status.status === 'food_ready') resolveReady?.();
				if (status.status === 'failed') {
					rejectFlow?.(new Error(`${status.code}: ${status.message}`));
				}
			},
			onTableSnapshot: () => {},
			onKitchenPressure: () => {},
			onError: (message) => rejectFlow?.(new Error(message))
		});
		const orderingClient = new RestaurantMqttClient(mqttUrl, {
			onConnectionChange: (state) => {
				if (state === 'connected') resolveOrderingConnected?.();
			},
			onOrderStatus: () => {},
			onTableSnapshot: () => {},
			onKitchenPressure: () => {},
			onError: (message) => rejectFlow?.(new Error(message))
		});
		const recoveryClient = new RestaurantMqttClient(mqttUrl, {
			onConnectionChange: (state) => {
				if (state === 'connected') resolveRecoveryConnected?.();
			},
			onOrderStatus: () => {},
			onTableSnapshot: (snapshot) => {
				const status = snapshot.orders.find((order) => order.orderId === orderId);
				if (status?.status !== 'food_ready') return;
				recoveredStatus = status;
				resolveRecovered?.();
			},
			onKitchenPressure: () => {},
			onError: (message) => rejectFlow?.(new Error(message))
		});

		try {
			observer.connect();
			orderingClient.connect();
			await withTimeout(
				Promise.race([Promise.all([observerConnected, orderingConnected]), flowFailure]),
				5_000,
				'ordering clients did not connect'
			);
			await orderingClient.publishOrder({
				schemaVersion: 1,
				orderId,
				tableId: 1,
				foodName: 'Recovered browser soup'
			});
			await orderingClient.disconnect();

			await withTimeout(
				Promise.race([ready, flowFailure]),
				10_000,
				'order did not finish after the ordering client closed'
			);
			await observer.disconnect();

			recoveryClient.connect();
			await withTimeout(
				Promise.race([Promise.all([recoveryConnected, recovered]), flowFailure]),
				5_000,
				'new client did not receive the retained table snapshot'
			);
		} finally {
			await Promise.all([
				observer.disconnect(),
				orderingClient.disconnect(),
				recoveryClient.disconnect()
			]);
		}

		expect(recoveredStatus).toMatchObject({
			orderId,
			tableId: 1,
			foodName: 'Recovered browser soup',
			status: 'food_ready'
		});
	}, 20_000);

	it.runIf(runLoad)(
		'sustains overload without allowing rejected orders to become ghost work',
		async () => {
			let resolveConnected: (() => void) | undefined;
			let resolvePressure: (() => void) | undefined;
			let rejectFlow: ((error: Error) => void) | undefined;
			const connection: { client?: RestaurantMqttClient } = {};

			const connected = new Promise<void>((resolve) => {
				resolveConnected = resolve;
			});
			const pressureReceived = new Promise<void>((resolve) => {
				resolvePressure = resolve;
			});
			const flowFailure = new Promise<never>((_resolve, reject) => {
				rejectFlow = reject;
			});
			const controller = new BoundaryTestController((order) => {
				if (!connection.client) throw new Error('MQTT client is not ready');
				return connection.client.publishOrder(order);
			});
			const client = new RestaurantMqttClient(
				import.meta.env.VITE_MQTT_URL ?? 'ws://localhost:9001/mqtt',
				{
					onConnectionChange: (state) => {
						if (state === 'connected') resolveConnected?.();
					},
					onOrderStatus: (status) => controller.handleOrderStatus(status),
					onTableSnapshot: () => {},
					onKitchenPressure: (snapshot) => {
						controller.handlePressure(snapshot);
						resolvePressure?.();
					},
					onError: (message) => rejectFlow?.(new Error(message))
				}
			);
			connection.client = client;

			try {
				client.connect();
				await withTimeout(
					Promise.race([Promise.all([connected, pressureReceived]), flowFailure]),
					5_000,
					'frontend MQTT pressure connection timed out'
				);
				await withTimeout(
					Promise.race([
						controller.startOverload({
							durationSeconds: 5,
							ordersPerSecond: 100,
							observationSeconds: 5
						}),
						flowFailure
					]),
					20_000,
					'overload ghost test timed out'
				);

				expect(get(controller.overload)).toMatchObject({
					status: 'passed',
					ghosts: 0
				});
				expect(get(controller.overload).overloaded).toBeGreaterThan(0);
			} finally {
				controller.destroy();
				await client.disconnect();
			}
		},
		25_000
	);
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
