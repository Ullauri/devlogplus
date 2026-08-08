import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ThemeToggle from "./ThemeToggle";
import { THEME_STORAGE_KEY } from "../hooks/useTheme";

/** Point window.matchMedia at a fixed OS preference. */
function stubSystemTheme(prefersDark: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: prefersDark,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  document.documentElement.style.colorScheme = "";
  stubSystemTheme(false);
});

afterEach(() => {
  document.documentElement.classList.remove("dark");
});

describe("ThemeToggle — initial theme", () => {
  it("starts light and offers to switch to dark when nothing is stored", () => {
    render(<ThemeToggle />);
    expect(
      screen.getByRole("button", { name: "Switch to dark theme" }),
    ).toBeInTheDocument();
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("honours a stored dark preference over the OS setting", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeToggle />);
    expect(document.documentElement).toHaveClass("dark");
    expect(
      screen.getByRole("button", { name: "Switch to light theme" }),
    ).toBeInTheDocument();
  });

  it("honours a stored light preference even when the OS prefers dark", () => {
    stubSystemTheme(true);
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    render(<ThemeToggle />);
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("falls back to the OS preference when nothing is stored", () => {
    stubSystemTheme(true);
    render(<ThemeToggle />);
    expect(document.documentElement).toHaveClass("dark");
  });

  it("falls back to light when localStorage throws", () => {
    const spy = vi
      .spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => {
        throw new Error("denied");
      });
    render(<ThemeToggle />);
    expect(document.documentElement).not.toHaveClass("dark");
    spy.mockRestore();
  });
});

describe("ThemeToggle — switching", () => {
  it("toggles the dark class on <html> and persists the choice", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    const button = screen.getByRole("button");

    await user.click(button);
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    await user.click(button);
    expect(document.documentElement).not.toHaveClass("dark");
    expect(document.documentElement.style.colorScheme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("reflects the current theme through aria-pressed", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-pressed", "false");

    await user.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");
  });

  it("still switches when localStorage rejects writes", async () => {
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("quota");
      });
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button"));
    expect(document.documentElement).toHaveClass("dark");
    spy.mockRestore();
  });
});
