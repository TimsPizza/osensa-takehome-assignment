import { describe, expect, it, vi } from 'vitest';

import type { OrderRequested } from '$lib/generated/contracts';
import type { BrokerCredentials, BrowserStorage, MqttClientCallbacks } from '$lib/mqtt-client';
import { RestaurantSession, type RestaurantMqttPort } from '$lib/restaurant-session.svelte';

const order: OrderRequested = {
	schemaVersion: 1,
	orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
	tableId: 2,
	foodName: 'Session soup'
};

describe('restaurant session', () => {
	it('owns connection callbacks, order projection, publishing, and cleanup', async () => {
		const localStorage = new MemoryStorage();
		const sessionStorage = new MemoryStorage();
		const clients: FakeMqttClient[] = [];
		const observedStatuses: string[] = [];
		const session = new RestaurantSession({
			createClient: (url, callbacks, credentials) => {
				const client = new FakeMqttClient(url, callbacks, credentials);
				clients.push(client);
				return client;
			},
			onOrderStatus: (status) => observedStatuses.push(status.status)
		});

		session.start({ protocol: 'http:', hostname: 'localhost' }, localStorage, sessionStorage);
		const client = clients[0];
		expect(client.url).toBe('ws://localhost:9001/mqtt');
		expect(client.connect).toHaveBeenCalledOnce();

		client.callbacks.onConnectionChange('connected');
		await session.placeOrder(order);
		expect(client.published).toEqual([order]);
		expect(session.orders[0]).toMatchObject({
			orderId: order.orderId,
			status: 'sending'
		});

		client.callbacks.onOrderStatus({
			...order,
			status: 'queued',
			occurredAt: '2026-07-29T18:00:00Z'
		});
		expect(session.orders[0]).toMatchObject({
			orderId: order.orderId,
			status: 'queued'
		});
		expect(observedStatuses).toEqual(['queued']);

		await session.destroy();
		expect(client.disconnect).toHaveBeenCalledOnce();
	});

	it('marks an optimistic order as failed when transport publishing fails', async () => {
		const client = new FakeMqttClient('ws://localhost/mqtt', emptyCallbacks());
		client.publishError = new Error('offline');
		const session = new RestaurantSession({
			createClient: (_url, callbacks) => {
				client.callbacks = callbacks;
				return client;
			}
		});
		session.start(
			{ protocol: 'http:', hostname: 'localhost' },
			new MemoryStorage(),
			new MemoryStorage()
		);
		client.callbacks.onConnectionChange('connected');

		await expect(session.placeOrder(order)).rejects.toThrow('offline');
		expect(session.orders[0]).toMatchObject({
			orderId: order.orderId,
			status: 'send_failed',
			retryable: true
		});
	});
});

class FakeMqttClient implements RestaurantMqttPort {
	readonly url: string;
	readonly credentials?: BrokerCredentials;
	readonly published: OrderRequested[] = [];
	readonly connect = vi.fn();
	readonly disconnect = vi.fn(async () => {});
	callbacks: MqttClientCallbacks;
	publishError?: Error;

	constructor(url: string, callbacks: MqttClientCallbacks, credentials?: BrokerCredentials) {
		this.url = url;
		this.callbacks = callbacks;
		this.credentials = credentials;
	}

	async publishOrder(nextOrder: OrderRequested): Promise<void> {
		if (this.publishError) {
			throw this.publishError;
		}
		this.published.push(nextOrder);
	}
}

class MemoryStorage implements BrowserStorage {
	readonly #values = new Map<string, string>();

	getItem(key: string): string | null {
		return this.#values.get(key) ?? null;
	}

	setItem(key: string, value: string): void {
		this.#values.set(key, value);
	}

	removeItem(key: string): void {
		this.#values.delete(key);
	}
}

function emptyCallbacks(): MqttClientCallbacks {
	return {
		onConnectionChange: () => {},
		onOrderStatus: () => {},
		onTableSnapshot: () => {},
		onKitchenPressure: () => {},
		onError: () => {}
	};
}
