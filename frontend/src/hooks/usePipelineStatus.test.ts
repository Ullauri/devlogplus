import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { usePipelineStatus } from "./usePipelineStatus";

vi.mock("../api/client", () => ({
  api: {
    pipelines: {
      listRuns: vi.fn(),
    },
  },
}));

import { api } from "../api/client";
const mockListRuns = api.pipelines.listRuns as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("usePipelineStatus", () => {
  it("fetches one list per pipeline type on mount", async () => {
    mockListRuns.mockResolvedValue([]);
    const { result } = renderHook(() =>
      usePipelineStatus(["quiz_generation", "quiz_evaluation"]),
    );
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(mockListRuns).toHaveBeenCalledTimes(2);
    expect(mockListRuns).toHaveBeenCalledWith(10, "quiz_generation");
    expect(mockListRuns).toHaveBeenCalledWith(10, "quiz_evaluation");
  });

  it("derives running pipelines from 'started' rows", async () => {
    mockListRuns.mockResolvedValueOnce([
      {
        id: "r1",
        pipeline: "quiz_generation",
        status: "started",
        started_at: "2026-04-19T10:00:00Z",
      },
    ]);
    mockListRuns.mockResolvedValueOnce([]);
    const { result } = renderHook(() =>
      usePipelineStatus(["quiz_generation", "quiz_evaluation"]),
    );
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.running).toEqual(["quiz_generation"]);
    expect(result.current.runningSince).toBe("2026-04-19T10:00:00Z");
  });

  it("runningSince uses the OLDEST in-flight started_at", async () => {
    mockListRuns.mockResolvedValueOnce([
      {
        id: "r1",
        pipeline: "quiz_generation",
        status: "started",
        started_at: "2026-04-19T10:05:00Z",
      },
      {
        id: "r2",
        pipeline: "quiz_generation",
        status: "started",
        started_at: "2026-04-19T10:00:00Z", // older
      },
    ]);
    mockListRuns.mockResolvedValueOnce([]);
    const { result } = renderHook(() =>
      usePipelineStatus(["quiz_generation", "quiz_evaluation"]),
    );
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.runningSince).toBe("2026-04-19T10:00:00Z");
  });

  it("reports the newest completed_at as lastCompletedAt", async () => {
    mockListRuns.mockResolvedValueOnce([
      {
        id: "r1",
        pipeline: "quiz_generation",
        status: "completed",
        started_at: "2026-04-18T10:00:00Z",
        completed_at: "2026-04-18T10:05:00Z",
      },
      {
        id: "r2",
        pipeline: "quiz_generation",
        status: "completed",
        started_at: "2026-04-19T10:00:00Z",
        completed_at: "2026-04-19T10:05:00Z",
      },
    ]);
    mockListRuns.mockResolvedValueOnce([]);
    const { result } = renderHook(() =>
      usePipelineStatus(["quiz_generation", "quiz_evaluation"]),
    );
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.lastCompletedAt).toBe("2026-04-19T10:05:00Z");
    expect(result.current.running).toEqual([]);
  });

  it("refresh() re-fetches", async () => {
    mockListRuns.mockResolvedValue([]);
    const { result } = renderHook(() => usePipelineStatus(["quiz_generation"]));
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(mockListRuns).toHaveBeenCalledTimes(1);
    await act(async () => {
      await result.current.refresh();
    });
    expect(mockListRuns).toHaveBeenCalledTimes(2);
  });

  it("re-fetches on window focus", async () => {
    mockListRuns.mockResolvedValue([]);
    const { result } = renderHook(() => usePipelineStatus(["quiz_generation"]));
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(mockListRuns).toHaveBeenCalledTimes(1);
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(mockListRuns).toHaveBeenCalledTimes(2));
  });

  it("survives fetch errors without throwing", async () => {
    mockListRuns.mockRejectedValue(new Error("nope"));
    const { result } = renderHook(() => usePipelineStatus(["quiz_generation"]));
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.running).toEqual([]);
    expect(result.current.lastCompletedAt).toBeNull();
  });
});
