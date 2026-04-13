import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ProjectsPage", () => {
  it("shows empty state when no current project", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText(/No active project/)).toBeInTheDocument();
    });
  });

  it("renders current project with tasks", async () => {
    mockList.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue({
      id: "p1",
      title: "HTTP Server",
      description: "Build a simple HTTP server",
      difficulty_level: 3,
      status: "issued",
      issued_at: "2026-01-01T00:00:00Z",
      submitted_at: null,
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
    });

    renderWithRouter(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("HTTP Server")).toBeInTheDocument();
      expect(
        screen.getByText("Build a simple HTTP server"),
      ).toBeInTheDocument();
      expect(screen.getByText("Difficulty: 3/5")).toBeInTheDocument();
      expect(screen.getByText("Fix handler")).toBeInTheDocument();
      expect(screen.getByText("Add middleware")).toBeInTheDocument();
      expect(screen.getByText("Submit for Evaluation")).toBeInTheDocument();
    });
  });

  it("renders past projects list", async () => {
    mockList.mockResolvedValue([
      {
        id: "p2",
        title: "CLI Tool",
        description: "Build a CLI tool",
        difficulty_level: 2,
        status: "evaluated",
        issued_at: "2025-12-01T00:00:00Z",
        submitted_at: "2025-12-07T00:00:00Z",
        tasks: [],
      },
    ]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("Past Projects")).toBeInTheDocument();
      expect(screen.getByText("CLI Tool")).toBeInTheDocument();
      expect(screen.getByText("evaluated")).toBeInTheDocument();
    });
  });
});
