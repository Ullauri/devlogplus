import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import ReadingsPage from "./ReadingsPage";
import { renderWithRouter } from "../test/helpers";
import userEvent from "@testing-library/user-event";

vi.mock("../api/client", () => ({
  api: {
    readings: {
      list: vi.fn(),
      allowlist: vi.fn(),
      addAllowlist: vi.fn(),
      deleteAllowlist: vi.fn(),
    },
    feedback: {
      create: vi.fn().mockResolvedValue({}),
      listFor: vi.fn().mockResolvedValue([]),
    },
    pipelines: {
      listRuns: vi.fn().mockResolvedValue([]),
    },
  },
}));

import { api } from "../api/client";
const mockList = api.readings.list as ReturnType<typeof vi.fn>;
const mockAllowlist = api.readings.allowlist as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ReadingsPage", () => {
  it("shows empty state when no readings", async () => {
    mockList.mockResolvedValue([]);
    mockAllowlist.mockResolvedValue([]);

    renderWithRouter(<ReadingsPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/No reading recommendations yet/),
      ).toBeInTheDocument();
    });
  });

  it("renders reading recommendations", async () => {
    mockList.mockResolvedValue([
      {
        id: "r1",
        title: "Go Testing Guide",
        url: "https://example.com/go-testing",
        source_domain: "example.com",
        description: "A guide on testing in Go",
        recommendation_type: "frontier",
        batch_date: "2026-01-01",
      },
    ]);
    mockAllowlist.mockResolvedValue([]);

    renderWithRouter(<ReadingsPage />);

    await waitFor(() => {
      expect(screen.getByText("Go Testing Guide")).toBeInTheDocument();
      expect(screen.getByText("A guide on testing in Go")).toBeInTheDocument();
      expect(screen.getByText("frontier")).toBeInTheDocument();
    });
  });

  it("toggles allowlist panel", async () => {
    mockList.mockResolvedValue([]);
    mockAllowlist.mockResolvedValue([
      {
        id: "a1",
        domain: "go.dev",
        name: "Go Official",
        description: null,
        is_default: true,
      },
    ]);
    const user = userEvent.setup();

    renderWithRouter(<ReadingsPage />);

    await user.click(screen.getByText("Manage Allowlist"));

    await waitFor(() => {
      expect(screen.getByText("Allowed Domains")).toBeInTheDocument();
      expect(screen.getByText("go.dev")).toBeInTheDocument();
      expect(screen.getByText("(default)")).toBeInTheDocument();
    });
  });
});
