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

// ---- General settings ----
// Editable DB-backed settings. Values are stored as JSON objects in the
// backend; by convention scalars live under a "value" key (matches the
// usage in quiz_pipeline and the transfer tests).
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
      <div className="mb-6 flex items-baseline gap-3">
        <h1 className="text-2xl font-bold">Settings</h1>
        <span className="text-sm text-gray-400">
          Configure your learning companion
        </span>
      </div>

      <div className="space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">About</h2>
          <p className="text-sm text-gray-600">
            <strong>DevLog+</strong> — A single-user, locally-run developer
            journal for technical learning and skill maintenance. Powered by
            LLMs via OpenRouter with Langfuse observability.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold">General</h2>
          <p className="mb-4 text-sm text-gray-500">
            These settings are stored in the database. Other configuration (API
            keys, model selection, etc.) is managed via environment variables in{" "}
            <code className="rounded bg-gray-100 px-1 text-xs">.env</code>.
          </p>

          {settingsStatus.kind === "loading" ? (
            <p className="text-xs text-gray-500">Loading settings…</p>
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
                    className="flex flex-wrap items-end gap-3 border-b border-gray-100 pb-3 last:border-b-0 last:pb-0"
                  >
                    <div className="min-w-[12rem] flex-1">
                      <label
                        htmlFor={`setting-${cfg.key}`}
                        className="block text-sm font-medium text-gray-800"
                      >
                        {cfg.label}
                      </label>
                      <p className="text-xs text-gray-500">
                        {cfg.description}{" "}
                        <span className="text-gray-400">
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
                      className="w-24 rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <button
                      onClick={() => void handleSettingSave(cfg)}
                      disabled={!dirty || isSaving || outOfRange}
                      className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300"
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
                      <span className="text-xs text-green-700">✓ Saved</span>
                    )}
                  </div>
                );
              })}
              {settingsStatus.kind === "error" && (
                <div className="rounded-md bg-red-50 p-3 text-sm text-red-800">
                  ✗ {settingsStatus.message}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ---- Advanced JSON editor ---- */}
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">
                Advanced settings (JSON){" "}
                <span className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-xs font-medium text-amber-800">
                  Advanced
                </span>
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                Raw JSON editor for every{" "}
                <code className="rounded bg-gray-100 px-1 text-xs">
                  user_settings
                </code>{" "}
                row. Each value must be a JSON object (the backend schema
                rejects bare scalars and arrays). Use the{" "}
                <code className="rounded bg-gray-100 px-1 text-xs">
                  {'{"value": ...}'}
                </code>{" "}
                convention for single-value keys.
              </p>
              <p className="mt-2 text-xs text-amber-700">
                🔒 For security, LLM model selection and credentials (API keys,
                database URL, Langfuse config) can only be changed via{" "}
                <code className="rounded bg-amber-50 px-1">.env</code>{" "}
                environment variables — not here.
              </p>
            </div>
          </div>

          {settingsStatus.kind === "loading" ? (
            <p className="text-xs text-gray-500">Loading…</p>
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
                        className="rounded-md border border-gray-200 p-3"
                      >
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <code className="text-sm font-medium text-gray-800">
                            {s.key}
                          </code>
                          <div className="flex items-center gap-2">
                            {dirty && (
                              <button
                                onClick={() => handleRawReset(s.key)}
                                disabled={isSaving}
                                className="text-xs font-medium text-gray-600 hover:text-gray-800 disabled:opacity-50"
                              >
                                Reset
                              </button>
                            )}
                            <button
                              onClick={() => void handleRawSave(s.key)}
                              disabled={!dirty || isSaving}
                              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300"
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
                              <span className="text-xs text-green-700">
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
                          className="w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-xs shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                        <p className="mt-1 text-[11px] text-gray-400">
                          Last updated {new Date(s.updated_at).toLocaleString()}
                        </p>
                        {errorMsg && (
                          <p className="mt-2 text-xs text-red-700">
                            ✗ {errorMsg}
                          </p>
                        )}
                      </div>
                    );
                  })}
                {rawSettings.filter((s) => !GENERAL_KEYS.has(s.key)).length ===
                  0 && (
                  <p className="text-xs text-gray-500">
                    No custom settings stored. Use the form below to create one.
                  </p>
                )}
              </div>

              {/* New-key form */}
              <div className="mt-5 border-t border-gray-200 pt-4">
                <h3 className="mb-2 text-sm font-semibold text-gray-800">
                  Add new setting
                </h3>
                <div className="space-y-2">
                  <div>
                    <label
                      htmlFor="new-setting-key"
                      className="block text-xs font-medium text-gray-700"
                    >
                      Key
                    </label>
                    <input
                      id="new-setting-key"
                      type="text"
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      placeholder="my_custom_setting"
                      className="mt-1 w-full max-w-md rounded-md border border-gray-300 px-3 py-1.5 font-mono text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="new-setting-value"
                      className="block text-xs font-medium text-gray-700"
                    >
                      Value (JSON object)
                    </label>
                    <textarea
                      id="new-setting-value"
                      value={newValueText}
                      onChange={(e) => setNewValueText(e.target.value)}
                      spellCheck={false}
                      rows={4}
                      className="mt-1 w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-xs shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => void handleCreateNewSetting()}
                      disabled={
                        rawStatus.kind === "saving" || newKey.trim() === ""
                      }
                      className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300"
                    >
                      Create
                    </button>
                    {newKeyError && (
                      <span className="text-xs text-red-700">
                        ✗ {newKeyError}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
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
