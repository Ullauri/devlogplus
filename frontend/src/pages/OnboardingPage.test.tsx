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

describe("OnboardingPage — shell", () => {
  it("renders the welcome heading", () => {
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    expect(screen.getByText("Welcome to DevLog+")).toBeInTheDocument();
  });

  it("shows step 0 (Technical Background) by default, other steps hidden", () => {
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    expect(screen.getByText("Technical Background")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. 5")).toBeInTheDocument();
    expect(screen.queryByText("Go Experience Level")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Topic Interests (optional)"),
    ).not.toBeInTheDocument();
  });

  it("Back button is disabled on step 0", () => {
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    expect(screen.getByText("Back")).toBeDisabled();
  });

  it("shows Next button (not Complete Setup) on steps 0 and 1", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    expect(screen.getByText("Next")).toBeInTheDocument();
    expect(screen.queryByText("Complete Setup")).not.toBeInTheDocument();

    await user.click(screen.getByText("Next"));
    expect(screen.getByText("Next")).toBeInTheDocument();
    expect(screen.queryByText("Complete Setup")).not.toBeInTheDocument();
  });
});

describe("OnboardingPage — navigation", () => {
  it("navigates to step 1 on Next click", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    expect(screen.getByText("Go Experience Level")).toBeInTheDocument();
  });

  it("navigates to step 2 with two Next clicks and shows Complete Setup (not Next)", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    expect(screen.getByText("Topic Interests (optional)")).toBeInTheDocument();
    expect(screen.getByText("Backend development")).toBeInTheDocument();
    expect(screen.getByText("Complete Setup")).toBeInTheDocument();
    expect(screen.queryByText("Next")).not.toBeInTheDocument();
  });

  it("can go back from step 1 to step 0", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Back"));
    expect(screen.getByText("Technical Background")).toBeInTheDocument();
  });

  it("can go back from step 2 to step 1", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Back"));
    expect(screen.getByText("Go Experience Level")).toBeInTheDocument();
  });

  it("progress indicator highlights only steps <= current", async () => {
    const user = userEvent.setup();
    const { container } = renderWithRouter(
      <OnboardingPage onComplete={() => {}} />,
    );
    let bars = container.querySelectorAll("div.h-1\\.5");
    expect(bars).toHaveLength(3);
    expect(bars[0]!.className).toContain("bg-brand-500");
    expect(bars[1]!.className).toContain("bg-gray-200");
    expect(bars[2]!.className).toContain("bg-gray-200");

    await user.click(screen.getByText("Next"));
    bars = container.querySelectorAll("div.h-1\\.5");
    expect(bars[0]!.className).toContain("bg-brand-500");
    expect(bars[1]!.className).toContain("bg-brand-500");
    expect(bars[2]!.className).toContain("bg-gray-200");
  });
});

describe("OnboardingPage — Go level radio", () => {
  it("defaults to beginner", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));

    const beginner = screen.getByLabelText(
      /Beginner — written a few small programs/,
    ) as HTMLInputElement;
    expect(beginner.checked).toBe(true);
  });

  it("selecting another level updates the submitted payload", async () => {
    mockComplete.mockResolvedValue({ completed: true });
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.click(screen.getByText("Next"));
    await user.click(
      screen.getByLabelText(/Advanced — extensive production experience/),
    );
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => {
      expect(mockComplete).toHaveBeenCalledWith(
        expect.objectContaining({ go_experience: { level: "advanced" } }),
      );
    });
  });
});

describe("OnboardingPage — topic toggle", () => {
  it("applies selected styling on click and removes it on second click", async () => {
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));

    const topic = screen.getByText("Databases");
    expect(topic.className).toContain("border-gray-300");
    expect(topic.className).not.toContain("border-brand-500");

    await user.click(topic);
    expect(topic.className).toContain("border-brand-500");
    expect(topic.className).toContain("bg-brand-50");

    await user.click(topic);
    expect(topic.className).toContain("border-gray-300");
    expect(topic.className).not.toContain("border-brand-500");
  });

  it("submits selected topics as an array", async () => {
    mockComplete.mockResolvedValue({ completed: true });
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Databases"));
    await user.click(screen.getByText("API design"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => expect(mockComplete).toHaveBeenCalled());
    const payload = mockComplete.mock.calls[0]![0];
    expect(payload.topic_interests).toEqual(["Databases", "API design"]);
  });

  it("omits topic_interests when no topic is selected", async () => {
    mockComplete.mockResolvedValue({ completed: true });
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => expect(mockComplete).toHaveBeenCalled());
    const payload = mockComplete.mock.calls[0]![0];
    expect(payload.topic_interests).toBeUndefined();
  });
});

describe("OnboardingPage — self-assessment payload", () => {
  it("parses years as integer and splits languages on comma", async () => {
    mockComplete.mockResolvedValue({ completed: true });
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);

    await user.type(screen.getByPlaceholderText("e.g. 5"), "7");
    await user.type(
      screen.getByPlaceholderText("e.g. Python, TypeScript, Go"),
      "Python, TypeScript , Go",
    );
    await user.type(
      screen.getByPlaceholderText("e.g. backend APIs, data pipelines"),
      "backend APIs",
    );
    await user.type(
      screen.getByPlaceholderText("e.g. systems programming, concurrency"),
      "concurrency",
    );

    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => expect(mockComplete).toHaveBeenCalled());
    const payload = mockComplete.mock.calls[0]![0];
    expect(payload.self_assessment.years_experience).toBe(7);
    expect(payload.self_assessment.primary_languages).toEqual([
      "Python",
      "TypeScript",
      "Go",
    ]);
    expect(payload.self_assessment.comfort_areas).toEqual(["backend APIs"]);
    expect(payload.self_assessment.growth_areas).toEqual(["concurrency"]);
  });

  it("sends null years_experience and empty arrays when fields are blank", async () => {
    mockComplete.mockResolvedValue({ completed: true });
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => expect(mockComplete).toHaveBeenCalled());
    const payload = mockComplete.mock.calls[0]![0];
    expect(payload.self_assessment.years_experience).toBeNull();
    expect(payload.self_assessment.primary_languages).toEqual([]);
    expect(payload.self_assessment.comfort_areas).toEqual([]);
    expect(payload.self_assessment.growth_areas).toEqual([]);
  });

  it("shows Saving… label while submitting", async () => {
    let resolve!: (v: unknown) => void;
    mockComplete.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={() => {}} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    expect(await screen.findByText("Saving…")).toBeInTheDocument();
    resolve({ completed: true });
  });

  it("calls onComplete callback after successful submit", async () => {
    const onComplete = vi.fn();
    mockComplete.mockResolvedValue({ completed: true });
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={onComplete} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));
    await waitFor(() => expect(onComplete).toHaveBeenCalled());
  });

  it("shows alert and does NOT call onComplete when API fails", async () => {
    mockComplete.mockRejectedValue(new Error("fail"));
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const onComplete = vi.fn();
    const user = userEvent.setup();
    renderWithRouter(<OnboardingPage onComplete={onComplete} />);
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Next"));
    await user.click(screen.getByText("Complete Setup"));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(
        "Failed to save onboarding. Is the backend running?",
      );
    });
    expect(onComplete).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });
});
