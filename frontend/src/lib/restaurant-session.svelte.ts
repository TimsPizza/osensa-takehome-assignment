import { SvelteMap, SvelteSet } from 'svelte/reactivity';

import type {
	KitchenPressureSnapshot,
	OrderRequested,
	OrderStatusChanged
} from '$lib/generated/contracts';
import {
	clearSessionMqttCredentials,
	clearStoredMqttUrl,
	readSessionMqttCredentials,
	readStoredMqttUrl,
	RestaurantMqttClient,
	resolveMqttUrl,
	storeSessionMqttCredentials,
	storeMqttUrl,
	type BrokerConnectionSettings,
	type BrokerCredentials,
	type BrowserLocation,
	type BrowserStorage,
	type ConnectionState,
	type MqttClientCallbacks
} from '$lib/mqtt-client';
import {
	addSendingOrder,
	applyOrderStatus,
	markSendFailed,
	replaceTableFromSnapshot,
	shouldApplyTableSnapshot,
	type OrderView,
	type TableId,
	type TableSnapshotCursor
} from '$lib/order-state';
import { createRandomOrders } from '$lib/random-orders';

interface RestaurantSessionObservers {
	onOrderStatus?: (status: OrderStatusChanged) => void;
	onKitchenPressure?: (snapshot: KitchenPressureSnapshot) => void;
}

export interface RestaurantMqttPort {
	connect(): void;
	publishOrder(order: OrderRequested): Promise<void>;
	disconnect(): Promise<void>;
}

export type RestaurantMqttFactory = (
	url: string,
	callbacks: MqttClientCallbacks,
	credentials?: BrokerCredentials
) => RestaurantMqttPort;

interface RestaurantSessionOptions extends RestaurantSessionObservers {
	createClient?: RestaurantMqttFactory;
}

export class RestaurantSession {
	orders = $state<OrderView[]>([]);
	kitchenPressure = $state<KitchenPressureSnapshot>();
	connectionState = $state<ConnectionState>('connecting');
	connectionError = $state('');
	activeBrokerUrl = $state('');
	activeBrokerCredentials = $state<BrokerCredentials>();
	defaultBrokerUrl = $state('');
	pageProtocol = $state('');
	readonly bulkOrderingTables = new SvelteSet<TableId>();

	readonly #observers: RestaurantSessionObservers;
	readonly #createClient: RestaurantMqttFactory;
	readonly #snapshotCursors = new SvelteMap<TableId, TableSnapshotCursor>();
	#mqttClient?: RestaurantMqttPort;
	#localStorage?: BrowserStorage;
	#sessionStorage?: BrowserStorage;
	#connectionGeneration = 0;

	constructor(options: RestaurantSessionOptions = {}) {
		const { createClient, ...observers } = options;
		this.#observers = observers;
		this.#createClient =
			createClient ??
			((url, callbacks, credentials) => new RestaurantMqttClient(url, callbacks, credentials));
	}

	get connected(): boolean {
		return this.connectionState === 'connected';
	}

	get connectionCopy(): string {
		switch (this.connectionState) {
			case 'connected':
				return 'Kitchen online';
			case 'connecting':
				return 'Connecting';
			case 'reconnecting':
				return 'Reconnecting';
			case 'offline':
				return 'Kitchen offline';
		}
	}

	start(
		location: BrowserLocation,
		localStorage: BrowserStorage,
		sessionStorage: BrowserStorage,
		configuredUrl?: string
	): void {
		this.#localStorage = localStorage;
		this.#sessionStorage = sessionStorage;
		this.pageProtocol = location.protocol;
		this.defaultBrokerUrl = resolveMqttUrl(location, configuredUrl);
		this.activeBrokerUrl =
			readStoredMqttUrl(localStorage, location.protocol) ?? this.defaultBrokerUrl;
		this.activeBrokerCredentials = readSessionMqttCredentials(sessionStorage);
		this.#mqttClient = this.#createMqttClient(this.activeBrokerUrl, this.activeBrokerCredentials);
		this.#mqttClient.connect();
	}

