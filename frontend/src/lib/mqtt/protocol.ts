import {
	KitchenPressureSnapshotSchema,
	OrderStatusChangedSchema,
	TableSnapshotSchema,
	type KitchenPressureSnapshot,
	type OrderStatusChanged,
	type TableSnapshot
} from '$lib/generated/contracts';

const ORDER_STATUS_CHANGED_TOPIC = /^restaurant\/v1\/table\/([1-4])\/order\/status-changed$/;
const TABLE_SNAPSHOT_TOPIC = /^restaurant\/v1\/table\/([1-4])\/snapshot$/;

export const ORDER_STATUS_CHANGED_TOPIC_FILTER = 'restaurant/v1/table/+/order/status-changed';
export const TABLE_SNAPSHOT_TOPIC_FILTER = 'restaurant/v1/table/+/snapshot';
export const KITCHEN_PRESSURE_TOPIC = 'restaurant/v1/kitchen/pressure';
export const SUBSCRIPTION_TOPICS = [
	ORDER_STATUS_CHANGED_TOPIC_FILTER,
	TABLE_SNAPSHOT_TOPIC_FILTER,
	KITCHEN_PRESSURE_TOPIC
];
export const MQTT_QOS = 1 as const;

export function isOrderStatusTopic(topic: string): boolean {
	return ORDER_STATUS_CHANGED_TOPIC.test(topic);
}

export function isTableSnapshotTopic(topic: string): boolean {
	return TABLE_SNAPSHOT_TOPIC.test(topic);
}

export function orderRequestedTopic(tableId: number): string {
	if (![1, 2, 3, 4].includes(tableId)) {
		throw new Error('tableId must be between 1 and 4');
	}
	return `restaurant/v1/table/${tableId}/order/requested`;
}

export function decodeOrderStatusPayload(
	topic: string,
	payload: Uint8Array
): OrderStatusChanged | undefined {
	const topicMatch = ORDER_STATUS_CHANGED_TOPIC.exec(topic);
	if (!topicMatch) {
		return undefined;
	}

	try {
		const decoded: unknown = JSON.parse(new TextDecoder().decode(payload));
		const result = OrderStatusChangedSchema.safeParse(decoded);
		return result.success && result.data.tableId === Number(topicMatch[1])
			? result.data
			: undefined;
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
