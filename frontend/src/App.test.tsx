import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import App from "./App";
import { renderWithRouter } from "./test/helpers";

/* Mock the api client */
vi.mock("./api/client", () => ({
  api: {
    onboarding: {
      getState: vi.fn(),
    },
  },
}));

import { api } from "./api/client";
const mockGetState = api.onboarding.getState as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("App", () => {
  it("shows loading state initially", () => {
    // Never resolve the promise to keep loading
    mockGetState.mockReturnValue(new Promise(() => {}));
    renderWithRouter(<App />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to onboarding when not completed", async () => {
    mockGetState.mockResolvedValue({ completed: false });
    renderWithRouter(<App />, { route: "/journal" });

    await waitFor(() => {
      expect(screen.getByText("Welcome to DevLog+")).toBeInTheDocument();
    });
  });

  it("renders main layout when onboarding is completed", async () => {
    mockGetState.mockResolvedValue({ completed: true });
    renderWithRouter(<App />, { route: "/settings" });

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Settings" }),
      ).toBeInTheDocument();
    });
  });

  it("redirects to onboarding when API fails", async () => {
    mockGetState.mockRejectedValue(new Error("network"));
    renderWithRouter(<App />, { route: "/journal" });

    await waitFor(() => {
      expect(screen.getByText("Welcome to DevLog+")).toBeInTheDocument();
    });
  });
});
