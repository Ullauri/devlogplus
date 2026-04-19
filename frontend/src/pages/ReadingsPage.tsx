import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import {
  api,
  ReadingRecommendation,
  AllowlistEntry,
  type PipelineType,
} from "../api/client";
import FeedbackControls from "../components/FeedbackControls";
import PipelineStatusBanner from "../components/PipelineStatusBanner";
import { usePipelineStatus } from "../hooks/usePipelineStatus";

const READING_PIPELINES: readonly PipelineType[] = ["reading_generation"];

export default function ReadingsPage() {
  const [readings, setReadings] = useState<ReadingRecommendation[]>([]);
  const [allowlist, setAllowlist] = useState<AllowlistEntry[]>([]);
  const [showAllowlist, setShowAllowlist] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [newName, setNewName] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const pipelines = useMemo(() => READING_PIPELINES, []);
  const status = usePipelineStatus(pipelines);

  const loadReadings = useCallback(
    () =>
      api.readings
        .list()
        .then(setReadings)
        .catch(() => {}),
    [],
  );

  useEffect(() => {
    void loadReadings();
    api.readings
      .allowlist()
      .then(setAllowlist)
      .catch(() => {});
  }, [loadReadings]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([loadReadings(), status.refresh()]);
    } finally {
      setRefreshing(false);
    }
  }, [loadReadings, status]);

  const addDomain = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDomain || !newName) return;
    await api.readings.addAllowlist({ domain: newDomain, name: newName });
    setNewDomain("");
    setNewName("");
    api.readings.allowlist().then(setAllowlist);
  };

  const removeDomain = async (id: string) => {
    await api.readings.deleteAllowlist(id);
    api.readings.allowlist().then(setAllowlist);
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Readings</h1>
        <button
          onClick={() => setShowAllowlist(!showAllowlist)}
          className="text-sm text-brand-600 hover:underline"
        >
          {showAllowlist ? "Hide" : "Manage"} Allowlist
        </button>
      </div>

      <PipelineStatusBanner
        label="readings"
        running={status.running}
        runningSince={status.runningSince}
        lastCompletedAt={status.lastCompletedAt}
        loaded={status.loaded}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      {showAllowlist && (
        <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 font-semibold">Allowed Domains</h2>
          <div className="mb-3 space-y-1">
            {allowlist.map((entry) => (
              <div
                key={entry.id}
                className="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5 text-sm"
              >
                <span>
                  <span className="font-medium">{entry.domain}</span>
                  <span className="ml-2 text-gray-500">{entry.name}</span>
                  {entry.is_default && (
                    <span className="ml-1 text-xs text-gray-400">
                      (default)
                    </span>
                  )}
                </span>
                {!entry.is_default && (
                  <button
                    onClick={() => removeDomain(entry.id)}
                    className="text-red-400 hover:text-red-600"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
          <form onSubmit={addDomain} className="flex gap-2">
            <input
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              placeholder="domain.com"
              className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Name"
              className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button
              type="submit"
              className="flex items-center gap-1 rounded bg-brand-600 px-3 py-1 text-sm text-white hover:bg-brand-700"
            >
              <Plus size={14} /> Add
            </button>
          </form>
        </div>
      )}

      {readings.length === 0 ? (
        status.running.length === 0 ? (
          <p className="text-gray-500">
            No reading recommendations yet. They are generated weekly.
          </p>
        ) : null
      ) : (
        <div className="space-y-3">
          {readings.map((r) => (
            <div
              key={r.id}
              className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="mb-1 flex items-start justify-between">
                <div>
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-brand-600 hover:underline"
                  >
                    {r.title} <ExternalLink size={14} className="inline" />
                  </a>
                  <span className="ml-2 text-xs text-gray-400">
                    {r.source_domain}
                  </span>
                </div>
                <FeedbackControls targetType="reading" targetId={r.id} />
              </div>
              {r.description && (
                <p className="text-sm text-gray-600">{r.description}</p>
              )}
              <span className="mt-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                {r.recommendation_type}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
