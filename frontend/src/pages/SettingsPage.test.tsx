import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsPage from "./SettingsPage";
import { renderWithRouter } from "../test/helpers";

vi.mock("../api/client", () => ({
  api: {
    settings: {
      list: vi.fn(),
      update: vi.fn(),
    },
    pipelines: {
      runProfileUpdate: vi.fn(),
      runQuizGeneration: vi.fn(),
      runReadingGeneration: vi.fn(),
      runProjectGeneration: vi.fn(),
      listRuns: vi.fn(),
    },
    transfer: {
      metadata: vi.fn(),
      exportData: vi.fn(),
      importData: vi.fn(),
    },
  },
}));

import { api } from "../api/client";

const mockList = api.settings.list as ReturnType<typeof vi.fn>;
const mockUpdate = api.settings.update as ReturnType<typeof vi.fn>;
const mockListRuns = api.pipelines.listRuns as ReturnType<typeof vi.fn>;
const mockRunProfile = api.pipelines.runProfileUpdate as ReturnType<
  typeof vi.fn
>;
const mockRunQuiz = api.pipelines.runQuizGeneration as ReturnType<typeof vi.fn>;
const mockMetadata = api.transfer.metadata as ReturnType<typeof vi.fn>;
const mockImport = api.transfer.importData as ReturnType<typeof vi.fn>;

function seedEmpty() {
  mockList.mockResolvedValue([]);
  mockListRuns.mockResolvedValue([]);
}

beforeEach(() => {
  vi.clearAllMocks();
  seedEmpty();
});

describe("SettingsPage — page shell", () => {
  it("renders the Settings heading", () => {
    renderWithRouter(<SettingsPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Settings" }),
    ).toBeInTheDocument();
  });

  it("renders General, Scheduling, and About sections", () => {
    renderWithRouter(<SettingsPage />);
    expect(screen.getByText("General")).toBeInTheDocument();
    expect(screen.getByText("Scheduling")).toBeInTheDocument();
    expect(screen.getByText("About")).toBeInTheDocument();
  });

  it("mentions DevLog+ in About", () => {
    renderWithRouter(<SettingsPage />);
    expect(
      screen.getByText(/single-user, locally-run developer journal/),
    ).toBeInTheDocument();
  });

  it("lists each cron-scheduled pipeline with its time", () => {
    renderWithRouter(<SettingsPage />);
    // The pipeline descriptions below also mention the same times, so
    // assert presence via getAllByText length > 0 for the shared ones.
    expect(screen.getAllByText(/2:00 AM/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Monday 3:00 AM/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Monday 3:30 AM/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Monday 4:00 AM/).length).toBeGreaterThan(0);
  });
});

