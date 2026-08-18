import { useCallback, useEffect, useRef, useState } from "react";
import { api, type PipelineRunInfo, type Setting } from "../api/client";

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

/**
 * Condense a run's metadata into the one line the Details column has room for.
 *
 * This used to be `Object.entries(...).slice(0, 3)`, which is how a reading run
 * that stored nothing came to read `stored=0, generated=5, batch_date=...` —
 * three keys in insertion order, none of which said why. The pipeline had
 * recorded the reason all along (four dead links); the table just never showed
 * it. So: lead with the headline counts, then surface every *non-zero* skip
 * reason, which is precisely the set of facts that explains an empty batch.
 */
export function summarizeRunMetadata(
  metadata: Record<string, unknown> | null | undefined,
): string {
  if (!metadata) return "";

  const parts: string[] = [];
  const push = (key: string) => {
    const value = metadata[key];
    if (value !== null && value !== undefined)
      parts.push(`${key}=${String(value)}`);
  };

  for (const key of ["stored", "generated"]) push(key);

  // Zero skips are the normal case and say nothing; listing them buries the
  // one counter that is non-zero.
  for (const [key, value] of Object.entries(metadata)) {
    if (!key.startsWith("skipped_")) continue;
    const count = Array.isArray(value) ? value.length : value;
    if (typeof count === "number" && count > 0) parts.push(`${key}=${count}`);
  }

  // Distinguishes "no articles to choose from" (a feed problem) from "chose
  // nothing" (a selection problem) without opening the database.
  if (metadata.source_mode === "recall") parts.push("source=recall");
  if (typeof metadata.candidate_pool_size === "number") {
    parts.push(`pool=${metadata.candidate_pool_size}`);
  }

  if (parts.length === 0) {
    return Object.entries(metadata)
      .filter(([, v]) => v !== null && v !== undefined)
      .slice(0, 3)
      .map(([k, v]) => `${k}=${String(v)}`)
      .join(", ");
  }
  return parts.join(", ");
}

// ---- General settings ----
// Editable DB-backed settings. Values are stored as JSON objects in the
// backend; by convention scalars live under a "value" key, which is the shape
// `onboarding_svc.get_int_setting` unwraps when the pipelines read them back.
//
// min/max below must match the bounds in backend/app/config.py. The backend
// ignores an out-of-range stored value and falls back to its .env default, so
// a mismatch here shows up as a saved setting that silently does nothing.
type GeneralSettingKey = "quiz_question_count" | "reading_recommendation_count";

interface GeneralSettingConfig {
  key: GeneralSettingKey;
  label: string;
  description: string;
  min: number;
  max: number;
  /** Fallback shown when the key has never been set (matches backend defaults). */
  defaultValue: number;
}

const GENERAL_SETTINGS: GeneralSettingConfig[] = [
  {
    key: "quiz_question_count",
    label: "Quiz questions per session",
    description: "Number of questions generated in each quiz session.",
    min: 1,
    max: 50,
    defaultValue: 10,
  },
  {
    key: "reading_recommendation_count",
    label: "Reading recommendations per batch",
    description: "Number of reading items produced per generation run.",
    min: 1,
    max: 20,
    defaultValue: 5,
  },
];

type SettingsStatus =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "saving"; key: GeneralSettingKey }
  | { kind: "saved"; key: GeneralSettingKey }
  | { kind: "error"; message: string };

function extractNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value && typeof value === "object" && "value" in value) {
    const inner = (value as { value: unknown }).value;
    if (typeof inner === "number" && Number.isFinite(inner)) return inner;
  }
  return fallback;
}

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

// Keys that are already edited by the typed General form above — hide them
// from the generic JSON editor to avoid two UIs for the same value.
const GENERAL_KEYS: ReadonlySet<string> = new Set(
  GENERAL_SETTINGS.map((c) => c.key),
);

// Safety: refuse to let the generic editor touch anything that looks like it
// belongs in .env. We do *not* fetch these — they're `llm_model_*` / API
// keys — but a user could still try to create a key with the same name.
const RESERVED_KEY_PREFIXES = ["llm_model_", "openrouter_", "langfuse_"];
const RESERVED_KEYS: ReadonlySet<string> = new Set([
  "database_url",
  "app_env",
  "log_level",
  "workspace_projects_dir",
  "frontend_dist_dir",
]);

function isReservedKey(key: string): boolean {
  if (RESERVED_KEYS.has(key)) return true;
  return RESERVED_KEY_PREFIXES.some((p) => key.startsWith(p));
}

