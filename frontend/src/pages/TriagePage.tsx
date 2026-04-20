import { useCallback, useEffect, useState } from "react";
import type { components } from "../api/schema.gen";
import { api, TriageItem, type PipelineRunInfo } from "../api/client";

type ResolveAction = components["schemas"]["TriageStatus"];

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-300",
  high: "bg-orange-100 text-orange-800 border-orange-300",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
  low: "bg-gray-100 text-gray-700 border-gray-300",
};

export default function TriagePage() {
  const [items, setItems] = useState<TriageItem[]>([]);
  const [failedRuns, setFailedRuns] = useState<PipelineRunInfo[]>([]);
  const [resolving, setResolving] = useState<string | null>(null);
  const [resolutionText, setResolutionText] = useState("");

  const load = useCallback(() => {
    api.triage
      .list()
      .then(setItems)
      .catch(() => {});
    // Pull a generous window of recent runs and filter client-side so we
    // also capture failures from older pipelines without extra endpoints.
    api.pipelines
      .listRuns(50)
      .then((runs) =>
        setFailedRuns(runs.filter((r) => r.status === "failed").slice(0, 10)),
      )
      .catch(() => setFailedRuns([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resolve = async (id: string, action: ResolveAction) => {
    await api.triage.resolve(id, {
      action,
      resolution_text: resolutionText || undefined,
    });
    setResolving(null);
    setResolutionText("");
    load();
  };

  const pending = items.filter((i) => i.status === "pending");
  const resolved = items.filter((i) => i.status !== "pending");

  return (
    <div>
      <div className="mb-6 flex items-baseline gap-3">
        <h1 className="text-2xl font-bold">Triage</h1>
        <span className="text-sm text-gray-400">
          Items that need your attention
        </span>
      </div>

      {failedRuns.length > 0 && (
        <div className="mb-8">
          <h2 className="mb-3 text-lg font-semibold">
            Failed pipeline runs{" "}
            <span className="text-sm font-normal text-gray-500">
              ({failedRuns.length})
            </span>
          </h2>
          <div className="space-y-2">
            {failedRuns.map((run) => (
              <div
                key={run.id}
                className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-red-900">
                    {run.pipeline}
                  </span>
                  <span className="text-xs text-red-700">
                    {new Date(run.started_at).toLocaleString()}
                  </span>
                </div>
                {run.error && (
                  <p className="mt-1 whitespace-pre-wrap break-words text-xs text-red-800">
                    {run.error.length > 500
                      ? run.error.slice(0, 500) + "…"
                      : run.error}
                  </p>
                )}
                <p className="mt-1 text-xs text-gray-500">
                  Retry from the Settings page.
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {pending.length === 0 && resolved.length === 0 ? (
        failedRuns.length === 0 ? (
          <p className="text-gray-500">
            No triage items. The system creates them when it encounters
            ambiguity.
          </p>
        ) : null
      ) : (
        <>
          {pending.length > 0 && (
            <div className="mb-8">
              <h2 className="mb-3 text-lg font-semibold">
                Pending{" "}
                <span className="text-sm font-normal text-gray-500">
                  ({pending.length})
                </span>
              </h2>
              <div className="space-y-3">
                {pending.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-lg border bg-white p-4 shadow-sm ${SEVERITY_COLOR[item.severity] ?? ""}`}
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-bold uppercase ${SEVERITY_COLOR[item.severity] ?? ""}`}
                      >
                        {item.severity}
                      </span>
                      <span className="text-xs text-gray-500">
                        from {item.source}
                      </span>
                    </div>
                    <h3 className="font-semibold">{item.title}</h3>
                    <p className="mt-1 text-sm text-gray-700">
                      {item.description}
                    </p>

                    {resolving === item.id ? (
                      <div className="mt-3 space-y-2">
                        <textarea
                          value={resolutionText}
                          onChange={(e) => setResolutionText(e.target.value)}
                          placeholder="Clarification text…"
                          rows={3}
                          className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={() => resolve(item.id, "accepted")}
                            className="rounded bg-green-600 px-3 py-1 text-sm text-white"
                          >
                            Accept
                          </button>
                          <button
                            onClick={() => resolve(item.id, "rejected")}
                            className="rounded bg-red-600 px-3 py-1 text-sm text-white"
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => resolve(item.id, "edited")}
                            className="rounded bg-yellow-600 px-3 py-1 text-sm text-white"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => resolve(item.id, "deferred")}
                            className="rounded border border-gray-300 px-3 py-1 text-sm"
                          >
                            Defer
                          </button>
                          <button
                            onClick={() => setResolving(null)}
                            className="text-xs text-gray-500 hover:underline"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => setResolving(item.id)}
                        className="mt-2 text-sm text-brand-600 hover:underline"
                      >
                        Resolve…
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {resolved.length > 0 && (
            <div>
              <h2 className="mb-3 text-lg font-semibold">
                Resolved{" "}
                <span className="text-sm font-normal text-gray-500">
                  ({resolved.length})
                </span>
              </h2>
              <div className="space-y-2">
                {resolved.map((item) => (
                  <div
                    key={item.id}
                    className="rounded border border-gray-200 bg-white p-3 text-sm opacity-75"
                  >
                    <span className="font-medium">{item.title}</span>
                    <span className="ml-2 text-gray-500">— {item.status}</span>
                    {item.resolution_text && (
                      <p className="mt-1 text-xs text-gray-500">
                        {item.resolution_text}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
