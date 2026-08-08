import { Moon, Sun } from "lucide-react";
import { useTheme } from "../hooks/useTheme";

/** Light/dark switch. Lives in the top-right of the app shell. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      aria-pressed={isDark}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="flex items-center gap-2 rounded-md border border-gray-300 px-2.5 py-1.5 text-sm text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white"
    >
      {isDark ? <Moon size={16} aria-hidden /> : <Sun size={16} aria-hidden />}
    </button>
  );
}
