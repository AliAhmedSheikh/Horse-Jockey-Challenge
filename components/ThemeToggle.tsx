"use client";

import { useTheme } from "@/context/ThemeContext";
import { IconSun, IconMoon } from "@/data/icons";

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className="relative w-14 h-7 rounded-full bg-slate-700 dark:bg-slate-600 transition-colors duration-300 flex-shrink-0"
      aria-label="Toggle theme"
    >
      <span
        className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow-md transition-all duration-300 flex items-center justify-center ${
          theme === "dark" ? "left-0.5" : "left-7"
        }`}
      >
        {theme === "dark" ? (
          <IconMoon className="w-3.5 h-3.5 text-slate-700" />
        ) : (
          <IconSun className="w-3.5 h-3.5 text-amber-500" />
        )}
      </span>
    </button>
  );
}
