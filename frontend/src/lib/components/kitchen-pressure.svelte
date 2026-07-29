<script lang="ts">
	import ActivityIcon from '@lucide/svelte/icons/activity';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import ChevronUpIcon from '@lucide/svelte/icons/chevron-up';
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert';
	import GripHorizontalIcon from '@lucide/svelte/icons/grip-horizontal';

	import { Button } from '$lib/components/ui/button';
	import type { KitchenPressureSnapshot } from '$lib/generated/contracts';

	interface Props {
		snapshot?: KitchenPressureSnapshot;
		connected: boolean;
	}

	interface Position {
		x: number;
		y: number;
	}

	interface DragState {
		pointerId: number;
		offsetX: number;
		offsetY: number;
	}

	let { snapshot, connected }: Props = $props();
	let root: HTMLDivElement;
	let expanded = $state(false);
	let position = $state<Position>();
	let drag: DragState | undefined;

	const busyWorkers = $derived(
		snapshot?.workers.filter((worker) => worker.status === 'processing') ?? []
	);
	const queuePercent = $derived(
		snapshot ? Math.min(100, (snapshot.queuedOrders / snapshot.queueCapacity) * 100) : 0
	);
	const atCapacity = $derived(
		snapshot !== undefined && snapshot.queuedOrders >= snapshot.queueCapacity
	);

	function startDrag(event: PointerEvent): void {
		if (event.button !== 0 || window.innerWidth < 768) return;
		const bounds = root.getBoundingClientRect();
		position = { x: bounds.left, y: bounds.top };
		drag = {
			pointerId: event.pointerId,
			offsetX: event.clientX - bounds.left,
			offsetY: event.clientY - bounds.top
		};
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
	}

	function moveDrag(event: PointerEvent): void {
		if (!drag || drag.pointerId !== event.pointerId) return;
		position = clampPosition({
			x: event.clientX - drag.offsetX,
			y: event.clientY - drag.offsetY
		});
	}

	function stopDrag(event: PointerEvent): void {
		if (drag?.pointerId !== event.pointerId) return;
		drag = undefined;
	}

	function clampPosition(next = position): Position | undefined {
		if (!next || !root) return next;
		const gutter = 12;
		const maximumX = Math.max(gutter, window.innerWidth - root.offsetWidth - gutter);
		const maximumY = Math.max(gutter, window.innerHeight - root.offsetHeight - gutter);
		return {
			x: Math.min(Math.max(gutter, next.x), maximumX),
			y: Math.min(Math.max(gutter, next.y), maximumY)
		};
	}

	function handleResize(): void {
		if (window.innerWidth < 768) {
			position = undefined;
			return;
		}
		position = clampPosition();
	}

	function toggleExpanded(): void {
		expanded = !expanded;
		requestAnimationFrame(() => {
			position = clampPosition();
		});
	}
</script>

<svelte:window onresize={handleResize} />

<div
	bind:this={root}
	class={`fixed z-50 w-[calc(100vw-1.5rem)] overflow-hidden rounded-2xl border border-white/10 bg-stone-950 text-white shadow-2xl shadow-stone-950/30 sm:w-96 ${
		expanded ? 'md:w-[42rem]' : ''
	} ${position ? '' : 'right-3 bottom-3 sm:right-5 sm:bottom-5'}`}
	style={position ? `left:${position.x}px;top:${position.y}px` : undefined}
	aria-label="Kitchen pressure monitor"
>
	<div class="flex items-center gap-3 border-b border-white/10 px-4 py-3">
		<button
			type="button"
			class="hidden cursor-move touch-none text-stone-500 hover:text-stone-300 md:block"
			aria-label="Drag kitchen pressure monitor"
			onpointerdown={startDrag}
			onpointermove={moveDrag}
			onpointerup={stopDrag}
			onpointercancel={stopDrag}
		>
			<GripHorizontalIcon class="size-5" />
		</button>
		<span class="flex size-8 items-center justify-center rounded-lg bg-amber-400/15 text-amber-300">
			<ActivityIcon class="size-4" />
		</span>
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<p class="text-sm font-semibold">Kitchen pressure</p>
				<span class={`size-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-amber-400'}`}
				></span>
			</div>
			<p class="truncate text-[0.6875rem] text-stone-500">
				{snapshot ? `Revision ${snapshot.revision}` : 'Waiting for telemetry'}
			</p>
		</div>
		<Button
			variant="ghost"
			size="icon-sm"
			class="text-stone-400 hover:bg-white/10 hover:text-white"
			aria-label={expanded ? 'Collapse pressure monitor' : 'Expand pressure monitor'}
			onclick={toggleExpanded}
		>
			{#if expanded}
				<ChevronDownIcon />
			{:else}
				<ChevronUpIcon />
			{/if}
		</Button>
	</div>

	{#if snapshot}
		<div class="space-y-3 px-4 py-3">
			<div class="grid grid-cols-[1fr_auto] items-end gap-4">
				<div>
					<div class="mb-1.5 flex items-center justify-between text-xs">
						<span class="text-stone-400">Waiting queue</span>
						<span class="font-mono font-medium tabular-nums">
							{snapshot.queuedOrders}/{snapshot.queueCapacity}
						</span>
					</div>
					<div
						class="h-2 overflow-hidden rounded-full bg-white/10"
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
							style={`width:${queuePercent}%`}
						></div>
					</div>
				</div>
				<div class="text-right">
					<p class="text-[0.6875rem] text-stone-500">Workers</p>
					<p class="font-mono text-lg font-semibold tabular-nums">
						{busyWorkers.length}/{snapshot.workers.length}
					</p>
				</div>
			</div>

			{#if atCapacity}
				<p class="flex items-center gap-2 text-xs font-medium text-red-300" role="status">
					<CircleAlertIcon class="size-3.5" />
					Queue full — excess orders return service_overloaded.
				</p>
			{/if}

			{#if expanded}
				<div class="border-t border-white/10 pt-3">
					<div class="mb-2 flex items-center justify-between">
						<p class="text-xs font-medium text-stone-300">Worker pool</p>
						<p class="text-[0.6875rem] text-stone-500">
							Admission limit {snapshot.queueCapacity + snapshot.workers.length}
						</p>
					</div>
					<ul class="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Worker states">
						{#each snapshot.workers as worker (worker.workerId)}
							<li
								class={`min-w-0 rounded-lg border px-3 py-2 ${
									worker.status === 'processing'
										? 'border-amber-400/25 bg-amber-400/10'
										: 'border-white/10 bg-white/5'
								}`}
							>
								<div class="flex items-center gap-2">
									<span
										class={`size-2 rounded-full ${
											worker.status === 'processing'
												? 'animate-pulse bg-amber-400'
												: 'bg-emerald-500'
										}`}
									></span>
									<p class="font-mono text-xs font-semibold">
										W{String(worker.workerId).padStart(2, '0')}
									</p>
								</div>
								{#if worker.status === 'processing'}
									<p class="mt-1.5 truncate text-xs" title={worker.foodName}>
										{worker.foodName}
									</p>
									<p class="mt-0.5 text-[0.6875rem] text-amber-200">Table {worker.tableId}</p>
								{:else}
									<p class="mt-1.5 text-xs text-stone-500">Idle</p>
								{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		</div>
	{:else}
		<p class="px-4 py-4 text-sm text-stone-400">
			{connected ? 'Waiting for retained pressure snapshot…' : 'Connect to view pressure.'}
		</p>
	{/if}
</div>
