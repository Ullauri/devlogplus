import { useEffect, useState } from "react";
import { api, KnowledgeProfile } from "../api/client";

const STRENGTH_COLOR: Record<string, string> = {
  strong: "bg-green-100 text-green-800",
  developing: "bg-yellow-100 text-yellow-800",
  limited: "bg-gray-100 text-gray-600",
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<KnowledgeProfile | null>(null);

  useEffect(() => {
    api.profile
      .get()
      .then(setProfile)
      .catch(() => setProfile(null));
  }, []);

  if (!profile) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold">Knowledge Profile</h1>
        <p className="text-gray-500">
          No profile data yet. Write some journal entries and wait for the
          nightly update.
        </p>
      </div>
    );
  }

  const categories = Object.entries(profile.categories);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Knowledge Profile</h1>
        <span className="text-sm text-gray-500">
          {profile.total_topics} topics
        </span>
      </div>

      {categories.length === 0 ? (
        <p className="text-gray-500">No topics derived yet.</p>
      ) : (
        <div className="space-y-6">
          {categories.map(([category, topics]) => (
            <div key={category}>
              <h2 className="mb-3 text-lg font-semibold capitalize">
                {category}
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
