/* ============================================================
 * useTheme
 * ------------------------------------------------------------
 * Light/dark theme state, persisted to localStorage and applied
 * by toggling the `dark` class on <html> (Tailwind's
 * `darkMode: "class"` strategy).
 *
 * The initial class is set by an inline script in index.html so
 * the correct theme paints on first frame — no white flash on a
 * dark-mode reload. THEME_STORAGE_KEY is duplicated there by
 * necessity (the script runs before any module loads); keep the
 * two in sync.
 *
 * With no stored preference we follow the OS setting live. Once
 * the user picks a theme explicitly, that choice sticks and the
 * OS is ignored.
 * ============================================================ */

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "devlogplus-theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** localStorage throws in some privacy modes — never let that break the UI. */
function readStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Preference just won't survive a reload; not worth surfacing.
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.(DARK_QUERY).matches ? "dark" : "light";
}

export function getInitialTheme(): Theme {
  return readStoredTheme() ?? systemTheme();
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  // Tells the browser to render native widgets (scrollbars, form
  // controls, autofill) in the matching scheme.
  root.style.colorScheme = theme;
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Follow the OS only while the user hasn't chosen for themselves.
  useEffect(() => {
    const media = window.matchMedia?.(DARK_QUERY);
    if (!media?.addEventListener) return;
    const onChange = (event: MediaQueryListEvent) => {
      if (readStoredTheme() === null)
        setTheme(event.matches ? "dark" : "light");
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      storeTheme(next);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}
