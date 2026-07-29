import { describe, expect, it } from 'vitest';

import { decodeOrderStatusPayload, resolveMqttUrl } from '$lib/mqtt-client';

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
});
