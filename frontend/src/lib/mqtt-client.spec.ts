import { describe, expect, it } from 'vitest';

import {
	clearSessionMqttCredentials,
	clearStoredMqttUrl,
	decodeKitchenPressurePayload,
	decodeOrderStatusPayload,
	decodeTableSnapshotPayload,
	MQTT_URL_STORAGE_KEY,
	normalizeMqttCredentials,
	normalizeMqttUrl,
	orderRequestedTopic,
	readSessionMqttCredentials,
	readStoredMqttUrl,
	resolveMqttUrl,
	storeSessionMqttCredentials,
	storeMqttUrl
} from '$lib/mqtt-client';

const encoder = new TextEncoder();

describe('MQTT browser boundary', () => {
	it.each([
		[{ protocol: 'http:', hostname: 'localhost' }, undefined, 'ws://localhost:9001/mqtt'],
		[{ protocol: 'http:', hostname: '127.0.0.1' }, undefined, 'ws://127.0.0.1:9001/mqtt'],
		[
			{ protocol: 'https:', hostname: 'restaurant.example.com' },
			undefined,
			'wss://restaurant.example.com/mqtt'
		],
		[
			{ protocol: 'https:', hostname: 'restaurant.example.com' },
			'wss://broker.example.com/mqtt',
			'wss://broker.example.com/mqtt'
		]
	])('resolves a deployable broker URL', (location, configured, expected) => {
		expect(resolveMqttUrl(location, configured)).toBe(expected);
	});

	it.each([
		[' wss://broker.example.com/mqtt ', 'https:', 'wss://broker.example.com/mqtt'],
		['ws://10.0.0.4:9001/mqtt', 'http:', 'ws://10.0.0.4:9001/mqtt']
	])('normalizes a valid Broker URL', (value, pageProtocol, expected) => {
		expect(normalizeMqttUrl(value, pageProtocol)).toBe(expected);
	});

	it.each([
		['', 'http:', 'Enter a Broker WebSocket URL.'],
		['broker.example.com/mqtt', 'https:', 'Enter a complete URL'],
		['https://broker.example.com/mqtt', 'https:', 'must use ws:// or wss://'],
		['ws://broker.example.com/mqtt', 'https:', 'requires a secure wss://'],
		['wss://broker.example.com/mqtt#ignored', 'https:', 'Remove the #fragment']
	])('rejects an unusable Broker URL', (value, pageProtocol, expectedMessage) => {
		expect(() => normalizeMqttUrl(value, pageProtocol)).toThrow(expectedMessage);
	});

	it('reads a valid persisted Broker override and ignores a stale invalid value', () => {
		const validStorage = {
			getItem: (key: string) =>
				key === MQTT_URL_STORAGE_KEY ? 'wss://broker.example.com/mqtt' : null,
			setItem: () => undefined,
			removeItem: () => undefined
		};
		const invalidStorage = {
			...validStorage,
			getItem: () => 'http://broker.example.com/mqtt'
		};

		expect(readStoredMqttUrl(validStorage, 'https:')).toBe('wss://broker.example.com/mqtt');
		expect(readStoredMqttUrl(invalidStorage, 'https:')).toBeUndefined();
	});

	it('persists and clears a normalized Broker override', () => {
		const values = new Map<string, string>();
		const storage = {
			getItem: (key: string) => values.get(key) ?? null,
			setItem: (key: string, value: string) => values.set(key, value),
			removeItem: (key: string) => values.delete(key)
		};

		expect(storeMqttUrl(storage, ' wss://broker.example.com/mqtt ', 'https:')).toBe(
			'wss://broker.example.com/mqtt'
		);
		expect(readStoredMqttUrl(storage, 'https:')).toBe('wss://broker.example.com/mqtt');

		clearStoredMqttUrl(storage);
		expect(readStoredMqttUrl(storage, 'https:')).toBeUndefined();
	});

	it('stores Broker credentials for the current browser session', () => {
		const values = new Map<string, string>();
		const storage = {
			getItem: (key: string) => values.get(key) ?? null,
			setItem: (key: string, value: string) => values.set(key, value),
			removeItem: (key: string) => values.delete(key)
		};

		storeSessionMqttCredentials(storage, {
			username: ' restaurant-console ',
			password: 'demo-secret'
		});
		expect(readSessionMqttCredentials(storage)).toEqual({
			username: 'restaurant-console',
			password: 'demo-secret'
		});

		clearSessionMqttCredentials(storage);
		expect(readSessionMqttCredentials(storage)).toBeUndefined();
	});

	it('requires a complete username and password pair', () => {
		expect(normalizeMqttCredentials('', '')).toBeUndefined();
		expect(() => normalizeMqttCredentials('restaurant-console', '')).toThrow(
			'Enter both the Broker username and password.'
		);
		expect(() => normalizeMqttCredentials('', 'demo-secret')).toThrow(
			'Enter both the Broker username and password.'
		);
	});

	it.each([
		[1, 'restaurant/v1/table/1/order/requested'],
		[4, 'restaurant/v1/table/4/order/requested']
	])('scopes order publishes to table %i', (tableId, expectedTopic) => {
		expect(orderRequestedTopic(tableId)).toBe(expectedTopic);
	});

	it('decodes and validates a status update', () => {
		const status = {
			schemaVersion: 1,
			orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
			tableId: 2,
			foodName: 'Chicken sandwich',
			status: 'food_ready',
			occurredAt: '2026-07-29T18:00:03Z',
			readyAt: '2026-07-29T18:00:03Z'
		};

		expect(
			decodeOrderStatusPayload(
				'restaurant/v1/table/2/order/status-changed',
				encoder.encode(JSON.stringify(status))
			)
		).toEqual(status);
		expect(
			decodeOrderStatusPayload(
				'restaurant/v1/table/4/order/status-changed',
				encoder.encode(JSON.stringify(status))
			)
		).toBeUndefined();
	});

	it.each([
		encoder.encode('not-json'),
		encoder.encode(
			JSON.stringify({
				schemaVersion: 1,
				orderId: 'not-a-uuid',
				status: 'food_ready'
			})
		),
		encoder.encode(
			JSON.stringify({
				schemaVersion: 1,
				orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
				tableId: 2,
				foodName: 'Chicken sandwich',
				status: 'unknown',
				occurredAt: '2026-07-29T18:00:03Z'
			})
		)
	])('rejects an invalid status payload without throwing', (payload) => {
		expect(
			decodeOrderStatusPayload('restaurant/v1/table/2/order/status-changed', payload)
		).toBeUndefined();
	});

	it('decodes a table snapshot only when topic and payload tables agree', () => {
		const snapshot = {
			schemaVersion: 1,
			serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
			tableId: 2,
			revision: 3,
			generatedAt: '2026-07-29T18:00:04Z',
			orders: [
				{
					schemaVersion: 1,
					orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
					tableId: 2,
					foodName: 'Chicken sandwich',
					status: 'food_ready',
					occurredAt: '2026-07-29T18:00:03Z',
					readyAt: '2026-07-29T18:00:03Z'
				}
			]
		};
		const payload = encoder.encode(JSON.stringify(snapshot));

		expect(decodeTableSnapshotPayload('restaurant/v1/table/2/snapshot', payload)).toEqual(snapshot);
		expect(decodeTableSnapshotPayload('restaurant/v1/table/3/snapshot', payload)).toBeUndefined();
	});

	it('rejects a snapshot containing an order from another table', () => {
		const payload = encoder.encode(
			JSON.stringify({
				schemaVersion: 1,
				serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
				tableId: 2,
				revision: 1,
				generatedAt: '2026-07-29T18:00:04Z',
				orders: [
					{
						schemaVersion: 1,
						orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
						tableId: 3,
						foodName: 'Wrong table soup',
						status: 'queued',
						occurredAt: '2026-07-29T18:00:03Z'
					}
				]
			})
		);

		expect(decodeTableSnapshotPayload('restaurant/v1/table/2/snapshot', payload)).toBeUndefined();
	});

	it('decodes valid queue and worker pressure', () => {
		const pressure = {
			schemaVersion: 1,
			serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
			revision: 7,
			generatedAt: '2026-07-29T18:00:04Z',
			queuedOrders: 3,
			queueCapacity: 256,
			workers: [
				{ workerId: 1, status: 'idle' },
				{
					workerId: 2,
					status: 'processing',
					orderId: '3b11d31c-7d34-4dda-91e5-d64721a50463',
					tableId: 2,
					foodName: 'Chicken sandwich'
				}
			]
		};

		expect(decodeKitchenPressurePayload(encoder.encode(JSON.stringify(pressure)))).toEqual(
			pressure
		);
	});

	it.each([
		{ queuedOrders: 257 },
		{
			workers: [
				{ workerId: 1, status: 'idle' },
				{ workerId: 1, status: 'idle' }
			]
		}
	])('rejects inconsistent kitchen pressure: %o', (override) => {
		const pressure = {
			schemaVersion: 1,
			serviceInstanceId: '1058bf2e-0ef0-4ae6-a3bc-267f1abbbd54',
			revision: 7,
			generatedAt: '2026-07-29T18:00:04Z',
			queuedOrders: 3,
			queueCapacity: 256,
			workers: [{ workerId: 1, status: 'idle' }],
			...override
		};

		expect(decodeKitchenPressurePayload(encoder.encode(JSON.stringify(pressure)))).toBeUndefined();
	});
});
