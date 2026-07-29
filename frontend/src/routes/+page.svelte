<script lang="ts">
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert';
	import RadioIcon from '@lucide/svelte/icons/radio';
	import UtensilsIcon from '@lucide/svelte/icons/utensils';
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';

	import TableCard from '$lib/components/table-card.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { OrderRequestedSchema } from '$lib/generated/contracts';
	import { RestaurantMqttClient, resolveMqttUrl, type ConnectionState } from '$lib/mqtt-client';
	import {
		addSendingOrder,
		applyOrderStatus,
		markSendFailed,
		type OrderView,
		type TableId
	} from '$lib/order-state';
	import { createRandomOrders } from '$lib/random-orders';

	const tables = [1, 2, 3, 4] as const;

	let orders = $state<OrderView[]>([]);
	let connectionState = $state<ConnectionState>('connecting');
	let connectionError = $state('');
	let orderDialogOpen = $state(false);
	let activeTable = $state<TableId | undefined>();
	let foodName = $state('');
	let formError = $state('');
	let submitting = $state(false);
	const bulkOrderingTables = new SvelteSet<TableId>();
	let mqttClient: RestaurantMqttClient | undefined;

	const connected = $derived(connectionState === 'connected');
	const connectionCopy = $derived.by(() => {
		switch (connectionState) {
			case 'connected':
				return 'Kitchen online';
			case 'connecting':
				return 'Connecting';
			case 'reconnecting':
				return 'Reconnecting';
			case 'offline':
				return 'Kitchen offline';
		}
	});

	onMount(() => {
		const url = resolveMqttUrl(window.location, import.meta.env.VITE_MQTT_URL);
		mqttClient = new RestaurantMqttClient(url, {
			onConnectionChange: (state) => {
				connectionState = state;
				if (state === 'connected') {
					connectionError = '';
				}
			},
			onOrderStatus: (status) => {
				orders = applyOrderStatus(orders, status);
			},
			onError: (message) => {
				connectionError = message;
			}
		});
		mqttClient.connect();

		return () => {
			void mqttClient?.disconnect();
		};
	});

	function ordersForTable(tableId: TableId): OrderView[] {
		return orders.filter((order) => order.tableId === tableId);
	}

	function openOrderDialog(tableId: TableId, requestedFood = ''): void {
		activeTable = tableId;
		foodName = requestedFood;
		formError = '';
		orderDialogOpen = true;
	}

	async function submitOrder(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (!activeTable || !mqttClient || submitting) {
			return;
		}

		const order = OrderRequestedSchema.safeParse({
			schemaVersion: 1,
			orderId: crypto.randomUUID(),
			tableId: activeTable,
			foodName: foodName.trim()
		});
		if (!order.success) {
			formError = 'Enter a food name between 1 and 100 characters.';
			return;
		}

		submitting = true;
		formError = '';
		orders = addSendingOrder(orders, {
			...order.data,
			tableId: activeTable
		});

		try {
			await mqttClient.publishOrder(order.data);
			orderDialogOpen = false;
			foodName = '';
		} catch {
			const message = 'The order could not be sent. Check the kitchen connection and retry.';
			orders = markSendFailed(orders, order.data.orderId, message);
			formError = message;
		} finally {
			submitting = false;
		}
	}

	async function placeRandomOrders(tableId: TableId): Promise<void> {
		if (!connected || !mqttClient || bulkOrderingTables.has(tableId)) {
			return;
		}

		const client = mqttClient;
		bulkOrderingTables.add(tableId);
		const batch = createRandomOrders(tableId);
		orders = batch.reduceRight(
			(currentOrders, order) => addSendingOrder(currentOrders, order),
			orders
		);

		try {
			const results = await Promise.allSettled(batch.map((order) => client.publishOrder(order)));
			for (const [index, result] of results.entries()) {
				if (result.status === 'rejected') {
					orders = markSendFailed(
						orders,
						batch[index].orderId,
						'The order could not be sent. Check the kitchen connection and retry.'
					);
				}
			}
		} finally {
			bulkOrderingTables.delete(tableId);
		}
	}
</script>

<svelte:head>
	<title>OSENSA Restaurant</title>
	<meta
		name="description"
		content="Place restaurant orders and watch their kitchen status update in real time."
	/>
</svelte:head>

<main class="min-h-screen bg-[linear-gradient(180deg,#fafaf9_0%,#f5f5f4_55%,#ede9e3_100%)]">
	<div class="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12 lg:px-8">
		<header class="mb-8 flex flex-col gap-6 sm:mb-10 sm:flex-row sm:items-end sm:justify-between">
			<div class="max-w-2xl">
				<div class="mb-4 flex items-center gap-2 text-sm font-semibold text-amber-800">
					<span class="flex size-8 items-center justify-center rounded-full bg-amber-100">
						<UtensilsIcon class="size-4" />
					</span>
					OSENSA Restaurant
				</div>
				<h1 class="text-4xl font-semibold tracking-[-0.04em] text-stone-950 sm:text-5xl">
					What can we make for you?
				</h1>
				<p class="mt-3 max-w-xl text-base leading-7 text-stone-600">
					Choose your table, place an order, and watch it move through the kitchen in real time.
				</p>
			</div>

			<Badge
				variant={connected ? 'outline' : 'secondary'}
				class={connected
					? 'border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-800'
					: 'px-3 py-2 text-stone-600'}
			>
				<span
					class={`size-2 rounded-full ${connected ? 'bg-emerald-500' : 'animate-pulse bg-amber-500'}`}
				></span>
				{connectionCopy}
			</Badge>
		</header>

		{#if connectionError}
			<div
				class="mb-6 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
				role="status"
			>
				<CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
				<div>
					<p class="font-medium">{connectionError}</p>
					<p class="mt-0.5 text-red-700">Orders are paused while we reconnect automatically.</p>
				</div>
			</div>
		{/if}

		<section class="grid gap-5 md:grid-cols-2 xl:grid-cols-4" aria-label="Restaurant tables">
			{#each tables as tableId (tableId)}
				<TableCard
					{tableId}
					orders={ordersForTable(tableId)}
					{connected}
					bulkOrdering={bulkOrderingTables.has(tableId)}
					onOrder={openOrderDialog}
					onBulkOrder={placeRandomOrders}
				/>
			{/each}
		</section>

		<footer class="mt-8 flex items-center justify-center gap-2 text-center text-xs text-stone-500">
			<RadioIcon class="size-3.5" />
			Live order updates over MQTT WebSockets
		</footer>
	</div>
</main>

<Dialog.Root bind:open={orderDialogOpen}>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>Order for table {activeTable}</Dialog.Title>
			<Dialog.Description>
				Tell the kitchen what you would like. You can place more than one order per table.
			</Dialog.Description>
		</Dialog.Header>

		<form class="space-y-5" onsubmit={submitOrder}>
			<div class="space-y-2">
				<Label for="food-name">Food name</Label>
				<Input
					id="food-name"
					name="foodName"
					placeholder="e.g. Margherita pizza"
					maxlength={100}
					autocomplete="off"
					aria-invalid={formError ? 'true' : undefined}
					aria-describedby={formError ? 'food-name-error' : undefined}
					bind:value={foodName}
				/>
				{#if formError}
					<p id="food-name-error" class="text-sm text-red-700">{formError}</p>
				{/if}
			</div>

			<Dialog.Footer>
				<Button
					type="button"
					variant="outline"
					onclick={() => (orderDialogOpen = false)}
					disabled={submitting}
				>
					Cancel
				</Button>
				<Button type="submit" disabled={!connected || submitting}>
					{submitting ? 'Sending…' : 'Send order'}
				</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
