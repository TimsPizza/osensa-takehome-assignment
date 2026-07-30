import { get, writable, type Readable } from 'svelte/store';

import { BurstTest } from '$lib/boundary-tests/burst';
import { IdempotencyTest } from '$lib/boundary-tests/idempotency';
import { OverloadTest } from '$lib/boundary-tests/overload';
import {
	resolveDependencies,
	type ControllerOptions,
	type PublishOrder
} from '$lib/boundary-tests/shared';
import { SaturationTest } from '$lib/boundary-tests/saturation';
import type { OverloadOptions, SaturationOptions } from '$lib/boundary-tests/types';
import type { KitchenPressureSnapshot, OrderStatusChanged } from '$lib/generated/contracts';

export type {
	BurstRun,
	IdempotencyRun,
	OverloadOptions,
	OverloadRun,
	SaturationOptions,
	SaturationRun
} from '$lib/boundary-tests/types';

export class BoundaryTestController {
	readonly burst;
	readonly idempotency;
	readonly saturation;
	readonly overload;
	readonly pressure: Readable<KitchenPressureSnapshot | undefined>;

	readonly #pressure = writable<KitchenPressureSnapshot>();
	readonly #burstTest: BurstTest;
	readonly #idempotencyTest: IdempotencyTest;
	readonly #saturationTest: SaturationTest;
	readonly #overloadTest: OverloadTest;

	constructor(publishOrder: PublishOrder, options: ControllerOptions = {}) {
		const dependencies = resolveDependencies(publishOrder, options);
		const getPressure = (): KitchenPressureSnapshot | undefined => get(this.#pressure);

		this.#burstTest = new BurstTest(dependencies);
		this.#idempotencyTest = new IdempotencyTest(dependencies);
		this.#saturationTest = new SaturationTest(dependencies, getPressure);
		this.#overloadTest = new OverloadTest(dependencies, getPressure);
		this.burst = this.#burstTest.state;
		this.idempotency = this.#idempotencyTest.state;
		this.saturation = this.#saturationTest.state;
		this.overload = this.#overloadTest.state;
		this.pressure = { subscribe: this.#pressure.subscribe };
	}

	handlePressure(snapshot: KitchenPressureSnapshot): void {
		this.#pressure.set(snapshot);
		this.#overloadTest.handlePressure(snapshot);
	}

	handleOrderStatus(update: OrderStatusChanged): void {
		this.#burstTest.handleStatus(update);
		this.#idempotencyTest.handleStatus(update);
		this.#saturationTest.handleStatus(update);
		this.#overloadTest.handleStatus(update);
	}

	runRandomBurst(count: number): Promise<void> {
		return this.#burstTest.run(count);
	}

	runIdempotency(): Promise<void> {
		return this.#idempotencyTest.run();
	}

	startSaturation(options: SaturationOptions): Promise<void> {
		return this.#saturationTest.start(options);
	}

	stopSaturation(): void {
		this.#saturationTest.stop();
	}

	startOverload(options: OverloadOptions): Promise<void> {
		return this.#overloadTest.start(options);
	}

	stopOverload(): void {
		this.#overloadTest.stop();
	}

	destroy(): void {
		this.#burstTest.destroy();
		this.#idempotencyTest.destroy();
		this.#saturationTest.destroy();
		this.#overloadTest.destroy();
	}
}
