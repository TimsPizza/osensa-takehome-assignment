import { get, writable } from 'svelte/store';

import type { OrderStatusChanged } from '$lib/generated/contracts';
import {
	createOrders,
	publishOrders,
	type BoundaryTestDependencies
} from '$lib/boundary-tests/shared';
import type { IdempotencyRun } from '$lib/boundary-tests/types';

const EMPTY_IDEMPOTENCY: IdempotencyRun = {
	status: 'idle',
	published: 0,
	rawEvents: 0,
	uniqueStatuses: []
};

export class IdempotencyTest {
	readonly state = writable<IdempotencyRun>({ ...EMPTY_IDEMPOTENCY });

	readonly #dependencies: BoundaryTestDependencies;
	readonly #statuses = new Set<OrderStatusChanged['status']>();
	#orderId?: string;
	#timeout?: ReturnType<typeof setTimeout>;

	constructor(dependencies: BoundaryTestDependencies) {
		this.#dependencies = dependencies;
	}

	async run(): Promise<void> {
		this.#clear();
		const order = createOrders(1, this.#dependencies)[0];
		this.#orderId = order.orderId;
		this.state.set({
			...EMPTY_IDEMPOTENCY,
			status: 'publishing',
			orderId: order.orderId,
			startedAt: this.#dependencies.now()
		});

		const result = await publishOrders([order, order, order], this.#dependencies.publishOrder);
		this.state.update((run) => ({
			...run,
			status: result.published === 3 ? 'observing' : 'failed',
			published: result.published,
			...(result.published === 3
				? {}
				: {
						finishedAt: this.#dependencies.now(),
						error: `Only ${result.published} of 3 duplicate publishes reached the broker.`
					})
		}));

		if (result.published === 3) {
			this.#completeIfReady();
		}
		if (result.published === 3 && get(this.state).status === 'observing') {
			this.#timeout = setTimeout(() => {
				this.state.update((run) =>
					run.status === 'observing'
						? {
								...run,
								status: 'failed',
								finishedAt: this.#dependencies.now(),
								error: 'Timed out waiting for the duplicate order lifecycle.'
							}
						: run
				);
			}, 15_000);
		}
	}

	handleStatus(update: OrderStatusChanged): void {
		if (update.orderId !== this.#orderId) {
			return;
		}
		this.#statuses.add(update.status);
		this.state.update((run) => ({
			...run,
			rawEvents: run.rawEvents + 1,
			uniqueStatuses: [...this.#statuses]
		}));
		this.#completeIfReady();
	}

	destroy(): void {
		this.#clear();
	}

	#completeIfReady(): void {
		const run = get(this.state);
		const hasTerminal = this.#statuses.has('food_ready') || this.#statuses.has('failed');
		if (run.published !== 3 || !hasTerminal) {
			return;
		}
		if (this.#timeout) clearTimeout(this.#timeout);
		const passed =
			this.#statuses.has('queued') && this.#statuses.has('processing') && this.#statuses.size === 3;
		this.state.update((current) => ({
			...current,
			status: passed ? 'passed' : 'failed',
			finishedAt: this.#dependencies.now(),
			...(passed ? {} : { error: 'Duplicate publishes produced an unexpected lifecycle.' })
		}));
	}

	#clear(): void {
		if (this.#timeout) clearTimeout(this.#timeout);
		this.#timeout = undefined;
		this.#orderId = undefined;
		this.#statuses.clear();
	}
}
