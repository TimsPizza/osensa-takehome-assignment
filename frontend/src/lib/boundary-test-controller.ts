import { get, writable, type Readable } from 'svelte/store';

import type {
	KitchenPressureSnapshot,
	OrderRequested,
	OrderStatusChanged
} from '$lib/generated/contracts';
import { createRandomOrders } from '$lib/random-orders';
import type { TableId } from '$lib/order-state';

type PublishOrder = (order: OrderRequested) => Promise<void>;
type RunStatus = 'idle' | 'publishing' | 'observing' | 'completed' | 'failed';
type SaturationStatus = 'idle' | 'running' | 'completed' | 'stopped' | 'failed';
type OverloadStatus = 'idle' | 'running' | 'observing' | 'passed' | 'stopped' | 'failed';

export interface BurstRun {
	status: RunStatus;
	requested: number;
	published: number;
	publishFailed: number;
	accepted: number;
	overloaded: number;
	terminal: number;
	startedAt?: number;
	finishedAt?: number;
	error?: string;
}

export interface IdempotencyRun {
	status: RunStatus | 'passed';
	orderId?: string;
	published: number;
	rawEvents: number;
	uniqueStatuses: OrderStatusChanged['status'][];
	startedAt?: number;
	finishedAt?: number;
	error?: string;
}

export interface SaturationRun {
	status: SaturationStatus;
	durationSeconds: number;
	targetPercent: number;
	maxOrdersPerSecond: number;
	published: number;
	publishFailed: number;
	accepted: number;
	overloaded: number;
	terminal: number;
	startedAt?: number;
	finishedAt?: number;
	error?: string;
}

export interface SaturationOptions {
	durationSeconds: number;
	targetPercent: number;
	maxOrdersPerSecond: number;
}

export interface OverloadRun {
	status: OverloadStatus;
	durationSeconds: number;
	ordersPerSecond: number;
	observationSeconds: number;
	published: number;
	publishFailed: number;
	accepted: number;
	overloaded: number;
	terminal: number;
	ghosts: number;
	ghostOrderIds: string[];
	startedAt?: number;
	trafficStoppedAt?: number;
	finishedAt?: number;
	error?: string;
}

export interface OverloadOptions {
	durationSeconds: number;
	ordersPerSecond: number;
	observationSeconds: number;
}

interface ControllerOptions {
	now?: () => number;
	wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
	createId?: () => string;
	random?: () => number;
}

const EMPTY_BURST: BurstRun = {
	status: 'idle',
	requested: 0,
	published: 0,
	publishFailed: 0,
	accepted: 0,
	overloaded: 0,
	terminal: 0
};

const EMPTY_IDEMPOTENCY: IdempotencyRun = {
	status: 'idle',
	published: 0,
	rawEvents: 0,
	uniqueStatuses: []
};

const EMPTY_SATURATION: SaturationRun = {
	status: 'idle',
	durationSeconds: 20,
	targetPercent: 95,
	maxOrdersPerSecond: 40,
	published: 0,
	publishFailed: 0,
	accepted: 0,
	overloaded: 0,
	terminal: 0
};

const EMPTY_OVERLOAD: OverloadRun = {
	status: 'idle',
	durationSeconds: 10,
	ordersPerSecond: 100,
	observationSeconds: 10,
	published: 0,
	publishFailed: 0,
	accepted: 0,
	overloaded: 0,
	terminal: 0,
	ghosts: 0,
	ghostOrderIds: []
};

export class BoundaryTestController {
	readonly burst = writable<BurstRun>({ ...EMPTY_BURST });
	readonly idempotency = writable<IdempotencyRun>({ ...EMPTY_IDEMPOTENCY });
	readonly saturation = writable<SaturationRun>({ ...EMPTY_SATURATION });
	readonly overload = writable<OverloadRun>({ ...EMPTY_OVERLOAD });
	readonly pressure: Readable<KitchenPressureSnapshot | undefined>;

