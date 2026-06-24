"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Meeting } from "@/data/types";
import DataCard from "@/components/DataCard";
import { IconList, IconUser, IconCar, IconChevronRight, IconRefresh } from "@/data/icons";

export default function ResultsPage() {
  const router = useRouter();
  const { data: meetingsData, error, isLoading, mutate } = useSWR<Meeting[]>("/api/meetings/today", fetcher, { refreshInterval: 30000 });

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
            <button
              key={m.id}
              onClick={() => router.push(`/meetings/${m.id}`)}
              className="w-full flex items-center justify-between px-4 py-3 bg-white dark:bg-slate-800/30 border border-slate-200 dark:border-slate-700/50 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors text-left group"
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
                  m.status === "Completed" ? "badge-completed" : m.status === "Abandoned" ? "bg-red-500/10 text-red-500 border-red-500/20" : "badge-upcoming"
                }`}>
                  {m.status === "Abandoned" ? "Abandoned" : m.status}
                </span>
                <IconChevronRight className="w-4 h-4 text-slate-400 group-hover:text-amber-500 transition-colors" />
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
