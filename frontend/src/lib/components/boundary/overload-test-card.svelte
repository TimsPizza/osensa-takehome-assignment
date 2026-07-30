<script lang="ts">
	import CheckCircle2Icon from '@lucide/svelte/icons/check-circle-2';
	import GhostIcon from '@lucide/svelte/icons/ghost';
	import SquareIcon from '@lucide/svelte/icons/square';

	import type { BoundaryTestController } from '$lib/boundary-test-controller';
	import { clampInteger, statusVariant } from '$lib/components/boundary/boundary-ui';
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
	const overload = $derived(controller.overload);
	const pressure = $derived(controller.pressure);
	const active = $derived($overload.status === 'running' || $overload.status === 'observing');
	let durationSeconds = $state(10);
	let ordersPerSecond = $state(100);
	let observationSeconds = $state(10);

	function start(): void {
		durationSeconds = clampInteger(durationSeconds, 5, 30);
		ordersPerSecond = clampInteger(ordersPerSecond, 20, 200);
		observationSeconds = clampInteger(observationSeconds, 5, 60);
		void controller.startOverload({
			durationSeconds,
			ordersPerSecond,
			observationSeconds
		});
	}
</script>

<Card.Root class="border-red-200 bg-white/95 shadow-sm xl:col-span-2">
	<Card.Header>
		<div class="flex items-start justify-between gap-4">
			<div class="flex gap-3">
				<span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-100">
					<GhostIcon class="size-5 text-red-800" />
				</span>
				<div>
					<Card.Title>Overload and ghost guard</Card.Title>
					<Card.Description class="mt-1 max-w-3xl">
						Fill the queue, continuously publish beyond capacity, then quarantine every rejected
						UUID and watch for impossible later work.
					</Card.Description>
				</div>
			</div>
			<Badge variant={statusVariant($overload.status)}>{$overload.status}</Badge>
		</div>
	</Card.Header>
	<Card.Content class="space-y-5">
		<div class="grid gap-4 sm:grid-cols-3">
			<div class="space-y-2">
				<Label for="overload-duration">Traffic duration, seconds</Label>
				<Input id="overload-duration" type="number" min="5" max="30" bind:value={durationSeconds} />
			</div>
			<div class="space-y-2">
				<Label for="overload-rate">Offered rate, orders/s</Label>
				<Input id="overload-rate" type="number" min="20" max="200" bind:value={ordersPerSecond} />
			</div>
			<div class="space-y-2">
				<Label for="ghost-observation">Quiet observation, seconds</Label>
				<Input
					id="ghost-observation"
					type="number"
					min="5"
					max="60"
					bind:value={observationSeconds}
				/>
			</div>
		</div>

		<div class="grid grid-cols-3 gap-2 sm:grid-cols-4 xl:grid-cols-7">
			<TestStat label="Published" value={$overload.published} />
			<TestStat label="Publish errors" value={$overload.publishFailed} />
			<TestStat label="Accepted" value={$overload.accepted} />
			<TestStat label="Overloaded" value={$overload.overloaded} />
			<TestStat label="Terminal" value={$overload.terminal} />
			<TestStat label="Ghosts" value={$overload.ghosts} />
			<TestStat
				label="Queue now"
				value={$pressure ? `${$pressure.queuedOrders}/${$pressure.queueCapacity}` : '—'}
			/>
		</div>

		<div
			class="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
		>
			<div>
				<p class="text-sm font-semibold text-red-950">
					{$overload.status === 'observing'
						? 'Traffic stopped. Rejected UUIDs remain under observation.'
						: 'This deliberately crosses the admission boundary.'}
				</p>
				<p class="mt-0.5 text-xs leading-5 text-red-700">
					A rejected UUID appearing later as queued, processing, food ready, or inside a worker
					immediately fails the test. Monitoring remains active after a pass.
				</p>
			</div>
			{#if active}
				<Button variant="destructive" onclick={() => controller.stopOverload()}>
					<SquareIcon data-icon="inline-start" />
					Stop test
				</Button>
			{:else}
				<Button
					variant="destructive"
					disabled={!connected || disabled || !$pressure}
					onclick={start}
				>
					<GhostIcon data-icon="inline-start" />
					Start overload test
				</Button>
			{/if}
		</div>

		{#if $overload.status === 'passed'}
			<p class="flex items-center gap-2 text-sm font-medium text-emerald-700">
				<CheckCircle2Icon class="size-4" />
				Overload responses were observed and no rejected order returned as work.
			</p>
		{:else if $overload.error}
			<div class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
				<p class="font-semibold">{$overload.error}</p>
				{#if $overload.ghostOrderIds.length > 0}
					<p class="mt-1 font-mono text-xs break-all">
						{$overload.ghostOrderIds.slice(0, 3).join(', ')}
					</p>
				{/if}
			</div>
		{/if}
	</Card.Content>
</Card.Root>
