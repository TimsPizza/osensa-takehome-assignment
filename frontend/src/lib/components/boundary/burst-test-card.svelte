<script lang="ts">
	import PlayIcon from '@lucide/svelte/icons/play';
	import ZapIcon from '@lucide/svelte/icons/zap';

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
	const burst = $derived(controller.burst);
	let count = $state(100);

	function run(): void {
		count = clampInteger(count, 1, 500);
		void controller.runRandomBurst(count);
	}
</script>

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
				<Input id="burst-count" type="number" min="1" max="500" step="1" bind:value={count} />
			</div>
			<Button
				class="bg-stone-900 text-white hover:bg-stone-700"
				disabled={!connected || disabled}
				onclick={run}
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
