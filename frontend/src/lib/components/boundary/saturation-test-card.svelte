<script lang="ts">
	import GaugeIcon from '@lucide/svelte/icons/gauge';
	import PlayIcon from '@lucide/svelte/icons/play';
	import SquareIcon from '@lucide/svelte/icons/square';

	import type { BoundaryTestController } from '$lib/boundary-test-controller';
	import { clampInteger, elapsed, statusVariant } from '$lib/components/boundary/boundary-ui';
	import TestStat from '$lib/components/test-stat.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';

	interface Props {
		controller: BoundaryTestController;
		connected: boolean;
		disabled: boolean;
	}

	let { controller, connected, disabled }: Props = $props();
	const saturation = $derived(controller.saturation);
	const pressure = $derived(controller.pressure);
	const active = $derived($saturation.status === 'running');
	let durationSeconds = $state(20);
	let targetPercent = $state(95);
	let maxOrdersPerSecond = $state(40);

	function start(): void {
		durationSeconds = clampInteger(durationSeconds, 5, 60);
		targetPercent = clampInteger(targetPercent, 50, 100);
		maxOrdersPerSecond = clampInteger(maxOrdersPerSecond, 1, 200);
		void controller.startSaturation({
			durationSeconds,
			targetPercent,
			maxOrdersPerSecond
		});
	}
</script>

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
				<p class="text-sm font-semibold text-red-950">This intentionally applies sustained load.</p>
				<p class="mt-0.5 text-xs text-red-700">
					The controller is bounded by duration and publish rate and can be stopped immediately.
				</p>
			</div>
			{#if active}
				<Button variant="destructive" onclick={() => controller.stopSaturation()}>
					<SquareIcon data-icon="inline-start" />
					Stop test
				</Button>
			{:else}
				<Button
					variant="destructive"
					disabled={!connected || disabled || !$pressure}
					onclick={start}
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
