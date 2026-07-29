import { describe, expect, it } from 'vitest';

import {
	decodeKitchenPressurePayload,
	decodeOrderStatusPayload,
	decodeTableSnapshotPayload,
	resolveMqttUrl
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

		expect(decodeOrderStatusPayload(encoder.encode(JSON.stringify(status)))).toEqual(status);
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
		expect(decodeOrderStatusPayload(payload)).toBeUndefined();
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
