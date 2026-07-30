import mqtt, { type MqttClient } from 'mqtt';

import { OrderRequestedSchema, type OrderRequested } from '$lib/generated/contracts';
import {
	decodeKitchenPressurePayload,
	decodeOrderStatusPayload,
	decodeTableSnapshotPayload,
	isOrderStatusTopic,
	isTableSnapshotTopic,
	KITCHEN_PRESSURE_TOPIC,
	MQTT_QOS,
	orderRequestedTopic,
	SUBSCRIPTION_TOPICS
} from '$lib/mqtt/protocol';
import type { BrokerCredentials } from '$lib/mqtt/settings';
import type {
	KitchenPressureSnapshot,
	OrderStatusChanged,
	TableSnapshot
} from '$lib/generated/contracts';

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'offline';

export interface MqttClientCallbacks {
	onConnectionChange: (state: ConnectionState) => void;
	onOrderStatus: (status: OrderStatusChanged) => void;
	onTableSnapshot: (snapshot: TableSnapshot) => void;
	onKitchenPressure: (snapshot: KitchenPressureSnapshot) => void;
	onError: (message: string) => void;
}

export class RestaurantMqttClient {
	readonly #url: string;
	readonly #callbacks: MqttClientCallbacks;
	readonly #credentials?: BrokerCredentials;
	#client?: MqttClient;
	#disconnecting = false;
	#state: ConnectionState = 'offline';

	constructor(url: string, callbacks: MqttClientCallbacks, credentials?: BrokerCredentials) {
		this.#url = url;
		this.#callbacks = callbacks;
		this.#credentials = credentials;
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
			queueQoSZero: false,
			...this.#credentials
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
			if (isOrderStatusTopic(topic)) {
				const status = decodeOrderStatusPayload(topic, payload);
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

			if (!isTableSnapshotTopic(topic)) {
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

		await client.publishAsync(
			orderRequestedTopic(validatedOrder.tableId),
			JSON.stringify(validatedOrder),
			{
				qos: MQTT_QOS,
				retain: false
			}
		);
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
