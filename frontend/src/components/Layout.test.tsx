import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import Layout from "./Layout";
import { renderWithRouter } from "../test/helpers";

describe("Layout", () => {
  it("renders the brand name", () => {
    renderWithRouter(<Layout />);
    expect(screen.getByText("DevLog+")).toBeInTheDocument();
  });

  it("renders all navigation links", () => {
    renderWithRouter(<Layout />);
    const labels = [
      "Journal",
      "Profile",
      "Quiz",
      "Readings",
      "Projects",
      "Triage",
      "Settings",
    ];
    for (const label of labels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("navigation links have correct hrefs", () => {
    renderWithRouter(<Layout />);
    expect(screen.getByText("Journal").closest("a")).toHaveAttribute(
      "href",
      "/journal",
    );
    expect(screen.getByText("Profile").closest("a")).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(screen.getByText("Settings").closest("a")).toHaveAttribute(
      "href",
      "/settings",
    );
  });
});
