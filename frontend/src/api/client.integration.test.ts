/**
 * Integration tests that hit the Prism mock server.
 *
 * These verify that the frontend API client can successfully communicate
 * with a server that implements the OpenAPI spec — validating request
 * shapes, response parsing, and status codes against the single source
 * of truth (docs/openapi.json).
 *
 * The Prism server is started/stopped automatically by the globalSetup
 * defined in vitest.integration.config.ts.
 */

import { describe, it, expect } from "vitest";

const PRISM_BASE = "http://localhost:4010/api/v1";

/* ------------------------------------------------------------------ *
 *  Helpers                                                            *
 * ------------------------------------------------------------------ */

async function get(path: string) {
  const res = await fetch(`${PRISM_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
  });
  return res;
}

async function post(path: string, body?: unknown) {
  const res = await fetch(`${PRISM_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res;
}

async function put(path: string, body?: unknown) {
  const res = await fetch(`${PRISM_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res;
}

async function del(path: string) {
  const res = await fetch(`${PRISM_BASE}${path}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  return res;
}

/* ================================================================== *
 *  Journal endpoints                                                  *
 * ================================================================== */

describe("Journal API contract", () => {
  it("GET /journal/entries returns 200 with array", async () => {
    const res = await get("/journal/entries");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  it("POST /journal/entries returns 201 with entry object", async () => {
    const res = await post("/journal/entries", {
      content: "Learned about channels in Go",
    });
    expect(res.status).toBe(201);
    const data = await res.json();
    expect(data).toHaveProperty("id");
    expect(data).toHaveProperty("current_content");
  });

  it("GET /journal/entries/:id returns 200 with entry", async () => {
    // Prism accepts any UUID-shaped path param in dynamic mode
    const res = await get(
      "/journal/entries/00000000-0000-0000-0000-000000000001",
    );
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("id");
  });

  it("PUT /journal/entries/:id returns 200", async () => {
    const res = await put(
      "/journal/entries/00000000-0000-0000-0000-000000000001",
      {
        content: "Updated content",
      },
    );
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("id");
  });

  it("DELETE /journal/entries/:id returns 200 with message", async () => {
    const res = await del(
      "/journal/entries/00000000-0000-0000-0000-000000000001",
    );
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("message");
  });
});

/* ================================================================== *
 *  Profile endpoints                                                  *
 * ================================================================== */

describe("Profile API contract", () => {
  it("GET /profile returns 200 with knowledge profile", async () => {
    const res = await get("/profile");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("total_topics");
  });

  it("GET /profile/snapshots returns 200 with array", async () => {
    const res = await get("/profile/snapshots");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });
});

/* ================================================================== *
 *  Quiz endpoints                                                     *
 * ================================================================== */

describe("Quiz API contract", () => {
  it("GET /quizzes/sessions returns 200 with array", async () => {
    const res = await get("/quizzes/sessions");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  it("GET /quizzes/sessions/current returns 200 with session or null", async () => {
    const res = await get("/quizzes/sessions/current");
    expect(res.status).toBe(200);
    const data = await res.json();
    // Spec allows null (no active session) or a session object
    if (data !== null) {
      expect(data).toHaveProperty("id");
      expect(data).toHaveProperty("status");
    }
  });

  it("POST /quizzes/questions/:id/answer returns 201", async () => {
    const res = await post(
      "/quizzes/questions/00000000-0000-0000-0000-000000000001/answer",
      {
        answer_text:
          "Goroutines are lightweight threads managed by the Go runtime",
      },
    );
    expect(res.status).toBe(201);
  });
});

/* ================================================================== *
 *  Readings endpoints                                                 *
 * ================================================================== */

describe("Readings API contract", () => {
  it("GET /readings/recommendations returns 200 with array", async () => {
    const res = await get("/readings/recommendations");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  it("GET /readings/allowlist returns 200 with array", async () => {
    const res = await get("/readings/allowlist");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  it("POST /readings/allowlist returns 201", async () => {
    const res = await post("/readings/allowlist", {
      domain: "go.dev",
      name: "Official Go site",
    });
    expect(res.status).toBe(201);
    const data = await res.json();
    expect(data).toHaveProperty("id");
    expect(data).toHaveProperty("domain");
  });
});

/* ================================================================== *
 *  Projects endpoints                                                 *
 * ================================================================== */

describe("Projects API contract", () => {
  it("GET /projects returns 200 with array", async () => {
    const res = await get("/projects");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  it("GET /projects/current returns 200 with project", async () => {
    const res = await get("/projects/current");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("id");
    expect(data).toHaveProperty("title");
  });
});

/* ================================================================== *
 *  Triage endpoints                                                   *
 * ================================================================== */

describe("Triage API contract", () => {
  it("GET /triage returns 200 with array", async () => {
    const res = await get("/triage");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  it("GET /triage/blocking returns 200", async () => {
    const res = await get("/triage/blocking");
    expect(res.status).toBe(200);
  });
});

/* ================================================================== *
 *  Feedback endpoints                                                 *
 * ================================================================== */

describe("Feedback API contract", () => {
  it("POST /feedback returns 201", async () => {
    const res = await post("/feedback", {
      target_type: "quiz_question",
      target_id: "00000000-0000-0000-0000-000000000001",
      reaction: "thumbs_up",
      note: "Great question",
    });
    expect(res.status).toBe(201);
    const data = await res.json();
    expect(data).toHaveProperty("id");
  });

  it("GET /feedback returns 200 with array", async () => {
    const res = await get(
      "/feedback?target_type=quiz_question&target_id=00000000-0000-0000-0000-000000000001",
    );
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });
});

/* ================================================================== *
 *  Settings endpoints                                                 *
 * ================================================================== */

describe("Settings API contract", () => {
  it("GET /settings returns 200 with array", async () => {
    const res = await get("/settings");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  it("GET /settings/:key returns 200", async () => {
    const res = await get("/settings/quiz_question_count");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("key");
    expect(data).toHaveProperty("value");
  });

  it("PUT /settings/:key returns 200", async () => {
    const res = await put("/settings/quiz_question_count", {
      value: { count: 15 },
    });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("key");
  });
});

/* ================================================================== *
 *  Onboarding endpoints                                               *
 * ================================================================== */

describe("Onboarding API contract", () => {
  it("GET /onboarding/status returns 200", async () => {
    const res = await get("/onboarding/status");
    expect(res.status).toBe(200);
  });

  it("GET /onboarding/state returns 200", async () => {
    const res = await get("/onboarding/state");
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("completed");
  });

  it("POST /onboarding/complete returns 200", async () => {
    const res = await post("/onboarding/complete", {
      self_assessment: {
        years_programming: 5,
        primary_languages: ["Python", "TypeScript"],
        areas_of_experience: ["backend", "devops"],
      },
      go_experience: {
        level: "beginner",
        months_experience: 2,
      },
    });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data).toHaveProperty("completed");
  });
});
