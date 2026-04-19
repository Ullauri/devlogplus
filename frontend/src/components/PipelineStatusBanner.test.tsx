import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelineStatusBanner from "./PipelineStatusBanner";

describe("PipelineStatusBanner", () => {
  it("renders nothing until loaded", () => {
    const { container } = render(
      <PipelineStatusBanner
        label="quiz"
        running={[]}
        runningSince={null}
        lastCompletedAt={null}
        loaded={false}
        onRefresh={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows running state with spinner and label noun", () => {
    render(
      <PipelineStatusBanner
        label="quiz"
        running={["quiz_generation"]}
        runningSince={new Date(Date.now() - 2 * 60_000).toISOString()}
        lastCompletedAt={null}
        loaded={true}
        onRefresh={() => {}}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      /Generating your quiz/,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/started 2m ago/);
  });

  it("shows last updated when idle with history", () => {
    render(
      <PipelineStatusBanner
        label="quiz"
        running={[]}
        runningSince={null}
        lastCompletedAt={new Date(Date.now() - 60 * 60_000).toISOString()}
        loaded={true}
        onRefresh={() => {}}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/Last updated 1h ago/);
  });

  it("invokes onRefresh when the refresh button is clicked", async () => {
    const onRefresh = vi.fn();
    render(
      <PipelineStatusBanner
        label="quiz"
        running={[]}
        runningSince={null}
        lastCompletedAt={new Date().toISOString()}
        loaded={true}
        onRefresh={onRefresh}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("disables the refresh button while refreshing", () => {
    render(
      <PipelineStatusBanner
        label="quiz"
        running={[]}
        runningSince={null}
        lastCompletedAt={new Date().toISOString()}
        loaded={true}
        onRefresh={() => {}}
        refreshing
      />,
    );
    expect(screen.getByRole("button", { name: /Refresh/ })).toBeDisabled();
  });

  it("only shows a bare refresh button when no history and not running", () => {
    render(
      <PipelineStatusBanner
        label="quiz"
        running={[]}
        runningSince={null}
        lastCompletedAt={null}
        loaded={true}
        onRefresh={() => {}}
      />,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Refresh/ })).toBeInTheDocument();
  });
});
