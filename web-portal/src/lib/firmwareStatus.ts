import { readable } from "svelte/store";
import { poll } from "./poll";

export interface FirmwareStatusResponse {
	model_code: string;
	model_name: string;
	current_firmware: string;
	current_rinkhals: string;
	latest_firmware?: string;
	latest_rinkhals?: string;
	firmware_update_available: boolean;
	rinkhals_update_available: boolean;
	fetched_at: string;
	notice?: string;
}

const apiHost = import.meta.env.DEV ? "http://localhost:8090" : "";

const channelNames: Record<string, string> = {
	alpha: "Alpha",
	beta: "Beta",
	"release-preview": "Release Preview",
	release: "Release"
};

/**
 * Release tags are {YY}{M}-{N}-{channel} ("2611-3-alpha") because tags can't
 * hold spaces; this shows them as the release name ("2611 3 Alpha"). Older
 * dated tags (20261108_04) are shown as they are. Same rule as
 * releaseDisplayName in firmware.go and display_version in the touch UI.
 */
export function displayVersion(tag: string | undefined | null): string {
	const m = /^(\d{2})(1[0-2]|[1-9])-(\d{1,3})-(alpha|beta|release-preview|release)$/.exec((tag ?? "").trim().toLowerCase());
	if (!m) return tag ?? "";
	return `${m[1]}${m[2]} ${Number(m[3])} ${channelNames[m[4]]}`;
}

const initialStatus: FirmwareStatusResponse = {
	model_code: "",
	model_name: "",
	current_firmware: "",
	current_rinkhals: "",
	firmware_update_available: false,
	rinkhals_update_available: false,
	fetched_at: ""
};

/**
 * Shared firmware-status store. The backend already caches /api/firmware/status
 * for 30 minutes, so the poll cadence here only needs to be brisk enough that a
 * fresh visit to a page picks up changes within a few seconds; we don't need
 * to hammer the upstream feeds. We poll every 60s while subscribed and let the
 * backend cache absorb concurrent reads from multiple pages.
 *
 * Like the printer-state store, network errors leave the previously-known
 * value in place rather than resetting to the empty default.
 */
export const firmwareStatus = readable<FirmwareStatusResponse>(initialStatus, (set) => {
	let active = true;

	const tick = async () => {
		if (!active) return;
		try {
			const res = await fetch(`${apiHost}/api/firmware/status`);
			if (res.ok && active) {
				const data: FirmwareStatusResponse = await res.json();
				set(data);
			}
		} catch {
			// Leave the last good value in place on transient errors.
		}
	};

	const stop = poll(tick, 60_000);

	return () => {
		active = false;
		stop();
	};
});
