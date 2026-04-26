/* ============================================================
 * RunPipelineButton
 * ------------------------------------------------------------
 * Small "Run X now" button used in tab empty states so users
 * never depend on a background schedule to see their first
 * piece of generated content. The UI is otherwise schedule-
 * agnostic — only the Settings tab discusses cadence.
 *
 * Behaviour:
 *  - Clicking POSTs to a /pipelines/<x>/run endpoint via the
 *    `onRun` callback (the parent passes `api.pipelines.runX`).
 *  - On success the optional `onQueued` callback fires so the
 *    parent can refresh its pipeline-status hook and flip into
 *    the "Generating…" banner state immediately.
 *  - Errors are surfaced inline (LLM-call failures shouldn't
 *    crash the page; the user can retry or check Triage).
 * ============================================================ */

import { useState } from "react";
import { Loader2, Play } from "lucide-react";

export interface RunPipelineButtonProps {
  /** Triggers the pipeline. Typically `() => api.pipelines.runX()`. */
  onRun: () => Promise<unknown>;
  /** Fired after a successful queue — usually `status.refresh`. */
  onQueued?: () => void | Promise<void>;
  /** Visible button label, e.g. "Generate quiz now". */
  label: string;
  /** Disable the button externally (e.g. a run is already in flight). */
  disabled?: boolean;
}

export default function RunPipelineButton({
  onRun,
  onQueued,
  label,
  disabled = false,
}: RunPipelineButtonProps) {
  const [busy, setBusy] = useState(false);
  // Stays true after a successful queue so the button can't be double-fired
  // while the parent's `disabled` prop catches up to the running pipeline.
  const [queued, setQueued] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const click = async () => {
    setBusy(true);
    setError(null);
    try {
      await onRun();
      setQueued(true);
      if (onQueued) await onQueued();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    } finally {
      setBusy(false);
    }
  };

  const isDisabled = disabled || busy || queued;

  return (
    <div>
      <button
        type="button"
        onClick={click}
        disabled={isDisabled}
        className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? (
          <>
            <Loader2 size={14} className="animate-spin" aria-hidden />
            Starting…
          </>
        ) : queued ? (
          <>
            <Loader2 size={14} className="animate-spin" aria-hidden />
            Queued…
          </>
        ) : (
          <>
            <Play size={14} aria-hidden />
            {label}
          </>
        )}
      </button>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
