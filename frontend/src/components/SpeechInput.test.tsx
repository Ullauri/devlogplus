import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SpeechInput from "./SpeechInput";

interface FakeRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: { results: unknown }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
}

function installMockSpeechRecognition(): FakeRecognition {
  const instance: FakeRecognition = {
    continuous: false,
    interimResults: false,
    lang: "",
    onresult: null,
    onerror: null,
    onend: null,
    start: vi.fn(),
    stop: vi.fn(),
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).SpeechRecognition = vi.fn(() => instance);
  return instance;
}

afterEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (window as any).SpeechRecognition;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (window as any).webkitSpeechRecognition;
});

describe("SpeechInput — idle state", () => {
  it("renders a button with 'Start dictation' title", () => {
    render(<SpeechInput onTranscript={() => {}} />);
    expect(screen.getByTitle("Start dictation")).toBeInTheDocument();
  });

  it("uses gray styling (not red) when idle", () => {
    render(<SpeechInput onTranscript={() => {}} />);
    const btn = screen.getByTitle("Start dictation");
    expect(btn.className).toContain("bg-gray-100");
    expect(btn.className).toContain("text-gray-500");
    expect(btn.className).not.toContain("bg-red-100");
  });
});

describe("SpeechInput — unsupported browser", () => {
  it("alerts when SpeechRecognition is not supported", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const user = userEvent.setup();

    render(<SpeechInput onTranscript={() => {}} />);
    await user.click(screen.getByTitle("Start dictation"));

    expect(alertSpy).toHaveBeenCalledWith(
      "Speech recognition not supported in this browser.",
    );
    alertSpy.mockRestore();
  });

  it("does NOT switch to listening state when unsupported", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const user = userEvent.setup();

    render(<SpeechInput onTranscript={() => {}} />);
    await user.click(screen.getByTitle("Start dictation"));

    expect(screen.getByTitle("Start dictation")).toBeInTheDocument();
    expect(screen.queryByTitle("Stop dictation")).not.toBeInTheDocument();
    alertSpy.mockRestore();
  });
});

describe("SpeechInput — supported browser", () => {
  it("starts recognition and shows listening state on click", async () => {
    installMockSpeechRecognition();
    const user = userEvent.setup();
    render(<SpeechInput onTranscript={() => {}} />);

    await user.click(screen.getByTitle("Start dictation"));

    const stopBtn = screen.getByTitle("Stop dictation");
    expect(stopBtn).toBeInTheDocument();
    expect(stopBtn.className).toContain("bg-red-100");
    expect(stopBtn.className).toContain("text-red-600");
  });

  it("configures recognition with continuous=true and en-US lang", async () => {
    const instance = installMockSpeechRecognition();
    const user = userEvent.setup();
    render(<SpeechInput onTranscript={() => {}} />);

    await user.click(screen.getByTitle("Start dictation"));

    expect(instance.continuous).toBe(true);
    expect(instance.interimResults).toBe(false);
    expect(instance.lang).toBe("en-US");
    expect(instance.start).toHaveBeenCalledTimes(1);
  });

  it("delivers joined transcripts via onTranscript callback", async () => {
    const instance = installMockSpeechRecognition();
    const onTranscript = vi.fn();
    const user = userEvent.setup();
    render(<SpeechInput onTranscript={onTranscript} />);

    await user.click(screen.getByTitle("Start dictation"));

    act(() => {
      instance.onresult?.({
        results: [[{ transcript: "hello" }], [{ transcript: "world" }]],
      });
    });

    expect(onTranscript).toHaveBeenCalledWith("hello world");
  });

  it("calls stop() and returns to idle on second click", async () => {
    const instance = installMockSpeechRecognition();
    const user = userEvent.setup();
    render(<SpeechInput onTranscript={() => {}} />);

    await user.click(screen.getByTitle("Start dictation"));
    await user.click(screen.getByTitle("Stop dictation"));

    expect(instance.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByTitle("Start dictation")).toBeInTheDocument();
  });

  it("returns to idle state when onerror fires", async () => {
    const instance = installMockSpeechRecognition();
    const user = userEvent.setup();
    render(<SpeechInput onTranscript={() => {}} />);

    await user.click(screen.getByTitle("Start dictation"));
    expect(screen.getByTitle("Stop dictation")).toBeInTheDocument();

    act(() => {
      instance.onerror?.();
    });
    expect(screen.getByTitle("Start dictation")).toBeInTheDocument();
  });

  it("returns to idle state when onend fires", async () => {
    const instance = installMockSpeechRecognition();
    const user = userEvent.setup();
    render(<SpeechInput onTranscript={() => {}} />);

    await user.click(screen.getByTitle("Start dictation"));
    act(() => {
      instance.onend?.();
    });
    expect(screen.getByTitle("Start dictation")).toBeInTheDocument();
  });

  it("falls back to webkitSpeechRecognition when SpeechRecognition is absent", async () => {
    const instance: FakeRecognition = {
      continuous: false,
      interimResults: false,
      lang: "",
      onresult: null,
      onerror: null,
      onend: null,
      start: vi.fn(),
      stop: vi.fn(),
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).webkitSpeechRecognition = vi.fn(() => instance);

    const user = userEvent.setup();
    render(<SpeechInput onTranscript={() => {}} />);
    await user.click(screen.getByTitle("Start dictation"));

    expect(instance.start).toHaveBeenCalled();
    expect(screen.getByTitle("Stop dictation")).toBeInTheDocument();
  });
});

// Keep beforeEach importable even though not used at top-level (future edits).
void beforeEach;
