/* ============================================================
 * DevLog+ API Client
 * Thin typed wrapper around fetch() for all backend endpoints.
 *
 * Base URL resolution:
 *   - Default ("/api/v1") — uses Vite dev proxy to reach the backend
 *   - VITE_API_BASE_URL env var — override for Prism mock server,
 *     e.g. "http://localhost:4010/api/v1"
 * ============================================================ */

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

// ---- Types (mirrors backend schemas) ----

export interface JournalEntry {
  id: string;
  title: string | null;
  current_content: string;
  is_processed: boolean;
  processed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Topic {
  id: string;
  name: string;
  description: string | null;
  category: string;
  evidence_strength: string;
  confidence: number;
  created_at: string;
}

export interface KnowledgeProfile {
  categories: Record<string, Topic[]>;
  total_topics: number;
  last_updated: string | null;
}

export interface QuizSession {
  id: string;
  status: string;
  question_count: number;
  created_at: string;
  completed_at: string | null;
}

export interface QuizQuestion {
  id: string;
  question_text: string;
  question_type: string;
  order_index: number;
  answer?: { answer_text: string };
  evaluation?: {
    correctness: string;
    depth_assessment: string | null;
    explanation: string;
    confidence: number;
  };
}

export interface ReadingRecommendation {
  id: string;
  title: string;
  url: string;
  source_domain: string;
  description: string | null;
  recommendation_type: string;
  batch_date: string;
}

export interface AllowlistEntry {
  id: string;
  domain: string;
  name: string;
  description: string | null;
  is_default: boolean;
}

export interface WeeklyProject {
  id: string;
  title: string;
  description: string;
  difficulty_level: number;
  status: string;
  issued_at: string;
  submitted_at: string | null;
  tasks: ProjectTask[];
}

export interface ProjectTask {
  id: string;
  title: string;
  description: string;
  task_type: string;
  order_index: number;
}

export interface TriageItem {
  id: string;
  source: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  resolution_text: string | null;
  created_at: string;
}

export interface Feedback {
  id: string;
  target_type: string;
  target_id: string;
  reaction: string | null;
  note: string | null;
  created_at: string;
}

export interface OnboardingState {
  completed: boolean;
  completed_at: string | null;
  self_assessment: Record<string, unknown> | null;
  go_experience_level: string | null;
  topic_interests: string[] | null;
}

// ---- API namespaces ----

export const api = {
  journal: {
    list: () => get<JournalEntry[]>("/journal/entries"),
    get: (id: string) => get<JournalEntry>(`/journal/entries/${id}`),
    create: (data: { title?: string; content: string }) =>
      post<JournalEntry>("/journal/entries", data),
    update: (id: string, data: { title?: string; content?: string }) =>
      put<JournalEntry>(`/journal/entries/${id}`, data),
    delete: (id: string) => del<void>(`/journal/entries/${id}`),
  },

  profile: {
    get: () => get<KnowledgeProfile>("/profile"),
    snapshots: () => get<unknown[]>("/profile/snapshots"),
  },

  quiz: {
    listSessions: () => get<QuizSession[]>("/quizzes/sessions"),
    getSession: (id: string) =>
      get<QuizSession & { questions: QuizQuestion[] }>(
        `/quizzes/sessions/${id}`,
      ),
    getCurrent: () =>
      get<QuizSession & { questions: QuizQuestion[] }>(
        "/quizzes/sessions/current",
      ),
    submitAnswer: (questionId: string, answer: string) =>
      post<unknown>(`/quizzes/questions/${questionId}/answer`, {
        answer_text: answer,
      }),
    completeSession: (id: string) =>
      post<QuizSession>(`/quizzes/sessions/${id}/complete`),
  },

  readings: {
    list: () => get<ReadingRecommendation[]>("/readings/recommendations"),
    allowlist: () => get<AllowlistEntry[]>("/readings/allowlist"),
    addAllowlist: (data: {
      domain: string;
      name: string;
      description?: string;
    }) => post<AllowlistEntry>("/readings/allowlist", data),
    deleteAllowlist: (id: string) => del<void>(`/readings/allowlist/${id}`),
  },

  projects: {
    list: () => get<WeeklyProject[]>("/projects"),
    get: (id: string) => get<WeeklyProject>(`/projects/${id}`),
    getCurrent: () => get<WeeklyProject>("/projects/current"),
    submit: (id: string) => post<WeeklyProject>(`/projects/${id}/submit`),
  },

  triage: {
    list: () => get<TriageItem[]>("/triage"),
    get: (id: string) => get<TriageItem>(`/triage/${id}`),
    resolve: (id: string, data: { action: string; resolution_text?: string }) =>
      post<TriageItem>(`/triage/${id}/resolve`, data),
  },

  feedback: {
    create: (data: {
      target_type: string;
      target_id: string;
      reaction?: string;
      note?: string;
    }) => post<Feedback>("/feedback", data),
    listFor: (targetType: string, targetId: string) =>
      get<Feedback[]>(
        `/feedback?target_type=${targetType}&target_id=${targetId}`,
      ),
  },

  settings: {
    list: () => get<Record<string, unknown>[]>("/settings"),
    update: (key: string, value: unknown) =>
      put<unknown>(`/settings/${key}`, { value }),
  },

  onboarding: {
    getState: () => get<OnboardingState>("/onboarding/state"),
    complete: (data: {
      self_assessment: Record<string, unknown>;
      go_experience_level: string;
      topic_interests?: string[];
    }) => post<OnboardingState>("/onboarding/complete", data),
  },

  transfer: {
    /** Get row counts and metadata before exporting. */
    metadata: () =>
      get<{
        format_version: number;
        exported_at: string;
        app_version: string;
        table_counts: Record<string, number>;
      }>("/transfer/export/metadata"),

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
    ): Promise<{ message: string; counts: Record<string, number> }> {
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
