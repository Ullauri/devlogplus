import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
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
      dismissRun: vi.fn(),
      dismissFailedRuns: vi.fn(),
    },
  },
}));

import { api } from "../api/client";
const mockList = api.triage.list as ReturnType<typeof vi.fn>;
const mockListRuns = api.pipelines.listRuns as ReturnType<typeof vi.fn>;
const mockDismissRun = api.pipelines.dismissRun as ReturnType<typeof vi.fn>;
const mockDismissFailedRuns = api.pipelines.dismissFailedRuns as ReturnType<
  typeof vi.fn
>;

const failedRun = (id: string, pipeline = "quiz_generation") => ({
  id,
  pipeline,
  status: "failed",
  started_at: "2026-04-19T10:00:00Z",
  completed_at: "2026-04-19T10:01:00Z",
  error: null,
  dismissed_at: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockListRuns.mockResolvedValue([]);
  mockDismissRun.mockResolvedValue({});
  mockDismissFailedRuns.mockResolvedValue({ dismissed: 0 });
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
      { ...failedRun("r1"), error: "LLM timeout after 60s" },
    ]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => {
      expect(screen.getByText(/Failed pipeline runs/)).toBeInTheDocument();
    });
    expect(screen.getByText("quiz_generation")).toBeInTheDocument();
    expect(screen.getByText(/LLM timeout after 60s/)).toBeInTheDocument();
  });

  it("asks the server for undismissed failures only", async () => {
    // Filtering server-side is what makes dismissal work: a dismissed run
    // must not come back, and the newest failure must not be crowded out of
    // the window by successful runs.
    mockList.mockResolvedValue([]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => expect(mockListRuns).toHaveBeenCalled());
    expect(mockListRuns).toHaveBeenCalledWith(expect.any(Number), undefined, {
      status: "failed",
      includeDismissed: false,
    });
  });

  it("dismisses a single failed run and drops it from the list", async () => {
    mockList.mockResolvedValue([]);
    mockListRuns
      .mockResolvedValueOnce([
        failedRun("r1", "quiz_generation"),
        failedRun("r2", "profile_update"),
      ])
      .mockResolvedValue([failedRun("r2", "profile_update")]);
    const user = userEvent.setup();

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("quiz_generation"));
    await user.click(
      screen.getByLabelText("Dismiss failed quiz_generation run"),
    );

    expect(mockDismissRun).toHaveBeenCalledWith("r1");
    await waitFor(() => {
      expect(screen.queryByText("quiz_generation")).not.toBeInTheDocument();
    });
    // The other failure is untouched.
    expect(screen.getByText("profile_update")).toBeInTheDocument();
  });

  it("re-reads the server and reports the error when dismissing fails", async () => {
    mockList.mockResolvedValue([]);
    // The run is still failed and still undismissed, so the re-read brings
    // it back — the list must not keep the optimistic removal.
    mockListRuns.mockResolvedValue([failedRun("r1")]);
    mockDismissRun.mockRejectedValue(new Error("API 500: boom"));
    const user = userEvent.setup();

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("quiz_generation"));
    await user.click(
      screen.getByLabelText("Dismiss failed quiz_generation run"),
    );

    await waitFor(() => {
      expect(screen.getByText(/API 500: boom/)).toBeInTheDocument();
    });
    expect(screen.getByText("quiz_generation")).toBeInTheDocument();
  });

  it("dismisses every failed run at once", async () => {
    mockList.mockResolvedValue([]);
    mockListRuns.mockResolvedValueOnce([failedRun("r1"), failedRun("r2")]);
    mockDismissFailedRuns.mockResolvedValue({ dismissed: 2 });
    mockListRuns.mockResolvedValue([]);
    const user = userEvent.setup();

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("Dismiss all"));
    await user.click(screen.getByText("Dismiss all"));

    expect(mockDismissFailedRuns).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.queryByText(/Failed pipeline runs/),
      ).not.toBeInTheDocument();
    });
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

  it("summarises a resolved item's origin on the collapsed row", async () => {
    mockList.mockResolvedValue([
      {
        id: "i2",
        source: "quiz_evaluation",
        title: "Quiz evaluation issue",
        description: "Answer contradicts the rubric",
        severity: "low",
        status: "accepted",
        resolution_text: null,
        created_at: "2025-12-15T00:00:00Z",
        resolved_at: "2025-12-16T09:30:00Z",
      },
    ]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("Quiz evaluation issue"));
    // Severity, description, source and status distinguish rows whose
    // titles are all the pipeline's fallback ("Quiz evaluation issue").
    expect(screen.getByText("low")).toBeInTheDocument();
    expect(
      screen.getByText("Answer contradicts the rubric"),
    ).toBeInTheDocument();
    expect(screen.getByText(/from quiz_evaluation/)).toBeInTheDocument();
    expect(screen.getByText("accepted")).toBeInTheDocument();
  });

  it("expands a resolved item to show its full details", async () => {
    mockList.mockResolvedValue([
      {
        id: "i2",
        source: "quiz_evaluation",
        source_id: "q-123",
        title: "Quiz evaluation issue",
        description: "Answer contradicts the rubric",
        context: { question_id: "q-123", reason: "ambiguous rubric" },
        severity: "low",
        status: "accepted",
        resolution_text: "Accepted as-is",
        created_at: "2025-12-15T00:00:00Z",
        resolved_at: "2025-12-16T09:30:00Z",
      },
    ]);
    const user = userEvent.setup();

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("Quiz evaluation issue"));
    expect(screen.queryByText("Resolution")).not.toBeInTheDocument();
    expect(screen.queryByText(/ambiguous rubric/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { expanded: false }));

    expect(screen.getByText("Resolution")).toBeInTheDocument();
    expect(screen.getByText("Accepted as-is")).toBeInTheDocument();
    expect(screen.getByText("Origin")).toBeInTheDocument();
    expect(screen.getByText("quiz_evaluation")).toBeInTheDocument();
    expect(screen.getByText("q-123")).toBeInTheDocument();
    expect(screen.getByText(/ambiguous rubric/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { expanded: true }));
    expect(screen.queryByText("Resolution")).not.toBeInTheDocument();
  });

  it("expands a sparse resolved item without its optional sections", async () => {
    // A deferred item with no clarification, no context and no source entity
    // is a common real record — expanding it must not crash or render
    // empty section headings.
    mockList.mockResolvedValue([
      {
        id: "i3",
        source: "profile_update",
        source_id: null,
        title: "Deferred item",
        description: "",
        context: null,
        severity: "low",
        status: "deferred",
        resolution_text: null,
        created_at: "2025-12-15T00:00:00Z",
        resolved_at: null,
      },
    ]);
    const user = userEvent.setup();

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("Deferred item"));
    await user.click(screen.getByRole("button", { expanded: false }));

    // Scope to the detail panel: "Resolved" also names the section heading.
    const panel = within(document.getElementById("triage-detail-i3")!);
    expect(panel.getByText("Origin")).toBeInTheDocument();
    expect(panel.getByText("Created")).toBeInTheDocument();
    expect(panel.queryByText("Resolution")).not.toBeInTheDocument();
    expect(panel.queryByText("Pipeline context")).not.toBeInTheDocument();
    expect(panel.queryByText("Source ID")).not.toBeInTheDocument();
    expect(panel.queryByText("Resolved")).not.toBeInTheDocument();
  });

  it("slots a never-resolved item into the order by its creation time", async () => {
    mockList.mockResolvedValue([
      {
        id: "old",
        source: "quiz_evaluation",
        title: "Older resolution",
        description: "",
        severity: "low",
        status: "rejected",
        resolution_text: null,
        created_at: "2025-12-01T00:00:00Z",
        resolved_at: "2025-12-02T00:00:00Z",
      },
      {
        id: "deferred",
        source: "quiz_evaluation",
        title: "Deferred mid item",
        description: "",
        severity: "low",
        status: "deferred",
        resolution_text: null,
        created_at: "2025-12-05T00:00:00Z",
        resolved_at: null,
      },
      {
        id: "new",
        source: "quiz_evaluation",
        title: "Newer resolution",
        description: "",
        severity: "low",
        status: "accepted",
        resolution_text: null,
        created_at: "2025-12-10T00:00:00Z",
        resolved_at: "2025-12-11T00:00:00Z",
      },
    ]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("Newer resolution"));
    const rows = screen.getAllByRole("button", { expanded: false });
    expect(rows[0]).toHaveTextContent("Newer resolution");
    expect(rows[1]).toHaveTextContent("Deferred mid item");
    expect(rows[2]).toHaveTextContent("Older resolution");
  });

  it("lists resolved items most recently resolved first", async () => {
    mockList.mockResolvedValue([
      {
        id: "old",
        source: "quiz_evaluation",
        title: "Older resolution",
        description: "",
        severity: "low",
        status: "rejected",
        resolution_text: null,
        created_at: "2025-12-01T00:00:00Z",
        resolved_at: "2025-12-02T00:00:00Z",
      },
      {
        id: "new",
        source: "quiz_evaluation",
        title: "Newer resolution",
        description: "",
        severity: "low",
        status: "accepted",
        resolution_text: null,
        created_at: "2025-12-10T00:00:00Z",
        resolved_at: "2025-12-11T00:00:00Z",
      },
    ]);

    renderWithRouter(<TriagePage />);

    await waitFor(() => screen.getByText("Newer resolution"));
    const rows = screen.getAllByRole("button", { expanded: false });
    expect(rows[0]).toHaveTextContent("Newer resolution");
    expect(rows[1]).toHaveTextContent("Older resolution");
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
