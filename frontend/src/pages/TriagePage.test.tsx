import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TriagePage from "./TriagePage";
import { renderWithRouter } from "../test/helpers";

vi.mock("../api/client", () => ({
  api: {
    triage: {
      list: vi.fn(),
      resolve: vi.fn(),
    },
    pipelines: {
      listRuns: vi.fn().mockResolvedValue([]),
    },
  },
}));

import { api } from "../api/client";
const mockList = api.triage.list as ReturnType<typeof vi.fn>;
const mockListRuns = api.pipelines.listRuns as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  mockListRuns.mockResolvedValue([]);
});

describe("TriagePage", () => {
  it("shows empty state", async () => {
    mockList.mockResolvedValue([]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => {
      expect(screen.getByText(/No triage items/)).toBeInTheDocument();
    });
  });

  it("surfaces failed pipeline runs in their own section", async () => {
    mockList.mockResolvedValue([]);
    mockListRuns.mockResolvedValue([
      {
        id: "r1",
        pipeline: "quiz_generation",
        status: "failed",
        started_at: "2026-04-19T10:00:00Z",
        completed_at: "2026-04-19T10:01:00Z",
        error: "LLM timeout after 60s",
      },
      {
        id: "r2",
        pipeline: "profile_update",
        status: "completed",
        started_at: "2026-04-19T02:00:00Z",
        completed_at: "2026-04-19T02:05:00Z",
      },
    ]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => {
      expect(screen.getByText(/Failed pipeline runs/)).toBeInTheDocument();
    });
    expect(screen.getByText("quiz_generation")).toBeInTheDocument();
    expect(screen.getByText(/LLM timeout after 60s/)).toBeInTheDocument();
    // Succeeded run must not be rendered in the failed section.
    expect(screen.queryByText("profile_update")).not.toBeInTheDocument();
  });

  it("renders pending and resolved sections", async () => {
    mockList.mockResolvedValue([
      {
        id: "i1",
        source: "profile_update",
        title: "Ambiguous topic",
        description: "Cannot determine if Go or Go+",
        severity: "high",
        status: "pending",
        resolution_text: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "i2",
        source: "quiz_evaluation",
        title: "Resolved item",
        description: "Was resolved",
        severity: "low",
        status: "accepted",
        resolution_text: "Accepted as-is",
        created_at: "2025-12-15T00:00:00Z",
      },
    ]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => {
      expect(screen.getByText("Pending")).toBeInTheDocument();
      expect(screen.getByText("Ambiguous topic")).toBeInTheDocument();
      expect(screen.getByText("high")).toBeInTheDocument();

      expect(screen.getByText("Resolved")).toBeInTheDocument();
      expect(screen.getByText("Resolved item")).toBeInTheDocument();
    });
  });

  it("shows resolution form on 'Resolve…' click", async () => {
    mockList.mockResolvedValue([
      {
        id: "i1",
        source: "profile_update",
        title: "Ambiguous topic",
        description: "Desc",
        severity: "medium",
        status: "pending",
        resolution_text: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const user = userEvent.setup();

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("Resolve…"));
    await user.click(screen.getByText("Resolve…"));

    expect(
      screen.getByPlaceholderText("Clarification text…"),
    ).toBeInTheDocument();
    expect(screen.getByText("Accept")).toBeInTheDocument();
    expect(screen.getByText("Reject")).toBeInTheDocument();
    expect(screen.getByText("Defer")).toBeInTheDocument();
  });
});
