"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Meeting, PodiumEntry } from "@/data/types";
import DataCard from "@/components/DataCard";
import { IconList, IconUser, IconCar, IconChevronRight, IconStar, IconRefresh } from "@/data/icons";

export default function ResultsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: meetingsData, error, isLoading, mutate } = useSWR<Meeting[]>("/api/meetings/today", fetcher, { refreshInterval: 30000 });
  const { data: podium, isLoading: podiumLoading } = useSWR<PodiumEntry[]>(
    selectedId ? `/api/meetings/${selectedId}/podium` : null,
    fetcher,
    { refreshInterval: 15000 }
  );

  const meetings = (meetingsData ?? []).filter((m) => m.status === "Completed" || m.status === "Abandoned");

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading results...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Failed to load results.</p>
      </div>
    );
  }

  return (
    <div className="page-transition space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">Results</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Select a meeting to view final standings</p>
        </div>
        <button onClick={async () => { try { const r = await fetch("/api/refresh", { method: "POST" }); if (!r.ok) throw new Error("Refresh failed"); mutate(); } catch (e) { alert("Refresh failed. Is the backend running?"); } }} className="btn-secondary flex items-center gap-2">
          <IconRefresh className="w-4 h-4" />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
        <DataCard title="Total Meetings" value={meetings.length} subtitle="All meetings" icon={<IconList className="w-5 h-5" />} />
        <DataCard title="Jockey Meetings" value={meetings.filter((m) => m.type === "Jockey").length} subtitle="Jockey challenges" icon={<IconUser className="w-5 h-5" />} />
        <DataCard title="Driver Meetings" value={meetings.filter((m) => m.type === "Driver").length} subtitle="Driver challenges" icon={<IconCar className="w-5 h-5" />} />
      </div>

      <div className="card p-4 md:p-5">
        <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Meeting Results</h2>
        <div className="space-y-2">
          {meetings.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-8">No meetings available</p>
          ) : meetings.map((m) => (
            <div key={m.id} className="border border-slate-200 dark:border-slate-700/50 rounded-lg overflow-hidden">
              <button
                onClick={() => setSelectedId(selectedId === m.id ? null : m.id)}
                className="w-full flex items-center justify-between px-4 py-3 bg-white dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors text-left"
              >
                <div className="flex items-center gap-3">
                  {m.type === "Jockey" ? <IconUser className="w-4 h-4 text-slate-400" /> : <IconCar className="w-4 h-4 text-slate-400" />}
                  <div>
                    <span className="text-sm font-semibold text-slate-900 dark:text-white">{m.name}</span>
                    <span className="ml-2 text-[10px] text-slate-500 dark:text-slate-400">{m.type}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                    m.status === "Live" ? "badge-value" : m.status === "Completed" ? "badge-completed" : m.status === "Abandoned" ? "bg-red-500/10 text-red-500 border-red-500/20" : "badge-upcoming"
                  }`}>
                    {m.status === "Not Started" ? "Upcoming" : m.status === "Abandoned" ? "Abandoned" : m.status}
                  </span>
                  <IconChevronRight className={`w-4 h-4 text-slate-400 transition-transform ${selectedId === m.id ? "rotate-90" : ""}`} />
                </div>
              </button>

              {selectedId === m.id && (
                <div key={selectedId} className="px-4 py-4 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-200 dark:border-slate-700/50">
                  {podiumLoading ? (
                    <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-4">Loading...</p>
                  ) : !podium || podium.length === 0 ? (
                    <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-4">
                      {m.status === "Not Started" ? "Meeting has not started yet" : "No results available"}
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {podium.map((entry) => (
                        <div key={entry.position} className={`rounded-xl p-4 text-center ${
                          entry.position === 1
                            ? "bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-500/10 dark:to-amber-500/5 border border-amber-200 dark:border-amber-500/20"
                            : entry.position === 2
                            ? "bg-slate-50 dark:bg-slate-700/20 border border-slate-200 dark:border-slate-700/50"
                            : "bg-slate-50 dark:bg-slate-700/20 border border-slate-200 dark:border-slate-700/50"
                        }`}>
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-2 ${
                            entry.position === 1
                              ? "bg-amber-500 text-white"
                              : entry.position === 2
                              ? "bg-slate-300 dark:bg-slate-600 text-slate-700 dark:text-slate-200"
                              : "bg-amber-100 dark:bg-amber-800/30 text-amber-700 dark:text-amber-300"
                          }`}>
                            <span className="text-sm font-bold">{entry.position}</span>
                          </div>
                          <p className="text-sm font-bold text-slate-900 dark:text-white">{entry.participant_name}</p>
                          <div className="flex items-center justify-center gap-1 mt-1">
                            <span className="text-lg font-bold text-emerald-500">{entry.final_points}</span>
                            <span className="text-[10px] text-slate-500 dark:text-slate-400">pts</span>
                            {entry.position === 1 && <IconStar className="w-3.5 h-3.5 text-amber-400 ml-1" />}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
