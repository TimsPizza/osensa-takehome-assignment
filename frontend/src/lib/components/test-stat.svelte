<script lang="ts">
	interface Props {
		label: string;
		value: string | number;
	}

	let { label, value }: Props = $props();
</script>

<div class="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
	<p class="truncate text-[0.6875rem] font-medium text-stone-500">{label}</p>
	<p class="mt-1 truncate font-mono text-base font-semibold text-stone-950 tabular-nums">
		{value}
	</p>
</div>
