import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectsPage from "./ProjectsPage";
import { renderWithRouter } from "../test/helpers";

vi.mock("../api/client", () => ({
  api: {
    projects: {
      list: vi.fn(),
      getCurrent: vi.fn(),
      submit: vi.fn(),
    },
    feedback: {
      create: vi.fn().mockResolvedValue({}),
    },
  },
}));

import { api } from "../api/client";
const mockList = api.projects.list as ReturnType<typeof vi.fn>;
const mockGetCurrent = api.projects.getCurrent as ReturnType<typeof vi.fn>;
const mockSubmit = api.projects.submit as ReturnType<typeof vi.fn>;

function makeProject(overrides: Record<string, unknown> = {}) {
  return {
    id: "p1",
    title: "HTTP Server",
    description: "Build a simple HTTP server",
    difficulty_level: 3,
    status: "issued",
    issued_at: "2026-01-01T00:00:00Z",
    submitted_at: null,
    tasks: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ProjectsPage — empty state", () => {
  it("shows empty state when no current project", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockRejectedValue(new Error("none"));
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => {
      expect(screen.getByText(/No active project/)).toBeInTheDocument();
    });
    expect(screen.queryByText("Past Projects")).not.toBeInTheDocument();
  });
});

describe("ProjectsPage — current project", () => {
  it("renders current project with tasks", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(
      makeProject({
        tasks: [
          {
            id: "t1",
            title: "Fix handler",
            description: "Fix the request handler",
            task_type: "bug_fix",
            order_index: 0,
          },
          {
            id: "t2",
            title: "Add middleware",
            description: "Add logging middleware",
            task_type: "feature",
            order_index: 1,
          },
        ],
      }),
    );
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("HTTP Server"));
    expect(screen.getByText("Build a simple HTTP server")).toBeInTheDocument();
    expect(screen.getByText("Difficulty: 3/5")).toBeInTheDocument();
    expect(screen.getByText("Fix handler")).toBeInTheDocument();
    expect(screen.getByText("Add middleware")).toBeInTheDocument();
  });

  it("omits the Tasks section when no tasks", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(makeProject({ tasks: [] }));
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("HTTP Server"));
    expect(screen.queryByText("Tasks")).not.toBeInTheDocument();
  });

  it("shows Submit button when status is in_progress", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(makeProject({ status: "in_progress" }));
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("HTTP Server"));
    expect(
      screen.getByRole("button", { name: "Submit for Evaluation" }),
    ).toBeInTheDocument();
  });

  it("hides Submit button when status is evaluated", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(makeProject({ status: "evaluated" }));
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("HTTP Server"));
    expect(
      screen.queryByRole("button", { name: "Submit for Evaluation" }),
    ).not.toBeInTheDocument();
  });

  it("hides Submit button when status is submitted", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(makeProject({ status: "submitted" }));
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("HTTP Server"));
    expect(
      screen.queryByRole("button", { name: "Submit for Evaluation" }),
    ).not.toBeInTheDocument();
  });

  it("clicking Submit calls api.projects.submit with the project id", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValueOnce(makeProject({ status: "issued" }));
    mockGetCurrent.mockRejectedValueOnce(new Error("none"));
    mockSubmit.mockResolvedValue({});
    const user = userEvent.setup();
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("HTTP Server"));

    await user.click(
      screen.getByRole("button", { name: "Submit for Evaluation" }),
    );

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith("p1");
    });
  });
});

describe("ProjectsPage — status badge colors", () => {
  it.each([
    ["issued", "bg-blue-100", "text-blue-800"],
    ["in_progress", "bg-yellow-100", "text-yellow-800"],
    ["submitted", "bg-purple-100", "text-purple-800"],
    ["evaluated", "bg-green-100", "text-green-800"],
  ])("status %s → %s %s", async (status, bg, fg) => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(makeProject({ status }));
    renderWithRouter(<ProjectsPage />);
    const badge = await screen.findByText(status);
    expect(badge.className).toContain(bg);
    expect(badge.className).toContain(fg);
  });

  it("unknown status falls back to bg-gray-100", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(makeProject({ status: "bogus" }));
    renderWithRouter(<ProjectsPage />);
    const badge = await screen.findByText("bogus");
    expect(badge.className).toContain("bg-gray-100");
  });
});

describe("ProjectsPage — task type badge colors", () => {
  it.each([
    ["bug_fix", "bg-red-100", "text-red-700"],
    ["feature", "bg-green-100", "text-green-700"],
    ["refactor", "bg-yellow-100", "text-yellow-700"],
    ["optimization", "bg-blue-100", "text-blue-700"],
  ])("task type %s → %s %s", async (task_type, bg, fg) => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(
      makeProject({
        tasks: [
          {
            id: "t1",
            title: "A task",
            description: "d",
            task_type,
            order_index: 0,
          },
        ],
      }),
    );
    renderWithRouter(<ProjectsPage />);
    const badge = await screen.findByText(task_type);
    expect(badge.className).toContain(bg);
    expect(badge.className).toContain(fg);
  });
});

describe("ProjectsPage — past projects list", () => {
  it("renders Past Projects heading when list has items", async () => {
    mockList.mockResolvedValue([
      makeProject({
        id: "p2",
        title: "CLI Tool",
        description: "Build a CLI tool",
        status: "evaluated",
      }),
    ]);
    mockGetCurrent.mockRejectedValue(new Error("none"));
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("Past Projects"));
    expect(screen.getByText("CLI Tool")).toBeInTheDocument();
    expect(screen.getByText("evaluated")).toBeInTheDocument();
  });

  it("excludes the current project from the past list", async () => {
    mockList.mockResolvedValue([
      makeProject({ id: "p1", title: "Current" }),
      makeProject({ id: "p2", title: "Old one", status: "evaluated" }),
    ]);
    mockGetCurrent.mockResolvedValue(
      makeProject({ id: "p1", title: "Current" }),
    );
    renderWithRouter(<ProjectsPage />);
    await waitFor(() => screen.getByText("Past Projects"));
    // "Current" appears once (in the header), not duplicated in past list.
    expect(screen.getAllByText("Current")).toHaveLength(1);
    expect(screen.getByText("Old one")).toBeInTheDocument();
  });
});
