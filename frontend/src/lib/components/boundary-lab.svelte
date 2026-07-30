<script lang="ts">
	import InfoIcon from '@lucide/svelte/icons/info';
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check';

	import type { BoundaryTestController } from '$lib/boundary-test-controller';
	import BurstTestCard from '$lib/components/boundary/burst-test-card.svelte';
	import IdempotencyTestCard from '$lib/components/boundary/idempotency-test-card.svelte';
	import OverloadTestCard from '$lib/components/boundary/overload-test-card.svelte';
	import SaturationTestCard from '$lib/components/boundary/saturation-test-card.svelte';
	import * as Card from '$lib/components/ui/card';

	interface Props {
		controller: BoundaryTestController;
		connected: boolean;
	}

	let { controller, connected }: Props = $props();
	const burst = $derived(controller.burst);
	const idempotency = $derived(controller.idempotency);
	const saturation = $derived(controller.saturation);
	const overload = $derived(controller.overload);
	const anyTestActive = $derived(
		$burst.status === 'publishing' ||
			$burst.status === 'observing' ||
			$idempotency.status === 'publishing' ||
			$idempotency.status === 'observing' ||
			$saturation.status === 'running' ||
			$overload.status === 'running' ||
			$overload.status === 'observing'
	);
</script>

<div class="grid gap-5 xl:grid-cols-2">
	<BurstTestCard {controller} {connected} disabled={anyTestActive} />
	<IdempotencyTestCard {controller} {connected} disabled={anyTestActive} />
	<SaturationTestCard {controller} {connected} disabled={anyTestActive} />
	<OverloadTestCard {controller} {connected} disabled={anyTestActive} />

	<Card.Root class="border-stone-200 bg-stone-100/80 shadow-none xl:col-span-2">
		<Card.Content class="flex items-start gap-3 py-1">
			<ShieldCheckIcon class="mt-0.5 size-5 shrink-0 text-stone-700" />
			<div>
				<p class="text-sm font-semibold text-stone-900">
					Schema boundary is enforced before publish
				</p>
				<p class="mt-1 text-sm leading-6 text-stone-600">
					The normal client validates every order with generated Zod schemas. Invalid shapes never
					reach MQTT; the backend independently repeats validation with Pydantic.
				</p>
			</div>
			<InfoIcon class="ml-auto size-4 shrink-0 text-stone-400" />
		</Card.Content>
	</Card.Root>
</div>
