"use client";

import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Meeting, Participant } from "@/data/types";
import { BOOKMAKERS } from "@/data/types";
import { IconUser, IconCar, IconStar, IconChevronRight } from "@/data/icons";

const statusLabels: Record<string, string> = {
  Live: "Live",
  "Not Started": "Upcoming",
  Completed: "Completed",
};
const statusStyles: Record<string, string> = {
  Live: "badge-value",
  "Not Started": "badge-upcoming",
  Completed: "badge-completed",
};

function valueRatingColor(rating: string) {
  switch (rating) {
    case "Strong Value": return "text-emerald-500";
    case "Value": return "text-emerald-400";
    case "Neutral": return "text-amber-400";
    default: return "text-red-400";
  }
}

export default function MeetingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { data: meeting, error: meetingError, isLoading: meetingLoading } = useSWR<Meeting>(
    params.id ? `/api/meetings/${params.id}` : null,
    fetcher,
    { refreshInterval: 30000 }
  );
  const { data: participants, isLoading: participantsLoading } = useSWR<Participant[]>(
    params.id ? `/api/meetings/${params.id}/participants` : null,
    fetcher,
    { refreshInterval: 30000 }
  );

  if (meetingLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading meeting...</p>
      </div>
    );
  }

  if (meetingError) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Failed to load meeting.</p>
        <button onClick={() => router.push("/meetings")} className="btn-primary mt-4">
          Back to Meetings
        </button>
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

  const sorted = participants ? [...participants].sort((a, b) => b.currentPoints - a.currentPoints) : [];
  const participantsEmpty = !participantsLoading && (!participants || participants.length === 0);

  return (
    <div className="page-transition space-y-6">
      <button
        onClick={() => router.push("/meetings")}
        className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400 hover:text-amber-500 transition-colors px-2 py-1.5 mb-2"
      >
        <IconChevronRight className="w-4 h-4 rotate-180" />
        Back to Meetings
      </button>

      <div className="card p-4 md:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${
              meeting.type === "Jockey"
                ? "bg-blue-50 dark:bg-blue-500/10 text-blue-500"
                : "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500"
            }`}>
              {meeting.type === "Jockey" ? <IconUser className="w-7 h-7" /> : <IconCar className="w-7 h-7" />}
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">{meeting.name}</h1>
                <span className={statusStyles[meeting.status]}>{statusLabels[meeting.status] || meeting.status}</span>
              </div>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{meeting.type} Challenge</p>
            </div>
          </div>
          <div className="flex items-center gap-4 md:gap-6">
            <div className="text-center">
              <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">Completed</p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">{meeting.completedRaces}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">Remaining</p>
              <p className="text-lg font-bold text-amber-500">{meeting.totalRaces - meeting.completedRaces}</p>
            </div>
            <div className="text-center">
              <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">Total Races</p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">{meeting.totalRaces}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="card p-4 md:p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">Participants & Prices</h2>
          {meeting.projectedWinner && (
            <span className="flex items-center gap-1.5 text-xs text-amber-500">
              <IconStar className="w-3.5 h-3.5" />
              {meeting.projectedWinner}
            </span>
          )}
        </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700/50">
          <table className="w-full">
            <colgroup>
              <col className="w-8" />
              <col />
              {BOOKMAKERS.map(bm => <col key={bm} className="w-[72px]" />)}
              <col className="w-[72px]" />
              <col className="w-[72px]" />
              <col className="w-[64px]" />
              <col className="w-[64px]" />
            </colgroup>
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800/80">
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">#</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Participant</th>
                {BOOKMAKERS.map((bm) => (
                  <th key={bm} className="text-center px-1 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">{bm}</th>
                ))}
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">AI</th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Ovl</th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Value</th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Pts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/30">
              {participantsLoading ? (
                <tr>
                  <td colSpan={11} className="px-4 py-12 text-center text-sm text-slate-500 dark:text-slate-400">
                    Loading participants...
                  </td>
                </tr>
              ) : participantsEmpty ? (
                <tr>
                  <td colSpan={11} className="px-4 py-12 text-center text-sm text-slate-500 dark:text-slate-400">
                    No participants loaded
                  </td>
                </tr>
              ) : sorted.map((p, i) => (
                <tr key={p.id} className={`bg-white dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors ${
                  i === 0 ? "bg-gradient-to-r from-amber-50/50 to-transparent dark:from-amber-500/5 dark:to-transparent" : ""
                }`}>
                  <td className="px-4 py-3">
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      i === 0 ? "bg-amber-500 text-white" : i === 1 ? "bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-300" : i === 2 ? "bg-amber-100 dark:bg-amber-800/30 text-amber-700 dark:text-amber-300" : "text-slate-400"
                    }`}>{i + 1}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900 dark:text-white">{p.name}</span>
                      {i === 0 && p.isProjectedWinner && <IconStar className="w-3 h-3 text-amber-400" />}
                    </div>
                  </td>
                  {BOOKMAKERS.map((bm) => {
                    const bp = p.bookmakerPrices?.[bm];
                    return (
                      <td key={bm} className="px-1 py-3 text-right">
                        <span className="text-sm font-semibold text-slate-900 dark:text-white">{bp != null ? `$${bp.toFixed(2)}` : "—"}</span>
                      </td>
                    );
                  })}
                  <td className="px-2 py-3 text-right">
                    <span className="text-sm font-semibold text-slate-900 dark:text-white">${p.aiPrice.toFixed(2)}</span>
                  </td>
                  <td className="px-2 py-3 text-right">
                    <span className={`text-sm font-semibold ${p.overlayPercent > 0 ? "text-emerald-500" : "text-red-500"}`}>
                      {p.overlayPercent > 0 ? "+" : ""}{p.overlayPercent.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-2 py-3 text-right">
                    <span className={`text-sm font-semibold ${valueRatingColor(p.valueRating)}`}>{p.valueRating}</span>
                  </td>
                  <td className="px-2 py-3 text-right">
                    <span className="text-sm font-bold text-slate-900 dark:text-white">{p.currentPoints}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="md:hidden space-y-3 mt-4">
          {sorted.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-6">No participants loaded</p>
          ) : sorted.map((p) => (
            <div key={p.id} className="bg-slate-50 dark:bg-slate-700/20 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold text-slate-900 dark:text-white">{p.name}</span>
                <span className={p.overlayPercent > 0 ? "text-sm font-semibold text-emerald-500" : "text-sm font-semibold text-red-500"}>
                  {p.overlayPercent > 0 ? "+" : ""}{p.overlayPercent.toFixed(1)}%
                </span>
              </div>
              <div className="grid grid-cols-5 gap-1 text-center mb-2">
                {BOOKMAKERS.map((bm) => {
                  const bp = p.bookmakerPrices?.[bm];
                  return (
                    <div key={bm} className="bg-white dark:bg-slate-800 rounded-lg p-1 min-h-[44px] flex flex-col items-center justify-center">
                      <p className="text-[8px] text-slate-500 dark:text-slate-400 truncate w-full leading-tight">{bm}</p>
                      <p className="text-xs font-bold text-slate-900 dark:text-white leading-tight">{bp != null ? `$${bp.toFixed(2)}` : "—"}</p>
                    </div>
                  );
                })}
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-white dark:bg-slate-800 rounded-lg p-2">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">AI Price</p>
                  <p className="text-sm font-bold text-slate-900 dark:text-white">${p.aiPrice.toFixed(2)}</p>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-lg p-2">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">Value</p>
                  <p className={`text-sm font-bold ${valueRatingColor(p.valueRating)}`}>{p.valueRating}</p>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-lg p-2">
                  <p className="text-[10px] text-slate-500 dark:text-slate-400">Points</p>
                  <p className="text-sm font-bold text-slate-900 dark:text-white">{p.currentPoints}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        <div className="card p-4 md:p-5">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Race Progress</h2>
          <div>
            <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 mb-1.5">
              <span>Progress</span>
              <span>{meeting.completedRaces}/{meeting.totalRaces}</span>
            </div>
            <div className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all duration-500 ${
                meeting.status === "Completed" ? "bg-blue-500" : meeting.status === "Live" ? "bg-emerald-500" : "bg-slate-400"
              }`} style={{ width: `${meeting.totalRaces > 0 ? (meeting.completedRaces / meeting.totalRaces) * 100 : 0}%` }} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 mt-4">
            <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-slate-900 dark:text-white">{meeting.completedRaces}</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">Completed</p>
            </div>
            <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-amber-500">{meeting.totalRaces - meeting.completedRaces}</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">Remaining</p>
            </div>
          </div>
        </div>

        <div className="card p-4 md:p-5">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Projected Winner</h2>
          <div className="text-center py-4">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-white font-bold text-xl mx-auto shadow-lg shadow-amber-500/20">
              {meeting.projectedWinner ? meeting.projectedWinner.split(" ").map((n) => n[0]).join("") : "?"}
            </div>
            <h3 className="text-base font-bold text-slate-900 dark:text-white mt-3">{meeting.projectedWinner || "—"}</h3>
            <div className="flex items-center justify-center gap-1 mt-1">
              <IconStar className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs font-medium text-amber-500">AI Projected Winner</span>
            </div>
          </div>
        </div>

        <div className="card p-4 md:p-5">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">Latest Updates</h2>
          {meeting.latestUpdates.length > 0 ? (
            <div className="space-y-2">
              {meeting.latestUpdates.slice(0, 5).map((u, i) => (
                <div key={`${u.participant}-${u.time}`} className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-50 dark:bg-slate-700/20">
                  <div className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span className="text-sm font-medium text-slate-900 dark:text-white">{u.participant}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-bold text-emerald-500">+{u.pointsAdded} pts</span>
                    <span className="text-[10px] text-slate-400">{u.time}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-6">No updates yet</p>
          )}
        </div>
      </div>
    </div>
  );
}
