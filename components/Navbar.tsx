"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "./ThemeToggle";
import {
  IconGrid,
  IconUser,
  IconCar,
  IconCalendar,
  IconList,
  IconSettings,
  IconSun,
  IconMoon,
} from "@/data/icons";
import { useTheme } from "@/context/ThemeContext";

const navItems = [
  { href: "/", label: "Dashboard", icon: IconGrid },
  { href: "/live", label: "Live", icon: IconCalendar },
  { href: "/meetings", label: "Meetings", icon: IconList },
  { href: "/results", label: "Results", icon: IconList },
  { href: "/settings", label: "Formula Settings", icon: IconSettings },
];

export default function Navbar() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();

  return (
    <>
      <aside className="hidden lg:flex flex-col w-64 h-screen fixed left-0 top-0 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-40 transition-colors duration-300">
        <div className="p-5 border-b border-slate-200 dark:border-slate-800">
          <Link href="/" className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
              <span className="text-white font-bold text-sm">JD</span>
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-900 dark:text-white leading-tight">
                Challenge AI
              </h1>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">
                Pricing Dashboard
              </p>
            </div>
          </Link>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}
              >
                <item.icon
                  className={`w-5 h-5 flex-shrink-0 ${
                    isActive
                      ? "text-amber-500"
                      : "text-slate-400 dark:text-slate-500"
                  }`}
                />
                <span>{item.label}</span>
                {isActive && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-500" />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Theme
            </span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 z-50 transition-colors duration-300">
        <div className="flex items-center justify-around px-1 py-1.5 safe-area-pb">
          {navItems.slice(0, 6).map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center gap-0.5 py-2.5 px-1.5 rounded-lg min-w-0 ${
                  isActive
                    ? "text-amber-500"
                    : "text-slate-500 dark:text-slate-400"
                }`}
              >
                <item.icon className="w-5 h-5" />
                <span className="text-[10px] font-medium whitespace-nowrap">
                  {item.label.split(" ")[0]}
                </span>
              </Link>
            );
          })}
          {navItems.slice(6, 7).map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center gap-0.5 py-2.5 px-1.5 rounded-lg min-w-0 ${
                  isActive
                    ? "text-amber-500"
                    : "text-slate-500 dark:text-slate-400"
                }`}
              >
                <IconSettings className="w-5 h-5" />
                <span className="text-[10px] font-medium">Settings</span>
              </Link>
            );
          })}
          <button
            onClick={toggleTheme}
            className="flex flex-col items-center gap-0.5 py-2.5 px-1.5 rounded-lg min-w-0 text-slate-500 dark:text-slate-400 active:text-amber-500 transition-colors"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? (
              <IconMoon className="w-5 h-5" />
            ) : (
              <IconSun className="w-5 h-5" />
            )}
            <span className="text-[10px] font-medium">
              {theme === "dark" ? "Dark" : "Light"}
            </span>
          </button>
        </div>
      </nav>
    </>
  );
}
