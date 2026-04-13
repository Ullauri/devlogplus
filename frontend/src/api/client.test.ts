import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "./client";

/* ------------------------------------------------------------------ */
/*  Stub global fetch for every test                                   */
/* ------------------------------------------------------------------ */

function mockFetch(status: number, body: unknown, statusText = "OK") {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: () => Promise.resolve(body),
    text: () =>
      Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

/* ================================================================== */
/*  Journal                                                            */
/* ================================================================== */

describe("api.journal", () => {
  it("list() calls GET /api/v1/journal/entries", async () => {
    const entries = [{ id: "1", title: "hi", current_content: "body" }];
    globalThis.fetch = mockFetch(200, entries);

    const result = await api.journal.list();

    expect(fetch).toHaveBeenCalledOnce();
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/journal/entries");
    expect(init?.method).toBeUndefined(); // GET is default
    expect(result).toEqual(entries);
  });

  it("create() calls POST /api/v1/journal/entries with body", async () => {
    const entry = { id: "2", title: null, current_content: "test" };
    globalThis.fetch = mockFetch(200, entry);

    await api.journal.create({ content: "test" });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/journal/entries");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ content: "test" });
  });

  it("update() calls PUT", async () => {
    globalThis.fetch = mockFetch(200, {});

    await api.journal.update("abc", { content: "updated" });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/journal/entries/abc");
    expect(init.method).toBe("PUT");
  });

  it("delete() calls DELETE", async () => {
    globalThis.fetch = mockFetch(204, undefined);

    await api.journal.delete("abc");

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/journal/entries/abc");
    expect(init.method).toBe("DELETE");
  });
});

/* ================================================================== */
/*  Profile                                                            */
/* ================================================================== */

describe("api.profile", () => {
  it("get() calls GET /api/v1/profile", async () => {
    const profile = { categories: {}, total_topics: 0, last_updated: null };
    globalThis.fetch = mockFetch(200, profile);

    const result = await api.profile.get();

    expect(result).toEqual(profile);
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toBe(
      "/api/v1/profile",
    );
  });
});

/* ================================================================== */
/*  Quiz                                                               */
/* ================================================================== */

describe("api.quiz", () => {
  it("submitAnswer() sends POST with answer body", async () => {
    globalThis.fetch = mockFetch(200, {});

    await api.quiz.submitAnswer("q1", "my answer");

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/quizzes/questions/q1/answer");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ answer_text: "my answer" });
  });
});

/* ================================================================== */
/*  Triage                                                             */
/* ================================================================== */

describe("api.triage", () => {
  it("resolve() sends POST with action", async () => {
    globalThis.fetch = mockFetch(200, {});

    await api.triage.resolve("t1", { action: "accept", resolution_text: "ok" });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/triage/t1/resolve");
    expect(JSON.parse(init.body)).toEqual({
      action: "accept",
      resolution_text: "ok",
    });
  });
});

/* ================================================================== */
/*  Feedback                                                           */
/* ================================================================== */

describe("api.feedback", () => {
  it("create() sends POST", async () => {
    globalThis.fetch = mockFetch(200, { id: "f1" });

    await api.feedback.create({
      target_type: "quiz_question",
      target_id: "q1",
      reaction: "thumbs_up",
    });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/feedback");
    expect(init.method).toBe("POST");
  });

  it("listFor() builds correct query string", async () => {
    globalThis.fetch = mockFetch(200, []);

    await api.feedback.listFor("reading", "r1");

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/feedback?target_type=reading&target_id=r1");
  });
});

/* ================================================================== */
/*  Onboarding                                                         */
/* ================================================================== */

describe("api.onboarding", () => {
  it("complete() sends POST with payload", async () => {
    globalThis.fetch = mockFetch(200, { completed: true });

    await api.onboarding.complete({
      self_assessment: { years_programming: "5" },
      go_experience_level: "intermediate",
    });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/api/v1/onboarding/complete");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body).go_experience_level).toBe("intermediate");
  });
});

/* ================================================================== */
/*  Error handling                                                     */
/* ================================================================== */

describe("request error handling", () => {
  it("throws on non-ok response", async () => {
    globalThis.fetch = mockFetch(422, "Validation error");

    await expect(api.journal.list()).rejects.toThrow("API 422");
  });
});
