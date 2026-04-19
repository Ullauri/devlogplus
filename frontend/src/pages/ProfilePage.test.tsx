import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import ProfilePage from "./ProfilePage";
import { renderWithRouter } from "../test/helpers";

vi.mock("../api/client", () => ({
  api: {
    profile: {
      get: vi.fn(),
    },
  },
}));

import { api } from "../api/client";
const mockGet = api.profile.get as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ProfilePage", () => {
  it("shows empty state when profile is null", async () => {
    mockGet.mockRejectedValue(new Error("not found"));

    renderWithRouter(<ProfilePage />);

    await waitFor(() => {
      expect(screen.getByText(/No profile data yet/)).toBeInTheDocument();
    });
  });

  it("renders topics grouped by category", async () => {
    mockGet.mockResolvedValue({
      strengths: [
        {
          id: "t1",
          name: "Go concurrency",
          description: "Goroutines and channels",
          category: "demonstrated_strength",
          evidence_strength: "strong",
          confidence: 0.85,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      weak_spots: [],
      current_frontier: [],
      next_frontier: [],
      recurring_themes: [],
      unresolved: [],
      total_topics: 1,
      last_updated: "2026-01-02T00:00:00Z",
    });

    renderWithRouter(<ProfilePage />);

    await waitFor(() => {
      expect(screen.getByText("strengths")).toBeInTheDocument();
      expect(screen.getByText("Go concurrency")).toBeInTheDocument();
      expect(screen.getByText("strong")).toBeInTheDocument();
      expect(screen.getByText("85% confidence")).toBeInTheDocument();
      expect(screen.getByText("1 topics")).toBeInTheDocument();
    });
  });

  it("shows 'No topics derived yet' when all categories are empty", async () => {
    mockGet.mockResolvedValue({
      strengths: [],
      weak_spots: [],
      current_frontier: [],
      next_frontier: [],
      recurring_themes: [],
      unresolved: [],
      total_topics: 0,
      last_updated: null,
    });

    renderWithRouter(<ProfilePage />);

    await waitFor(() => {
      expect(screen.getByText("No topics derived yet.")).toBeInTheDocument();
    });
  });
});
