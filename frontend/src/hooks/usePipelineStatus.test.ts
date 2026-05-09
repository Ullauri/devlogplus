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

  it("loaded is false while a re-fetch is in-flight", async () => {
    // First fetch completes immediately so the hook reaches loaded=true.
    mockListRuns.mockResolvedValueOnce([]);

    const { result } = renderHook(() => usePipelineStatus(["quiz_generation"]));
    await waitFor(() => expect(result.current.loaded).toBe(true));

    // Second fetch is held open so we can observe the in-flight state.
    let resolveSecond!: (v: unknown[]) => void;
    mockListRuns.mockReturnValue(
      new Promise<unknown[]>((r) => {
        resolveSecond = r;
      }),
    );

    act(() => {
      void result.current.refresh();
    });

    // While the fetch is pending, loaded must be false so consumers disable
    // any action buttons that depend on fresh pipeline status.
    expect(result.current.loaded).toBe(false);

    // Resolving restores loaded=true.
    await act(async () => {
      resolveSecond([]);
    });
    expect(result.current.loaded).toBe(true);
  });

  it("re-fetches on visibilitychange and keeps loaded=false during the round-trip", async () => {
    // Initial load.
    mockListRuns.mockResolvedValueOnce([]);
    const { result } = renderHook(() => usePipelineStatus(["quiz_generation"]));
    await waitFor(() => expect(result.current.loaded).toBe(true));

    // Hold the next fetch so we can inspect the in-flight state.
    let resolveVis!: (v: unknown[]) => void;
    mockListRuns.mockReturnValue(
      new Promise<unknown[]>((r) => {
        resolveVis = r;
      }),
    );

    act(() => {
      // Simulate the user returning to the browser tab.
      Object.defineProperty(document, "visibilityState", {
        value: "visible",
        configurable: true,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });

    // loaded must be false while the re-fetch is in-flight — this is the
    // critical guard that prevents the Generate button from being enabled
    // in the race window after a tab switch or SPA navigation remount.
    expect(result.current.loaded).toBe(false);

    await act(async () => {
      resolveVis([]);
    });
    expect(result.current.loaded).toBe(true);
  });
});