	async saveBrokerSettings(settings: BrokerConnectionSettings): Promise<void> {
		const localStorage = this.#requireLocalStorage();
		const sessionStorage = this.#requireSessionStorage();
		const storedUrl = storeMqttUrl(localStorage, settings.url, this.pageProtocol);
		storeSessionMqttCredentials(sessionStorage, settings.credentials);
		await this.#reconnectToBroker({
			url: storedUrl,
			credentials: settings.credentials
		});
	}

	async resetBrokerSettings(): Promise<void> {
		clearStoredMqttUrl(this.#requireLocalStorage());
		clearSessionMqttCredentials(this.#requireSessionStorage());
		await this.#reconnectToBroker({ url: this.defaultBrokerUrl });
	}

	async publishOrder(order: OrderRequested): Promise<void> {
		if (!this.#mqttClient || !this.connected) {
			throw new Error('MQTT client is not ready');
		}
		await this.#mqttClient.publishOrder(order);
	}

	async placeOrder(order: OrderRequested): Promise<void> {
		this.orders = addSendingOrder(this.orders, {
			...order,
			tableId: order.tableId as TableId
		});

		try {
			await this.publishOrder(order);
		} catch (error) {
			const message = 'The order could not be sent. Check the kitchen connection and retry.';
			this.orders = markSendFailed(this.orders, order.orderId, message);
			throw error;
		}
	}

	async placeRandomOrders(tableId: TableId): Promise<void> {
		if (!this.connected || this.bulkOrderingTables.has(tableId)) {
			return;
		}

		this.bulkOrderingTables.add(tableId);
		const batch = createRandomOrders(tableId);
		this.orders = batch.reduceRight(
			(currentOrders, order) => addSendingOrder(currentOrders, order),
			this.orders
		);

		try {
			const results = await Promise.allSettled(batch.map((order) => this.publishOrder(order)));
			for (const [index, result] of results.entries()) {
				if (result.status === 'rejected') {
					this.orders = markSendFailed(
						this.orders,
						batch[index].orderId,
						'The order could not be sent. Check the kitchen connection and retry.'
					);
				}
			}
		} finally {
			this.bulkOrderingTables.delete(tableId);
		}
	}

	ordersForTable(tableId: TableId): OrderView[] {
		return this.orders.filter((order) => order.tableId === tableId);
	}

	async destroy(): Promise<void> {
		this.#connectionGeneration += 1;
		const client = this.#mqttClient;
		this.#mqttClient = undefined;
		await client?.disconnect();
	}

	#createMqttClient(url: string, credentials?: BrokerCredentials): RestaurantMqttPort {
		const callbacks: MqttClientCallbacks = {
			onConnectionChange: (state) => {
				this.connectionState = state;
				if (state === 'connected') {
					this.connectionError = '';
				}
			},
			onOrderStatus: (status) => {
				this.orders = applyOrderStatus(this.orders, status);
				this.#observers.onOrderStatus?.(status);
			},
			onTableSnapshot: (snapshot) => {
				const tableId = snapshot.tableId as TableId;
				if (!shouldApplyTableSnapshot(snapshot, this.#snapshotCursors.get(tableId))) {
					return;
				}
				this.orders = replaceTableFromSnapshot(this.orders, snapshot);
				this.#snapshotCursors.set(tableId, {
					serviceInstanceId: snapshot.serviceInstanceId,
					revision: snapshot.revision
				});
			},
			onKitchenPressure: (snapshot) => {
				if (
					!this.kitchenPressure ||
					this.kitchenPressure.serviceInstanceId !== snapshot.serviceInstanceId ||
					snapshot.revision > this.kitchenPressure.revision
				) {
					this.kitchenPressure = snapshot;
					this.#observers.onKitchenPressure?.(snapshot);
				}
			},
			onError: (message) => {
				this.connectionError = message;
			}
		};
		return this.#createClient(url, callbacks, credentials);
	}

	async #reconnectToBroker(settings: BrokerConnectionSettings): Promise<void> {
		const generation = ++this.#connectionGeneration;
		const previousClient = this.#mqttClient;
		this.#mqttClient = undefined;
		this.connectionState = 'connecting';
		this.connectionError = '';
		this.kitchenPressure = undefined;

		await previousClient?.disconnect();
		if (generation !== this.#connectionGeneration) {
			return;
		}

		this.activeBrokerUrl = settings.url;
		this.activeBrokerCredentials = settings.credentials;
		const nextClient = this.#createMqttClient(settings.url, settings.credentials);
		this.#mqttClient = nextClient;
		nextClient.connect();
	}

	#requireLocalStorage(): BrowserStorage {
		if (!this.#localStorage) {
			throw new Error('Restaurant session has not started.');
		}
		return this.#localStorage;
	}

	#requireSessionStorage(): BrowserStorage {
		if (!this.#sessionStorage) {
			throw new Error('Restaurant session has not started.');
		}
		return this.#sessionStorage;
	}
}
