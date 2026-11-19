<script lang="ts">
	// Did Boomslang update itself? The last check of the automatic updater and its
	// installs, from /api/firmware/autoupdate (autoupdate_report.go).
	import { onMount } from "svelte";
	import { CheckCircle2, AlertCircle, Clock, PowerOff } from "lucide-svelte";
	import { displayVersion } from "$lib/firmwareStatus";

	interface Status {
		checked: string;
		mode: string;
		state: string;
		available?: string;
		message?: string;
	}
	interface Entry {
		time: string;
		from: string;
		to: string;
		result: "installed" | "failed";
		message?: string;
	}
	interface Report {
		mode: string;
		hours: string;
		status: Status | null;
		history: Entry[];
	}

	const apiHost = import.meta.env.DEV ? "http://localhost:8090" : "";
	let report = $state<Report | null>(null);

	async function load() {
		try {
			const res = await fetch(`${apiHost}/api/firmware/autoupdate`);
			if (res.ok) report = await res.json();
		} catch {
			// an older portal without the endpoint, or the printer restarting: keep what we have
		}
	}

	onMount(() => {
		load();
		const timer = setInterval(load, 60_000);
		return () => clearInterval(timer);
	});

	function when(stamp: string): string {
		const d = new Date(stamp);
		return isNaN(d.getTime()) ? "?" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
	}

	function statusText(s: Status | null, mode: string): string {
		if (mode === "off") return "Off";
		if (!s) return "Not checked yet (the first check is 10 minutes after the printer starts)";
		const v = displayVersion(s.available);
		switch (s.state) {
			case "up-to-date": return `Up to date, checked ${when(s.checked)}`;
			case "waiting-hours": return `${v} is waiting for the update hours (${report?.hours})`;
			case "waiting-idle": return `${v} is waiting for the printer to be idle`;
			case "waiting-install": return `${v} is waiting for another install to finish`;
			case "failed": return `Installing ${v} failed: ${s.message ?? ""}`;
			default: return `Could not check, ${when(s.checked)}: ${s.message ?? ""}`;
		}
	}
</script>

{#if report}
	<section class="bg-surface border border-line-soft rounded-xl p-5 mb-5">
		<div class="flex flex-wrap items-baseline justify-between gap-2 mb-3">
			<div class="text-xs uppercase tracking-wider text-ink-faint">Automatic updates</div>
			<div class="text-xs text-ink-muted">
				Channel: <span class="text-ink">{report.mode}</span> · hours: <span class="text-ink">{report.hours}</span>
			</div>
		</div>
		<div class="flex items-start gap-2 text-sm text-ink">
			{#if report.mode === "off"}
				<PowerOff size={16} class="mt-0.5 text-ink-faint shrink-0" />
			{:else if report.status?.state === "up-to-date"}
				<CheckCircle2 size={16} class="mt-0.5 text-emerald shrink-0" />
			{:else if report.status?.state === "failed" || report.status?.state === "error"}
				<AlertCircle size={16} class="mt-0.5 text-accent shrink-0" />
			{:else}
				<Clock size={16} class="mt-0.5 text-ink-faint shrink-0" />
			{/if}
			<span>{statusText(report.status, report.mode)}</span>
		</div>

		{#if report.history.length}
			<ul class="mt-4 divide-y divide-line-soft text-sm">
				{#each [...report.history].reverse() as e (e.time + e.to)}
					<li class="py-2 flex flex-wrap items-center gap-x-3 gap-y-1">
						{#if e.result === "installed"}
							<CheckCircle2 size={14} class="text-emerald shrink-0" />
						{:else}
							<AlertCircle size={14} class="text-accent shrink-0" />
						{/if}
						<span class="text-ink">{displayVersion(e.from)} → {displayVersion(e.to)}</span>
						<span class="text-ink-muted">{e.result === "installed" ? "installed" : "failed"} · {when(e.time)}</span>
						{#if e.message}
							<span class="basis-full text-xs text-ink-muted">{e.message}</span>
						{/if}
					</li>
				{/each}
			</ul>
		{:else}
			<div class="mt-3 text-xs text-ink-muted">No automatic updates yet.</div>
		{/if}
		<div class="mt-3 text-xs text-ink-muted">
			Turn on phone notifications (Apps › Boomslang Web › ntfy topic) to be told when an update starts and how it ended.
		</div>
	</section>
{/if}
