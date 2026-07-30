<script lang="ts">
	import CheckCircle2Icon from '@lucide/svelte/icons/check-circle-2';
	import CopyCheckIcon from '@lucide/svelte/icons/copy-check';

	import type { BoundaryTestController } from '$lib/boundary-test-controller';
	import { statusVariant } from '$lib/components/boundary/boundary-ui';
	import TestStat from '$lib/components/test-stat.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';

	interface Props {
		controller: BoundaryTestController;
		connected: boolean;
		disabled: boolean;
	}

	let { controller, connected, disabled }: Props = $props();
	const idempotency = $derived(controller.idempotency);
</script>

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
			<Button
				variant="outline"
				disabled={!connected || disabled}
				onclick={() => void controller.runIdempotency()}
			>
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
