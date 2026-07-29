import mqtt, { type MqttClient } from 'mqtt';

import {
	KitchenPressureSnapshotSchema,
	OrderRequestedSchema,
	OrderStatusChangedSchema,
	TableSnapshotSchema,
	type KitchenPressureSnapshot,
	type OrderRequested,
	type OrderStatusChanged,
	type TableSnapshot
} from '$lib/generated/contracts';

const ORDER_REQUESTED_TOPIC = 'restaurant/v1/order/requested';
const ORDER_STATUS_CHANGED_TOPIC = 'restaurant/v1/order/status-changed';
const TABLE_SNAPSHOT_TOPIC_FILTER = 'restaurant/v1/table/+/snapshot';
const TABLE_SNAPSHOT_TOPIC = /^restaurant\/v1\/table\/([1-4])\/snapshot$/;
const KITCHEN_PRESSURE_TOPIC = 'restaurant/v1/kitchen/pressure';
const SUBSCRIPTION_TOPICS = [
	ORDER_STATUS_CHANGED_TOPIC,
	TABLE_SNAPSHOT_TOPIC_FILTER,
	KITCHEN_PRESSURE_TOPIC
];
const MQTT_QOS = 1 as const;
export const MQTT_URL_STORAGE_KEY = 'osensa.mqtt.websocket-url';

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'offline';

export interface MqttClientCallbacks {
	onConnectionChange: (state: ConnectionState) => void;
	onOrderStatus: (status: OrderStatusChanged) => void;
	onTableSnapshot: (snapshot: TableSnapshot) => void;
	onKitchenPressure: (snapshot: KitchenPressureSnapshot) => void;
	onError: (message: string) => void;
}

interface BrowserLocation {
	protocol: string;
	hostname: string;
}

interface BrowserStorage {
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
	removeItem(key: string): void;
}

export function resolveMqttUrl(location: BrowserLocation, configuredUrl?: string): string {
	const explicitUrl = configuredUrl?.trim();
	if (explicitUrl) {
		return explicitUrl;
	}

	const websocketProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
	const localPort =
		location.hostname === 'localhost' || location.hostname === '127.0.0.1' ? ':9001' : '';
	return `${websocketProtocol}//${location.hostname}${localPort}/mqtt`;
}

export function normalizeMqttUrl(value: string, pageProtocol?: string): string {
	const candidate = value.trim();
	if (!candidate) {
		throw new Error('Enter a Broker WebSocket URL.');
	}

	let url: URL;
	try {
		url = new URL(candidate);
	} catch {
		throw new Error('Enter a complete URL, for example wss://broker.example.com/mqtt.');
	}

	if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
		throw new Error('The Broker URL must use ws:// or wss://.');
	}
	if (!url.hostname) {
		throw new Error('The Broker URL must include a hostname.');
	}
	if (pageProtocol === 'https:' && url.protocol !== 'wss:') {
		throw new Error('An HTTPS page requires a secure wss:// Broker URL.');
	}
	if (url.hash) {
		throw new Error('Remove the #fragment from the Broker URL.');
	}

	return url.href;
}

export function readStoredMqttUrl(
	storage: BrowserStorage,
	pageProtocol?: string
): string | undefined {
	try {
		const storedUrl = storage.getItem(MQTT_URL_STORAGE_KEY);
		return storedUrl ? normalizeMqttUrl(storedUrl, pageProtocol) : undefined;
	} catch {
		return undefined;
	}
}

export function storeMqttUrl(
	storage: BrowserStorage,
	value: string,
	pageProtocol?: string
): string {
	const normalizedUrl = normalizeMqttUrl(value, pageProtocol);
	storage.setItem(MQTT_URL_STORAGE_KEY, normalizedUrl);
	return normalizedUrl;
}

export function clearStoredMqttUrl(storage: BrowserStorage): void {
	storage.removeItem(MQTT_URL_STORAGE_KEY);
}

export function decodeOrderStatusPayload(payload: Uint8Array): OrderStatusChanged | undefined {
	try {
		const decoded: unknown = JSON.parse(new TextDecoder().decode(payload));
		const result = OrderStatusChangedSchema.safeParse(decoded);
		return result.success ? result.data : undefined;
	} catch {
		return undefined;
	}
}

export function decodeTableSnapshotPayload(
	topic: string,
	payload: Uint8Array
): TableSnapshot | undefined {
	const topicMatch = TABLE_SNAPSHOT_TOPIC.exec(topic);
	if (!topicMatch) {
		return undefined;
	}

	try {
		const decoded: unknown = JSON.parse(new TextDecoder().decode(payload));
		const result = TableSnapshotSchema.safeParse(decoded);
		if (
			!result.success ||
			result.data.tableId !== Number(topicMatch[1]) ||
			result.data.orders.some((order) => order.tableId !== result.data.tableId)
		) {
			return undefined;
		}
		return result.data;
	} catch {
		return undefined;
	}
}

