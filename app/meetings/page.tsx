"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import type { Meeting } from "@/data/types";
import DataCard from "@/components/DataCard";
import { IconCalendar, IconUser, IconCar, IconChevronRight } from "@/data/icons";

const statusStyles: Record<string, string> = {
  Live: "badge-value",
  "Not Started": "bg-slate-50 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400 border-slate-200 dark:border-slate-500/20 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border",
  Completed:
    "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 border-blue-200 dark:border-blue-500/20 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border",
};

export default function MeetingsPage() {
  const router = useRouter();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/meetings/today");
        const json = await res.json();
        setMeetings(json);
      } catch (e) {
        console.error("Failed to fetch meetings:", e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading meetings...</p>
      </div>
    );
  }

  return (
    <div className="page-transition space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
          Meetings
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Track all Jockey and Driver race meetings
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
        <DataCard
          title="Total Meetings"
          value={meetings.length}
          subtitle="All race meetings"
          icon={<IconCalendar className="w-5 h-5" />}
        />
        <DataCard
          title="Live Now"
          value={meetings.filter((m) => m.status === "Live").length}
          subtitle="Currently in progress"
          trend="up"
          trendLabel="Active"
        />
        <DataCard
          title="Completed Today"
          value={meetings.filter((m) => m.status === "Completed").length}
          subtitle="Finalized meetings"
        />
      </div>

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
                    <span
                      className={
                        statusStyles[m.status]
                      }
                    >
                      {m.status}
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
                  {m.projectedWinner}
                </p>
              </div>
            </div>

            {m.status === "Live" && (
              <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/50">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                  <span className="text-xs font-medium text-emerald-500">
                    Live — {m.latestUpdates.length} update
                    {m.latestUpdates.length !== 1 ? "s" : ""}
                  </span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
