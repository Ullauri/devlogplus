import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import SettingsPage from "./SettingsPage";
import { renderWithRouter } from "../test/helpers";

describe("SettingsPage", () => {
  it("renders the Settings heading", () => {
    renderWithRouter(<SettingsPage />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders General, Scheduling, and About sections", () => {
    renderWithRouter(<SettingsPage />);
    expect(screen.getByText("General")).toBeInTheDocument();
    expect(screen.getByText("Scheduling")).toBeInTheDocument();
    expect(screen.getByText("About")).toBeInTheDocument();
  });

  it("shows scheduling details", () => {
    renderWithRouter(<SettingsPage />);
    // Each schedule label may now appear in multiple places
    // (the Scheduling summary + the Manual pipeline runs buttons), so
    // assert presence with getAllByText.
    expect(screen.getAllByText(/Profile update/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Quiz generation/i).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/Reading (recommendations|generation)/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(/Project generation/i).length).toBeGreaterThan(
      0,
    );
  });

  it("includes a Manual pipeline runs section", () => {
    renderWithRouter(<SettingsPage />);
    expect(screen.getByText(/Manual pipeline runs/i)).toBeInTheDocument();
    // One "Run now" button per pipeline (4).
    expect(screen.getAllByRole("button", { name: /run now/i })).toHaveLength(4);
  });

  it("mentions DevLog+ in About", () => {
    renderWithRouter(<SettingsPage />);
    expect(
      screen.getByText(/single-user, locally-run developer journal/),
    ).toBeInTheDocument();
  });
});
