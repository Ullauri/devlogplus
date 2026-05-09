/**
 * Contract integration tests — exercise the real `api` client against
 * a Prism mock server serving docs/openapi.json with `--errors` enabled.
 *
 * These tests are the trip-wire that catches client↔spec drift.
 *
 * Rules:
 *   1. Always call methods on the exported `api` object — never raw
 *      fetch/post helpers. The whole point is to validate that the
 *      generated request shapes in client.ts match the contract.
 *   2. Prism returns 422 on any spec-violating request body. The `api`
 *      client throws on non-2xx, so a validation failure becomes a
 *      rejected promise.
 *   3. Dynamic mode means response bodies are synthesized from the
 *      schema. Assertions only check for presence of required fields.
 *
 * The Prism server is started/stopped automatically by the globalSetup
 * defined in vitest.integration.config.ts.
 */

import { describe, it, expect } from "vitest";
import { api } from "./client";

const UUID = "00000000-0000-0000-0000-000000000001";

/* ================================================================== *
 *  Journal                                                            *
 * ================================================================== */
describe("api.journal contract", () => {
  it("list() resolves with array", async () => {
    const data = await api.journal.list();
    expect(Array.isArray(data)).toBe(true);
  });

  it("create() with valid body resolves", async () => {
    const entry = await api.journal.create({
      content: "Learned about channels in Go",
    });
    expect(entry).toHaveProperty("id");
  });

  it("get() resolves with detail entry", async () => {
    const entry = await api.journal.get(UUID);
    expect(entry).toHaveProperty("id");
  });

  it("update() with valid body resolves", async () => {
    const entry = await api.journal.update(UUID, { content: "Updated" });
    expect(entry).toHaveProperty("id");
  });

  it("delete() resolves without throwing", async () => {
    await expect(api.journal.delete(UUID)).resolves.not.toThrow();
  });
});

/* ================================================================== *
 *  Profile                                                            *
 * ================================================================== */
describe("api.profile contract", () => {
  it("get() resolves with knowledge profile", async () => {
    const profile = await api.profile.get();
    expect(profile).toHaveProperty("total_topics");
  });

  it("snapshots() resolves with array", async () => {
    const snaps = await api.profile.snapshots();
    expect(Array.isArray(snaps)).toBe(true);
  });
});

/* ================================================================== *
 *  Quiz                                                               *
 * ================================================================== */
describe("api.quiz contract", () => {
  it("listSessions() resolves with array", async () => {
    const sessions = await api.quiz.listSessions();
    expect(Array.isArray(sessions)).toBe(true);
  });

  it("submitAnswer() resolves", async () => {
    const r = await api.quiz.submitAnswer(UUID, "answer");
    expect(r).toHaveProperty("id");
  });
});

/* ================================================================== *
 *  Readings                                                           *
 * ================================================================== */
describe("api.readings contract", () => {
  it("list() resolves with array", async () => {
    const items = await api.readings.list();
    expect(Array.isArray(items)).toBe(true);
  });

  it("allowlist() resolves with array", async () => {
    const items = await api.readings.allowlist();
    expect(Array.isArray(items)).toBe(true);
  });

  it("addAllowlist() with valid body resolves", async () => {
    const entry = await api.readings.addAllowlist({
      domain: "go.dev",
      name: "Official Go site",
    });
    expect(entry).toHaveProperty("id");
  });
});

/* ================================================================== *
 *  Projects                                                           *
 * ================================================================== */
describe("api.projects contract", () => {
  it("list() resolves with array", async () => {
    const items = await api.projects.list();
    expect(Array.isArray(items)).toBe(true);
  });

  it("getCurrent() resolves with project or null", async () => {
    const p = await api.projects.getCurrent();
    // Endpoint returns WeeklyProjectDetailResponse | null — both are valid per spec.
    expect(p === null || typeof p === "object").toBe(true);
    if (p !== null) expect(p).toHaveProperty("id");
  });

  it("submit() with empty body resolves", async () => {
    const p = await api.projects.submit(UUID, {});
    expect(p).toHaveProperty("id");
  });
});

/* ================================================================== *
 *  Triage                                                             *
 * ================================================================== */
describe("api.triage contract", () => {
  it("list() resolves with array", async () => {
    const items = await api.triage.list();
    expect(Array.isArray(items)).toBe(true);
  });

  it("resolve() with valid enum action resolves", async () => {
    const r = await api.triage.resolve(UUID, { action: "accepted" });
    expect(r).toHaveProperty("id");
  });

  it("resolve() with all enum actions resolves", async () => {
    for (const action of [
      "accepted",
      "rejected",
      "edited",
      "deferred",
    ] as const) {
      const r = await api.triage.resolve(UUID, {
        action,
        resolution_text: "x",
      });
      expect(r).toHaveProperty("id");
    }
  });
});

