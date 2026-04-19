import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FeedbackControls from "./FeedbackControls";

vi.mock("../api/client", () => ({
  api: {
    feedback: {
      create: vi.fn().mockResolvedValue({ id: "f1" }),
      listFor: vi.fn().mockResolvedValue([]),
    },
  },
}));

import { api } from "../api/client";

beforeEach(() => {
  vi.clearAllMocks();
  (
    api.feedback.listFor as unknown as ReturnType<typeof vi.fn>
  ).mockResolvedValue([]);
});

describe("FeedbackControls", () => {
  it("renders thumbs up and thumbs down buttons", () => {
    render(<FeedbackControls targetType="quiz_question" targetId="q1" />);
    expect(screen.getByLabelText("Mark this as helpful")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Mark this as not helpful"),
    ).toBeInTheDocument();
  });

  it("renders the '+ note' button", () => {
    render(<FeedbackControls targetType="reading" targetId="r1" />);
    expect(screen.getByText("+ note")).toBeInTheDocument();
  });

  it("calls api.feedback.create on thumbs up click", async () => {
    const user = userEvent.setup();
    render(<FeedbackControls targetType="reading" targetId="r1" />);

    await user.click(screen.getByLabelText("Mark this as helpful"));

    expect(api.feedback.create).toHaveBeenCalledWith(
      expect.objectContaining({
        target_type: "reading",
        target_id: "r1",
        reaction: "thumbs_up",
      }),
    );
  });

  it("shows note input after clicking '+ note'", async () => {
    const user = userEvent.setup();
    render(<FeedbackControls targetType="project" targetId="p1" />);

    await user.click(screen.getByText("+ note"));
    expect(
      screen.getByPlaceholderText("Feedforward note…"),
    ).toBeInTheDocument();
  });

  it("shows 'Saved' text after submitting feedback", async () => {
    const user = userEvent.setup();
    render(<FeedbackControls targetType="reading" targetId="r1" />);

    await user.click(screen.getByLabelText("Mark this as not helpful"));
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("hydrates persisted reaction on mount", async () => {
    (
      api.feedback.listFor as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValueOnce([
      {
        id: "f1",
        target_type: "reading",
        target_id: "r1",
        reaction: "thumbs_up",
        note: null,
        created_at: "2026-04-19T12:00:00Z",
      },
    ]);

    render(<FeedbackControls targetType="reading" targetId="r1" />);

    await waitFor(() => {
      expect(screen.getByLabelText("Mark this as helpful")).toHaveClass(
        "text-green-600",
      );
    });
  });

  it("hydrates persisted note on mount and shows edit affordance", async () => {
    (
      api.feedback.listFor as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValueOnce([
      {
        id: "f2",
        target_type: "reading",
        target_id: "r2",
        reaction: null,
        note: "too basic",
        created_at: "2026-04-19T12:00:00Z",
      },
    ]);

    render(<FeedbackControls targetType="reading" targetId="r2" />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("too basic")).toBeInTheDocument();
    });
    expect(screen.getByText("edit note")).toBeInTheDocument();
  });

  it("clicking an already-active reaction clears it", async () => {
    (
      api.feedback.listFor as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValueOnce([
      {
        id: "f3",
        target_type: "reading",
        target_id: "r3",
        reaction: "thumbs_down",
        note: null,
        created_at: "2026-04-19T12:00:00Z",
      },
    ]);

    const user = userEvent.setup();
    render(<FeedbackControls targetType="reading" targetId="r3" />);

    await waitFor(() => {
      expect(screen.getByLabelText("Mark this as not helpful")).toHaveClass(
        "text-red-600",
      );
    });
    await user.click(screen.getByLabelText("Mark this as not helpful"));

    expect(api.feedback.create).toHaveBeenCalledWith(
      expect.objectContaining({ reaction: undefined }),
    );
  });
});