describe("SettingsPage — General settings", () => {
  it("renders default values when no setting rows exist", async () => {
    renderWithRouter(<SettingsPage />);
    await waitFor(() => {
      const quiz = screen.getByLabelText(
        /Quiz questions per session/,
      ) as HTMLInputElement;
      expect(quiz.value).toBe("10");
    });
    const readings = screen.getByLabelText(
      /Reading recommendations per batch/,
    ) as HTMLInputElement;
    expect(readings.value).toBe("5");
  });

  it("uses values from the server when present (extracts {value: N})", async () => {
    mockList.mockResolvedValue([
      {
        id: "1",
        key: "quiz_question_count",
        value: { value: 7 },
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "2",
        key: "reading_recommendation_count",
        value: { value: 3 },
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    renderWithRouter(<SettingsPage />);
    await waitFor(() => {
      expect(
        (
          screen.getByLabelText(
            /Quiz questions per session/,
          ) as HTMLInputElement
        ).value,
      ).toBe("7");
    });
    expect(
      (
        screen.getByLabelText(
          /Reading recommendations per batch/,
        ) as HTMLInputElement
      ).value,
    ).toBe("3");
  });

  it("Save button is disabled until the value is changed", async () => {
    renderWithRouter(<SettingsPage />);
    await waitFor(() => screen.getByLabelText(/Quiz questions per session/));
    const quizInput = screen.getByLabelText(/Quiz questions per session/);
    const quizRow = quizInput.closest("div.flex") as HTMLElement;
    const saveBtn = within(quizRow).getByRole("button", { name: /save/i });
    expect(saveBtn).toBeDisabled();
  });

  it("enables Save after editing and calls api.settings.update with the new value", async () => {
    mockUpdate.mockResolvedValue({
      id: "1",
      key: "quiz_question_count",
      value: { value: 15 },
      updated_at: "2026-01-01T00:00:00Z",
    });
    const user = userEvent.setup();
    renderWithRouter(<SettingsPage />);
    await waitFor(() => screen.getByLabelText(/Quiz questions per session/));
    const quizInput = screen.getByLabelText(
      /Quiz questions per session/,
    ) as HTMLInputElement;
    // Direct change event is more reliable than clear+type on type=number,
    // where the intermediate empty string parses as NaN and is ignored by
    // handleSettingChange, leaving dirty=false.
    fireEvent.change(quizInput, { target: { value: "15" } });

    const quizRow = quizInput.closest("div.flex") as HTMLElement;
    const saveBtn = within(quizRow).getByRole("button", { name: /save/i });
    await waitFor(() => expect(saveBtn).toBeEnabled());
    await user.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith("quiz_question_count", {
        value: 15,
      });
    });
    await waitFor(() => {
      expect(screen.getByText(/✓ Saved/)).toBeInTheDocument();
    });
  });

  it("keeps Save disabled when the value is out of range", async () => {
    renderWithRouter(<SettingsPage />);
    await waitFor(() => screen.getByLabelText(/Quiz questions per session/));
    const quizInput = screen.getByLabelText(
      /Quiz questions per session/,
    ) as HTMLInputElement;
    fireEvent.change(quizInput, { target: { value: "999" } });

    const quizRow = quizInput.closest("div.flex") as HTMLElement;
    const saveBtn = within(quizRow).getByRole("button", { name: /save/i });
    expect(saveBtn).toBeDisabled();
  });

  it("shows an error banner when the list call fails", async () => {
    mockList.mockRejectedValue(new Error("boom"));
    renderWithRouter(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText(/✗ boom/)).toBeInTheDocument();
    });
  });
});

