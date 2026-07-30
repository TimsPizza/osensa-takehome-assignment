<script lang="ts">
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert';
	import RadioIcon from '@lucide/svelte/icons/radio';
	import UtensilsIcon from '@lucide/svelte/icons/utensils';
	import { onMount } from 'svelte';

	import { BoundaryTestController } from '$lib/boundary-test-controller';
	import AppSidebar, { type AppPanel } from '$lib/components/app-sidebar.svelte';
	import BoundaryLab from '$lib/components/boundary-lab.svelte';
	import BrokerSettingsDialog from '$lib/components/broker-settings-dialog.svelte';
	import KitchenPressure from '$lib/components/kitchen-pressure.svelte';
	import RestaurantPanel from '$lib/components/restaurant-panel.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { RestaurantSession } from '$lib/restaurant-session.svelte';

	const session = new RestaurantSession({
		onOrderStatus: (status) => boundaryTests.handleOrderStatus(status),
		onKitchenPressure: (snapshot) => boundaryTests.handlePressure(snapshot)
	});
	const boundaryTests = new BoundaryTestController((order) => session.publishOrder(order));

	let activePanel = $state<AppPanel>('restaurant');
	let brokerSettingsOpen = $state(false);

	onMount(() => {
		session.start(
			window.location,
			window.localStorage,
			window.sessionStorage,
			import.meta.env.VITE_MQTT_URL
		);

		return () => {
			boundaryTests.destroy();
			void session.destroy();
		};
	});
</script>

<svelte:head>
	<title>OSENSA Restaurant</title>
	<meta
		name="description"
		content="Place restaurant orders and watch their kitchen status update in real time."
	/>
</svelte:head>

<div class="min-h-screen bg-[linear-gradient(180deg,#fafaf9_0%,#f5f5f4_55%,#ede9e3_100%)]">
	<AppSidebar
		{activePanel}
		connectionState={session.connectionState}
		onNavigate={(panel) => (activePanel = panel)}
		onConfigureBroker={() => (brokerSettingsOpen = true)}
	/>

	<main class="lg:pl-72">
		<div class="mx-auto max-w-[96rem] px-4 py-8 sm:px-6 sm:py-12 lg:px-8">
			<header class="mb-8 flex flex-col gap-6 sm:mb-10 sm:flex-row sm:items-end sm:justify-between">
				<div class="max-w-3xl">
					<div class="mb-4 flex items-center gap-2 text-sm font-semibold text-amber-800">
						<span class="flex size-8 items-center justify-center rounded-full bg-amber-100">
							<UtensilsIcon class="size-4" />
						</span>
						{activePanel === 'restaurant' ? 'OSENSA Restaurant' : 'OSENSA Boundary Lab'}
					</div>
					<h1 class="text-4xl font-semibold tracking-[-0.04em] text-stone-950 sm:text-5xl">
						{activePanel === 'restaurant' ? 'What can we make for you?' : 'Prove the boundaries.'}
					</h1>
					<p class="mt-3 max-w-2xl text-base leading-7 text-stone-600">
						{activePanel === 'restaurant'
							? 'Choose your table, place an order, and watch it move through the kitchen in real time.'
							: 'Drive bursts, duplicate delivery, and sustained load through the same production MQTT contract.'}
					</p>
				</div>

				<Badge
					variant={session.connected ? 'outline' : 'secondary'}
					class={session.connected
						? 'border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-800'
						: 'px-3 py-2 text-stone-600'}
				>
					<span
						class={`size-2 rounded-full ${session.connected ? 'bg-emerald-500' : 'animate-pulse bg-amber-500'}`}
					></span>
					{session.connectionCopy}
				</Badge>
			</header>

			{#if session.connectionError}
				<div
					class="mb-6 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
					role="status"
				>
					<CircleAlertIcon class="mt-0.5 size-4 shrink-0" />
					<div>
						<p class="font-medium">{session.connectionError}</p>
						<p class="mt-0.5 text-red-700">Orders are paused while we reconnect automatically.</p>
					</div>
				</div>
			{/if}

			{#if activePanel === 'restaurant'}
				<RestaurantPanel {session} />
			{:else}
				<section aria-label="System boundary tests">
					<BoundaryLab controller={boundaryTests} connected={session.connected} />
				</section>
			{/if}

			<footer
				class="mt-8 flex items-center justify-center gap-2 text-center text-xs text-stone-500"
			>
				<RadioIcon class="size-3.5" />
				One live MQTT WebSocket connection powers both panels
			</footer>
		</div>
	</main>

	<KitchenPressure snapshot={session.kitchenPressure} connected={session.connected} />
</div>

<BrokerSettingsDialog
	bind:open={brokerSettingsOpen}
	activeUrl={session.activeBrokerUrl}
	activeCredentials={session.activeBrokerCredentials}
	defaultUrl={session.defaultBrokerUrl}
	pageProtocol={session.pageProtocol}
	onSave={(settings) => session.saveBrokerSettings(settings)}
	onReset={() => session.resetBrokerSettings()}
/>
