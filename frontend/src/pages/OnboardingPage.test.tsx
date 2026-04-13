import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import OnboardingPage from "./OnboardingPage";
import { renderWithRouter } from "../test/helpers";

vi.mock("../api/client", () => ({
  api: {
    onboarding: {
      complete: vi.fn(),
    },
  },
}));

import { api } from "../api/client";
const mockComplete = api.onboarding.complete as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("OnboardingPage", () => {
  it("renders the welcome heading", () => {
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    expect(screen.getByText("Welcome to DevLog+")).toBeInTheDocument();
  });

  it("shows step 0 (Technical Background) by default", () => {
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    expect(screen.getByText("Technical Background")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. 5")).toBeInTheDocument();
  });

  it("navigates to step 1 on Next click", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.click(screen.getByText("Next"));

    expect(screen.getByText("Go Experience Level")).toBeInTheDocument();
  });

  it("navigates to step 2 (Interests) with two Next clicks", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));

    expect(screen.getByText("Topic Interests (optional)")).toBeInTheDocument();
    expect(screen.getByText("Backend development")).toBeInTheDocument();
    expect(screen.getByText("Complete Setup")).toBeInTheDocument();
  });

  it("can go back from step 1 to step 0", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.click(screen.getByText("Next"));
    expect(screen.getByText("Go Experience Level")).toBeInTheDocument();

    await user.click(screen.getByText("Back"));
    expect(screen.getByText("Technical Background")).toBeInTheDocument();
  });

  it("Back button is disabled on step 0", () => {
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    expect(screen.getByText("Back")).toBeDisabled();
  });

  it("calls api.onboarding.complete and onComplete on submit", async () => {
    const onComplete = vi.fn();
    mockComplete.mockResolvedValue({ completed: true });
    const user = userEvent.setup();

    renderWithRouter(<OnboardingPage onComplete={onComplete} />);

    // Navigate to last step
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => {
      expect(mockComplete).toHaveBeenCalledWith(
        expect.objectContaining({ go_experience_level: "beginner" }),
      );
      expect(onComplete).toHaveBeenCalled();
    });
  });

  it("shows alert when API call fails", async () => {
    mockComplete.mockRejectedValue(new Error("fail"));
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const user = userEvent.setup();

    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(
        "Failed to save onboarding. Is the backend running?",
      );
    });
    alertSpy.mockRestore();
  });

  it("allows selecting topic interests", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));

    // Click a topic to select it
    const topicButton = screen.getByText("Databases");
    await user.click(topicButton);

    // The button should now have the selected styling (brand colors)
    expect(topicButton).toHaveClass("border-brand-500");
  });
});
