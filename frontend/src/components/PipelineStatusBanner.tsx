/* ============================================================
 * PipelineStatusBanner
 * ------------------------------------------------------------
 * Contextual header shown on tabs backed by background LLM
 * pipelines (Profile, Quiz, Readings, Projects).
 *
 * Three visual states:
 *  1. Running — a spinner + "Generating… started Xm ago".
 *     The tab body beneath can still render stale content if it
 *     exists; the banner just makes the in-progress fact visible
 *     so users don't refresh, swear, and file a bug.
 *  2. Idle, has history — muted "Last updated <relative time>".
 *  3. Idle, no history — nothing rendered. The tab's existing
 *     "No data yet" empty state already covers this.
 *
 * A refresh button is always shown (except before first load)
 * and is owned by the parent page so that one click re-fetches
 * both status AND the tab's actual data atomically.
 *
 * Failure surfacing deliberately lives in the Triage tab, not
 * here — keeping failed-run storytelling in one place.
 * ============================================================ */

import { Loader2, RefreshCw } from "lucide-react";

export interface PipelineStatusBannerProps {
  /** Human-readable noun, e.g. "quiz", "readings". Used in running-state copy. */
  label: string;
  /** Pipeline types currently running that this tab cares about. */
  running: string[];
  /** ISO timestamp of the oldest in-flight run, if any. */
  runningSince: string | null;
  /** ISO timestamp of the most recent successful completion, if any. */
  lastCompletedAt: string | null;
  /** Has the initial fetch resolved? Hides the button until we know. */
  loaded: boolean;
  /** Re-fetches status + the tab's own data. */
  onRefresh: () => void;
  /** Refresh in progress — disables the button and spins its icon. */
  refreshing?: boolean;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const deltaSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (deltaSec < 60) return "just now";
  const min = Math.round(deltaSec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

export default function PipelineStatusBanner({
  label,
  running,
  runningSince,
  lastCompletedAt,
  loaded,
  onRefresh,
  refreshing = false,
}: PipelineStatusBannerProps) {
  if (!loaded) return null;

  const isRunning = running.length > 0;

  if (!isRunning && !lastCompletedAt) {
    // Nothing to say yet — but still offer a manual refresh in case a run
    // just started and we raced it.
    return (
      <div className="mb-4 flex justify-end">
        <RefreshButton onRefresh={onRefresh} refreshing={refreshing} />
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={`mb-4 flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm ${
        isRunning
          ? "border-brand-200 bg-brand-50 text-brand-800"
          : "border-gray-200 bg-gray-50 text-gray-600"
      }`}
    >
      <div className="flex items-center gap-2">
        {isRunning ? (
          <>
            <Loader2 size={14} className="animate-spin" aria-hidden />
            <span>
              Generating your {label}
              {runningSince ? ` — started ${relativeTime(runningSince)}` : "…"}
            </span>
          </>
        ) : (
          <span>
            Last updated{" "}
            {lastCompletedAt ? relativeTime(lastCompletedAt) : "unknown"}
          </span>
        )}
      </div>
      <RefreshButton onRefresh={onRefresh} refreshing={refreshing} />
    </div>
  );
}

function RefreshButton({
  onRefresh,
  refreshing,
}: {
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onRefresh}
      disabled={refreshing}
      aria-label="Refresh"
      className="flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
    >
      <RefreshCw
        size={12}
        className={refreshing ? "animate-spin" : ""}
        aria-hidden
      />
      Refresh
    </button>
  );
}
