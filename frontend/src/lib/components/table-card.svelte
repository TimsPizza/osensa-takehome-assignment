<script lang="ts">
	import CheckCircle2Icon from '@lucide/svelte/icons/check-circle-2';
	import ChefHatIcon from '@lucide/svelte/icons/chef-hat';
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert';
	import Clock3Icon from '@lucide/svelte/icons/clock-3';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import SendIcon from '@lucide/svelte/icons/send';
	import ZapIcon from '@lucide/svelte/icons/zap';

	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import type { OrderView, OrderViewStatus, TableId } from '$lib/order-state';

	interface Props {
		tableId: TableId;
		orders: OrderView[];
		connected: boolean;
		bulkOrdering: boolean;
		onOrder: (tableId: TableId, foodName?: string) => void;
		onBulkOrder: (tableId: TableId) => void;
	}

	let { tableId, orders, connected, bulkOrdering, onOrder, onBulkOrder }: Props = $props();

	const statusCopy: Record<OrderViewStatus, string> = {
		sending: 'Sending',
		send_failed: 'Not sent',
		queued: 'Queued',
		processing: 'Preparing',
		food_ready: 'Ready',
		failed: 'Failed'
	};

	function badgeVariant(status: OrderViewStatus) {
		if (status === 'failed' || status === 'send_failed') return 'destructive';
		if (status === 'food_ready') return 'default';
		if (status === 'processing') return 'secondary';
		return 'outline';
	}
</script>

<Card.Root
	class="group overflow-hidden border-stone-200/90 bg-white/90 shadow-[0_18px_50px_-32px_rgba(41,37,36,0.45)] backdrop-blur"
>
	<Card.Header class="border-b border-stone-100 bg-stone-50/80">
		<div class="flex items-start justify-between gap-4">
			<div>
				<p class="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Dining room</p>
				<Card.Title class="mt-1 text-2xl tracking-tight">Table {tableId}</Card.Title>
			</div>
			<div
				class="flex size-11 items-center justify-center rounded-full bg-amber-100 text-lg font-semibold text-amber-950"
			>
				{tableId}
			</div>
		</div>
	</Card.Header>

	<Card.Content class="max-h-[8rem] min-h-64 overflow-y-auto pt-5">
		{#if orders.length === 0}
			<div
				class="flex min-h-44 flex-col items-center justify-center rounded-xl border border-dashed border-stone-200 bg-stone-50/60 px-6 text-center"
			>
				<ChefHatIcon class="mb-3 size-7 text-stone-400" />
				<p class="font-medium text-stone-700">Nothing ordered yet</p>
				<p class="mt-1 text-sm text-stone-500">Your food will appear here as it is prepared.</p>
			</div>
		{:else}
			<ul class="space-y-3" aria-live="polite" aria-label={`Orders for table ${tableId}`}>
				{#each orders as order (order.orderId)}
					<li
						class:ready-order={order.status === 'food_ready'}
						class="rounded-xl border border-stone-200 bg-white p-3.5 transition-colors"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0">
								<p class="truncate font-semibold text-stone-900">{order.foodName}</p>
								<p class="mt-1 flex items-center gap-1.5 text-xs text-stone-500">
									{#if order.status === 'food_ready'}
										<CheckCircle2Icon class="size-3.5 text-emerald-600" />
									{:else if order.status === 'failed' || order.status === 'send_failed'}
										<CircleAlertIcon class="size-3.5 text-red-600" />
									{:else if order.status === 'sending'}
										<SendIcon class="size-3.5" />
									{:else}
										<Clock3Icon class="size-3.5" />
									{/if}
									{statusCopy[order.status]}
								</p>
							</div>
							<Badge
								variant={badgeVariant(order.status)}
								class={order.status === 'food_ready' ? 'bg-emerald-700 text-white' : undefined}
							>
								{statusCopy[order.status]}
							</Badge>
						</div>

						{#if order.failureMessage}
							<p class="mt-2 text-xs leading-5 text-red-700">{order.failureMessage}</p>
						{/if}

						{#if order.retryable}
							<Button
								variant="ghost"
								size="xs"
								class="mt-2 px-0 text-red-700 hover:bg-transparent hover:text-red-900"
								disabled={!connected}
								onclick={() => onOrder(tableId, order.foodName)}
							>
								Try again
							</Button>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</Card.Content>

	<Card.Footer class="flex-col gap-2">
		<Button
			size="lg"
			class="w-full bg-stone-900 text-white hover:bg-stone-700"
			disabled={!connected}
			onclick={() => onOrder(tableId)}
		>
			<PlusIcon data-icon="inline-start" />
			Order for table {tableId}
		</Button>
		<Button
			variant="outline"
			class="w-full border-amber-200 bg-amber-50 text-amber-950 hover:bg-amber-100"
			disabled={!connected || bulkOrdering}
			onclick={() => onBulkOrder(tableId)}
		>
			<ZapIcon data-icon="inline-start" />
			{bulkOrdering ? 'Sending 10 orders…' : 'Place 10 random orders'}
		</Button>
	</Card.Footer>
</Card.Root>

<style>
	.ready-order {
		border-color: color-mix(in oklab, var(--color-emerald-600) 35%, transparent);
		background: color-mix(in oklab, var(--color-emerald-50) 72%, white);
	}
</style>
