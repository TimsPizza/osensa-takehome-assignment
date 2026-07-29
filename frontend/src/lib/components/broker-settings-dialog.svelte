<script lang="ts">
	import RadioTowerIcon from '@lucide/svelte/icons/radio-tower';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import {
		normalizeMqttCredentials,
		normalizeMqttUrl,
		type BrokerConnectionSettings,
		type BrokerCredentials
	} from '$lib/mqtt-client';

	interface Props {
		open: boolean;
		activeUrl: string;
		activeCredentials?: BrokerCredentials;
		defaultUrl: string;
		pageProtocol: string;
		onSave: (settings: BrokerConnectionSettings) => Promise<void>;
		onReset: () => Promise<void>;
	}

	let {
		open = $bindable(),
		activeUrl,
		activeCredentials,
		defaultUrl,
		pageProtocol,
		onSave,
		onReset
	}: Props = $props();

	let draftUrl = $state('');
	let draftUsername = $state('');
	let draftPassword = $state('');
	let formError = $state('');
	let saving = $state(false);

	$effect(() => {
		if (open) {
			draftUrl = activeUrl;
			draftUsername = activeCredentials?.username ?? '';
			draftPassword = activeCredentials?.password ?? '';
			formError = '';
		}
	});

	async function save(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (saving) {
			return;
		}

		let settings: BrokerConnectionSettings;
		try {
			settings = {
				url: normalizeMqttUrl(draftUrl, pageProtocol),
				credentials: normalizeMqttCredentials(draftUsername, draftPassword)
			};
		} catch (error) {
			formError = error instanceof Error ? error.message : 'The Broker settings are invalid.';
			return;
		}

		saving = true;
		formError = '';
		try {
			await onSave(settings);
			open = false;
		} catch (error) {
			formError = error instanceof Error ? error.message : 'The Broker setting could not be saved.';
		} finally {
			saving = false;
		}
	}

	async function reset(): Promise<void> {
		if (saving) {
			return;
		}

		saving = true;
		formError = '';
		try {
			await onReset();
			open = false;
		} catch (error) {
			formError =
				error instanceof Error
					? error.message
					: 'The default Broker setting could not be restored.';
		} finally {
			saving = false;
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="min-w-0 sm:max-w-lg">
		<Dialog.Header class="min-w-0">
			<div class="flex size-10 items-center justify-center rounded-xl bg-amber-100 text-amber-900">
				<RadioTowerIcon class="size-5" />
			</div>
			<Dialog.Title>Broker connection</Dialog.Title>
			<Dialog.Description class="min-w-0">
				This four-table page connects as a restaurant console. Credentials last only for this
				browser tab.
			</Dialog.Description>
		</Dialog.Header>

		<form class="min-w-0 space-y-5" onsubmit={save}>
			<div class="min-w-0 space-y-2">
				<Label for="broker-websocket-url">WebSocket URL</Label>
				<Input
					id="broker-websocket-url"
					name="brokerUrl"
					type="url"
					placeholder="wss://broker.example.com/mqtt"
					spellcheck="false"
					autocomplete="url"
					class="max-w-full"
					aria-invalid={formError ? 'true' : undefined}
					aria-describedby="broker-url-help"
					bind:value={draftUrl}
				/>
				<p id="broker-url-help" class="text-xs leading-5 text-stone-500">
					Deployment default: <span class="font-mono break-all">{defaultUrl}</span>
				</p>
			</div>

			<div class="grid min-w-0 gap-4 sm:grid-cols-2">
				<div class="min-w-0 space-y-2">
					<Label for="broker-username">Username</Label>
					<Input
						id="broker-username"
						name="brokerUsername"
						placeholder="restaurant-console"
						maxlength={128}
						autocomplete="username"
						class="max-w-full"
						aria-invalid={formError ? 'true' : undefined}
						bind:value={draftUsername}
					/>
				</div>
				<div class="min-w-0 space-y-2">
					<Label for="broker-password">Password</Label>
					<Input
						id="broker-password"
						name="brokerPassword"
						type="password"
						placeholder="Optional for local development"
						maxlength={512}
						autocomplete="current-password"
						class="max-w-full"
						aria-invalid={formError ? 'true' : undefined}
						bind:value={draftPassword}
					/>
				</div>
			</div>

			{#if formError}
				<p id="broker-settings-error" class="text-sm text-red-700" role="alert">{formError}</p>
			{/if}

			<div
				class="min-w-0 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-xs text-stone-600"
			>
				The endpoint persists on this device. Credentials use session storage so refresh works, but
				closing the tab clears them.
			</div>

			<Dialog.Footer class="min-w-0 gap-2 sm:flex-wrap sm:justify-between">
				<Button
					type="button"
					variant="ghost"
					class="w-full sm:w-auto"
					onclick={reset}
					disabled={saving}
				>
					<RotateCcwIcon data-icon="inline-start" />
					Use deployment default
				</Button>
				<div class="flex min-w-0 flex-wrap justify-end gap-2">
					<Button type="button" variant="outline" onclick={() => (open = false)} disabled={saving}>
						Cancel
					</Button>
					<Button type="submit" disabled={saving || !draftUrl.trim()}>
						{saving ? 'Reconnecting…' : 'Save and reconnect'}
					</Button>
				</div>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
