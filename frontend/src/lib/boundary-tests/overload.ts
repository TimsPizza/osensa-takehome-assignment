import { get, writable } from 'svelte/store';

import type { KitchenPressureSnapshot, OrderStatusChanged } from '$lib/generated/contracts';
import {
	createOrders,
	publishOrders,
	type BoundaryTestDependencies
} from '$lib/boundary-tests/shared';
import type { OverloadOptions, OverloadRun } from '$lib/boundary-tests/types';

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

export class OverloadTest {
	readonly state = writable<OverloadRun>({ ...EMPTY_OVERLOAD });

	readonly #dependencies: BoundaryTestDependencies;
	readonly #getPressure: () => KitchenPressureSnapshot | undefined;
	readonly #orderIds = new Set<string>();
	readonly #accepted = new Set<string>();
	readonly #rejected = new Set<string>();
	readonly #terminal = new Set<string>();
	readonly #ghosts = new Set<string>();
	#abort?: AbortController;

	constructor(
		dependencies: BoundaryTestDependencies,
		getPressure: () => KitchenPressureSnapshot | undefined
	) {
		this.#dependencies = dependencies;
		this.#getPressure = getPressure;
	}

	async start(options: OverloadOptions): Promise<void> {
		validateOptions(options);
		this.stop();
		this.#clear();
		const abort = new AbortController();
		this.#abort = abort;
		const startedAt = this.#dependencies.now();
		const warmupOvershoot = Math.max(1, Math.ceil(options.ordersPerSecond / 4));
		let publishBudget = 0;
		this.state.set({
			...EMPTY_OVERLOAD,
			...options,
			status: 'running',
			startedAt
		});

		try {
			const pressure = this.#getPressure();
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
				await this.#publishBatch(warmupCount);
			}

			while (
				!abort.signal.aborted &&
				this.#dependencies.now() - startedAt < options.durationSeconds * 1_000
			) {
				publishBudget += options.ordersPerSecond / 4;
				const orderCount = Math.floor(publishBudget);
				publishBudget -= orderCount;
				if (orderCount > 0) {
					await this.#publishBatch(orderCount);
				}
				await this.#dependencies.wait(250, abort.signal);
			}

			if (abort.signal.aborted) {
				return;
			}

			this.state.update((run) => ({
				...run,
				status: 'observing',
				trafficStoppedAt: this.#dependencies.now()
			}));
			await this.#dependencies.wait(options.observationSeconds * 1_000, abort.signal);
			if (!abort.signal.aborted) {
				this.#finishObservation();
			}
		} catch (error) {
			if (!abort.signal.aborted) {
				this.state.update((run) => ({
					...run,
					status: 'failed',
					finishedAt: this.#dependencies.now(),
					error: error instanceof Error ? error.message : 'Overload test failed.'
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
		this.state.update((run) =>
			run.status === 'running' || run.status === 'observing'
				? {
						...run,
						status: 'stopped',
						finishedAt: this.#dependencies.now()
					}
				: run
		);
	}

	handleStatus(update: OrderStatusChanged): void {
		if (!this.#orderIds.has(update.orderId)) {
			return;
		}

		const wasRejected = this.#rejected.has(update.orderId);
		const isOverloadFailure = update.status === 'failed' && update.code === 'service_overloaded';
		if (update.status === 'queued') {
			this.#accepted.add(update.orderId);
		}
		if (isOverloadFailure) {
			this.#rejected.add(update.orderId);
		}
		if (update.status === 'food_ready' || update.status === 'failed') {
			this.#terminal.add(update.orderId);
		}
		if (wasRejected && !isOverloadFailure) {
			this.#recordGhost(update.orderId, `Rejected order later transitioned to ${update.status}.`);
		}
		this.#updateCounts();
	}

	handlePressure(snapshot: KitchenPressureSnapshot): void {
		for (const worker of snapshot.workers) {
			if (worker.status === 'processing' && this.#rejected.has(worker.orderId)) {
				this.#recordGhost(worker.orderId, 'A rejected order appeared in worker telemetry.');
			}
		}
	}

	destroy(): void {
		this.stop();
		this.#clear();
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

	#recordGhost(orderId: string, message: string): void {
		if (this.#ghosts.has(orderId)) {
			return;
		}
		this.#ghosts.add(orderId);
		this.#abort?.abort();
		this.state.update((run) => ({
			...run,
			status: 'failed',
			ghosts: this.#ghosts.size,
			ghostOrderIds: [...this.#ghosts],
			finishedAt: this.#dependencies.now(),
			error: message
		}));
	}

	#finishObservation(): void {
		const run = get(this.state);
		if (run.ghosts > 0) {
			return;
		}
		const passed = run.overloaded > 0;
		this.state.update((current) => ({
			...current,
			status: passed ? 'passed' : 'failed',
			finishedAt: this.#dependencies.now(),
			...(passed
				? {}
				: {
						error:
							'No service_overloaded response was observed; the rejection boundary was not proven.'
					})
		}));
	}

	#updateCounts(): void {
		this.state.update((run) => ({
			...run,
			accepted: this.#accepted.size,
			overloaded: this.#rejected.size,
			terminal: this.#terminal.size,
			ghosts: this.#ghosts.size,
			ghostOrderIds: [...this.#ghosts]
		}));
	}

	#clear(): void {
		this.#orderIds.clear();
		this.#accepted.clear();
		this.#rejected.clear();
		this.#terminal.clear();
		this.#ghosts.clear();
	}
}

function validateOptions(options: OverloadOptions): void {
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