describe("SettingsPage — Advanced JSON editor", () => {
  it("shows empty-state message when only General keys are stored", async () => {
    mockList.mockResolvedValue([
      {
        id: "1",
        key: "quiz_question_count",
        value: { value: 10 },
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    renderWithRouter(<SettingsPage />);
    await waitFor(() => {
      expect(
        screen.getByText(/No custom settings stored\. Use the form below/),
      ).toBeInTheDocument();
    });
  });

  it("renders custom setting rows (not General keys)", async () => {
    mockList.mockResolvedValue([
      {
        id: "99",
        key: "custom_flag",
        value: { enabled: true },
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    renderWithRouter(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText("custom_flag")).toBeInTheDocument();
    });
  });

  it("rejects invalid snake_case key on Create", async () => {
    const user = userEvent.setup();
    renderWithRouter(<SettingsPage />);
    await waitFor(() => screen.getByText(/Add new setting/));

    await user.type(screen.getByLabelText("Key"), "BadKey");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    expect(screen.getByText(/Key must be snake_case/)).toBeInTheDocument();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it("rejects reserved key prefix (llm_model_)", async () => {
    const user = userEvent.setup();
    renderWithRouter(<SettingsPage />);
    await waitFor(() => screen.getByText(/Add new setting/));

    await user.type(screen.getByLabelText("Key"), "llm_model_topic");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    expect(
      screen.getByText(/reserved for environment variables/),
    ).toBeInTheDocument();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it("creates a new setting when inputs are valid", async () => {
    mockUpdate.mockResolvedValue({
      id: "new",
      key: "my_flag",
      value: { value: "" },
      updated_at: "2026-01-01T00:00:00Z",
    });
    const user = userEvent.setup();
    renderWithRouter(<SettingsPage />);
    await waitFor(() => screen.getByText(/Add new setting/));

    await user.type(screen.getByLabelText("Key"), "my_flag");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        "my_flag",
        expect.objectContaining({ value: "" }),
      );
    });
  });
});

describe("SettingsPage — Data transfer", () => {
  it("fetches export metadata and renders non-zero table counts", async () => {
    mockMetadata.mockResolvedValue({
      table_counts: { journal_entries: 42, quiz_sessions: 0, projects: 3 },
      exported_at: "2026-01-01T00:00:00Z",
    });
    const user = userEvent.setup();
    renderWithRouter(<SettingsPage />);

    await user.click(screen.getByRole("button", { name: /Preview/i }));

    await waitFor(() => {
      expect(screen.getByText(/Export preview/)).toBeInTheDocument();
    });
    expect(screen.getByText(/journal entries:/)).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    // Zero count filtered out
    expect(screen.queryByText(/quiz sessions:/)).not.toBeInTheDocument();
  });

  it("renders Export Data button label", () => {
    renderWithRouter(<SettingsPage />);
    expect(
      screen.getByRole("button", { name: /Export Data/i }),
    ).toBeInTheDocument();
  });

  it("shows import confirmation dialog on file select", async () => {
    const user = userEvent.setup();
    const { container } = renderWithRouter(<SettingsPage />);

    const fileInput = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = new File(["{}"], "bundle.json", { type: "application/json" });
    await user.upload(fileInput, file);

    expect(screen.getByText(/This will/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Yes, replace all data/i }),
    ).toBeInTheDocument();
  });

  it("cancels import and hides the confirmation dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderWithRouter(<SettingsPage />);

    const fileInput = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = new File(["{}"], "bundle.json", { type: "application/json" });
    await user.upload(fileInput, file);

    await user.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(
      screen.queryByRole("button", { name: /Yes, replace all data/i }),
    ).not.toBeInTheDocument();
  });

  it("calls api.transfer.importData with confirmOverwrite=true on confirm", async () => {
    mockImport.mockResolvedValue({
      message: "Imported 42 rows",
      counts: { journal_entries: 42 },
    });
    const user = userEvent.setup();
    const { container } = renderWithRouter(<SettingsPage />);

    const fileInput = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = new File(["{}"], "bundle.json", { type: "application/json" });
    await user.upload(fileInput, file);
    await user.click(
      screen.getByRole("button", { name: /Yes, replace all data/i }),
    );

    await waitFor(() => {
      expect(mockImport).toHaveBeenCalledWith(expect.any(File), true);
    });
    await waitFor(() => {
      expect(screen.getByText(/Imported 42 rows/)).toBeInTheDocument();
    });
  });
});

describe("SettingsPage — Manual pipeline runs", () => {
  it("renders one Run now button per pipeline", () => {
    renderWithRouter(<SettingsPage />);
    expect(screen.getAllByRole("button", { name: /Run now/i })).toHaveLength(4);
  });

  it("calls api.pipelines.runProfileUpdate on its button click", async () => {
    mockRunProfile.mockResolvedValue({ message: "Queued profile update" });
    const user = userEvent.setup();
    renderWithRouter(<SettingsPage />);

    const profileLabel = screen.getByText("Profile update");
    const card = profileLabel.closest("div.rounded-md") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: /Run now/i }));

    await waitFor(() => {
      expect(mockRunProfile).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(
        within(card).getByText(/Queued profile update/),
      ).toBeInTheDocument();
    });
  });

  it("shows an error message when pipeline trigger fails", async () => {
    mockRunQuiz.mockRejectedValue(new Error("no llm"));
    const user = userEvent.setup();
    renderWithRouter(<SettingsPage />);

    const quizLabel = screen.getByText("Generate quiz");
    const card = quizLabel.closest("div.rounded-md") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: /Run now/i }));

    await waitFor(() => {
      expect(within(card).getByText(/no llm/)).toBeInTheDocument();
    });
  });

  it("renders empty runs message when no runs have occurred", async () => {
    renderWithRouter(<SettingsPage />);
    await waitFor(() => {
      expect(
        screen.getByText(/No pipeline runs recorded yet/),
      ).toBeInTheDocument();
    });
  });

  it("renders the runs table with status and pipeline name", async () => {
    mockListRuns.mockResolvedValue([
      {
        id: "r1",
        pipeline: "profile_update",
        status: "completed",
        started_at: "2026-01-01T00:00:00Z",
        completed_at: "2026-01-01T00:00:02Z",
        error: null,
        metadata: { entries: 3 },
      },
      {
        id: "r2",
        pipeline: "quiz_generation",
        status: "failed",
        started_at: "2026-01-02T00:00:00Z",
        completed_at: "2026-01-02T00:00:01Z",
        error: "api key missing",
        metadata: null,
      },
    ]);
    renderWithRouter(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByText("profile_update")).toBeInTheDocument();
    });
    expect(screen.getByText("quiz_generation")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("api key missing")).toBeInTheDocument();
    // Duration formatting: 2000ms → "2.0s"
    expect(screen.getByText("2.0s")).toBeInTheDocument();
  });
});
