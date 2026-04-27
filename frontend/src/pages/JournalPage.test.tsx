import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import JournalPage from "./JournalPage";
import { renderWithRouter } from "../test/helpers";
import userEvent from "@testing-library/user-event";

vi.mock("../api/client", () => ({
  api: {
    journal: {
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
    },
    pipelines: {
      listRuns: vi.fn().mockResolvedValue([]),
    },
  },
}));

import { api } from "../api/client";
const mockList = api.journal.list as ReturnType<typeof vi.fn>;
const mockCreate = api.journal.create as ReturnType<typeof vi.fn>;
const mockListRuns = api.pipelines.listRuns as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("JournalPage", () => {
  it("shows empty state when no entries", async () => {
    mockList.mockResolvedValue([]);

    renderWithRouter(<JournalPage />);

    await waitFor(() => {
      expect(
        screen.getByText("No journal entries yet. Start writing!"),
      ).toBeInTheDocument();
    });
  });

  it("renders journal entries", async () => {
    mockList.mockResolvedValue([
      {
        id: "1",
        title: "Day 1",
        current_content: "Learned Go basics",
        is_processed: false,
        processed_at: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);

    renderWithRouter(<JournalPage />);

    await waitFor(() => {
      expect(screen.getByText("Day 1")).toBeInTheDocument();
      expect(screen.getByText("Learned Go basics")).toBeInTheDocument();
    });
  });

  it("shows the new entry form when clicking New Entry", async () => {
    mockList.mockResolvedValue([]);
    const user = userEvent.setup();

    renderWithRouter(<JournalPage />);
    await waitFor(() => screen.getByText("New Entry"));

    await user.click(screen.getByText("New Entry"));

    expect(
      screen.getByPlaceholderText(/What did you learn today\?/i),
    ).toBeInTheDocument();
  });

  it("creates an entry on form submit", async () => {
    mockList.mockResolvedValue([]);
    mockCreate.mockResolvedValue({ id: "2" });
    const user = userEvent.setup();

    renderWithRouter(<JournalPage />);
    await waitFor(() => screen.getByText("New Entry"));

    await user.click(screen.getByText("New Entry"));
    await user.type(
      screen.getByPlaceholderText(/What did you learn today\?/i),
      "New learning",
    );
    await user.click(screen.getByText("Save"));

    expect(mockCreate).toHaveBeenCalledWith({ content: "New learning" });
  });

  it("shows processed badge for processed entries", async () => {
    mockList.mockResolvedValue([
      {
        id: "1",
        title: null,
        current_content: "Processed entry",
        is_processed: true,
        processed_at: "2026-01-02T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);

    renderWithRouter(<JournalPage />);

    await waitFor(() => {
      expect(screen.getByText(/✅ Processed/)).toBeInTheDocument();
    });
  });

  it("disables Process entries button until pipeline status has loaded", async () => {
    // Simulate an unresolved pipeline status fetch — this is what happens
    // when a user navigates back to the tab and the component remounts.
    let resolveRuns!: (v: unknown[]) => void;
    mockListRuns.mockReturnValue(
      new Promise<unknown[]>((r) => {
        resolveRuns = r;
      }),
    );
    mockList.mockResolvedValue([
      {
        id: "1",
        title: null,
        current_content: "Unprocessed entry",
        is_processed: false,
        processed_at: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);

    renderWithRouter(<JournalPage />);

    // Button should be present but disabled while status is loading
    const btn = await screen.findByRole("button", { name: /process entries/i });
    expect(btn).toBeDisabled();

    // Once the status fetch resolves with no running pipelines, button becomes active
    resolveRuns([]);
    await waitFor(() => expect(btn).not.toBeDisabled());
  });
});
