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
      listFor: vi.fn().mockResolvedValue([]),
    },
    pipelines: {
      listRuns: vi.fn().mockResolvedValue([]),
      runQuizEvaluation: vi.fn().mockResolvedValue({}),
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
const mockListRuns = api.pipelines.listRuns as ReturnType<typeof vi.fn>;

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

  it("disables Generate quiz button until pipeline status has loaded", async () => {
    // Unresolved fetch simulates the remount-after-tab-switch race window
    let resolveRuns!: (v: unknown[]) => void;
    mockListRuns.mockReturnValue(
      new Promise<unknown[]>((r) => {
        resolveRuns = r;
      }),
    );
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<QuizPage />);

    const btn = await screen.findByRole("button", {
      name: /generate quiz now/i,
    });
    expect(btn).toBeDisabled();

    resolveRuns([]);
    await waitFor(() => expect(btn).not.toBeDisabled());
  });

  it("hides Generate button when quiz_generation pipeline is running", async () => {
    mockListRuns.mockResolvedValue([
      {
        id: "r1",
        pipeline: "quiz_generation",
        status: "started",
        started_at: new Date().toISOString(),
      },
    ]);
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<QuizPage />);

    // Wait for status to load.
    await waitFor(() => {
      expect(mockListRuns).toHaveBeenCalled();
    });

    // The generate button should not be present while the pipeline is running.
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /generate quiz now/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("keeps Generate button disabled during the re-fetch triggered by returning to the tab", async () => {
    // First render: pipeline is idle, button loads normally.
    // Use persistent mock (not Once) so both listRuns calls (quiz_generation
    // and quiz_evaluation) resolve with the same empty array.
    mockListRuns.mockResolvedValue([]);
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<QuizPage />);

    const btn = await screen.findByRole("button", {
      name: /generate quiz now/i,
    });
    await waitFor(() => expect(btn).not.toBeDisabled());

    // Simulate the user switching back to the tab while a pipeline is now
    // running. Hold the next fetch open so we can assert on the in-flight
    // state — this is the race window that previously allowed a click.
    let resolveRecheck!: (v: unknown[]) => void;
    mockListRuns.mockReturnValue(
      new Promise<unknown[]>((r) => {
        resolveRecheck = r;
      }),
    );

    // Fire visibilitychange (same as returning to a browser tab).
    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    // During the in-flight re-fetch the button must be disabled.
    await waitFor(() => expect(btn).toBeDisabled());

    // Resolve with a running pipeline — button section disappears entirely.
    resolveRecheck([
      {
        id: "r1",
        pipeline: "quiz_generation",
        status: "started",
        started_at: new Date().toISOString(),
      },
    ]);

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /generate quiz now/i }),
      ).not.toBeInTheDocument();
    });
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
    await user.type(textareas[0]!, "concurrent functions");
    const submitBtns = screen.getAllByRole("button", { name: "Submit" });
    await user.click(submitBtns[0]!);

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
    await user.click(submitBtns[0]!);

    expect(mockSubmitAnswer).not.toHaveBeenCalled();
  });

  it("clicking Complete Quiz calls api.quiz.completeSession with session id", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValueOnce(activeSession);
    mockCompleteSession.mockResolvedValue({});
    mockGetSession.mockResolvedValue({ ...activeSession, status: "completed" });
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText("Complete Quiz"));
    await user.click(screen.getByRole("button", { name: "Complete Quiz" }));

    await waitFor(() => {
      expect(mockCompleteSession).toHaveBeenCalledWith("s1");
    });
    // After completion, review view should show
    await waitFor(() => {
      expect(screen.getByText("Quiz Results")).toBeInTheDocument();
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

describe("QuizPage — review past session", () => {
  const pastSession = {
    id: "s1",
    status: "evaluated",
    question_count: 2,
    created_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T12:00:00Z",
    questions: [
      {
        id: "q1",
        question_text: "Explain goroutines",
        question_type: "free_text",
        order_index: 0,
        answer: { answer_text: "Lightweight threads" },
        evaluation: {
          correctness: "full",
          explanation: "Correct — goroutines are lightweight.",
        },
        reference_answer:
          "Goroutines are lightweight threads managed by the Go runtime.",
      },
      {
        id: "q2",
        question_text: "What is a channel?",
        question_type: "free_text",
        order_index: 1,
        answer: { answer_text: "A pipe" },
        evaluation: {
          correctness: "partial",
          explanation: "Partially correct.",
        },
      },
    ],
  };

  it("clicking a past session opens the review view with questions and evaluations", async () => {
    mockListSessions.mockResolvedValue([
      {
        id: "s1",
        status: "evaluated",
        question_count: 2,
        created_at: "2026-01-01T00:00:00Z",
        completed_at: "2026-01-01T12:00:00Z",
      },
    ]);
    mockGetCurrent.mockRejectedValue(new Error("none"));
    mockGetSession.mockResolvedValue(pastSession);
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);

    await waitFor(() => {
      expect(screen.getByText("Past Sessions")).toBeInTheDocument();
    });

    // Past session items are now buttons
    const sessionBtn = screen.getByText(/2 questions/).closest("button")!;
    await user.click(sessionBtn);

    await waitFor(() => {
      expect(screen.getByText("Quiz Results")).toBeInTheDocument();
    });
    expect(mockGetSession).toHaveBeenCalledWith("s1");
    expect(screen.getByText(/Explain goroutines/)).toBeInTheDocument();
    expect(screen.getByText("full")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
  });

  it("shows score summary with correct/partial/incorrect counts", async () => {
    mockListSessions.mockResolvedValue([
      {
        id: "s1",
        status: "evaluated",
        question_count: 2,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mockGetCurrent.mockRejectedValue(new Error("none"));
    mockGetSession.mockResolvedValue(pastSession);
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText("Past Sessions"));
    await user.click(screen.getByText(/2 questions/).closest("button")!);

    await waitFor(() => {
      expect(screen.getByText("Quiz Results")).toBeInTheDocument();
    });
    // Score summary: 1 full, 1 partial, 0 incorrect
    expect(screen.getByText("Correct")).toBeInTheDocument();
    expect(screen.getByText("Partial")).toBeInTheDocument();
    expect(screen.getByText("Incorrect")).toBeInTheDocument();
  });

  it("back button returns to the main quiz view", async () => {
    mockListSessions.mockResolvedValue([
      {
        id: "s1",
        status: "evaluated",
        question_count: 2,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mockGetCurrent.mockRejectedValue(new Error("none"));
    mockGetSession.mockResolvedValue(pastSession);
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText("Past Sessions"));
    await user.click(screen.getByText(/2 questions/).closest("button")!);
    await waitFor(() => screen.getByText("Quiz Results"));

    await user.click(screen.getByText("← Back to Quiz"));

    await waitFor(() => {
      expect(screen.getByText("Past Sessions")).toBeInTheDocument();
    });
    expect(screen.queryByText("Quiz Results")).not.toBeInTheDocument();
  });

  it("shows pending evaluation banner when session is not yet evaluated", async () => {
    const pendingSession = {
      ...pastSession,
      status: "completed",
      questions: pastSession.questions.map((q) => ({
        ...q,
        evaluation: undefined,
      })),
    };
    mockListSessions.mockResolvedValue([
      {
        id: "s1",
        status: "completed",
        question_count: 2,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mockGetCurrent.mockRejectedValue(new Error("none"));
    mockGetSession.mockResolvedValue(pendingSession);
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText("Past Sessions"));
    await user.click(screen.getByText(/2 questions/).closest("button")!);

    await waitFor(() => {
      expect(
        screen.getByText(/Evaluations have not been generated yet/),
      ).toBeInTheDocument();
    });
  });

  it("completing a quiz redirects to the review view", async () => {
    const activeSession = {
      id: "s1",
      status: "in_progress",
      question_count: 1,
      created_at: "2026-01-01T00:00:00Z",
      questions: [
        {
          id: "q1",
          question_text: "Explain goroutines",
          question_type: "free_text",
          order_index: 0,
          answer: { answer_text: "Lightweight threads" },
        },
      ],
    };
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue(activeSession);
    mockCompleteSession.mockResolvedValue({});
    mockGetSession.mockResolvedValue({
      ...pastSession,
      question_count: 1,
      questions: [pastSession.questions[0]],
    });
    const user = userEvent.setup();

    renderWithRouter(<QuizPage />);
    await waitFor(() => screen.getByText("Complete Quiz"));
    await user.click(screen.getByRole("button", { name: "Complete Quiz" }));

    await waitFor(() => {
      expect(screen.getByText("Quiz Results")).toBeInTheDocument();
    });
    expect(mockCompleteSession).toHaveBeenCalledWith("s1");
    expect(mockGetSession).toHaveBeenCalledWith("s1");
  });
});