export function decodeKitchenPressurePayload(
	payload: Uint8Array
): KitchenPressureSnapshot | undefined {
	try {
		const decoded: unknown = JSON.parse(new TextDecoder().decode(payload));
		const result = KitchenPressureSnapshotSchema.safeParse(decoded);
		if (!result.success || result.data.queuedOrders > result.data.queueCapacity) {
			return undefined;
		}

		const workerIds = result.data.workers.map((worker) => worker.workerId);
		if (new Set(workerIds).size !== workerIds.length) {
			return undefined;
		}
		return result.data;
	} catch {
		return undefined;
	}
}

export class RestaurantMqttClient {
	readonly #url: string;
	readonly #callbacks: MqttClientCallbacks;
	#client?: MqttClient;
	#disconnecting = false;
	#state: ConnectionState = 'offline';

	constructor(url: string, callbacks: MqttClientCallbacks) {
		this.#url = url;
		this.#callbacks = callbacks;
	}

	connect(): void {
		if (this.#client) {
			return;
		}

		this.#disconnecting = false;
		this.#setState('connecting');

		const client = mqtt.connect(this.#url, {
			protocolVersion: 4,
			clean: true,
			clientId: `osensa-web-${crypto.randomUUID()}`,
			connectTimeout: 8_000,
			reconnectPeriod: 1_000,
			keepalive: 30,
			queueQoSZero: false
		});
		this.#client = client;

		client.on('connect', () => {
			void client
				.subscribeAsync(SUBSCRIPTION_TOPICS, {
					qos: MQTT_QOS
				})
				.then(() => {
					this.#setState('connected');
					console.info('mqtt_subscribed', {
						topics: SUBSCRIPTION_TOPICS,
						qos: MQTT_QOS
					});
				})
				.catch((error: unknown) => {
					this.#callbacks.onError(errorMessage('Could not subscribe to order updates', error));
				});
		});

		client.on('message', (topic, payload) => {
			if (topic === ORDER_STATUS_CHANGED_TOPIC) {
				const status = decodeOrderStatusPayload(payload);
				if (!status) {
					console.warn('mqtt_status_rejected', { topic });
					this.#callbacks.onError('An invalid order update was ignored.');
					return;
				}
				this.#callbacks.onOrderStatus(status);
				return;
			}

			if (topic === KITCHEN_PRESSURE_TOPIC) {
				const pressure = decodeKitchenPressurePayload(payload);
				if (!pressure) {
					console.warn('mqtt_pressure_rejected', { topic });
					this.#callbacks.onError('An invalid kitchen pressure update was ignored.');
					return;
				}
				this.#callbacks.onKitchenPressure(pressure);
				return;
			}

			if (!TABLE_SNAPSHOT_TOPIC.test(topic)) {
				return;
			}

			const snapshot = decodeTableSnapshotPayload(topic, payload);
			if (!snapshot) {
				console.warn('mqtt_snapshot_rejected', { topic });
				this.#callbacks.onError('An invalid table snapshot was ignored.');
				return;
			}
			this.#callbacks.onTableSnapshot(snapshot);
		});

		client.on('reconnect', () => this.#setState('reconnecting'));
		client.on('offline', () => this.#setState('reconnecting'));
		client.on('close', () => {
			if (!this.#disconnecting) {
				this.#setState('offline');
			}
		});
		client.on('error', (error) => {
			console.error('mqtt_connection_error', { message: error.message });
			this.#callbacks.onError('The restaurant connection was interrupted.');
		});
	}

	async publishOrder(order: OrderRequested): Promise<void> {
		const validatedOrder = OrderRequestedSchema.parse(order);
		const client = this.#client;
		if (!client?.connected || this.#state !== 'connected') {
			throw new Error('MQTT client is not ready');
		}

		await client.publishAsync(ORDER_REQUESTED_TOPIC, JSON.stringify(validatedOrder), {
			qos: MQTT_QOS,
			retain: false
		});
		console.info('order_published', {
			orderId: validatedOrder.orderId,
			tableId: validatedOrder.tableId
		});
	}

	async disconnect(): Promise<void> {
		const client = this.#client;
		if (!client) {
			return;
		}

		this.#disconnecting = true;
		this.#client = undefined;
		if (client.connected) {
			try {
				await client.unsubscribeAsync(SUBSCRIPTION_TOPICS);
			} catch (error) {
				console.warn('mqtt_unsubscribe_failed', {
					message: error instanceof Error ? error.message : 'Unknown unsubscribe error'
				});
			}
		}
		await client.endAsync();
		this.#setState('offline');
	}

	#setState(state: ConnectionState): void {
		if (this.#state === state) {
			return;
		}
		this.#state = state;
		this.#callbacks.onConnectionChange(state);
	}
}

function errorMessage(context: string, error: unknown): string {
	return error instanceof Error && error.message ? `${context}: ${error.message}` : context;
}
