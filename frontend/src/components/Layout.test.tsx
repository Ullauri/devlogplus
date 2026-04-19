import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import Layout from "./Layout";
import { renderWithRouter } from "../test/helpers";

describe("Layout — static content", () => {
  it("renders the brand name", () => {
    renderWithRouter(<Layout />);
    expect(screen.getByText("DevLog+")).toBeInTheDocument();
  });

  it("renders all navigation links with expected labels and hrefs", () => {
    renderWithRouter(<Layout />);
    const pairs: ReadonlyArray<readonly [string, string]> = [
      ["Journal", "/journal"],
      ["Profile", "/profile"],
      ["Quiz", "/quiz"],
      ["Readings", "/readings"],
      ["Projects", "/projects"],
      ["Triage", "/triage"],
      ["Settings", "/settings"],
    ];
    for (const [label, href] of pairs) {
      const link = screen.getByText(label).closest("a");
      expect(link).toHaveAttribute("href", href);
    }
  });
});

describe("Layout — active link highlighting", () => {
  it("highlights the active route with brand colors and leaves others gray", () => {
    renderWithRouter(<Layout />, { route: "/journal" });
    const activeLink = screen.getByText("Journal").closest("a")!;
    expect(activeLink.className).toContain("bg-brand-50");
    expect(activeLink.className).toContain("text-brand-700");

    const inactiveLink = screen.getByText("Profile").closest("a")!;
    expect(inactiveLink.className).toContain("text-gray-600");
    expect(inactiveLink.className).not.toContain("bg-brand-50");
  });

  it("highlights /settings when that route is active", () => {
    renderWithRouter(<Layout />, { route: "/settings" });
    const settings = screen.getByText("Settings").closest("a")!;
    expect(settings.className).toContain("bg-brand-50");
    expect(settings.className).toContain("text-brand-700");
  });

  it("no link is highlighted for an unknown route", () => {
    renderWithRouter(<Layout />, { route: "/nowhere" });
    for (const label of [
      "Journal",
      "Profile",
      "Quiz",
      "Readings",
      "Projects",
      "Triage",
      "Settings",
    ]) {
      const link = screen.getByText(label).closest("a")!;
      expect(link.className).toContain("text-gray-600");
      expect(link.className).not.toContain("bg-brand-50");
    }
  });
});
