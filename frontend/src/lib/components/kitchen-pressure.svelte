<script lang="ts">
	import ActivityIcon from '@lucide/svelte/icons/activity';
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert';

	import { Badge } from '$lib/components/ui/badge';
	import * as Card from '$lib/components/ui/card';
	import type { KitchenPressureSnapshot } from '$lib/generated/contracts';

	interface Props {
		snapshot?: KitchenPressureSnapshot;
		connected: boolean;
	}

	let { snapshot, connected }: Props = $props();

	const busyWorkers = $derived(
		snapshot?.workers.filter((worker) => worker.status === 'processing') ?? []
	);
	const queuePercent = $derived(
		snapshot ? Math.min(100, (snapshot.queuedOrders / snapshot.queueCapacity) * 100) : 0
	);
	const atCapacity = $derived(
		snapshot !== undefined && snapshot.queuedOrders >= snapshot.queueCapacity
	);
</script>

<Card.Root
	class="mb-6 border-stone-200/90 bg-stone-950 text-stone-50 shadow-[0_18px_50px_-32px_rgba(28,25,23,0.7)]"
>
	<Card.Header class="gap-4 border-b border-white/10">
		<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
			<div>
				<div
					class="flex items-center gap-2 text-xs font-semibold tracking-[0.16em] text-amber-300 uppercase"
				>
					<ActivityIcon class="size-4" />
					Bounded concurrency
				</div>
				<Card.Title class="mt-2 text-xl text-white">Kitchen pressure</Card.Title>
				<Card.Description class="mt-1 max-w-2xl text-stone-400">
					The waiting queue is capped. Every order beyond that boundary receives an explicit
					overload response.
				</Card.Description>
			</div>
			<Badge
				variant="outline"
				class={connected
					? 'border-white/15 bg-white/5 text-stone-200'
					: 'border-amber-400/30 bg-amber-400/10 text-amber-200'}
			>
				{snapshot ? 'Live backend telemetry' : 'Waiting for telemetry'}
			</Badge>
		</div>
	</Card.Header>

	<Card.Content class="space-y-6">
		{#if snapshot}
			<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
				<div>
					<div class="mb-2 flex items-end justify-between gap-4">
						<div>
							<p class="text-sm font-medium text-stone-200">Waiting queue</p>
							<p class="mt-0.5 text-xs text-stone-400">
								{snapshot.queuedOrders} of {snapshot.queueCapacity} slots occupied
							</p>
						</div>
						<p class="font-mono text-2xl font-semibold text-white tabular-nums">
							{Math.round(queuePercent)}%
						</p>
					</div>
					<div
						class="h-3 overflow-hidden rounded-full bg-white/10 ring-1 ring-white/10"
						role="progressbar"
						aria-label="Waiting queue utilization"
						aria-valuemin="0"
						aria-valuemax={snapshot.queueCapacity}
						aria-valuenow={snapshot.queuedOrders}
					>
						<div
							class={`h-full rounded-full transition-[width,background-color] duration-300 ${
								atCapacity ? 'bg-red-500' : queuePercent >= 75 ? 'bg-amber-400' : 'bg-emerald-500'
							}`}
							style={`width: ${queuePercent}%`}
						></div>
					</div>
				</div>

				<div class="flex gap-6 rounded-xl border border-white/10 bg-white/5 px-5 py-3">
					<div>
						<p class="text-xs text-stone-400">Workers busy</p>
						<p class="mt-1 font-mono text-xl font-semibold tabular-nums">
							{busyWorkers.length}/{snapshot.workers.length}
						</p>
					</div>
					<div>
						<p class="text-xs text-stone-400">Admission limit</p>
						<p class="mt-1 font-mono text-xl font-semibold tabular-nums">
							{snapshot.queueCapacity + snapshot.workers.length}
						</p>
					</div>
				</div>
			</div>

			{#if atCapacity}
				<div
					class="flex items-start gap-2 rounded-lg border border-red-400/25 bg-red-400/10 px-3 py-2 text-sm text-red-100"
					role="status"
				>
					<CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
					Queue full — new orders are rejected with the retryable
					<code class="font-mono text-xs">service_overloaded</code> status.
				</div>
			{/if}

			<div>
				<div class="mb-2 flex items-center justify-between">
					<p class="text-sm font-medium text-stone-200">Worker pool</p>
					<p class="text-xs text-stone-500">One order per worker</p>
				</div>
				<ul class="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8" aria-label="Worker states">
					{#each snapshot.workers as worker (worker.workerId)}
						<li
							class={`min-w-0 rounded-lg border px-3 py-2 ${
								worker.status === 'processing'
									? 'border-amber-400/30 bg-amber-400/10'
									: 'border-white/10 bg-white/5'
							}`}
						>
							<div class="flex items-center gap-2">
								<span
									class={`size-2 shrink-0 rounded-full ${
										worker.status === 'processing' ? 'animate-pulse bg-amber-400' : 'bg-emerald-500'
									}`}
								></span>
								<p class="font-mono text-xs font-semibold text-stone-200">
									W{String(worker.workerId).padStart(2, '0')}
								</p>
							</div>
							{#if worker.status === 'processing'}
								<p class="mt-2 truncate text-xs font-medium text-white" title={worker.foodName}>
									{worker.foodName}
								</p>
								<p class="mt-0.5 text-[0.6875rem] text-amber-200">Table {worker.tableId}</p>
							{:else}
								<p class="mt-2 text-xs text-stone-500">Idle</p>
							{/if}
						</li>
					{/each}
				</ul>
			</div>
		{:else}
			<div class="rounded-xl border border-dashed border-white/15 px-4 py-8 text-center">
				<p class="text-sm text-stone-400">
					{connected
						? 'Waiting for the retained pressure snapshot…'
						: 'Connect to view queue pressure.'}
				</p>
			</div>
		{/if}
	</Card.Content>
</Card.Root>
