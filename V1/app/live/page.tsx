"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Meeting } from "@/data/types";
import DataCard from "@/components/DataCard";
import { IconCalendar, IconUser, IconCar, IconChevronRight } from "@/data/icons";

const statusStyles: Record<string, string> = {
  Live: "badge-value",
  "Not Started": "badge-upcoming",
  Completed: "badge-completed",
};

export default function LiveMeetingsPage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<Meeting[]>("/api/meetings/live", fetcher, { refreshInterval: 30000 });
  const meetings = data ?? [];

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading live meetings...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Failed to load live meetings.</p>
      </div>
    );
  }

  return (
    <div className="page-transition space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
          Live Now
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Meetings currently in progress
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
        <DataCard
          title="Live Meetings"
          value={meetings.length}
          subtitle="Currently in progress"
          icon={<IconCalendar className="w-5 h-5" />}
          trend="up"
          trendLabel="Live"
        />
        <DataCard
          title="Jockey"
          value={meetings.filter((m) => m.type === "Jockey").length}
          subtitle="Live jockey meetings"
          icon={<IconUser className="w-5 h-5" />}
        />
        <DataCard
          title="Driver"
          value={meetings.filter((m) => m.type === "Driver").length}
          subtitle="Live driver meetings"
          icon={<IconCar className="w-5 h-5" />}
        />
      </div>

      {meetings.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-slate-500 dark:text-slate-400">No live meetings right now</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {meetings.map((m) => (
            <div
              key={m.id}
              onClick={() => router.push(`/meetings/${m.id}`)}
              className="card p-4 md:p-5 card-hover cursor-pointer group"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                      m.type === "Jockey"
                        ? "bg-blue-50 dark:bg-blue-500/10 text-blue-500"
                        : "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500"
                    }`}
                  >
                    {m.type === "Jockey" ? (
                      <IconUser className="w-5 h-5" />
                    ) : (
                      <IconCar className="w-5 h-5" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-slate-900 dark:text-white">
                      {m.name}
                    </h3>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                      </span>
                      <span className="text-[10px] text-slate-400">
                        {m.type} Challenge
                      </span>
                    </div>
                  </div>
                </div>
                <IconChevronRight className="w-5 h-5 text-slate-400 group-hover:text-amber-500 transition-colors" />
              </div>

              <div className="flex items-center gap-4 text-sm">
                <div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">
                    Races
                  </p>
                  <p className="font-semibold text-slate-900 dark:text-white mt-0.5">
                    {m.completedRaces}/{m.totalRaces}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">
                    Leader
                  </p>
                  <p className="font-semibold text-slate-900 dark:text-white mt-0.5">
                    {m.leaderboard[0]?.name || "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">
                    Projected
                  </p>
                  <p className="font-semibold text-amber-500 mt-0.5">
                    {m.projectedWinner || "—"}
                  </p>
                </div>
              </div>

              {m.latestUpdates.length > 0 && (
                <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/50">
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                    <span className="text-xs font-medium text-emerald-500">
                      Live — {m.latestUpdates.length} update{m.latestUpdates.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