	readonly #publishOrder: PublishOrder;
	readonly #now: () => number;
	readonly #wait: (milliseconds: number, signal: AbortSignal) => Promise<void>;
	readonly #createId: () => string;
	readonly #random: () => number;
	readonly #pressure = writable<KitchenPressureSnapshot>();
	readonly #burstOrderIds = new Set<string>();
	readonly #burstAccepted = new Set<string>();
	readonly #burstOverloaded = new Set<string>();
	readonly #burstTerminal = new Set<string>();
	readonly #saturationOrderIds = new Set<string>();
	readonly #saturationAccepted = new Set<string>();
	readonly #saturationOverloaded = new Set<string>();
	readonly #overloadOrderIds = new Set<string>();
	readonly #overloadAccepted = new Set<string>();
	readonly #overloadRejected = new Set<string>();
	readonly #overloadTerminal = new Set<string>();
	readonly #overloadGhosts = new Set<string>();
	readonly #idempotencyStatuses = new Set<OrderStatusChanged['status']>();
	#idempotencyOrderId?: string;
	#idempotencyTimeout?: ReturnType<typeof setTimeout>;
	#burstTimeout?: ReturnType<typeof setTimeout>;
	#saturationAbort?: AbortController;
	#overloadAbort?: AbortController;

	constructor(publishOrder: PublishOrder, options: ControllerOptions = {}) {
		this.#publishOrder = publishOrder;
		this.#now = options.now ?? Date.now;
		this.#wait = options.wait ?? waitFor;
		this.#createId = options.createId ?? (() => crypto.randomUUID());
		this.#random = options.random ?? Math.random;
		this.pressure = { subscribe: this.#pressure.subscribe };
	}

	handlePressure(snapshot: KitchenPressureSnapshot): void {
		this.#pressure.set(snapshot);
		for (const worker of snapshot.workers) {
			if (worker.status === 'processing' && this.#overloadRejected.has(worker.orderId)) {
				this.#recordOverloadGhost(worker.orderId, 'A rejected order appeared in worker telemetry.');
			}
		}
	}

	handleOrderStatus(update: OrderStatusChanged): void {
		this.#handleBurstStatus(update);
		this.#handleIdempotencyStatus(update);
		this.#handleSaturationStatus(update);
		this.#handleOverloadStatus(update);
	}

	async runRandomBurst(count: number): Promise<void> {
		if (!Number.isInteger(count) || count < 1 || count > 500) {
			throw new RangeError('count must be an integer between 1 and 500');
		}

		this.#clearBurst();
		const startedAt = this.#now();
		const orders = this.#createOrders(count);
		for (const order of orders) {
			this.#burstOrderIds.add(order.orderId);
		}
		this.burst.set({
			...EMPTY_BURST,
			status: 'publishing',
			requested: count,
			startedAt
		});

		const results = await Promise.allSettled(orders.map((order) => this.#publishOrder(order)));
		const published = results.filter((result) => result.status === 'fulfilled').length;
		const publishFailed = count - published;
		for (const [index, result] of results.entries()) {
			if (result.status === 'rejected') {
				this.#burstOrderIds.delete(orders[index].orderId);
			}
		}

		this.burst.update((run) => ({
			...run,
			status: published === 0 ? 'failed' : 'observing',
			published,
			publishFailed,
			...(published === 0
				? {
						finishedAt: this.#now(),
						error: 'No orders reached the broker.'
					}
				: {})
		}));
		this.#completeBurstIfReady();

		if (published > 0 && get(this.burst).status === 'observing') {
			this.#burstTimeout = setTimeout(() => {
				this.burst.update((run) =>
					run.status === 'observing'
						? {
								...run,
								status: 'failed',
								finishedAt: this.#now(),
								error: 'Timed out waiting for terminal order states.'
							}
						: run
				);
			}, 30_000);
		}
	}

	async runIdempotency(): Promise<void> {
		this.#clearIdempotency();
		const order = this.#createOrders(1)[0];
		this.#idempotencyOrderId = order.orderId;
		this.idempotency.set({
			...EMPTY_IDEMPOTENCY,
			status: 'publishing',
			orderId: order.orderId,
			startedAt: this.#now()
		});

		const results = await Promise.allSettled([
			this.#publishOrder(order),
			this.#publishOrder(order),
			this.#publishOrder(order)
		]);
		const published = results.filter((result) => result.status === 'fulfilled').length;
		this.idempotency.update((run) => ({
			...run,
			status: published === 3 ? 'observing' : 'failed',
			published,
			...(published === 3
				? {}
				: {
						finishedAt: this.#now(),
						error: `Only ${published} of 3 duplicate publishes reached the broker.`
					})
		}));

		if (published === 3) {
			this.#completeIdempotencyIfReady();
		}
		if (published === 3 && get(this.idempotency).status === 'observing') {
			this.#idempotencyTimeout = setTimeout(() => {
				this.idempotency.update((run) =>
					run.status === 'observing'
						? {
								...run,
								status: 'failed',
								finishedAt: this.#now(),
								error: 'Timed out waiting for the duplicate order lifecycle.'
							}
						: run
				);
			}, 15_000);
		}
	}

	async startSaturation(options: SaturationOptions): Promise<void> {
		validateSaturationOptions(options);
		this.stopSaturation();
		this.#saturationOrderIds.clear();
		this.#saturationAccepted.clear();
		this.#saturationOverloaded.clear();
		const abort = new AbortController();
		this.#saturationAbort = abort;
		const startedAt = this.#now();
		this.saturation.set({
			...EMPTY_SATURATION,
			...options,
			status: 'running',
			startedAt
		});

		try {
			while (!abort.signal.aborted && this.#now() - startedAt < options.durationSeconds * 1_000) {
				const pressure = get(this.#pressure);
				if (!pressure) {
					await this.#wait(250, abort.signal);
					continue;
				}

				const targetDepth = Math.ceil(pressure.queueCapacity * (options.targetPercent / 100));
				const deficit = Math.max(0, targetDepth - pressure.queuedOrders);
				const perTickLimit = Math.max(1, Math.ceil(options.maxOrdersPerSecond / 4));
				const orderCount = Math.min(deficit, perTickLimit);

				if (orderCount > 0) {
					await this.#publishSaturationBatch(orderCount);
				}
				await this.#wait(250, abort.signal);
			}

			if (!abort.signal.aborted) {
				this.saturation.update((run) => ({
					...run,
					status: 'completed',
					finishedAt: this.#now()
				}));
			}
		} catch (error) {
			if (!abort.signal.aborted) {
				this.saturation.update((run) => ({
					...run,
					status: 'failed',
					finishedAt: this.#now(),
					error: error instanceof Error ? error.message : 'Saturation test failed.'
				}));
			}
		} finally {
			if (this.#saturationAbort === abort) {
				this.#saturationAbort = undefined;
			}
		}
	}

	stopSaturation(): void {
		const abort = this.#saturationAbort;
		if (!abort) {
			return;
		}
		abort.abort();
		this.#saturationAbort = undefined;
		this.saturation.update((run) => ({
			...run,
			status: 'stopped',
			finishedAt: this.#now()
		}));
	}

	async startOverload(options: OverloadOptions): Promise<void> {
		validateOverloadOptions(options);
		this.stopOverload();
		this.#clearOverload();
		const abort = new AbortController();
		this.#overloadAbort = abort;
		const startedAt = this.#now();
		const warmupOvershoot = Math.max(1, Math.ceil(options.ordersPerSecond / 4));
		let publishBudget = 0;
		this.overload.set({
			...EMPTY_OVERLOAD,
			...options,
			status: 'running',
			startedAt
		});

		try {
			const pressure = get(this.#pressure);
			if (pressure) {
				const warmupCount = Math.min(
					500,
					Math.max(
						warmupOvershoot,
						pressure.queueCapacity -
							pressure.queuedOrders +
							pressure.workers.length +
							warmupOvershoot
					)
				);
				await this.#publishOverloadBatch(warmupCount);
			}

			while (!abort.signal.aborted && this.#now() - startedAt < options.durationSeconds * 1_000) {
				publishBudget += options.ordersPerSecond / 4;
				const orderCount = Math.floor(publishBudget);
				publishBudget -= orderCount;
				if (orderCount > 0) {
					await this.#publishOverloadBatch(orderCount);
				}
				await this.#wait(250, abort.signal);
			}

			if (abort.signal.aborted) {
				return;
			}

			this.overload.update((run) => ({
				...run,
				status: 'observing',
				trafficStoppedAt: this.#now()
			}));
			await this.#wait(options.observationSeconds * 1_000, abort.signal);
			if (!abort.signal.aborted) {
				this.#finishOverloadObservation();
			}
		} catch (error) {
			if (!abort.signal.aborted) {
				this.overload.update((run) => ({
					...run,
					status: 'failed',
					finishedAt: this.#now(),
					error: error instanceof Error ? error.message : 'Overload test failed.'
				}));
			}
		} finally {
			if (this.#overloadAbort === abort) {
				this.#overloadAbort = undefined;
			}
		}
	}

	stopOverload(): void {
		const abort = this.#overloadAbort;
		if (!abort) {
			return;
		}
		abort.abort();
		this.#overloadAbort = undefined;
		this.overload.update((run) =>
			run.status === 'running' || run.status === 'observing'
				? {
						...run,
						status: 'stopped',
						finishedAt: this.#now()
					}
				: run
		);
	}

	destroy(): void {
		this.stopSaturation();
		this.stopOverload();
		this.#clearBurst();
		this.#clearIdempotency();
		this.#clearOverload();
	}

	#createOrders(count: number): OrderRequested[] {
		return Array.from({ length: count }, () => {
			const tableId = (Math.floor(this.#random() * 4) + 1) as TableId;
			return createRandomOrders(tableId, {
				count: 1,
				random: this.#random,
				createId: this.#createId
			})[0];
		});
	}

	async #publishSaturationBatch(count: number): Promise<void> {
		const orders = this.#createOrders(count);
		for (const order of orders) {
			this.#saturationOrderIds.add(order.orderId);
		}
		const results = await Promise.allSettled(orders.map((order) => this.#publishOrder(order)));
		const published = results.filter((result) => result.status === 'fulfilled').length;
		for (const [index, result] of results.entries()) {
			if (result.status === 'rejected') {
				this.#saturationOrderIds.delete(orders[index].orderId);
			}
		}
		this.saturation.update((run) => ({
			...run,
			published: run.published + published,
			publishFailed: run.publishFailed + (count - published)
		}));
	}

	async #publishOverloadBatch(count: number): Promise<void> {
		const orders = this.#createOrders(count);
		for (const order of orders) {
			this.#overloadOrderIds.add(order.orderId);
		}
		const results = await Promise.allSettled(orders.map((order) => this.#publishOrder(order)));
		const published = results.filter((result) => result.status === 'fulfilled').length;
		for (const [index, result] of results.entries()) {
			if (result.status === 'rejected') {
				this.#overloadOrderIds.delete(orders[index].orderId);
			}
		}
		this.overload.update((run) => ({
			...run,
			published: run.published + published,
			publishFailed: run.publishFailed + (count - published)
		}));
	}

	#handleBurstStatus(update: OrderStatusChanged): void {
		if (!this.#burstOrderIds.has(update.orderId)) {
			return;
		}
		if (update.status === 'queued') {
			this.#burstAccepted.add(update.orderId);
		}
		if (update.status === 'food_ready' || update.status === 'failed') {
			this.#burstTerminal.add(update.orderId);
		}
		if (update.status === 'failed' && update.code === 'service_overloaded') {
			this.#burstOverloaded.add(update.orderId);
		}
		this.burst.update((run) => ({
			...run,
			accepted: this.#burstAccepted.size,
			overloaded: this.#burstOverloaded.size,
			terminal: this.#burstTerminal.size
		}));
		this.#completeBurstIfReady();
	}

	#completeBurstIfReady(): void {
		const run = get(this.burst);
		if (
			(run.status === 'publishing' || run.status === 'observing') &&
			run.published > 0 &&
			this.#burstTerminal.size >= run.published
		) {
			if (this.#burstTimeout) clearTimeout(this.#burstTimeout);
			this.burst.update((current) => ({
				...current,
				status: 'completed',
				finishedAt: this.#now()
			}));
		}
	}

	#handleIdempotencyStatus(update: OrderStatusChanged): void {
		if (update.orderId !== this.#idempotencyOrderId) {
			return;
		}
		this.#idempotencyStatuses.add(update.status);
		this.idempotency.update((run) => ({
			...run,
			rawEvents: run.rawEvents + 1,
			uniqueStatuses: [...this.#idempotencyStatuses]
		}));

		this.#completeIdempotencyIfReady();
	}

	#completeIdempotencyIfReady(): void {
		const run = get(this.idempotency);
		const statuses = this.#idempotencyStatuses;
		const hasTerminal = statuses.has('food_ready') || statuses.has('failed');
		if (run.published !== 3 || !hasTerminal) {
			return;
		}
		if (this.#idempotencyTimeout) clearTimeout(this.#idempotencyTimeout);
		const passed = statuses.has('queued') && statuses.has('processing') && statuses.size === 3;
		this.idempotency.update((current) => ({
			...current,
			status: passed ? 'passed' : 'failed',
			finishedAt: this.#now(),
			...(passed ? {} : { error: 'Duplicate publishes produced an unexpected lifecycle.' })
		}));
	}

	#handleSaturationStatus(update: OrderStatusChanged): void {
		if (!this.#saturationOrderIds.has(update.orderId)) {
			return;
		}
		if (update.status === 'queued') {
			this.#saturationAccepted.add(update.orderId);
		}
		const terminal = update.status === 'food_ready' || update.status === 'failed';
		if (update.status === 'failed' && update.code === 'service_overloaded') {
			this.#saturationOverloaded.add(update.orderId);
		}
		this.saturation.update((run) => ({
			...run,
			accepted: this.#saturationAccepted.size,
			overloaded: this.#saturationOverloaded.size,
			terminal: terminal ? run.terminal + 1 : run.terminal
		}));
		if (terminal) {
			this.#saturationOrderIds.delete(update.orderId);
		}
	}

	#handleOverloadStatus(update: OrderStatusChanged): void {
		if (!this.#overloadOrderIds.has(update.orderId)) {
			return;
		}

		const wasRejected = this.#overloadRejected.has(update.orderId);
		const isOverloadFailure = update.status === 'failed' && update.code === 'service_overloaded';
		if (update.status === 'queued') {
			this.#overloadAccepted.add(update.orderId);
		}
		if (isOverloadFailure) {
			this.#overloadRejected.add(update.orderId);
		}
		if (update.status === 'food_ready' || update.status === 'failed') {
			this.#overloadTerminal.add(update.orderId);
		}
		if (wasRejected && !isOverloadFailure) {
			this.#recordOverloadGhost(
				update.orderId,
				`Rejected order later transitioned to ${update.status}.`
			);
		}
		this.overload.update((run) => ({
			...run,
			accepted: this.#overloadAccepted.size,
			overloaded: this.#overloadRejected.size,
			terminal: this.#overloadTerminal.size,
			ghosts: this.#overloadGhosts.size,
			ghostOrderIds: [...this.#overloadGhosts]
		}));
	}

	#recordOverloadGhost(orderId: string, message: string): void {
		if (this.#overloadGhosts.has(orderId)) {
			return;
		}
		this.#overloadGhosts.add(orderId);
		this.#overloadAbort?.abort();
		this.overload.update((run) => ({
			...run,
			status: 'failed',
			ghosts: this.#overloadGhosts.size,
			ghostOrderIds: [...this.#overloadGhosts],
			finishedAt: this.#now(),
			error: message
		}));
	}

	#finishOverloadObservation(): void {
		const run = get(this.overload);
		if (run.ghosts > 0) {
			return;
		}
		const passed = run.overloaded > 0;
		this.overload.update((current) => ({
			...current,
			status: passed ? 'passed' : 'failed',
			finishedAt: this.#now(),
			...(passed
				? {}
				: {
						error:
							'No service_overloaded response was observed; the rejection boundary was not proven.'
					})
		}));
	}

	#clearBurst(): void {
		if (this.#burstTimeout) clearTimeout(this.#burstTimeout);
		this.#burstTimeout = undefined;
		this.#burstOrderIds.clear();
		this.#burstAccepted.clear();
		this.#burstOverloaded.clear();
		this.#burstTerminal.clear();
	}

	#clearIdempotency(): void {
		if (this.#idempotencyTimeout) clearTimeout(this.#idempotencyTimeout);
		this.#idempotencyTimeout = undefined;
		this.#idempotencyOrderId = undefined;
		this.#idempotencyStatuses.clear();
	}

	#clearOverload(): void {
		this.#overloadOrderIds.clear();
		this.#overloadAccepted.clear();
		this.#overloadRejected.clear();
		this.#overloadTerminal.clear();
		this.#overloadGhosts.clear();
	}
}

