import { useState } from "react";
import { api } from "../api/client";

interface Props {
  onComplete: () => void;
}

const GO_LEVELS = [
  { value: "none", label: "No experience — brand new to Go" },
  { value: "beginner", label: "Beginner — written a few small programs" },
  {
    value: "intermediate",
    label: "Intermediate — comfortable with core concepts",
  },
  { value: "advanced", label: "Advanced — extensive production experience" },
];

const TOPIC_OPTIONS = [
  "Backend development",
  "Systems programming",
  "Distributed systems",
  "Databases",
  "Cloud infrastructure",
  "DevOps / CI-CD",
  "Networking",
  "Security",
  "Performance optimization",
  "Testing strategies",
  "API design",
  "Concurrency / parallelism",
];

export default function OnboardingPage({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [goLevel, setGoLevel] = useState("beginner");
  const [selfAssessment, setSelfAssessment] = useState({
    years_programming: "",
    primary_languages: "",
    strongest_area: "",
    weakest_area: "",
  });
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const toggleTopic = (topic: string) => {
    setSelectedTopics((prev) =>
      prev.includes(topic) ? prev.filter((t) => t !== topic) : [...prev, topic],
    );
  };

  const handleComplete = async () => {
    setSubmitting(true);
    try {
      await api.onboarding.complete({
        self_assessment: selfAssessment,
        go_experience_level: goLevel,
        topic_interests: selectedTopics.length > 0 ? selectedTopics : undefined,
      });
      onComplete();
    } catch {
      alert("Failed to save onboarding. Is the backend running?");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-white p-6">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-lg">
        <h1 className="mb-1 text-2xl font-bold text-brand-700">
          Welcome to DevLog+
        </h1>
        <p className="mb-6 text-sm text-gray-500">
          Let's set up your profile. This takes about 10 minutes.
        </p>

        {/* Progress */}
        <div className="mb-8 flex gap-2">
          {[0, 1, 2].map((s) => (
            <div
              key={s}
              className={`h-1.5 flex-1 rounded-full ${s <= step ? "bg-brand-500" : "bg-gray-200"}`}
            />
          ))}
        </div>

        {/* Step 0: Self-assessment */}
        {step === 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Technical Background</h2>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Years of programming experience
              </label>
              <input
                type="text"
                value={selfAssessment.years_programming}
                onChange={(e) =>
                  setSelfAssessment({
                    ...selfAssessment,
                    years_programming: e.target.value,
                  })
                }
                placeholder="e.g. 5"
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Primary languages
              </label>
              <input
                type="text"
                value={selfAssessment.primary_languages}
                onChange={(e) =>
                  setSelfAssessment({
                    ...selfAssessment,
                    primary_languages: e.target.value,
                  })
                }
                placeholder="e.g. Python, TypeScript, Go"
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Strongest area
              </label>
              <input
                type="text"
                value={selfAssessment.strongest_area}
                onChange={(e) =>
                  setSelfAssessment({
                    ...selfAssessment,
                    strongest_area: e.target.value,
                  })
                }
                placeholder="e.g. backend APIs, data pipelines"
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                Area you'd like to improve
              </label>
              <input
                type="text"
                value={selfAssessment.weakest_area}
                onChange={(e) =>
                  setSelfAssessment({
                    ...selfAssessment,
                    weakest_area: e.target.value,
                  })
                }
                placeholder="e.g. systems programming, concurrency"
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
          </div>
        )}

        {/* Step 1: Go experience */}
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Go Experience Level</h2>
            <div className="space-y-2">
              {GO_LEVELS.map(({ value, label }) => (
                <label
                  key={value}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-gray-200 p-3 hover:bg-gray-50"
                >
                  <input
                    type="radio"
                    name="goLevel"
                    value={value}
                    checked={goLevel === value}
                    onChange={() => setGoLevel(value)}
                    className="accent-brand-600"
                  />
                  <span className="text-sm">{label}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Interests */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">
              Topic Interests (optional)
            </h2>
            <p className="text-sm text-gray-500">
              Select topics you'd like to explore:
            </p>
            <div className="flex flex-wrap gap-2">
              {TOPIC_OPTIONS.map((topic) => (
                <button
                  key={topic}
                  onClick={() => toggleTopic(topic)}
                  className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                    selectedTopics.includes(topic)
                      ? "border-brand-500 bg-brand-50 text-brand-700"
                      : "border-gray-300 text-gray-600 hover:border-gray-400"
                  }`}
                >
                  {topic}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Navigation */}
        <div className="mt-8 flex justify-between">
          <button
            onClick={() => setStep(step - 1)}
            disabled={step === 0}
            className="rounded border border-gray-300 px-4 py-2 text-sm disabled:opacity-30"
          >
            Back
          </button>
          {step < 2 ? (
            <button
              onClick={() => setStep(step + 1)}
              className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700"
            >
              Next
            </button>
          ) : (
            <button
              onClick={handleComplete}
              disabled={submitting}
              className="rounded bg-green-600 px-6 py-2 text-sm text-white hover:bg-green-700 disabled:opacity-50"
            >
              {submitting ? "Saving…" : "Complete Setup"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
