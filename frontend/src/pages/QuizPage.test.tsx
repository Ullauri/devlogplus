import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuizPage from "./QuizPage";
import { renderWithRouter } from "../test/helpers";

vi.mock("../api/client", () => ({
  api: {
    quiz: {
      listSessions: vi.fn(),
      getCurrent: vi.fn(),
      getSession: vi.fn(),
      submitAnswer: vi.fn(),
      completeSession: vi.fn(),
    },
    feedback: {
      create: vi.fn().mockResolvedValue({}),
    },
  },
}));

import { api } from "../api/client";
const mockListSessions = api.quiz.listSessions as ReturnType<typeof vi.fn>;
const mockGetCurrent = api.quiz.getCurrent as ReturnType<typeof vi.fn>;
const mockGetSession = api.quiz.getSession as ReturnType<typeof vi.fn>;
const mockSubmitAnswer = api.quiz.submitAnswer as ReturnType<typeof vi.fn>;
const mockCompleteSession = api.quiz.completeSession as ReturnType<
  typeof vi.fn
>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("QuizPage — empty state", () => {
  it("shows empty state when no current quiz", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<QuizPage />);

    await waitFor(() => {
      expect(screen.getByText(/No active quiz/)).toBeInTheDocument();
    });
    expect(screen.queryByText("Past Sessions")).not.toBeInTheDocument();
  });

  it("renders past sessions", async () => {
    mockListSessions.mockResolvedValue([
      {
        id: "s1",
        status: "completed",
        question_count: 10,
        created_at: "2026-01-01T00:00:00Z",
        completed_at: "2026-01-01T12:00:00Z",
      },
    ]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<QuizPage />);

    await waitFor(() => {
      expect(screen.getByText("Past Sessions")).toBeInTheDocument();
    });
    expect(screen.getByText(/10 questions/)).toBeInTheDocument();
    expect(screen.getByText(/completed/)).toBeInTheDocument();
  });
});

describe("QuizPage — active session", () => {
  const activeSession = {
    id: "s1",
    status: "in_progress",
    question_count: 2,
    created_at: "2026-01-01T00:00:00Z",
    questions: [
      {
        id: "q1",
        question_text: "Explain goroutines",
        question_type: "free_text",
        order_index: 0,
      },
      {
        id: "q2",
        question_text: "What is a channel?",
        question_type: "free_text",
        order_index: 1,
      },
    ],
  };

  it("renders current quiz questions and Complete button", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(activeSession);

    renderWithRouter(<QuizPage />);

    await waitFor(() => {
      expect(screen.getByText(/Explain goroutines/)).toBeInTheDocument();
    });
    expect(screen.getByText(/What is a channel/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Complete Quiz" }),
    ).toBeInTheDocument();
  });

  it("hides Complete button when status is not in_progress", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue({
      ...activeSession,
      status: "completed",
    });

    renderWithRouter(<QuizPage />);

    await waitFor(() =>
      expect(screen.getByText(/Explain goroutines/)).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: "Complete Quiz" }),
    ).not.toBeInTheDocument();
  });

  it("submit button sends the typed answer to api.quiz.submitAnswer", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(activeSession);
    mockSubmitAnswer.mockResolvedValue({});
    mockGetSession.mockResolvedValue(activeSession);
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText(/Explain goroutines/));

    const textareas = screen.getAllByPlaceholderText("Your answer…");
    await user.type(textareas[0], "concurrent functions");
    const submitBtns = screen.getAllByRole("button", { name: "Submit" });
    await user.click(submitBtns[0]);

    await waitFor(() => {
      expect(mockSubmitAnswer).toHaveBeenCalledWith(
        "q1",
        "concurrent functions",
      );
    });
  });

  it("does NOT call submitAnswer when the textarea is empty", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(activeSession);
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText(/Explain goroutines/));

    const submitBtns = screen.getAllByRole("button", { name: "Submit" });
    await user.click(submitBtns[0]);

    expect(mockSubmitAnswer).not.toHaveBeenCalled();
  });

  it("clicking Complete Quiz calls api.quiz.completeSession with session id", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValueOnce(activeSession);
    mockGetCurrent.mockRejectedValueOnce(new Error("none"));
    mockCompleteSession.mockResolvedValue({});
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText("Complete Quiz"));
    await user.click(screen.getByRole("button", { name: "Complete Quiz" }));

    await waitFor(() => {
      expect(mockCompleteSession).toHaveBeenCalledWith("s1");
    });
  });
});

describe("QuizPage — answered questions render evaluation badges", () => {
  const baseSession = {
    id: "s1",
    status: "in_progress",
    question_count: 1,
    created_at: "2026-01-01T00:00:00Z",
  };

  function withAnswer(correctness: string, explanation = "Feedback") {
    return {
      ...baseSession,
      questions: [
        {
          id: "q1",
          question_text: "Explain goroutines",
          question_type: "free_text",
          order_index: 0,
          answer: { answer_text: "ans" },
          evaluation: { correctness, explanation },
        },
      ],
    };
  }

  it("uses green badge for 'full' correctness", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(withAnswer("full"));
    renderWithRouter(<QuizPage />);
    const badge = await screen.findByText("full");
    expect(badge.className).toContain("bg-green-100");
    expect(badge.className).toContain("text-green-800");
    expect(badge.className).not.toContain("bg-red-100");
  });

  it("uses yellow badge for 'partial' correctness", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(withAnswer("partial"));
    renderWithRouter(<QuizPage />);
    const badge = await screen.findByText("partial");
    expect(badge.className).toContain("bg-yellow-100");
    expect(badge.className).toContain("text-yellow-800");
  });

  it("uses red badge for other (fallback) correctness", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(withAnswer("none"));
    renderWithRouter(<QuizPage />);
    const badge = await screen.findByText("none");
    expect(badge.className).toContain("bg-red-100");
    expect(badge.className).toContain("text-red-800");
  });

  it("shows the answer text instead of the textarea when question has an answer", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue({
      ...baseSession,
      questions: [
        {
          id: "q1",
          question_text: "Q",
          question_type: "free_text",
          order_index: 0,
          answer: { answer_text: "my answer" },
        },
      ],
    });
    renderWithRouter(<QuizPage />);
    await screen.findByText("my answer");
    expect(
      screen.queryByPlaceholderText("Your answer…"),
    ).not.toBeInTheDocument();
  });

  it("numbers questions starting at 1", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue({
      id: "s1",
      status: "in_progress",
      question_count: 2,
      created_at: "2026-01-01T00:00:00Z",
      questions: [
        {
          id: "q1",
          question_text: "First",
          question_type: "free_text",
          order_index: 0,
        },
        {
          id: "q2",
          question_text: "Second",
          question_type: "free_text",
          order_index: 1,
        },
      ],
    });
    renderWithRouter(<QuizPage />);
    await screen.findByText(/1\. First/);
    expect(screen.getByText(/2\. Second/)).toBeInTheDocument();
  });
});
