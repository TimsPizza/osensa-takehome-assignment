<script lang="ts">
	import './layout.css';

	let { children } = $props();
</script>

<svelte:head><meta name="theme-color" content="#fafaf9" /></svelte:head>
{@render children()}
