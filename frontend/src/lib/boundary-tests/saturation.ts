import { writable } from 'svelte/store';

import type { KitchenPressureSnapshot, OrderStatusChanged } from '$lib/generated/contracts';
import {
	createOrders,
	publishOrders,
	type BoundaryTestDependencies
} from '$lib/boundary-tests/shared';
import type { SaturationOptions, SaturationRun } from '$lib/boundary-tests/types';

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

export class SaturationTest {
	readonly state = writable<SaturationRun>({ ...EMPTY_SATURATION });

	readonly #dependencies: BoundaryTestDependencies;
	readonly #getPressure: () => KitchenPressureSnapshot | undefined;
	readonly #orderIds = new Set<string>();
	readonly #accepted = new Set<string>();
	readonly #overloaded = new Set<string>();
	#abort?: AbortController;

	constructor(
		dependencies: BoundaryTestDependencies,
		getPressure: () => KitchenPressureSnapshot | undefined
	) {
		this.#dependencies = dependencies;
		this.#getPressure = getPressure;
	}

	async start(options: SaturationOptions): Promise<void> {
		validateOptions(options);
		this.stop();
		this.#orderIds.clear();
		this.#accepted.clear();
		this.#overloaded.clear();
		const abort = new AbortController();
		this.#abort = abort;
		const startedAt = this.#dependencies.now();
		this.state.set({
			...EMPTY_SATURATION,
			...options,
			status: 'running',
			startedAt
		});

		try {
			while (
				!abort.signal.aborted &&
				this.#dependencies.now() - startedAt < options.durationSeconds * 1_000
			) {
				const pressure = this.#getPressure();
				if (!pressure) {
					await this.#dependencies.wait(250, abort.signal);
					continue;
				}

				const targetDepth = Math.ceil(pressure.queueCapacity * (options.targetPercent / 100));
				const deficit = Math.max(0, targetDepth - pressure.queuedOrders);
				const perTickLimit = Math.max(1, Math.ceil(options.maxOrdersPerSecond / 4));
				const orderCount = Math.min(deficit, perTickLimit);

				if (orderCount > 0) {
					await this.#publishBatch(orderCount);
				}
				await this.#dependencies.wait(250, abort.signal);
			}

			if (!abort.signal.aborted) {
				this.state.update((run) => ({
					...run,
					status: 'completed',
					finishedAt: this.#dependencies.now()
				}));
			}
		} catch (error) {
			if (!abort.signal.aborted) {
				this.state.update((run) => ({
					...run,
					status: 'failed',
					finishedAt: this.#dependencies.now(),
					error: error instanceof Error ? error.message : 'Saturation test failed.'
				}));
			}
		} finally {
			if (this.#abort === abort) {
				this.#abort = undefined;
			}
		}
	}

	stop(): void {
		const abort = this.#abort;
		if (!abort) {
			return;
		}
		abort.abort();
		this.#abort = undefined;
		this.state.update((run) => ({
			...run,
			status: 'stopped',
			finishedAt: this.#dependencies.now()
		}));
	}

	handleStatus(update: OrderStatusChanged): void {
		if (!this.#orderIds.has(update.orderId)) {
			return;
		}
		if (update.status === 'queued') {
			this.#accepted.add(update.orderId);
		}
		const terminal = update.status === 'food_ready' || update.status === 'failed';
		if (update.status === 'failed' && update.code === 'service_overloaded') {
			this.#overloaded.add(update.orderId);
		}
		this.state.update((run) => ({
			...run,
			accepted: this.#accepted.size,
			overloaded: this.#overloaded.size,
			terminal: terminal ? run.terminal + 1 : run.terminal
		}));
		if (terminal) {
			this.#orderIds.delete(update.orderId);
		}
	}

	destroy(): void {
		this.stop();
		this.#orderIds.clear();
		this.#accepted.clear();
		this.#overloaded.clear();
	}

	async #publishBatch(count: number): Promise<void> {
		const orders = createOrders(count, this.#dependencies);
		for (const order of orders) {
			this.#orderIds.add(order.orderId);
		}
		const result = await publishOrders(orders, this.#dependencies.publishOrder);
		for (const orderId of result.failedOrderIds) {
			this.#orderIds.delete(orderId);
		}
		this.state.update((run) => ({
			...run,
			published: run.published + result.published,
			publishFailed: run.publishFailed + result.publishFailed
		}));
	}
}

function validateOptions(options: SaturationOptions): void {
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
