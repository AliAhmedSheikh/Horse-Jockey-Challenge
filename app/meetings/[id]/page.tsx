"use client";

import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Meeting } from "@/data/types";
import { IconUser, IconCar, IconStar, IconChevronRight, IconClock } from "@/data/icons";

const statusStyles: Record<string, string> = {
  Live: "badge-value",
  "Not Started":
    "bg-slate-50 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400 border-slate-200 dark:border-slate-500/20 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border",
  Completed:
    "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 border-blue-200 dark:border-blue-500/20 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border",
};

const rankColors = ["text-amber-500", "text-slate-400", "text-amber-700 dark:text-amber-300"];

export default function MeetingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { data: meeting, error, isLoading } = useSWR<Meeting>(
    params.id ? `/api/meetings/${params.id}` : null,
    fetcher,
    { refreshInterval: 30000 }
  );

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading meeting...</p>
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Meeting not found</p>
        <button onClick={() => router.push("/meetings")} className="btn-primary mt-4">
          Back to Meetings
        </button>
      </div>
    );
  }

  return (
    <div className="page-transition space-y-6">
      <button
        onClick={() => router.push("/meetings")}
        className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400 hover:text-amber-500 transition-colors mb-2"
      >
        <IconChevronRight className="w-4 h-4 rotate-180" />
        Back to Meetings
      </button>

      <div className="card p-4 md:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div
              className={`w-14 h-14 rounded-xl flex items-center justify-center ${
                meeting.type === "Jockey"
                  ? "bg-blue-50 dark:bg-blue-500/10 text-blue-500"
                  : "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500"
              }`}
            >
              {meeting.type === "Jockey" ? (
                <IconUser className="w-7 h-7" />
              ) : (
                <IconCar className="w-7 h-7" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
                  {meeting.name}
                </h1>
                <span className={statusStyles[meeting.status]}>
                  {meeting.status}
                </span>
              </div>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                {meeting.type} Challenge
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 md:gap-6">
            <div className="text-center">
              <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">
                Completed
              </p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {meeting.completedRaces}
              </p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">
                Remaining
              </p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {meeting.totalRaces - meeting.completedRaces}
              </p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">
                Total Races
              </p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {meeting.totalRaces}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        <div className="lg:col-span-2 space-y-4">
          <div className="card p-4 md:p-5">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">
              Leaderboard
            </h2>
            <div className="space-y-1">
              {meeting.leaderboard.map((entry, i) => (
                <div
                  key={entry.name}
                  className={`flex items-center justify-between py-2.5 px-3 rounded-lg ${
                    i === 0
                      ? "bg-gradient-to-r from-amber-50 to-transparent dark:from-amber-500/5 dark:to-transparent"
                      : "hover:bg-slate-50 dark:hover:bg-slate-700/30"
                  } transition-colors`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                        i === 0
                          ? "bg-amber-500 text-white"
                          : i === 1
                          ? "bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-300"
                          : i === 2
                          ? "bg-amber-100 dark:bg-amber-800/30 text-amber-700 dark:text-amber-300"
                          : "text-slate-400"
                      }`}
                    >
                      {i + 1}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-semibold text-slate-900 dark:text-white">
                        {entry.name}
                      </span>
                      {i === 0 && entry.name === meeting.projectedWinner && (
                        <IconStar className="w-3.5 h-3.5 text-amber-400" />
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-bold text-slate-900 dark:text-white">
                      {entry.points}
                    </span>
                    <span className="text-[10px] text-slate-500 dark:text-slate-400 ml-1">
                      pts
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Latest Points Updates
              </h2>
              <IconClock className="w-4 h-4 text-slate-400" />
            </div>
            {meeting.latestUpdates.length > 0 ? (
              <div className="space-y-2">
                {meeting.latestUpdates.map((u, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-50 dark:bg-slate-700/20"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-2 h-2 rounded-full bg-emerald-500" />
                      <span className="text-sm font-medium text-slate-900 dark:text-white">
                        {u.participant}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-bold text-emerald-500">
                        +{u.pointsAdded} pts
                      </span>
                      <span className="text-[10px] text-slate-400">{u.time}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-6">
                No updates yet — meeting has not started
              </p>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="card p-4 md:p-5">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">
              Race Progress
            </h2>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 mb-1.5">
                  <span>Progress</span>
                  <span>
                    {meeting.completedRaces}/{meeting.totalRaces}
                  </span>
                </div>
                <div className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      meeting.status === "Completed"
                        ? "bg-blue-500"
                        : meeting.status === "Live"
                        ? "bg-emerald-500"
                        : "bg-slate-400"
                    }`}
                    style={{
                      width: `${(meeting.completedRaces / meeting.totalRaces) * 100}%`,
                    }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-slate-900 dark:text-white">
                    {meeting.completedRaces}
                  </p>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">
                    Completed
                  </p>
                </div>
                <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-amber-500">
                    {meeting.totalRaces - meeting.completedRaces}
                  </p>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">
                    Remaining
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="card p-4 md:p-5">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">
              Projected Winner
            </h2>
            <div className="text-center py-4">
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-white font-bold text-xl mx-auto shadow-lg shadow-amber-500/20">
                {meeting.projectedWinner
                  .split(" ")
                  .map((n) => n[0])
                  .join("")}
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white mt-3">
                {meeting.projectedWinner}
              </h3>
              <div className="flex items-center justify-center gap-1 mt-1">
                <IconStar className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs font-medium text-amber-500">
                  AI Projected Winner
                </span>
              </div>
              {meeting.status !== "Not Started" && meeting.leaderboard[0] && (
                <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-700/50">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">
                    Current Leader
                  </p>
                  <p className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">
                    {meeting.leaderboard[0].name} — {meeting.leaderboard[0].points} pts
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
