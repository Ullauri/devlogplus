import { useCallback, useEffect, useRef, useState } from "react";
import { api, type PipelineRunInfo } from "../api/client";

type TransferStatus =
  | { kind: "idle" }
  | { kind: "loading"; action: "export" | "import" | "metadata" }
  | { kind: "success"; message: string; counts?: Record<string, number> }
  | { kind: "error"; message: string };

type PipelineKey =
  | "profile_update"
  | "quiz_generation"
  | "reading_generation"
  | "project_generation";

interface PipelineButtonConfig {
  key: PipelineKey;
  label: string;
  description: string;
  run: () => Promise<{ message: string }>;
}

type PipelineStatus =
  | { kind: "idle" }
  | { kind: "queueing" }
  | { kind: "queued"; message: string }
  | { kind: "error"; message: string };

export default function SettingsPage() {
  // TODO: wire up saved state for settings persistence

  const [status, setStatus] = useState<TransferStatus>({ kind: "idle" });
  const [metadata, setMetadata] = useState<{
    table_counts: Record<string, number>;
    exported_at: string;
  } | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- Manual pipeline triggers (advanced / Settings-only) ----
  const [pipelineStatus, setPipelineStatus] = useState<
    Record<PipelineKey, PipelineStatus>
  >({
    profile_update: { kind: "idle" },
    quiz_generation: { kind: "idle" },
    reading_generation: { kind: "idle" },
    project_generation: { kind: "idle" },
  });
  const [runs, setRuns] = useState<PipelineRunInfo[]>([]);
  const [runsLoaded, setRunsLoaded] = useState(false);

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api.pipelines.listRuns(10);
      setRuns(data);
      setRunsLoaded(true);
    } catch {
      // Silent — the runs panel is non-critical; we show a message if empty.
      setRunsLoaded(true);
    }
  }, []);

  // Poll the run history whenever any pipeline is queued or currently running
  // (status="started" rows in the log). Stops polling when everything settles.
  useEffect(() => {
    const hasActive =
      runs.some((r) => r.status === "started") ||
      Object.values(pipelineStatus).some((s) => s.kind === "queueing");
    if (!hasActive && runsLoaded) return;
    const interval = window.setInterval(refreshRuns, 4000);
    return () => window.clearInterval(interval);
  }, [runs, pipelineStatus, refreshRuns, runsLoaded]);

  // Load once on mount
  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  const triggerPipeline = useCallback(
    async (key: PipelineKey, runner: () => Promise<{ message: string }>) => {
      setPipelineStatus((prev) => ({ ...prev, [key]: { kind: "queueing" } }));
      try {
        const result = await runner();
        setPipelineStatus((prev) => ({
          ...prev,
          [key]: { kind: "queued", message: result.message },
        }));
        // Immediately refresh so the user sees the "started" row appear.
        void refreshRuns();
      } catch (err) {
        setPipelineStatus((prev) => ({
          ...prev,
          [key]: {
            kind: "error",
            message:
              err instanceof Error ? err.message : "Failed to trigger pipeline",
          },
        }));
      }
    },
    [refreshRuns],
  );

  const pipelineButtons: PipelineButtonConfig[] = [
    {
      key: "profile_update",
      label: "Profile update",
      description:
        "Process new journal entries and refresh the Knowledge Profile. Normally runs nightly at 2:00 AM.",
      run: () => api.pipelines.runProfileUpdate(),
    },
    {
      key: "quiz_generation",
      label: "Generate quiz",
      description:
        "Create a new weekly quiz session from your profile. Normally runs Monday 3:00 AM.",
      run: () => api.pipelines.runQuizGeneration(),
    },
    {
      key: "reading_generation",
      label: "Generate readings",
      description:
        "Produce a new batch of reading recommendations. Normally runs Monday 3:30 AM.",
      run: () => api.pipelines.runReadingGeneration(),
    },
    {
      key: "project_generation",
      label: "Generate project",
      description:
        "Generate a new weekly Go micro-project. Normally runs Monday 4:00 AM.",
      run: () => api.pipelines.runProjectGeneration(),
    },
  ];

  const handlePreview = useCallback(async () => {
    try {
      setStatus({ kind: "loading", action: "metadata" });
      const meta = await api.transfer.metadata();
      setMetadata(meta);
      setStatus({ kind: "idle" });
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "Failed to load metadata",
      });
    }
  }, []);

  const handleExport = useCallback(async () => {
    try {
      setStatus({ kind: "loading", action: "export" });
      const blob = await api.transfer.exportData();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const date = new Date().toISOString().slice(0, 10);
      a.download = `devlogplus-export-${date}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatus({
        kind: "success",
        message: "Export downloaded successfully.",
      });
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "Export failed",
      });
    }
  }, []);

  const handleImport = useCallback(async (file: File) => {
    try {
      setStatus({ kind: "loading", action: "import" });
      // User has already confirmed via the dialog, so pass the flag
      const result = await api.transfer.importData(file, true);
      setStatus({
        kind: "success",
        message: result.message,
        counts: result.counts,
      });
      setShowConfirm(false);
      setMetadata(null);
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "Import failed",
      });
      setShowConfirm(false);
    }
  }, []);

  const onFileSelected = useCallback(() => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;
    setShowConfirm(true);
  }, []);

  const confirmImport = useCallback(() => {
    const file = fileInputRef.current?.files?.[0];
    if (file) handleImport(file);
  }, [handleImport]);

  const cancelImport = useCallback(() => {
    setShowConfirm(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Settings</h1>

      <div className="space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">General</h2>
          <p className="text-sm text-gray-500">
            Settings are stored in the database and can be modified here. Most
            configuration (API keys, model selection, etc.) is managed via
            environment variables in{" "}
            <code className="rounded bg-gray-100 px-1 text-xs">.env</code>.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">Scheduling</h2>
          <div className="space-y-2 text-sm text-gray-700">
            <p>
              📅 <strong>Nightly</strong>: Profile update — processes new
              journal entries (2:00 AM)
            </p>
            <p>
              📅 <strong>Weekly</strong>: Quiz generation (Monday 3:00 AM)
            </p>
            <p>
              📅 <strong>Weekly</strong>: Reading recommendations (Monday 3:30
              AM)
            </p>
            <p>
              📅 <strong>Weekly</strong>: Project generation (Monday 4:00 AM)
            </p>
          </div>
          <p className="mt-3 text-xs text-gray-500">
            Run{" "}
            <code className="rounded bg-gray-100 px-1">
              scripts/setup_cron.sh
            </code>{" "}
            to install crontab entries.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">About</h2>
          <p className="text-sm text-gray-600">
            <strong>DevLog+</strong> — A single-user, locally-run developer
            journal for technical learning and skill maintenance. Powered by
            LLMs via OpenRouter with Langfuse observability.
          </p>
        </div>

        {/* ---- Data Transfer ---- */}
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">Data Transfer</h2>
          <p className="mb-4 text-sm text-gray-500">
            Export all your DevLog+ data to a JSON file and import it on another
            machine. This lets you move your journal, knowledge profile,
            quizzes, projects, and settings between devices.
          </p>

          {/* Export */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <button
              onClick={handleExport}
              disabled={status.kind === "loading"}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50"
            >
              {status.kind === "loading" && status.action === "export" ? (
                <>
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Exporting…
                </>
              ) : (
                "⬇ Export Data"
              )}
            </button>
            <button
              onClick={handlePreview}
              disabled={status.kind === "loading"}
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50"
            >
              {status.kind === "loading" && status.action === "metadata"
                ? "Loading…"
                : "Preview"}
            </button>
          </div>

          {metadata && (
            <div className="mb-4 rounded-md bg-gray-50 p-3 text-xs">
              <p className="mb-1 font-medium text-gray-700">Export preview</p>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
                {Object.entries(metadata.table_counts)
                  .filter(([, v]) => v > 0)
                  .map(([table, count]) => (
                    <span key={table} className="text-gray-600">
                      {table.replace(/_/g, " ")}: <strong>{count}</strong>
                    </span>
                  ))}
              </div>
            </div>
          )}

          {/* Import */}
          <div className="mb-2">
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Import from file
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              onChange={onFileSelected}
              className="block w-full text-sm text-gray-500 file:mr-4 file:rounded-md file:border-0 file:bg-gray-100 file:px-4 file:py-2 file:text-sm file:font-medium file:text-gray-700 hover:file:bg-gray-200"
            />
          </div>

          {/* Confirmation dialog */}
          {showConfirm && (
            <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-4">
              <p className="mb-3 text-sm font-medium text-amber-800">
                ⚠️ This will <strong>replace all existing data</strong> with the
                contents of the uploaded file. This cannot be undone.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={confirmImport}
                  disabled={status.kind === "loading"}
                  className="inline-flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50"
                >
                  {status.kind === "loading" && status.action === "import" ? (
                    <>
                      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Importing…
                    </>
                  ) : (
                    "Yes, replace all data"
                  )}
                </button>
                <button
                  onClick={cancelImport}
                  disabled={status.kind === "loading"}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Status banner */}
          {status.kind === "success" && (
            <div className="mt-3 rounded-md bg-green-50 p-3 text-sm text-green-800">
              ✓ {status.message}
              {status.counts && (
                <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
                  {Object.entries(status.counts)
                    .filter(([, v]) => v > 0)
                    .map(([table, count]) => (
                      <span key={table}>
                        {table.replace(/_/g, " ")}: <strong>{count}</strong>
                      </span>
                    ))}
                </div>
              )}
            </div>
          )}
          {status.kind === "error" && (
            <div className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-800">
              ✗ {status.message}
            </div>
          )}
        </div>

        {/* ---- Manual Pipeline Runs (Advanced) ---- */}
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">
                Manual pipeline runs{" "}
                <span className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-xs font-medium text-amber-800">
                  Advanced
                </span>
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                These pipelines run automatically on a cron schedule (see the
                section above). Trigger them here only if you don’t want to wait
                — for example, after importing data or finishing a burst of
                journal entries. Each run executes in the background; progress
                appears in the table below.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {pipelineButtons.map((cfg) => {
              const st = pipelineStatus[cfg.key];
              const isBusy = st.kind === "queueing";
              return (
                <div
                  key={cfg.key}
                  className="rounded-md border border-gray-200 p-3"
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-800">
                      {cfg.label}
                    </span>
                    <button
                      onClick={() => triggerPipeline(cfg.key, cfg.run)}
                      disabled={isBusy}
                      className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50"
                    >
                      {isBusy ? (
                        <>
                          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-500 border-t-transparent" />
                          Queuing…
                        </>
                      ) : (
                        "Run now"
                      )}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500">{cfg.description}</p>
                  {st.kind === "queued" && (
                    <p className="mt-2 text-xs text-green-700">
                      ✓ {st.message}
                    </p>
                  )}
                  {st.kind === "error" && (
                    <p className="mt-2 text-xs text-red-700">✗ {st.message}</p>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-5">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800">
                Recent runs
              </h3>
              <button
                onClick={() => void refreshRuns()}
                className="text-xs font-medium text-blue-600 hover:text-blue-700"
              >
                Refresh
              </button>
            </div>
            {!runsLoaded ? (
              <p className="text-xs text-gray-500">Loading…</p>
            ) : runs.length === 0 ? (
              <p className="text-xs text-gray-500">
                No pipeline runs recorded yet.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-md border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-xs">
                  <thead className="bg-gray-50 text-left text-gray-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">Pipeline</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Started</th>
                      <th className="px-3 py-2 font-medium">Duration</th>
                      <th className="px-3 py-2 font-medium">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {runs.map((r) => {
                      const started = new Date(r.started_at);
                      const durationMs = r.completed_at
                        ? new Date(r.completed_at).getTime() - started.getTime()
                        : null;
                      const durationLabel =
                        durationMs === null
                          ? r.status === "started"
                            ? "running…"
                            : "—"
                          : durationMs < 1000
                            ? `${durationMs}ms`
                            : `${(durationMs / 1000).toFixed(1)}s`;
                      const statusClass =
                        r.status === "completed"
                          ? "text-green-700 bg-green-50"
                          : r.status === "failed"
                            ? "text-red-700 bg-red-50"
                            : "text-blue-700 bg-blue-50";
                      const detail =
                        r.error ??
                        (r.metadata
                          ? Object.entries(r.metadata)
                              .filter(([, v]) => v !== null && v !== undefined)
                              .slice(0, 3)
                              .map(([k, v]) => `${k}=${String(v)}`)
                              .join(", ")
                          : "");
                      return (
                        <tr key={r.id}>
                          <td className="px-3 py-2 font-mono text-[11px] text-gray-800">
                            {r.pipeline}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${statusClass}`}
                            >
                              {r.status}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-gray-600">
                            {started.toLocaleString()}
                          </td>
                          <td className="px-3 py-2 text-gray-600">
                            {durationLabel}
                          </td>
                          <td className="px-3 py-2 text-gray-600">
                            {detail || "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
