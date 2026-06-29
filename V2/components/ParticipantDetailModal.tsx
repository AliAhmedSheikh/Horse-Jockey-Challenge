"use client";

import { useState, useEffect, useCallback } from "react";
import { ParticipantDetail, RideDetail } from "@/data/types";
import { fetcher } from "@/lib/api";

function RaceStatusBadge({ ride }: { ride: RideDetail }) {
  const colors: Record<string, string> = {
    Won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400",
    "2nd": "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400",
    "3rd": "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400",
    Placed: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
    Unplaced: "bg-red-50 text-red-500 dark:bg-red-900/20 dark:text-red-400",
    Completed: "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400",
    Upcoming: "bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[ride.status] || colors.Upcoming}`}>
      {ride.status}
    </span>
  );
}

export default function ParticipantDetailModal({
  participantId,
  meetingId,
  onClose,
}: {
  participantId: string;
  meetingId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ParticipantDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(async () => {
    try {
      const data = await fetcher(`/api/meetings/${meetingId}/participants/${participantId}/detail`);
      setDetail(data);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load details");
    } finally {
      setLoading(false);
    }
  }, [meetingId, participantId]);

  useEffect(() => {
    loadDetail();
    const interval = setInterval(loadDetail, 30000);
    return () => clearInterval(interval);
  }, [loadDetail]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div
        className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 w-full max-w-2xl max-h-[90vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {loading && !detail && (
          <div className="flex items-center justify-center p-12">
            <div className="w-8 h-8 border-4 border-amber-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="p-6 text-center">
            <p className="text-red-500 text-sm">{error}</p>
            <button onClick={onClose} className="mt-4 btn-secondary text-sm">Close</button>
          </div>
        )}

        {detail && (
          <>
            <div className="sticky top-0 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-6 py-4 flex items-center justify-between z-10">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
                  {detail.name.split(" ").map((n) => n[0]).join("")}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white">{detail.name}</h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {detail.meetingName} {detail.meetingType === "driver" ? "Driver" : "Jockey"} Challenge
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700/50">
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-slate-50 dark:bg-slate-700/50 rounded-xl p-3 text-center">
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-0.5">AI Price</p>
                  <p className="text-lg font-bold text-amber-500">${detail.aiPrice.toFixed(2)}</p>
                </div>
                <div className="bg-slate-50 dark:bg-slate-700/50 rounded-xl p-3 text-center">
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-0.5">Current Points</p>
                  <p className="text-lg font-bold text-slate-900 dark:text-white">{detail.currentPoints}</p>
                </div>
                <div className="bg-slate-50 dark:bg-slate-700/50 rounded-xl p-3 text-center">
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-0.5">Projected Final</p>
                  <p className="text-lg font-bold text-amber-500">{detail.projectedFinalPoints}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mt-3">
                <div className="text-center">
                  <p className="text-xs text-slate-500 dark:text-slate-400">Remaining</p>
                  <p className="text-sm font-bold text-slate-900 dark:text-white">{detail.remainingRides}/{detail.totalRaces}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-slate-500 dark:text-slate-400">Projected Additional</p>
                  <p className="text-sm font-bold text-slate-700 dark:text-slate-300">{detail.projectedAdditionalPoints} pts</p>
                </div>
              </div>
            </div>

            <div className="overflow-y-auto max-h-[50vh]">
              <table className="w-full">
                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-700/50">
                    <tr className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                      <th className="px-6 py-2.5 text-left font-medium">Race</th>
                      <th className="px-4 py-2.5 text-left font-medium">Horse</th>
                      <th className="px-4 py-2.5 text-center font-medium">Odds</th>
                      <th className="px-4 py-2.5 text-center font-medium">Expected Pts</th>
                      <th className="px-4 py-2.5 text-center font-medium">Win %</th>
                      <th className="px-4 py-2.5 text-center font-medium">Status</th>
                      <th className="px-6 py-2.5 text-center font-medium">Points</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                  {detail.rides.map((ride) => (
                    <tr key={ride.raceNumber} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                      <td className="px-6 py-3">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">R{ride.raceNumber}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm text-slate-700 dark:text-slate-300">
                          {ride.horseName || <span className="text-slate-400">—</span>}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {ride.raceOdds != null ? (
                          <span className="text-sm font-semibold text-amber-500">${ride.raceOdds.toFixed(1)}</span>
                        ) : (
                          <span className="text-sm text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {ride.expectedPoints != null ? (
                          <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">{ride.expectedPoints.toFixed(2)}</span>
                        ) : (
                          <span className="text-sm text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {ride.winProbability != null ? (
                          <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">{ride.winProbability.toFixed(1)}%</span>
                        ) : (
                          <span className="text-sm text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <RaceStatusBadge ride={ride} />
                      </td>
                      <td className="px-6 py-3 text-center">
                        {ride.pointsAwarded !== null && ride.pointsAwarded > 0 ? (
                          <span className="text-sm font-bold text-amber-500">+{ride.pointsAwarded}</span>
                        ) : (
                          <span className="text-sm text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {detail.rides.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-6 py-8 text-center text-sm text-slate-400">
                        No ride data available yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="sticky bottom-0 bg-slate-50 dark:bg-slate-700/30 border-t border-slate-200 dark:border-slate-700 px-6 py-3 flex items-center justify-between">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                AI Price: <span className="font-semibold text-amber-500">${detail.aiPrice.toFixed(2)}</span>
              </p>
              <button onClick={onClose} className="btn-secondary text-xs px-3 py-1.5">Close</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
