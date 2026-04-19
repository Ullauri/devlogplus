/* ============================================================
 * DevLog+ API Client
 * Thin typed wrapper around fetch() for all backend endpoints.
 *
 * All request/response types are imported from `schema.gen.ts`,
 * which is generated from `docs/openapi.json` by
 * `npm run openapi:types`. DO NOT hand-write payload shapes here —
 * keeping the contract single-sourced is what prevents the
 * client/server drift bugs that unit tests can't catch.
 *
 * Base URL resolution:
 *   - Default ("/api/v1") — uses Vite dev proxy to reach the backend
 *   - VITE_API_BASE_URL env var — override for Prism mock server,
 *     e.g. "http://localhost:4010/api/v1"
 * ============================================================ */

import type { components } from "./schema.gen";

type Schemas = components["schemas"];

// ---- Re-export backend schemas as friendly type aliases ----
// Consumers import these names; the shapes come straight from the spec.
export type JournalEntry = Schemas["JournalEntryResponse"];
export type JournalEntryDetail = Schemas["JournalEntryDetailResponse"];
export type JournalEntryVersion = Schemas["JournalEntryVersionResponse"];
export type Topic = Schemas["TopicResponse"];
export type KnowledgeProfile = Schemas["KnowledgeProfileResponse"];
export type QuizSession = Schemas["QuizSessionResponse"];
export type QuizSessionDetail = Schemas["QuizSessionDetailResponse"];
export type QuizQuestion = Schemas["QuizQuestionResponse"];
export type ReadingRecommendation = Schemas["ReadingRecommendationResponse"];
export type AllowlistEntry = Schemas["AllowlistEntryResponse"];
export type WeeklyProject = Schemas["WeeklyProjectResponse"];
export type WeeklyProjectDetail = Schemas["WeeklyProjectDetailResponse"];
export type ProjectTask = Schemas["ProjectTaskResponse"];
export type TriageItem = Schemas["TriageItemResponse"];
export type Feedback = Schemas["FeedbackResponse"];
export type OnboardingState = Schemas["OnboardingStateResponse"];
export type PipelineRunAccepted = Schemas["PipelineRunAccepted"];
export type PipelineRunInfo = Schemas["PipelineRunInfo"];
export type Setting = Schemas["SettingResponse"];

export type ManualPipelineName = Schemas["PipelineRunAccepted"]["pipeline"];

// ---- HTTP plumbing ----
const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function get<T>(path: string) {
  return request<T>(path);
}
function post<T>(path: string, body?: unknown) {
  return request<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}
function put<T>(path: string, body?: unknown) {
  return request<T>(path, {
    method: "PUT",
    body: body ? JSON.stringify(body) : undefined,
  });
}
function del<T>(path: string) {
  return request<T>(path, { method: "DELETE" });
}

// ---- API namespaces ----
// Every request-body parameter uses a generated schema type.
// If docs/openapi.json changes, `tsc` will catch any drift here.

export const api = {
  journal: {
    list: () => get<JournalEntry[]>("/journal/entries"),
    get: (id: string) => get<JournalEntryDetail>(`/journal/entries/${id}`),
    create: (data: Schemas["JournalEntryCreate"]) =>
      post<JournalEntry>("/journal/entries", data),
    update: (id: string, data: Schemas["JournalEntryUpdate"]) =>
      put<JournalEntry>(`/journal/entries/${id}`, data),
    delete: (id: string) => del<void>(`/journal/entries/${id}`),
  },

  profile: {
    get: () => get<KnowledgeProfile>("/profile"),
    snapshots: () =>
      get<Schemas["ProfileSnapshotResponse"][]>("/profile/snapshots"),
  },

  quiz: {
    listSessions: () => get<QuizSession[]>("/quizzes/sessions"),
    getSession: (id: string) =>
      get<QuizSessionDetail>(`/quizzes/sessions/${id}`),
    getCurrent: () => get<QuizSessionDetail>("/quizzes/sessions/current"),
    submitAnswer: (questionId: string, answer: string) => {
      const body: Schemas["QuizAnswerCreate"] = { answer_text: answer };
      return post<Schemas["QuizAnswerResponse"]>(
        `/quizzes/questions/${questionId}/answer`,
        body,
      );
    },
    completeSession: (id: string) =>
      post<QuizSession>(`/quizzes/sessions/${id}/complete`),
  },

  readings: {
    list: () => get<ReadingRecommendation[]>("/readings/recommendations"),
    allowlist: () => get<AllowlistEntry[]>("/readings/allowlist"),
    addAllowlist: (data: Schemas["AllowlistEntryCreate"]) =>
      post<AllowlistEntry>("/readings/allowlist", data),
    deleteAllowlist: (id: string) => del<void>(`/readings/allowlist/${id}`),
  },

  projects: {
    list: () => get<WeeklyProject[]>("/projects"),
    get: (id: string) => get<WeeklyProjectDetail>(`/projects/${id}`),
    getCurrent: () => get<WeeklyProjectDetail>("/projects/current"),
    submit: (id: string, data: Schemas["ProjectSubmitRequest"] = {}) =>
      post<WeeklyProject>(`/projects/${id}/submit`, data),
  },

  triage: {
    list: () => get<TriageItem[]>("/triage"),
    get: (id: string) => get<TriageItem>(`/triage/${id}`),
    resolve: (id: string, data: Schemas["TriageResolveRequest"]) =>
      post<TriageItem>(`/triage/${id}/resolve`, data),
  },

  feedback: {
    create: (data: Schemas["FeedbackCreate"]) =>
      post<Feedback>("/feedback", data),
    listFor: (targetType: string, targetId: string) =>
      get<Feedback[]>(
        `/feedback?target_type=${targetType}&target_id=${targetId}`,
      ),
  },

  settings: {
    list: () => get<Setting[]>("/settings"),
    update: (key: string, value: Record<string, unknown>) => {
      const body: Schemas["SettingUpdate"] = { value };
      return put<Setting>(`/settings/${key}`, body);
    },
  },

  onboarding: {
    getState: () => get<OnboardingState>("/onboarding/state"),
    complete: (data: Schemas["OnboardingCompleteRequest"]) =>
      post<OnboardingState>("/onboarding/complete", data),
  },

  pipelines: {
    runProfileUpdate: () =>
      post<PipelineRunAccepted>("/pipelines/profile-update/run"),
    runQuizGeneration: () => post<PipelineRunAccepted>("/pipelines/quiz/run"),
    runReadingGeneration: () =>
      post<PipelineRunAccepted>("/pipelines/readings/run"),
    runProjectGeneration: () =>
      post<PipelineRunAccepted>("/pipelines/project/run"),
    listRuns: (limit = 20) =>
      get<PipelineRunInfo[]>(`/pipelines/runs?limit=${limit}`),
  },

  transfer: {
    /** Get row counts and metadata before exporting. */
    metadata: () => get<Schemas["ExportMetadata"]>("/transfer/export/metadata"),

    /** Download the full export bundle as a JSON blob. */
    async exportData(): Promise<Blob> {
      const res = await fetch(`${BASE}/transfer/export`);
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`API ${res.status}: ${body}`);
      }
      return res.blob();
    },

    /** Upload a JSON export file to replace all data. */
    async importData(
      file: File,
      confirmOverwrite = false,
    ): Promise<Schemas["ImportResult"]> {
      const form = new FormData();
      form.append("file", file);
      const qs = confirmOverwrite ? "?confirm_overwrite=true" : "";
      const res = await fetch(`${BASE}/transfer/import${qs}`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`API ${res.status}: ${body}`);
      }
      return res.json();
    },
  },
};
