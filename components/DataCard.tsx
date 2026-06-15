"use client";

import { ReactNode } from "react";

interface DataCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
  trendLabel?: string;
  accent?: boolean;
  onClick?: () => void;
  className?: string;
}

export default function DataCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendLabel,
  accent,
  onClick,
  className = "",
}: DataCardProps) {
  return (
    <div
      onClick={onClick}
      className={`relative group p-4 md:p-5 rounded-xl border transition-all duration-200 ${onClick ? "cursor-pointer" : ""} ${
        accent
          ? "bg-gradient-to-br from-amber-500/10 to-orange-600/5 border-amber-500/20 dark:border-amber-500/20"
          : "bg-white dark:bg-slate-800/50 border-slate-200 dark:border-slate-700/50"
      } hover:shadow-lg hover:shadow-slate-900/5 dark:hover:shadow-black/20 hover:border-amber-500/30 dark:hover:border-amber-500/30 ${className}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            {title}
          </p>
          <p
            className={`mt-1.5 font-bold truncate ${
              accent
                ? "text-2xl md:text-3xl text-amber-500"
                : "text-xl md:text-2xl text-slate-900 dark:text-white"
            }`}
          >
            {value}
          </p>
          {subtitle && (
            <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
              {subtitle}
            </p>
          )}
          {trend && trendLabel && (
            <div className="flex items-center gap-1 mt-2">
              {trend === "up" && (
                <svg
                  className="w-3.5 h-3.5 text-emerald-500"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                >
                  <polyline points="18 15 12 9 6 15" />
                </svg>
              )}
              {trend === "down" && (
                <svg
                  className="w-3.5 h-3.5 text-red-500"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              )}
              <span
                className={`text-xs font-medium ${
                  trend === "up"
                    ? "text-emerald-500"
                    : trend === "down"
                    ? "text-red-500"
                    : "text-slate-500"
                }`}
              >
                {trendLabel}
              </span>
            </div>
          )}
        </div>
        {icon && (
          <div
            className={`flex-shrink-0 p-2.5 rounded-lg ${
              accent
                ? "bg-amber-500/10 text-amber-500"
                : "bg-slate-100 dark:bg-slate-700 text-slate-400 dark:text-slate-300"
            }`}
          >
            {icon}
          </div>
        )}
      </div>
      {onClick && (
        <div className="mt-3 flex items-center gap-1 text-xs font-medium text-amber-500 opacity-0 group-hover:opacity-100 transition-opacity">
          View details
          <svg
            className="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </div>
      )}
    </div>
  );
}
