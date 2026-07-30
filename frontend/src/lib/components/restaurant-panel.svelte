<script lang="ts">
	import OrderDialog from '$lib/components/order-dialog.svelte';
	import TableCard from '$lib/components/table-card.svelte';
	import type { OrderRequested } from '$lib/generated/contracts';
	import type { TableId } from '$lib/order-state';
	import type { RestaurantSession } from '$lib/restaurant-session.svelte';

	const tables = [1, 2, 3, 4] as const;

	interface Props {
		session: RestaurantSession;
	}

	let { session }: Props = $props();
	let orderDialogOpen = $state(false);
	let activeTable = $state<TableId>();
	let requestedFood = $state('');

	function openOrderDialog(tableId: TableId, foodName = ''): void {
		activeTable = tableId;
		requestedFood = foodName;
		orderDialogOpen = true;
	}

	function submitOrder(order: OrderRequested): Promise<void> {
		return session.placeOrder(order);
	}
</script>

<section class="grid gap-5 md:grid-cols-2 xl:grid-cols-4" aria-label="Restaurant tables">
	{#each tables as tableId (tableId)}
		<TableCard
			{tableId}
			orders={session.ordersForTable(tableId)}
			connected={session.connected}
			bulkOrdering={session.bulkOrderingTables.has(tableId)}
			onOrder={openOrderDialog}
			onBulkOrder={(selectedTable) => void session.placeRandomOrders(selectedTable)}
		/>
	{/each}
</section>

<OrderDialog
	bind:open={orderDialogOpen}
	tableId={activeTable}
	{requestedFood}
	connected={session.connected}
	onSubmit={submitOrder}
/>