function isValidKeyName(key: string): boolean {
  // Match typical snake_case config keys; keeps things predictable.
  return /^[a-z][a-z0-9_]{0,62}$/.test(key);
}

type RawStatus =
  | { kind: "idle" }
  | { kind: "saving"; key: string }
  | { kind: "saved"; key: string }
  | { kind: "error"; key?: string; message: string };

export default function SettingsPage() {
  // ---- General settings (DB-backed) ----
  const [settingsStatus, setSettingsStatus] = useState<SettingsStatus>({
    kind: "loading",
  });
  const [settingsValues, setSettingsValues] = useState<
    Record<GeneralSettingKey, number>
  >(() => {
    const init = {} as Record<GeneralSettingKey, number>;
    for (const cfg of GENERAL_SETTINGS) init[cfg.key] = cfg.defaultValue;
    return init;
  });
  const [settingsDirty, setSettingsDirty] = useState<
    Record<GeneralSettingKey, boolean>
  >(() => {
    const init = {} as Record<GeneralSettingKey, boolean>;
    for (const cfg of GENERAL_SETTINGS) init[cfg.key] = false;
    return init;
  });

  // ---- Generic JSON editor state ----
  const [rawSettings, setRawSettings] = useState<Setting[]>([]);
  // Map of key -> draft JSON text (as typed by user). Absent => use server value.
  const [rawDrafts, setRawDrafts] = useState<Record<string, string>>({});
  const [rawStatus, setRawStatus] = useState<RawStatus>({ kind: "idle" });
  const [newKey, setNewKey] = useState("");
  const [newValueText, setNewValueText] = useState('{\n  "value": ""\n}');
  const [newKeyError, setNewKeyError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    try {
      setSettingsStatus({ kind: "loading" });
      const list: Setting[] = await api.settings.list();
      const byKey = new Map(list.map((s) => [s.key, s.value] as const));
      setSettingsValues((prev) => {
        const next = { ...prev };
        for (const cfg of GENERAL_SETTINGS) {
          next[cfg.key] = extractNumber(byKey.get(cfg.key), cfg.defaultValue);
        }
        return next;
      });
      setSettingsDirty(() => {
        const init = {} as Record<GeneralSettingKey, boolean>;
        for (const cfg of GENERAL_SETTINGS) init[cfg.key] = false;
        return init;
      });
      setRawSettings(list);
      setRawDrafts({}); // reset drafts to server values
      setSettingsStatus({ kind: "idle" });
    } catch (err) {
      setSettingsStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "Failed to load settings",
      });
    }
  }, []);

  const handleRawDraftChange = useCallback((key: string, text: string) => {
    setRawDrafts((prev) => ({ ...prev, [key]: text }));
  }, []);

  const handleRawSave = useCallback(
    async (key: string) => {
      if (isReservedKey(key)) {
        setRawStatus({
          kind: "error",
          key,
          message:
            "This key is reserved for environment variables (.env) and cannot be set here.",
        });
        return;
      }
      const draft = rawDrafts[key];
      if (draft === undefined) return; // nothing changed
      let parsed: unknown;
      try {
        parsed = JSON.parse(draft);
      } catch (err) {
        setRawStatus({
          kind: "error",
          key,
          message:
            err instanceof Error
              ? `Invalid JSON: ${err.message}`
              : "Invalid JSON",
        });
        return;
      }
      if (
        parsed === null ||
        typeof parsed !== "object" ||
        Array.isArray(parsed)
      ) {
        setRawStatus({
          kind: "error",
          key,
          message:
            'Value must be a JSON object (e.g. {"value": 42}). Arrays and scalars aren\'t allowed by the backend schema.',
        });
        return;
      }
      setRawStatus({ kind: "saving", key });
      try {
        const updated = await api.settings.update(
          key,
          parsed as Record<string, unknown>,
        );
        setRawSettings((prev) => {
          const idx = prev.findIndex((s) => s.key === key);
          if (idx === -1)
            return [...prev, updated].sort((a, b) =>
              a.key.localeCompare(b.key),
            );
          const next = prev.slice();
          next[idx] = updated;
          return next;
        });
        setRawDrafts((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
        setRawStatus({ kind: "saved", key });
      } catch (err) {
        setRawStatus({
          kind: "error",
          key,
          message: err instanceof Error ? err.message : "Failed to save",
        });
      }
    },
    [rawDrafts],
  );

  const handleRawReset = useCallback((key: string) => {
    setRawDrafts((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const handleCreateNewSetting = useCallback(async () => {
    setNewKeyError(null);
    const trimmed = newKey.trim();
    if (!isValidKeyName(trimmed)) {
      setNewKeyError(
        "Key must be snake_case (lowercase, digits, underscores; start with a letter; max 63 chars).",
      );
      return;
    }
    if (isReservedKey(trimmed)) {
      setNewKeyError(
        "That key is reserved for environment variables and cannot be created here.",
      );
      return;
    }
    if (GENERAL_KEYS.has(trimmed)) {
      setNewKeyError(
        "That key is already editable in the General section above.",
      );
      return;
    }
    if (rawSettings.some((s) => s.key === trimmed)) {
      setNewKeyError("A setting with that key already exists — edit it below.");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(newValueText);
    } catch (err) {
      setNewKeyError(
        err instanceof Error ? `Invalid JSON: ${err.message}` : "Invalid JSON",
      );
      return;
    }
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      Array.isArray(parsed)
    ) {
      setNewKeyError("Value must be a JSON object.");
      return;
    }
    setRawStatus({ kind: "saving", key: trimmed });
    try {
      const created = await api.settings.update(
        trimmed,
        parsed as Record<string, unknown>,
      );
      setRawSettings((prev) =>
        [...prev, created].sort((a, b) => a.key.localeCompare(b.key)),
      );
      setNewKey("");
      setNewValueText('{\n  "value": ""\n}');
      setRawStatus({ kind: "saved", key: trimmed });
    } catch (err) {
      setRawStatus({
        kind: "error",
        key: trimmed,
        message: err instanceof Error ? err.message : "Failed to create",
      });
    }
  }, [newKey, newValueText, rawSettings]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const handleSettingChange = useCallback(
    (key: GeneralSettingKey, raw: string) => {
      const parsed = Number.parseInt(raw, 10);
      if (Number.isNaN(parsed)) return;
      setSettingsValues((prev) => ({ ...prev, [key]: parsed }));
      setSettingsDirty((prev) => ({ ...prev, [key]: true }));
    },
    [],
  );

  const handleSettingSave = useCallback(
    async (cfg: GeneralSettingConfig) => {
      const value = settingsValues[cfg.key];
      if (value < cfg.min || value > cfg.max) {
        setSettingsStatus({
          kind: "error",
          message: `${cfg.label}: value must be between ${cfg.min} and ${cfg.max}.`,
        });
        return;
      }
      setSettingsStatus({ kind: "saving", key: cfg.key });
      try {
        await api.settings.update(cfg.key, { value });
        setSettingsDirty((prev) => ({ ...prev, [cfg.key]: false }));
        setSettingsStatus({ kind: "saved", key: cfg.key });
      } catch (err) {
        setSettingsStatus({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to save",
        });
      }
    },
    [settingsValues],
  );

  const [status, setStatus] = useState<TransferStatus>({ kind: "idle" });
  const [metadata, setMetadata] = useState<{
    table_counts: Record<string, number>;
    exported_at: string;
  } | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- Pipeline triggers (Settings-only) ----
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

  // Pipelines with a `started` row in the log. These runs are minutes-long LLM
  // calls, so triggering a second one is always a mistake — the backend rejects
  // it with a 409, and this disables the button so the user doesn't have to
  // discover that by clicking.
  const runningPipelines = new Set(
    runs.filter((r) => r.status === "started").map((r) => r.pipeline),
  );

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
        "Process new journal entries and refresh the Knowledge Profile.",
      run: () => api.pipelines.runProfileUpdate(),
    },
    {
      key: "quiz_generation",
      label: "Generate quiz",
      description: "Create a new quiz session from your profile.",
      run: () => api.pipelines.runQuizGeneration(),
    },
    {
      key: "reading_generation",
      label: "Generate readings",
      description: "Produce a new batch of reading recommendations.",
      run: () => api.pipelines.runReadingGeneration(),
    },
    {
      key: "project_generation",
      label: "Generate project",
      description: "Generate a new Go micro-project.",
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
      <div className="mb-6 flex items-baseline gap-3">
        <h1 className="text-2xl font-bold">Settings</h1>
        <span className="text-sm text-gray-400 dark:text-gray-500">
          Configure your learning companion
        </span>
      </div>

      <div className="space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h2 className="mb-3 text-lg font-semibold">About</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            <strong>DevLog+</strong> — A single-user, locally-run developer
            journal for technical learning and skill maintenance. Powered by
            LLMs via OpenRouter with Langfuse observability.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h2 className="mb-3 text-lg font-semibold">General</h2>
          <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
            Saving here stores the value in the database and the next pipeline
            run uses it — no restart needed. Leave one unset and it falls back
            to the matching{" "}
            <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-800">
              .env
            </code>{" "}
            value. Credentials and model selection are{" "}
            <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-800">
              .env
            </code>
            -only and cannot be set from here.
          </p>

          {settingsStatus.kind === "loading" ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Loading settings…
            </p>
          ) : (
            <div className="space-y-4">
              {GENERAL_SETTINGS.map((cfg) => {
                const value = settingsValues[cfg.key];
                const dirty = settingsDirty[cfg.key];
                const isSaving =
                  settingsStatus.kind === "saving" &&
                  settingsStatus.key === cfg.key;
                const justSaved =
                  settingsStatus.kind === "saved" &&
                  settingsStatus.key === cfg.key;
                const outOfRange = value < cfg.min || value > cfg.max;
                return (
                  <div
                    key={cfg.key}
                    className="flex flex-wrap items-end gap-3 border-b border-gray-100 pb-3 last:border-b-0 last:pb-0 dark:border-gray-800"
                  >
                    <div className="min-w-[12rem] flex-1">
                      <label
                        htmlFor={`setting-${cfg.key}`}
                        className="block text-sm font-medium text-gray-800 dark:text-gray-100"
                      >
                        {cfg.label}
                      </label>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {cfg.description}{" "}
                        <span className="text-gray-400 dark:text-gray-500">
                          (range {cfg.min}–{cfg.max}, default {cfg.defaultValue}
                          )
                        </span>
                      </p>
                    </div>
                    <input
                      id={`setting-${cfg.key}`}
                      type="number"
                      min={cfg.min}
                      max={cfg.max}
                      value={value}
                      onChange={(e) =>
                        handleSettingChange(cfg.key, e.target.value)
                      }
                      className="w-24 rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                    />
                    <button
                      onClick={() => void handleSettingSave(cfg)}
                      disabled={!dirty || isSaving || outOfRange}
                      className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300 dark:focus:ring-offset-gray-900 dark:disabled:bg-gray-700"
                    >
                      {isSaving ? (
                        <>
                          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                          Saving…
                        </>
                      ) : (
                        "Save"
                      )}
                    </button>
                    {justSaved && !dirty && (
                      <span className="text-xs text-green-700 dark:text-green-300">
                        ✓ Saved
                      </span>
                    )}
                  </div>
                );
              })}
              {settingsStatus.kind === "error" && (
                <div className="rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-200">
                  ✗ {settingsStatus.message}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ---- Advanced JSON editor ---- */}
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">
                Advanced settings (JSON){" "}
                <span className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-xs font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
                  Advanced
                </span>
              </h2>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Raw JSON editor for every{" "}
                <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-800">
                  user_settings
                </code>{" "}
                row. Each value must be a JSON object (the backend schema
                rejects bare scalars and arrays). Use the{" "}
                <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-800">
                  {'{"value": ...}'}
                </code>{" "}
                convention for single-value keys.
              </p>
              <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                🔒 For security, LLM model selection and credentials (API keys,
                database URL, Langfuse config) can only be changed via{" "}
                <code className="rounded bg-amber-50 px-1 dark:bg-amber-900/20">
                  .env
                </code>{" "}
                environment variables — not here.
              </p>
            </div>
          </div>

          {settingsStatus.kind === "loading" ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">Loading…</p>
          ) : (
            <>
              {/* Existing rows (excluding ones shown in General) */}
              <div className="space-y-3">
                {rawSettings
                  .filter((s) => !GENERAL_KEYS.has(s.key))
                  .map((s) => {
                    const draft = rawDrafts[s.key];
                    const serverText = JSON.stringify(s.value, null, 2);
                    const displayText = draft ?? serverText;
                    const dirty = draft !== undefined && draft !== serverText;
                    const isSaving =
                      rawStatus.kind === "saving" && rawStatus.key === s.key;
                    const justSaved =
                      rawStatus.kind === "saved" &&
                      rawStatus.key === s.key &&
                      !dirty;
                    const errorMsg =
                      rawStatus.kind === "error" && rawStatus.key === s.key
                        ? rawStatus.message
                        : null;
                    return (
                      <div
                        key={s.id}
                        className="rounded-md border border-gray-200 p-3 dark:border-gray-800"
                      >
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <code className="text-sm font-medium text-gray-800 dark:text-gray-100">
                            {s.key}
                          </code>
                          <div className="flex items-center gap-2">
                            {dirty && (
                              <button
                                onClick={() => handleRawReset(s.key)}
                                disabled={isSaving}
                                className="text-xs font-medium text-gray-600 hover:text-gray-800 disabled:opacity-50 dark:text-gray-400 dark:hover:text-gray-100"
                              >
                                Reset
                              </button>
                            )}
                            <button
                              onClick={() => void handleRawSave(s.key)}
                              disabled={!dirty || isSaving}
                              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300 dark:focus:ring-offset-gray-900 dark:disabled:bg-gray-700"
                            >
                              {isSaving ? (
                                <>
                                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                                  Saving…
                                </>
                              ) : (
                                "Save"
                              )}
                            </button>
                            {justSaved && (
                              <span className="text-xs text-green-700 dark:text-green-300">
                                ✓ Saved
                              </span>
                            )}
                          </div>
                        </div>
                        <textarea
                          value={displayText}
                          onChange={(e) =>
                            handleRawDraftChange(s.key, e.target.value)
                          }
                          spellCheck={false}
                          rows={Math.min(
                            10,
                            Math.max(2, displayText.split("\n").length),
                          )}
                          className="w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-xs shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800/50"
                        />
                        <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
                          Last updated {new Date(s.updated_at).toLocaleString()}
                        </p>
                        {errorMsg && (
                          <p className="mt-2 text-xs text-red-700 dark:text-red-300">
                            ✗ {errorMsg}
                          </p>
                        )}
                      </div>
                    );
                  })}
                {rawSettings.filter((s) => !GENERAL_KEYS.has(s.key)).length ===
                  0 && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    No custom settings stored. Use the form below to create one.
                  </p>
                )}
              </div>

              {/* New-key form */}
              <div className="mt-5 border-t border-gray-200 pt-4 dark:border-gray-800">
                <h3 className="mb-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
                  Add new setting
                </h3>
                <div className="space-y-2">
                  <div>
                    <label
                      htmlFor="new-setting-key"
                      className="block text-xs font-medium text-gray-700 dark:text-gray-300"
                    >
                      Key
                    </label>
                    <input
                      id="new-setting-key"
                      type="text"
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      placeholder="my_custom_setting"
                      className="mt-1 w-full max-w-md rounded-md border border-gray-300 px-3 py-1.5 font-mono text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="new-setting-value"
                      className="block text-xs font-medium text-gray-700 dark:text-gray-300"
                    >
                      Value (JSON object)
                    </label>
                    <textarea
                      id="new-setting-value"
                      value={newValueText}
                      onChange={(e) => setNewValueText(e.target.value)}
                      spellCheck={false}
                      rows={4}
                      className="mt-1 w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-xs shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800/50"
                    />
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => void handleCreateNewSetting()}
                      disabled={
                        rawStatus.kind === "saving" || newKey.trim() === ""
                      }
                      className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300 dark:focus:ring-offset-gray-900 dark:disabled:bg-gray-700"
                    >
                      Create
                    </button>
                    {newKeyError && (
                      <span className="text-xs text-red-700 dark:text-red-300">
                        ✗ {newKeyError}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* ---- Data Transfer ---- */}
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h2 className="mb-3 text-lg font-semibold">Data Transfer</h2>
          <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
            Export your DevLog+ data to a JSON file and import it on another
            machine. This lets you move your journal, knowledge profile,
            quizzes, readings, and settings between devices.
          </p>
          <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
            Weekly projects are <strong>not</strong> included. Their Go code
            lives in <code className="font-mono">workspace/projects/</code> on
            disk, not in the database, so the rows alone would arrive without
            the files they describe. Copy that folder across yourself if you
            want to keep the code.
          </p>

          {/* Export */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <button
              onClick={handleExport}
              disabled={status.kind === "loading"}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 dark:focus:ring-offset-gray-900"
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
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:focus:ring-offset-gray-900"
            >
              {status.kind === "loading" && status.action === "metadata"
                ? "Loading…"
                : "Preview"}
            </button>
          </div>

          {metadata && (
            <div className="mb-4 rounded-md bg-gray-50 p-3 text-xs dark:bg-gray-800/50">
              <p className="mb-1 font-medium text-gray-700 dark:text-gray-300">
                Export preview
              </p>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
                {Object.entries(metadata.table_counts)
                  .filter(([, v]) => v > 0)
                  .map(([table, count]) => (
                    <span
                      key={table}
                      className="text-gray-600 dark:text-gray-400"
                    >
                      {table.replace(/_/g, " ")}: <strong>{count}</strong>
                    </span>
                  ))}
              </div>
            </div>
          )}

          {/* Import */}
          <div className="mb-2">
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Import from file
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              onChange={onFileSelected}
              className="block w-full text-sm text-gray-500 file:mr-4 file:rounded-md file:border-0 file:bg-gray-100 file:px-4 file:py-2 file:text-sm file:font-medium file:text-gray-700 hover:file:bg-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:text-gray-400 dark:placeholder-gray-500"
            />
          </div>

          {/* Confirmation dialog */}
          {showConfirm && (
            <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
              <p className="mb-3 text-sm font-medium text-amber-800 dark:text-amber-200">
                ⚠️ This will <strong>replace all existing data</strong> with the
                contents of the uploaded file. This cannot be undone.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={confirmImport}
                  disabled={status.kind === "loading"}
                  className="inline-flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 dark:focus:ring-offset-gray-900"
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
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Status banner */}
          {status.kind === "success" && (
            <div className="mt-3 rounded-md bg-green-50 p-3 text-sm text-green-800 dark:bg-green-900/20 dark:text-green-200">
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
            <div className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-200">
              ✗ {status.message}
            </div>
          )}
        </div>

        {/* ---- Pipeline Runs ---- */}
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">Pipeline runs</h2>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Nothing runs on its own — start a pipeline here whenever you
                want fresh output, for example after importing data or finishing
                a burst of journal entries. Each run executes in the background;
                progress appears in the table below.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {pipelineButtons.map((cfg) => {
              const st = pipelineStatus[cfg.key];
              const isQueueing = st.kind === "queueing";
              const isRunning = runningPipelines.has(cfg.key);
              const isBusy = isQueueing || isRunning;
              return (
                <div
                  key={cfg.key}
                  className="rounded-md border border-gray-200 p-3 dark:border-gray-800"
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-800 dark:text-gray-100">
                      {cfg.label}
                    </span>
                    <button
                      onClick={() => triggerPipeline(cfg.key, cfg.run)}
                      disabled={isBusy}
                      className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:focus:ring-offset-gray-900"
                    >
                      {isBusy ? (
                        <>
                          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-500 border-t-transparent dark:border-gray-500" />
                          {isQueueing ? "Queuing…" : "Running…"}
                        </>
                      ) : (
                        "Run now"
                      )}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {cfg.description}
                  </p>
                  {st.kind === "queued" && (
                    <p className="mt-2 text-xs text-green-700 dark:text-green-300">
                      ✓ {st.message}
                    </p>
                  )}
                  {st.kind === "error" && (
                    <p className="mt-2 text-xs text-red-700 dark:text-red-300">
                      ✗ {st.message}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-5">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                Recent runs
              </h3>
              <button
                onClick={() => void refreshRuns()}
                className="text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
              >
                Refresh
              </button>
            </div>
            {!runsLoaded ? (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Loading…
              </p>
            ) : runs.length === 0 ? (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                No pipeline runs recorded yet.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-md border border-gray-200 dark:border-gray-800">
                <table className="min-w-full divide-y divide-gray-200 text-xs dark:divide-gray-800">
                  <thead className="bg-gray-50 text-left text-gray-600 dark:bg-gray-800/50 dark:text-gray-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">Pipeline</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Started</th>
                      <th className="px-3 py-2 font-medium">Duration</th>
                      <th className="px-3 py-2 font-medium">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white dark:divide-gray-800 dark:bg-gray-900">
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
                          ? "text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/20"
                          : r.status === "failed"
                            ? "text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20"
                            : "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20";
                      const detail =
                        r.error ?? summarizeRunMetadata(r.metadata);
                      return (
                        <tr key={r.id}>
                          <td className="px-3 py-2 font-mono text-[11px] text-gray-800 dark:text-gray-100">
                            {r.pipeline}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${statusClass}`}
                            >
                              {r.status}
                            </span>
                            {/* Dismissed runs are hidden from Triage, so this
                                is the only place they remain visible. */}
                            {r.dismissed_at && (
                              <span className="ml-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                                dismissed
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                            {started.toLocaleString()}
                          </td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                            {durationLabel}
                          </td>
                          <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
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
