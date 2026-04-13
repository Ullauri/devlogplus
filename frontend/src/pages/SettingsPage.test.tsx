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
    expect(screen.getByText(/Profile update/)).toBeInTheDocument();
    expect(screen.getByText(/Quiz generation/)).toBeInTheDocument();
    expect(screen.getByText(/Reading recommendations/)).toBeInTheDocument();
    expect(screen.getByText(/Project generation/)).toBeInTheDocument();
  });

  it("mentions DevLog+ in About", () => {
    renderWithRouter(<SettingsPage />);
    expect(
      screen.getByText(/single-user, locally-run developer journal/),
    ).toBeInTheDocument();
  });
});
