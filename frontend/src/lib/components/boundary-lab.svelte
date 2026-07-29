<script lang="ts">
	import CheckCircle2Icon from '@lucide/svelte/icons/check-circle-2';
	import CopyCheckIcon from '@lucide/svelte/icons/copy-check';
	import GaugeIcon from '@lucide/svelte/icons/gauge';
	import InfoIcon from '@lucide/svelte/icons/info';
	import PlayIcon from '@lucide/svelte/icons/play';
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check';
	import SquareIcon from '@lucide/svelte/icons/square';
	import ZapIcon from '@lucide/svelte/icons/zap';

	import type { BoundaryTestController } from '$lib/boundary-test-controller';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import TestStat from '$lib/components/test-stat.svelte';

	interface Props {
		controller: BoundaryTestController;
		connected: boolean;
	}

	let { controller, connected }: Props = $props();
	const burst = $derived(controller.burst);
	const idempotency = $derived(controller.idempotency);
	const saturation = $derived(controller.saturation);
	const pressure = $derived(controller.pressure);

	let burstCount = $state(100);
	let durationSeconds = $state(20);
	let targetPercent = $state(95);
	let maxOrdersPerSecond = $state(40);

	const burstActive = $derived($burst.status === 'publishing' || $burst.status === 'observing');
	const idempotencyActive = $derived(
		$idempotency.status === 'publishing' || $idempotency.status === 'observing'
	);
	const saturationActive = $derived($saturation.status === 'running');
	const anyTestActive = $derived(burstActive || idempotencyActive || saturationActive);

	function statusVariant(status: string): 'outline' | 'secondary' | 'destructive' | 'default' {
		if (status === 'failed') return 'destructive';
		if (status === 'completed' || status === 'passed') return 'default';
		if (status === 'idle') return 'outline';
		return 'secondary';
	}

	function runBurst(): void {
		burstCount = clampInteger(burstCount, 1, 500);
		void controller.runRandomBurst(burstCount);
	}

	function runIdempotency(): void {
		void controller.runIdempotency();
	}

	function startSaturation(): void {
		durationSeconds = clampInteger(durationSeconds, 5, 60);
		targetPercent = clampInteger(targetPercent, 50, 100);
		maxOrdersPerSecond = clampInteger(maxOrdersPerSecond, 1, 200);
		void controller.startSaturation({
			durationSeconds,
			targetPercent,
			maxOrdersPerSecond
		});
	}

	function clampInteger(value: number, minimum: number, maximum: number): number {
		const numericValue = Number(value);
		if (!Number.isFinite(numericValue)) return minimum;
		return Math.min(maximum, Math.max(minimum, Math.round(numericValue)));
	}

	function elapsed(startedAt?: number, finishedAt?: number): string {
		if (startedAt === undefined) return '—';
		const milliseconds = (finishedAt ?? Date.now()) - startedAt;
		return `${Math.max(0, milliseconds / 1_000).toFixed(1)}s`;
	}
</script>