/* ================================================================== *
 *  Feedback                                                           *
 * ================================================================== */
describe("api.feedback contract", () => {
  it("create() with valid enums resolves", async () => {
    const f = await api.feedback.create({
      target_type: "quiz_question",
      target_id: UUID,
      reaction: "thumbs_up",
      note: "Great question",
    });
    expect(f).toHaveProperty("id");
  });

  it("listFor() resolves with array", async () => {
    const items = await api.feedback.listFor("quiz_question", UUID);
    expect(Array.isArray(items)).toBe(true);
  });
});

/* ================================================================== *
 *  Settings                                                           *
 * ================================================================== */
describe("api.settings contract", () => {
  it("list() resolves with array", async () => {
    const items = await api.settings.list();
    expect(Array.isArray(items)).toBe(true);
  });

  it("update() with valid body resolves", async () => {
    const s = await api.settings.update("quiz_question_count", { count: 15 });
    expect(s).toHaveProperty("key");
  });
});

/* ================================================================== *
 *  Onboarding — the endpoint that started this whole audit            *
 * ================================================================== */
describe("api.onboarding contract", () => {
  it("getState() resolves", async () => {
    const s = await api.onboarding.getState();
    expect(s).toHaveProperty("completed");
  });

  it("complete() with fully-valid body resolves", async () => {
    const s = await api.onboarding.complete({
      self_assessment: {
        primary_languages: ["Python", "TypeScript"],
        years_experience: 5,
        primary_domain: "backend",
        comfort_areas: ["REST APIs"],
        growth_areas: ["distributed systems"],
      },
      go_experience: { level: "beginner", details: "small CLI tools" },
      topic_interests: ["concurrency"],
    });
    expect(s).toHaveProperty("completed");
  });

  it("complete() with the minimal required fields resolves", async () => {
    // Required-only payload per spec — catches over-eager client validation
    const s = await api.onboarding.complete({
      self_assessment: {
        primary_languages: [],
        comfort_areas: [],
        growth_areas: [],
      },
      go_experience: { level: "none" },
    });
    expect(s).toHaveProperty("completed");
  });
});

/* ================================================================== *
 *  Pipelines                                                          *
 * ================================================================== */
describe("api.pipelines contract", () => {
  it("listRuns() resolves with array", async () => {
    const runs = await api.pipelines.listRuns();
    expect(Array.isArray(runs)).toBe(true);
  });

  it("runProfileUpdate() resolves", async () => {
    const r = await api.pipelines.runProfileUpdate();
    expect(r).toHaveProperty("pipeline");
  });

  it("runQuizGeneration() resolves", async () => {
    const r = await api.pipelines.runQuizGeneration();
    expect(r).toHaveProperty("pipeline");
  });

  it("runReadingGeneration() resolves", async () => {
    const r = await api.pipelines.runReadingGeneration();
    expect(r).toHaveProperty("pipeline");
  });

  it("runProjectGeneration() resolves", async () => {
    const r = await api.pipelines.runProjectGeneration();
    expect(r).toHaveProperty("pipeline");
  });
});

/* ================================================================== *
 *  Transfer                                                           *
 * ================================================================== */
describe("api.transfer contract", () => {
  it("metadata() resolves", async () => {
    const m = await api.transfer.metadata();
    expect(m).toHaveProperty("format_version");
  });
});

/* ================================================================== *
 *  Negative tests — ensure Prism --errors actually rejects bad bodies *
 * ================================================================== */
describe("contract enforcement (negative)", () => {
  it("raw malformed onboarding body produces 422", async () => {
    // Directly hit the endpoint with a deliberately bad body.
    // If this returns 200, Prism --errors is not active and the
    // contract tests above would silently pass on any shape.
    const res = await fetch(
      "http://localhost:4010/api/v1/onboarding/complete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Old buggy shape — go_experience_level instead of go_experience{}
        body: JSON.stringify({
          self_assessment: { years_programming: "5" },
          go_experience_level: "beginner",
        }),
      },
    );
    expect(res.status).toBe(422);
  });

  it("raw malformed triage action produces 422", async () => {
    const res = await fetch(
      `http://localhost:4010/api/v1/triage/${UUID}/resolve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "accept" }), // short form, not in enum
      },
    );
    expect(res.status).toBe(422);
  });
});
