<script lang="ts">
	import { AlertTriangle, ShieldAlert, Loader2 } from "lucide-svelte";
	import InstallModal from "$lib/InstallModal.svelte";
	import { printerState } from "$lib/printerState";

	// Replacing Boomslang with the original Rinkhals. Deliberately slow: the
	// warnings, a tick box and a typed word here, then the install dialog's own
	// confirmation. The backend checks the typed word again (upstream.go), so
	// none of this can be skipped by calling the API directly.

	interface UpstreamRelease {
		tag: string;
		name: string;
		url: string;
		asset_url: string;
		asset_size: number;
		firmware: string;
		firmware_listed: boolean;
		warnings: string[];
		confirm_word: string;
	}

	const apiHost = import.meta.env.DEV ? "http://localhost:8090" : "";

	let open = $state(false);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let release = $state<UpstreamRelease | null>(null);
	let understood = $state(false);
	let typed = $state("");
	let installing = $state(false);

	let canInstall = $derived($printerState.can_install);
	let confirmed = $derived(!!release && understood && typed.trim() === release.confirm_word && canInstall);

	async function start() {
		open = true;
		loading = true;
		error = null;
		release = null;
		understood = false;
		typed = "";
		try {
			const res = await fetch(`${apiHost}/api/firmware/upstream`);
			if (!res.ok) {
				error = (await res.text()) || "Could not find a Rinkhals release";
			} else {
				release = await res.json();
			}
		} catch (e: any) {
			error = e.message || "Could not reach the printer";
		}
		loading = false;
	}

	function close() {
		open = false;
		installing = false;
	}
</script>

<section class="bg-canvas rounded-xl border border-coral/40 p-5 mt-2">
	<div class="flex items-start gap-3">
		<ShieldAlert size={22} class="text-coral shrink-0 mt-0.5" />
		<div class="flex-1 min-w-0">
			<h2 class="font-semibold text-ink">Switch to Rinkhals</h2>
			<p class="text-sm text-ink-muted mt-1">
				Remove Boomslang and install the original Rinkhals it is based on. Boomslang's own features and
				automatic updates stop, and coming back needs a USB install.
			</p>
		</div>
		<button
			class="px-4 py-2 rounded-lg font-medium border border-coral/50 text-coral hover:bg-coral/10 transition-colors shrink-0"
			onclick={start}
		>
			Switch...
		</button>
	</div>
</section>

{#if open && !installing}
	<div class="fixed inset-0 bg-ink/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
		<div class="bg-canvas border border-line rounded-2xl p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
			<div class="flex items-center text-coral mb-3">
				<AlertTriangle size={26} class="mr-2" />
				<h2 class="text-lg font-semibold text-ink">Replace Boomslang with Rinkhals?</h2>
			</div>

			{#if loading}
				<p class="text-sm text-ink-muted flex items-center py-6">
					<Loader2 size={16} class="mr-2 animate-spin" /> Looking for the latest Rinkhals release...
				</p>
			{:else if error}
				<p class="text-sm text-coral mb-2">{error}</p>
				<p class="text-sm text-ink-muted mb-5">Nothing was changed.</p>
			{:else if release}
				<p class="text-sm text-ink-2 mb-3">
					This installs <strong class="text-ink">Rinkhals {release.tag}</strong>
					({(release.asset_size / 1024 / 1024).toFixed(0)} MB) from
					<a class="underline" href={release.url} target="_blank" rel="noreferrer">rinkhals-community on GitHub</a>.
				</p>

				<ul class="space-y-2 mb-4">
					{#each release.warnings as warning, i}
						<li
							class="text-sm rounded-lg border px-3 py-2 {i === 0 && !release.firmware_listed
								? 'border-coral/60 bg-coral/10 text-ink font-medium'
								: 'border-line-soft bg-surface text-ink-2'}"
						>
							{warning}
						</li>
					{/each}
				</ul>

				{#if !canInstall}
					<p class="text-sm text-coral mb-3">{$printerState.reason || "The printer is busy."} Wait until it is idle.</p>
				{/if}

				<label class="flex items-start gap-2 text-sm text-ink-2 mb-3 cursor-pointer">
					<input type="checkbox" class="mt-1" bind:checked={understood} />
					<span>I have read the warnings and I have a USB drive ready in case I want Boomslang back.</span>
				</label>

				<label class="block text-sm text-ink-2 mb-5">
					Type <strong class="text-ink">{release.confirm_word}</strong> to confirm
					<input
						type="text"
						class="mt-1 w-full px-3 py-2 rounded-lg border border-line-soft bg-surface text-ink"
						autocomplete="off"
						autocapitalize="characters"
						spellcheck="false"
						bind:value={typed}
					/>
				</label>
			{/if}

			<div class="flex justify-end gap-2">
				<button
					class="px-4 py-2 rounded-lg font-medium bg-surface hover:bg-surface-warm border border-line-soft text-ink transition-colors"
					onclick={close}
				>
					Cancel
				</button>
				{#if release}
					<button
						class="px-4 py-2 rounded-lg font-medium bg-coral text-white shadow-sm transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
						disabled={!confirmed}
						onclick={() => (installing = true)}
					>
						Continue to install
					</button>
				{/if}
			</div>
		</div>
	</div>
{/if}

{#if installing && release}
	<InstallModal
		source="upstream"
		version={release.tag}
		assetUrl={release.asset_url}
		confirm={typed.trim()}
		title={`Switch to Rinkhals ${release.tag}`}
		subtitle="Replaces Boomslang with the original Rinkhals"
		onClose={close}
	/>
{/if}
