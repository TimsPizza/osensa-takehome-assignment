import { get, writable } from 'svelte/store';

import type { OrderStatusChanged } from '$lib/generated/contracts';
import {
	createOrders,
	publishOrders,
	type BoundaryTestDependencies
} from '$lib/boundary-tests/shared';
import type { BurstRun } from '$lib/boundary-tests/types';

const EMPTY_BURST: BurstRun = {
	status: 'idle',
	requested: 0,
	published: 0,
	publishFailed: 0,
	accepted: 0,
	overloaded: 0,
	terminal: 0
};

export class BurstTest {
	readonly state = writable<BurstRun>({ ...EMPTY_BURST });

	readonly #dependencies: BoundaryTestDependencies;
	readonly #orderIds = new Set<string>();
	readonly #accepted = new Set<string>();
	readonly #overloaded = new Set<string>();
	readonly #terminal = new Set<string>();
	#timeout?: ReturnType<typeof setTimeout>;

	constructor(dependencies: BoundaryTestDependencies) {
		this.#dependencies = dependencies;
	}

	async run(count: number): Promise<void> {
		if (!Number.isInteger(count) || count < 1 || count > 500) {
			throw new RangeError('count must be an integer between 1 and 500');
		}

		this.#clear();
		const startedAt = this.#dependencies.now();
		const orders = createOrders(count, this.#dependencies);
		for (const order of orders) {
			this.#orderIds.add(order.orderId);
		}
		this.state.set({
			...EMPTY_BURST,
			status: 'publishing',
			requested: count,
			startedAt
		});

		const result = await publishOrders(orders, this.#dependencies.publishOrder);
		for (const orderId of result.failedOrderIds) {
			this.#orderIds.delete(orderId);
		}

		this.state.update((run) => ({
			...run,
			status: result.published === 0 ? 'failed' : 'observing',
			published: result.published,
			publishFailed: result.publishFailed,
			...(result.published === 0
				? {
						finishedAt: this.#dependencies.now(),
						error: 'No orders reached the broker.'
					}
				: {})
		}));
		this.#completeIfReady();

		if (result.published > 0 && get(this.state).status === 'observing') {
			this.#timeout = setTimeout(() => {
				this.state.update((run) =>
					run.status === 'observing'
						? {
								...run,
								status: 'failed',
								finishedAt: this.#dependencies.now(),
								error: 'Timed out waiting for terminal order states.'
							}
						: run
				);
			}, 30_000);
		}
	}

	handleStatus(update: OrderStatusChanged): void {
		if (!this.#orderIds.has(update.orderId)) {
			return;
		}
		if (update.status === 'queued') {
			this.#accepted.add(update.orderId);
		}
		if (update.status === 'food_ready' || update.status === 'failed') {
			this.#terminal.add(update.orderId);
		}
		if (update.status === 'failed' && update.code === 'service_overloaded') {
			this.#overloaded.add(update.orderId);
		}
		this.state.update((run) => ({
			...run,
			accepted: this.#accepted.size,
			overloaded: this.#overloaded.size,
			terminal: this.#terminal.size
		}));
		this.#completeIfReady();
	}

	destroy(): void {
		this.#clear();
	}

	#completeIfReady(): void {
		const run = get(this.state);
		if (
			(run.status === 'publishing' || run.status === 'observing') &&
			run.published > 0 &&
			this.#terminal.size >= run.published
		) {
			if (this.#timeout) clearTimeout(this.#timeout);
			this.state.update((current) => ({
				...current,
				status: 'completed',
				finishedAt: this.#dependencies.now()
			}));
		}
	}

	#clear(): void {
		if (this.#timeout) clearTimeout(this.#timeout);
		this.#timeout = undefined;
		this.#orderIds.clear();
		this.#accepted.clear();
		this.#overloaded.clear();
		this.#terminal.clear();
	}
}
