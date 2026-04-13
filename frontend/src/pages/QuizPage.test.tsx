import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

beforeEach(() => {
  vi.clearAllMocks();
});

describe("QuizPage", () => {
  it("shows empty state when no current quiz", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockRejectedValue(new Error("none"));

    renderWithRouter(<QuizPage />);

    await waitFor(() => {
      expect(screen.getByText(/No active quiz/)).toBeInTheDocument();
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
      expect(screen.getByText(/10 questions/)).toBeInTheDocument();
    });
  });

  it("renders current quiz questions", async () => {
    mockListSessions.mockResolvedValue([]);
    mockGetCurrent.mockResolvedValue({
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
    });

    renderWithRouter(<QuizPage />);

    await waitFor(() => {
      expect(screen.getByText(/Explain goroutines/)).toBeInTheDocument();
      expect(screen.getByText(/What is a channel/)).toBeInTheDocument();
      expect(screen.getByText("Complete Quiz")).toBeInTheDocument();
    });
  });
});