function validateSaturationOptions(options: SaturationOptions): void {
	if (
		!Number.isInteger(options.durationSeconds) ||
		options.durationSeconds < 5 ||
		options.durationSeconds > 60
	) {
		throw new RangeError('durationSeconds must be between 5 and 60');
	}
	if (
		!Number.isInteger(options.targetPercent) ||
		options.targetPercent < 50 ||
		options.targetPercent > 100
	) {
		throw new RangeError('targetPercent must be between 50 and 100');
	}
	if (
		!Number.isInteger(options.maxOrdersPerSecond) ||
		options.maxOrdersPerSecond < 1 ||
		options.maxOrdersPerSecond > 200
	) {
		throw new RangeError('maxOrdersPerSecond must be between 1 and 200');
	}
}

function validateOverloadOptions(options: OverloadOptions): void {
	if (
		!Number.isInteger(options.durationSeconds) ||
		options.durationSeconds < 5 ||
		options.durationSeconds > 30
	) {
		throw new RangeError('durationSeconds must be between 5 and 30');
	}
	if (
		!Number.isInteger(options.ordersPerSecond) ||
		options.ordersPerSecond < 20 ||
		options.ordersPerSecond > 200
	) {
		throw new RangeError('ordersPerSecond must be between 20 and 200');
	}
	if (
		!Number.isInteger(options.observationSeconds) ||
		options.observationSeconds < 5 ||
		options.observationSeconds > 60
	) {
		throw new RangeError('observationSeconds must be between 5 and 60');
	}
}

function waitFor(milliseconds: number, signal: AbortSignal): Promise<void> {
	return new Promise((resolve, reject) => {
		const handleAbort = (): void => {
			clearTimeout(timeout);
			reject(new DOMException('Test stopped', 'AbortError'));
		};
		const timeout = setTimeout(() => {
			signal.removeEventListener('abort', handleAbort);
			resolve();
		}, milliseconds);
		signal.addEventListener('abort', handleAbort, { once: true });
	});
}