<div class="grid gap-5 xl:grid-cols-2">
	<Card.Root class="border-stone-200 bg-white/90 shadow-sm">
		<Card.Header>
			<div class="flex items-start justify-between gap-4">
				<div class="flex gap-3">
					<span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-amber-100">
						<ZapIcon class="size-5 text-amber-800" />
					</span>
					<div>
						<Card.Title>Random burst</Card.Title>
						<Card.Description class="mt-1">
							Publish a contract-valid batch concurrently across random tables.
						</Card.Description>
					</div>
				</div>
				<Badge variant={statusVariant($burst.status)}>{$burst.status}</Badge>
			</div>
		</Card.Header>
		<Card.Content class="space-y-5">
			<div class="flex items-end gap-3">
				<div class="flex-1 space-y-2">
					<Label for="burst-count">Order count</Label>
					<Input
						id="burst-count"
						type="number"
						min="1"
						max="500"
						step="1"
						bind:value={burstCount}
					/>
				</div>
				<Button
					class="bg-stone-900 text-white hover:bg-stone-700"
					disabled={!connected || anyTestActive}
					onclick={runBurst}
				>
					<PlayIcon data-icon="inline-start" />
					Run burst
				</Button>
			</div>

			<div class="grid grid-cols-3 gap-2 sm:grid-cols-4 xl:grid-cols-7">
				<TestStat label="Requested" value={$burst.requested} />
				<TestStat label="Published" value={$burst.published} />
				<TestStat label="Publish errors" value={$burst.publishFailed} />
				<TestStat label="Accepted" value={$burst.accepted} />
				<TestStat label="Overloaded" value={$burst.overloaded} />
				<TestStat label="Terminal" value={$burst.terminal} />
				<TestStat label="Elapsed" value={elapsed($burst.startedAt, $burst.finishedAt)} />
			</div>
			{#if $burst.error}
				<p class="text-sm text-red-700">{$burst.error}</p>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root class="border-stone-200 bg-white/90 shadow-sm">
		<Card.Header>
			<div class="flex items-start justify-between gap-4">
				<div class="flex gap-3">
					<span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-emerald-100">
						<CopyCheckIcon class="size-5 text-emerald-800" />
					</span>
					<div>
						<Card.Title>Idempotency jitter</Card.Title>
						<Card.Description class="mt-1">
							Send the exact same UUID three times at high frequency.
						</Card.Description>
					</div>
				</div>
				<Badge variant={statusVariant($idempotency.status)}>{$idempotency.status}</Badge>
			</div>
		</Card.Header>
		<Card.Content class="space-y-5">
			<div class="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3">
				<p class="text-xs font-medium tracking-wide text-stone-500 uppercase">Expected proof</p>
				<p class="mt-1 text-sm text-stone-700">
					3 publishes → one queued, one processing, one terminal lifecycle.
				</p>
				{#if $idempotency.orderId}
					<p class="mt-2 truncate font-mono text-xs text-stone-500">
						{$idempotency.orderId}
					</p>
				{/if}
			</div>
			<div class="grid grid-cols-3 gap-2">
				<TestStat label="Publishes" value={$idempotency.published} />
				<TestStat label="Raw events" value={$idempotency.rawEvents} />
				<TestStat label="Unique states" value={$idempotency.uniqueStatuses.length} />
			</div>
			<div class="flex items-center justify-between gap-3">
				<div class="flex flex-wrap gap-1.5">
					{#each $idempotency.uniqueStatuses as status (status)}
						<Badge variant="outline">{status}</Badge>
					{/each}
				</div>
				<Button variant="outline" disabled={!connected || anyTestActive} onclick={runIdempotency}>
					<CopyCheckIcon data-icon="inline-start" />
					Run idempotency test
				</Button>
			</div>
			{#if $idempotency.status === 'passed'}
				<p class="flex items-center gap-2 text-sm font-medium text-emerald-700">
					<CheckCircle2Icon class="size-4" />
					Duplicate messages collapsed into one lifecycle.
				</p>
			{:else if $idempotency.error}
				<p class="text-sm text-red-700">{$idempotency.error}</p>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root class="border-stone-200 bg-white/90 shadow-sm xl:col-span-2">
		<Card.Header>
			<div class="flex items-start justify-between gap-4">
				<div class="flex gap-3">
					<span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-100">
						<GaugeIcon class="size-5 text-red-800" />
					</span>
					<div>
						<Card.Title>Sustained saturation</Card.Title>
						<Card.Description class="mt-1 max-w-3xl">
							Refill from live queue telemetry to hold the service near its configured boundary.
						</Card.Description>
					</div>
				</div>
				<Badge variant={statusVariant($saturation.status)}>{$saturation.status}</Badge>
			</div>
		</Card.Header>
		<Card.Content class="space-y-5">
			<div class="grid gap-4 sm:grid-cols-3">
				<div class="space-y-2">
					<Label for="duration">Duration, seconds</Label>
					<Input id="duration" type="number" min="5" max="60" bind:value={durationSeconds} />
				</div>
				<div class="space-y-2">
					<Label for="target-pressure">Target queue utilization, %</Label>
					<Input id="target-pressure" type="number" min="50" max="100" bind:value={targetPercent} />
				</div>
				<div class="space-y-2">
					<Label for="max-rate">Maximum publish rate, orders/s</Label>
					<Input id="max-rate" type="number" min="1" max="200" bind:value={maxOrdersPerSecond} />
				</div>
			</div>

			<div class="grid grid-cols-3 gap-2 sm:grid-cols-4 xl:grid-cols-7">
				<TestStat label="Published" value={$saturation.published} />
				<TestStat label="Publish errors" value={$saturation.publishFailed} />
				<TestStat label="Accepted" value={$saturation.accepted} />
				<TestStat label="Overloaded" value={$saturation.overloaded} />
				<TestStat label="Terminal" value={$saturation.terminal} />
				<TestStat
					label="Queue now"
					value={$pressure ? `${$pressure.queuedOrders}/${$pressure.queueCapacity}` : '—'}
				/>
				<TestStat label="Elapsed" value={elapsed($saturation.startedAt, $saturation.finishedAt)} />
			</div>

			<div
				class="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
			>
				<div>
					<p class="text-sm font-semibold text-red-950">
						This intentionally applies sustained load.
					</p>
					<p class="mt-0.5 text-xs text-red-700">
						The controller is bounded by duration and publish rate and can be stopped immediately.
					</p>
				</div>
				{#if saturationActive}
					<Button variant="destructive" onclick={() => controller.stopSaturation()}>
						<SquareIcon data-icon="inline-start" />
						Stop test
					</Button>
				{:else}
					<Button
						variant="destructive"
						disabled={!connected || anyTestActive || !$pressure}
						onclick={startSaturation}
					>
						<PlayIcon data-icon="inline-start" />
						Start sustained load
					</Button>
				{/if}
			</div>
			{#if $saturation.error}
				<p class="text-sm text-red-700">{$saturation.error}</p>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root class="border-stone-200 bg-stone-100/80 shadow-none xl:col-span-2">
		<Card.Content class="flex items-start gap-3 py-1">
			<ShieldCheckIcon class="mt-0.5 size-5 shrink-0 text-stone-700" />
			<div>
				<p class="text-sm font-semibold text-stone-900">
					Schema boundary is enforced before publish
				</p>
				<p class="mt-1 text-sm leading-6 text-stone-600">
					The normal client validates every order with generated Zod schemas. Invalid shapes never
					reach MQTT; the backend independently repeats validation with Pydantic.
				</p>
			</div>
			<InfoIcon class="ml-auto size-4 shrink-0 text-stone-400" />
		</Card.Content>
	</Card.Root>
</div>
