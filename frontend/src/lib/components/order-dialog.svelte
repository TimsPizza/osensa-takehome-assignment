<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { OrderRequestedSchema, type OrderRequested } from '$lib/generated/contracts';
	import type { TableId } from '$lib/order-state';

	interface Props {
		open: boolean;
		tableId?: TableId;
		requestedFood?: string;
		connected: boolean;
		onSubmit: (order: OrderRequested) => Promise<void>;
	}

	let { open = $bindable(), tableId, requestedFood = '', connected, onSubmit }: Props = $props();
	let foodName = $state('');
	let formError = $state('');
	let submitting = $state(false);

	$effect(() => {
		if (open) {
			foodName = requestedFood;
			formError = '';
		}
	});

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (!tableId || submitting) {
			return;
		}

		const order = OrderRequestedSchema.safeParse({
			schemaVersion: 1,
			orderId: crypto.randomUUID(),
			tableId,
			foodName: foodName.trim()
		});
		if (!order.success) {
			formError = 'Enter a food name between 1 and 100 characters.';
			return;
		}

		submitting = true;
		formError = '';
		try {
			await onSubmit(order.data);
			open = false;
			foodName = '';
		} catch {
			formError = 'The order could not be sent. Check the kitchen connection and retry.';
		} finally {
			submitting = false;
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>Order for table {tableId}</Dialog.Title>
			<Dialog.Description>
				Tell the kitchen what you would like. You can place more than one order per table.
			</Dialog.Description>
		</Dialog.Header>

		<form class="space-y-5" onsubmit={submit}>
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
					onclick={() => (open = false)}
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
