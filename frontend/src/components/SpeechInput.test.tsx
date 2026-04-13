import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SpeechInput from "./SpeechInput";

describe("SpeechInput", () => {
  it("renders a button with 'Start dictation' title", () => {
    render(<SpeechInput onTranscript={() => {}} />);
    expect(screen.getByTitle("Start dictation")).toBeInTheDocument();
  });

  it("alerts when SpeechRecognition is not supported", async () => {
    // jsdom doesn't have SpeechRecognition
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const user = userEvent.setup();

    render(<SpeechInput onTranscript={() => {}} />);
    await user.click(screen.getByTitle("Start dictation"));

    expect(alertSpy).toHaveBeenCalledWith(
      "Speech recognition not supported in this browser.",
    );
    alertSpy.mockRestore();
  });
});
