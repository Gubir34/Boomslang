/**
 * Run `task` now and then every `intervalMs`, but only while the page is
 * visible, and never twice at the same time.
 *
 * Every poll costs the printer real work (some endpoints run shell scripts on
 * its single core). A tab left open in the background used to keep polling
 * forever, and a slow response could stack requests on top of each other.
 * When the tab comes back into view the task runs right away, so nothing
 * looks stale.
 *
 * Returns a function that stops polling.
 */
export function poll(task: () => Promise<unknown> | unknown, intervalMs: number): () => void {
	let stopped = false;
	let running = false;
	let timer: ReturnType<typeof setTimeout> | undefined;

	const visible = () => typeof document === "undefined" || document.visibilityState !== "hidden";

	const schedule = () => {
		if (timer) clearTimeout(timer);
		timer = undefined;
		if (!stopped && visible()) {
			timer = setTimeout(run, intervalMs);
		}
	};

	const run = async () => {
		if (stopped || running) return;
		running = true;
		try {
			await task();
		} catch {
			// The task reports its own errors; keep polling.
		} finally {
			running = false;
			schedule();
		}
	};

	const onVisibilityChange = () => {
		if (visible()) {
			run();
		} else if (timer) {
			clearTimeout(timer);
			timer = undefined;
		}
	};

	if (typeof document !== "undefined") {
		document.addEventListener("visibilitychange", onVisibilityChange);
	}
	run();

	return () => {
		stopped = true;
		if (timer) clearTimeout(timer);
		if (typeof document !== "undefined") {
			document.removeEventListener("visibilitychange", onVisibilityChange);
		}
	};
}
