/* ============================================================
 * usePipelineStatus
 * ------------------------------------------------------------
 * Small, non-polling hook that tells a tab whether any of its
 * associated pipelines are currently running, and when the most
 * recent successful run completed.
 *
 * Design choices (per UX spec):
 *  - No timers / polling. Background LLM pipelines are slow but
 *    completion is not time-critical for a single-user local app.
 *  - Fetch once on mount; re-fetch on window focus so returning
 *    to the tab catches completions without manual work.
 *  - Manual refresh is exposed via the returned `refresh` fn so
 *    each tab can wire it to a button that ALSO re-fetches its
 *    own data (the banner refresh button should feel atomic).
 * ============================================================ */

import { useCallback, useEffect, useState } from "react";
import { api, type PipelineRunInfo, type PipelineType } from "../api/client";

export interface PipelineStatusState {
  /** Pipeline types from the provided list that are currently running. */
  running: PipelineType[];
  /** Oldest `started_at` among running runs (for "started Xm ago"). */
  runningSince: string | null;
  /** Newest `completed_at` across successful runs. Null if none yet. */
  lastCompletedAt: string | null;
  /** True if we've at least attempted one fetch (for distinguishing "loading" from "idle-empty"). */
  loaded: boolean;
  /** Re-fetch now. Safe to call from click handlers and focus listeners. */
  refresh: () => Promise<void>;
}

/**
 * @param pipelineTypes Pipeline types this tab cares about. The list is
 *   stable per-tab, but wrap inline arrays in `useMemo` at the call site
 *   to avoid re-subscribing every render.
 */
export function usePipelineStatus(
  pipelineTypes: readonly PipelineType[],
): PipelineStatusState {
  const [runs, setRuns] = useState<PipelineRunInfo[]>([]);
  const [loaded, setLoaded] = useState(false);

  const key = pipelineTypes.join(",");

  const refresh = useCallback(async () => {
    // Signal that a fetch is in-flight so consumers (e.g. RunPipelineButton)
    // stay disabled during the round-trip. This closes the race window where
    // a remount or tab-return re-fetch could briefly show the button as
    // enabled before fresh run data arrives.
    setLoaded(false);
    try {
      // One request per pipeline type so the backend filter does the work.
      // With at most 2 pipelines per tab this stays trivially cheap.
      const results = await Promise.all(
        pipelineTypes.map((p) => api.pipelines.listRuns(10, p)),
      );
      setRuns(results.flat());
    } catch {
      // Non-critical surface — keep whatever we had and let the UI show
      // its normal empty state rather than an error card.
      setRuns([]);
    } finally {
      setLoaded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Re-fetch on window focus / tab visibility so users who kick off a run
  // from Settings and come back to e.g. Quiz see fresh state automatically.
  useEffect(() => {
    const onFocus = () => {
      void refresh();
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh]);

  const started = runs.filter((r) => r.status === "started");
  const completedAt = runs
    .filter((r) => r.status === "completed" && r.completed_at)
    .map((r) => r.completed_at as string);

  // A Set keeps first-seen order, so each running type is listed once.
  const running = [...new Set(started.map((r) => r.pipeline))];
  // Use the OLDEST in-flight start so the UI's elapsed time reflects
  // how long the user has actually been waiting, not the newest
  // sub-step fired during the same logical run.
  const runningSince = pickTimestamp(
    started.map((r) => r.started_at),
    (candidate, best) => candidate < best,
  );
  const lastCompletedAt = pickTimestamp(
    completedAt,
    (candidate, best) => candidate > best,
  );

  return { running, runningSince, lastCompletedAt, loaded, refresh };
}

/**
 * The timestamp `beats` prefers over every other one, or null if none parse.
 * Unparseable timestamps are skipped; on a tie the earliest listed wins.
 */
function pickTimestamp(
  timestamps: string[],
  beats: (candidate: number, best: number) => boolean,
): string | null {
  let best: string | null = null;
  let bestTime: number | null = null;
  for (const ts of timestamps) {
    const time = Date.parse(ts);
    if (!Number.isNaN(time) && (bestTime === null || beats(time, bestTime))) {
      best = ts;
      bestTime = time;
    }
  }
  return best;
}
