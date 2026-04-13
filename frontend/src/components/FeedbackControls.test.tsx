import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FeedbackControls from "./FeedbackControls";

vi.mock("../api/client", () => ({
  api: {
    feedback: {
      create: vi.fn().mockResolvedValue({ id: "f1" }),
    },
  },
}));

import { api } from "../api/client";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FeedbackControls", () => {
  it("renders thumbs up and thumbs down buttons", () => {
    render(<FeedbackControls targetType="quiz_question" targetId="q1" />);
    expect(screen.getByTitle("Helpful")).toBeInTheDocument();
    expect(screen.getByTitle("Not helpful")).toBeInTheDocument();
  });

  it("renders the '+ note' button", () => {
    render(<FeedbackControls targetType="reading" targetId="r1" />);
    expect(screen.getByText("+ note")).toBeInTheDocument();
  });

  it("calls api.feedback.create on thumbs up click", async () => {
    const user = userEvent.setup();
    render(<FeedbackControls targetType="reading" targetId="r1" />);

    await user.click(screen.getByTitle("Helpful"));

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

    await user.click(screen.getByTitle("Not helpful"));
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });
});
