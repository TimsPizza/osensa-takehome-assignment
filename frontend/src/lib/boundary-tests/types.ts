import type { OrderStatusChanged } from '$lib/generated/contracts';

export type RunStatus = 'idle' | 'publishing' | 'observing' | 'completed' | 'failed';
export type SaturationStatus = 'idle' | 'running' | 'completed' | 'stopped' | 'failed';
export type OverloadStatus = 'idle' | 'running' | 'observing' | 'passed' | 'stopped' | 'failed';

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
