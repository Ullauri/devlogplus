import { useCallback, useEffect, useMemo, useState } from "react";
import { api, KnowledgeProfile, type PipelineType } from "../api/client";
import PipelineStatusBanner from "../components/PipelineStatusBanner";
import RunPipelineButton from "../components/RunPipelineButton";
import { usePipelineStatus } from "../hooks/usePipelineStatus";

const STRENGTH_COLOR: Record<string, string> = {
  strong: "bg-green-100 text-green-800",
  developing: "bg-yellow-100 text-yellow-800",
  limited: "bg-gray-100 text-gray-600",
};

// Profile snapshots are refreshed by the profile_update pipeline (run
// manually or on a user-configured schedule — see the Settings tab).
// We deliberately do NOT include topic_extraction here: it runs on every
// journal save and would make the banner flap "Generating your profile…"
// even though the visible profile snapshot only changes per profile_update run.
const PROFILE_PIPELINES: readonly PipelineType[] = ["profile_update"];

export default function ProfilePage() {
  const [profile, setProfile] = useState<KnowledgeProfile | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const pipelines = useMemo(() => PROFILE_PIPELINES, []);
  const status = usePipelineStatus(pipelines);

  const loadProfile = useCallback(() => {
    return api.profile
      .get()
      .then(setProfile)
      .catch(() => setProfile(null));
  }, []);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([loadProfile(), status.refresh()]);
    } finally {
      setRefreshing(false);
    }
  }, [loadProfile, status]);

  const banner = (
    <PipelineStatusBanner
      label="profile"
      running={status.running}
      runningSince={status.runningSince}
      lastCompletedAt={status.lastCompletedAt}
      loaded={status.loaded}
      onRefresh={handleRefresh}
      refreshing={refreshing}
    />
  );

  if (!profile) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">Knowledge Profile</h1>
        {banner}
        {status.running.length === 0 && (
          <div>
            <p className="mb-3 text-gray-500">
              No profile data yet. Write some journal entries, then run the
              profile update.
            </p>
            <RunPipelineButton
              label="Update profile now"
              onRun={() => api.pipelines.runProfileUpdate()}
              onQueued={() => status.refresh()}
            />
          </div>
        )}
      </div>
    );
  }

  const categoryLabels: Record<string, string> = {
    strengths: "Strengths",
    current_frontier: "Current Frontier",
    next_frontier: "Next Frontier",
    recurring_themes: "Recurring Themes",
    weak_spots: "Weak Spots",
    unresolved: "Unresolved",
  };

  const categories: [string, typeof profile.strengths][] = (
    [
      ["strengths", profile.strengths ?? []],
      ["current_frontier", profile.current_frontier ?? []],
      ["next_frontier", profile.next_frontier ?? []],
      ["recurring_themes", profile.recurring_themes ?? []],
      ["weak_spots", profile.weak_spots ?? []],
      ["unresolved", profile.unresolved ?? []],
    ] as [string, typeof profile.strengths][]
  ).filter(([, topics]) => topics.length > 0);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Knowledge Profile</h1>
        <span className="text-sm text-gray-500">
          {profile.total_topics} topics
        </span>
      </div>

      {banner}

      {categories.length === 0 ? (
        <p className="text-gray-500">No topics derived yet.</p>
      ) : (
        <div className="space-y-6">
          {categories.map(([category, topics]) => (
            <div key={category}>
              <h2 className="mb-3 text-lg font-semibold">
                {categoryLabels[category] ?? category}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {topics.map((t) => (
                  <div
                    key={t.id}
                    className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm"
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm font-medium">{t.name}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${STRENGTH_COLOR[t.evidence_strength] ?? "bg-gray-100"}`}
                      >
                        {t.evidence_strength}
                      </span>
                    </div>
                    {t.description && (
                      <p className="text-xs text-gray-500">{t.description}</p>
                    )}
                    <div className="mt-2 h-1.5 rounded-full bg-gray-200">
                      <div
                        className="h-1.5 rounded-full bg-brand-500"
                        style={{ width: `${Math.round(t.confidence * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-400">
                      {Math.round(t.confidence * 100)}% confidence
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
