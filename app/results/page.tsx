"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { RaceResult } from "@/data/types";
import DataCard from "@/components/DataCard";
import {
  IconList,
  IconUser,
  IconCar,
  IconClock,
  IconRefresh,
} from "@/data/icons";

export default function ResultsPage() {
  const [filter, setFilter] = useState<"all" | "jockey" | "driver">("all");
  const { data, error, isLoading, mutate } = useSWR<{ recentResults: RaceResult[] }>("/api/dashboard", fetcher, { refreshInterval: 30000 });
  const results = data?.recentResults ?? [];

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading results...</p>
      </div>
    );
  }

  const filtered =
    filter === "all"
      ? results
      : results.filter((r) => r.type === filter);

  return (
    <div className="page-transition space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
          Results & Updates
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Live race results, points updates, and price movements
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
        <DataCard
          title="Total Updates"
          value={results.length}
          subtitle="Latest race results"
          icon={<IconList className="w-5 h-5" />}
        />
        <DataCard
          title="Jockey Results"
          value={results.filter((r) => r.type === "jockey").length}
          subtitle="Jockey race updates"
          icon={<IconUser className="w-5 h-5" />}
        />
        <DataCard
          title="Driver Results"
          value={results.filter((r) => r.type === "driver").length}
          subtitle="Driver race updates"
          icon={<IconCar className="w-5 h-5" />}
        />
      </div>

      <div className="card p-4 md:p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">
            Recent Race Results
          </h2>
          <div className="flex items-center gap-2">
            <div className="flex bg-slate-100 dark:bg-slate-700 rounded-lg p-0.5">
              {(["all", "jockey", "driver"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                    filter === f
                      ? "bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm"
                      : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                  }`}
                >
                  {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
            <button onClick={() => mutate()} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 transition-colors">
              <IconRefresh className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="hidden md:block overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700/50">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800/80">
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Meeting
                </th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Race
                </th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Participant
                </th>
                <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Points Added
                </th>
                <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  AI Price
                </th>
                <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Overlay
                </th>
                <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Time
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/30">
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  className="bg-white dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                >
                  <td className="px-4 py-3">
                    <span className="text-sm font-medium text-slate-900 dark:text-white">
                      {r.meetingName}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      Race {r.raceNumber}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm font-semibold text-slate-900 dark:text-white">
                      {r.participant}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-sm font-bold text-emerald-500">
                      +{r.pointsAdded}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-sm font-semibold text-slate-900 dark:text-white">
                      ${r.updatedAiPrice.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span
                      className={`text-sm font-semibold ${
                        r.updatedOverlay > 0 ? "text-emerald-500" : "text-red-500"
                      }`}
                    >
                      {r.updatedOverlay > 0 ? "+" : ""}
                      {r.updatedOverlay.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="flex items-center justify-end gap-1 text-xs text-slate-400">
                      <IconClock className="w-3 h-3" />
                      {r.timeUpdated}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="md:hidden space-y-3">
          {filtered.map((r) => (
            <div
              key={r.id}
              className="bg-slate-50 dark:bg-slate-700/20 rounded-xl p-4"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="text-sm font-bold text-slate-900 dark:text-white">
                    {r.meetingName} — Race {r.raceNumber}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    {r.participant}
                  </p>
                </div>
                <span className="text-sm font-bold text-emerald-500">
                  +{r.pointsAdded} pts
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-white dark:bg-slate-800 rounded-lg p-2">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">
                    AI Price
                  </p>
                  <p className="text-sm font-bold text-slate-900 dark:text-white">
                    ${r.updatedAiPrice.toFixed(2)}
                  </p>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-lg p-2">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">
                    Overlay
                  </p>
                  <p
                    className={`text-sm font-bold ${
                      r.updatedOverlay > 0 ? "text-emerald-500" : "text-red-500"
                    }`}
                  >
                    {r.updatedOverlay > 0 ? "+" : ""}
                    {r.updatedOverlay.toFixed(1)}%
                  </p>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-lg p-2">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">
                    Time
                  </p>
                  <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                    {r.timeUpdated}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
