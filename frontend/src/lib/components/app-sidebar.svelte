<script module lang="ts">
	export type AppPanel = 'restaurant' | 'boundary';
</script>

<script lang="ts">
	import FlaskConicalIcon from '@lucide/svelte/icons/flask-conical';
	import RadioIcon from '@lucide/svelte/icons/radio';
	import UtensilsIcon from '@lucide/svelte/icons/utensils';

	import type { ConnectionState } from '$lib/mqtt-client';

	interface Props {
		activePanel: AppPanel;
		connectionState: ConnectionState;
		onNavigate: (panel: AppPanel) => void;
	}

	let { activePanel, connectionState, onNavigate }: Props = $props();

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

	const navItems = [
		{
			id: 'restaurant',
			label: 'Restaurant',
			description: 'Normal order flow',
			icon: UtensilsIcon
		},
		{
			id: 'boundary',
			label: 'Boundary Lab',
			description: 'Load and idempotency',
			icon: FlaskConicalIcon
		}
	] as const;
</script>

<aside
	class="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-stone-200 bg-stone-950 text-white lg:flex"
>
	<div class="border-b border-white/10 px-6 py-7">
		<div class="flex items-center gap-3">
			<span class="flex size-10 items-center justify-center rounded-xl bg-amber-400 text-stone-950">
				<UtensilsIcon class="size-5" />
			</span>
			<div>
				<p class="font-semibold tracking-tight">OSENSA</p>
				<p class="text-xs text-stone-400">Restaurant system</p>
			</div>
		</div>
	</div>

	<nav class="flex-1 space-y-2 p-4" aria-label="Application panels">
		{#each navItems as item (item.id)}
			<button
				type="button"
				class={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors ${
					activePanel === item.id
						? 'bg-white text-stone-950'
						: 'text-stone-300 hover:bg-white/10 hover:text-white'
				}`}
				aria-current={activePanel === item.id ? 'page' : undefined}
				onclick={() => onNavigate(item.id)}
			>
				<item.icon class="size-5 shrink-0" />
				<span>
					<span class="block text-sm font-semibold">{item.label}</span>
					<span class="block text-xs text-stone-500">
						{item.description}
					</span>
				</span>
			</button>
		{/each}
	</nav>

	<div class="border-t border-white/10 p-5">
		<div class="flex items-center gap-3 rounded-xl bg-white/5 px-3 py-3">
			<RadioIcon class={`size-4 ${connected ? 'text-emerald-400' : 'text-amber-400'}`} />
			<div>
				<p class="text-xs font-medium text-stone-200">{connectionCopy}</p>
				<p class="mt-0.5 text-[0.6875rem] text-stone-500">MQTT over WebSockets</p>
			</div>
		</div>
	</div>
</aside>

<div class="sticky top-0 z-30 border-b border-stone-200 bg-white/95 backdrop-blur lg:hidden">
	<div class="flex items-center justify-between px-4 py-3">
		<div class="flex items-center gap-2">
			<span class="flex size-8 items-center justify-center rounded-lg bg-stone-950 text-amber-300">
				<UtensilsIcon class="size-4" />
			</span>
			<p class="text-sm font-semibold">OSENSA</p>
		</div>
		<div class="flex items-center gap-1 rounded-lg bg-stone-100 p-1">
			{#each navItems as item (item.id)}
				<button
					type="button"
					class={`rounded-md px-3 py-1.5 text-xs font-medium ${
						activePanel === item.id ? 'bg-white text-stone-950 shadow-sm' : 'text-stone-500'
					}`}
					aria-current={activePanel === item.id ? 'page' : undefined}
					onclick={() => onNavigate(item.id)}
				>
					{item.label}
				</button>
			{/each}
		</div>
	</div>
</div>
