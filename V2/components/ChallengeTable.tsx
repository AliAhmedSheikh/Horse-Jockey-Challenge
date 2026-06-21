"use client";

import type { Participant } from "@/data/types";
import { IconStar } from "@/data/icons";

interface ChallengeTableProps {
  participants: Participant[];
  type: "jockey" | "driver";
  onShowDetail?: (participantId: string, meetingId: string) => void;
}

export default function ChallengeTable({
  participants,
  type,
  onShowDetail,
}: ChallengeTableProps) {
  const sorted = [...participants].sort((a, b) => b.currentPoints - a.currentPoints);

  return (
    <>
      <div className="hidden md:block overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700/50">
        <div className="overflow-x-auto">
          <table className="w-full table-fixed">
            <colgroup>
              <col className="w-[40%]" />
              <col className="w-[20%]" />
              <col className="w-[12%]" />
              <col className="w-[14%]" />
              <col className="w-[14%]" />
            </colgroup>
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800/80">
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Participant
                </th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Meeting
                </th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  AI Price
                </th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Win %
                </th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Pts
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/30">
              {sorted.map((p, i) => (
                <tr
                  key={p.id}
                  className="bg-white dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${
                          p.isProjectedWinner
                            ? "bg-gradient-to-br from-amber-400 to-orange-500 text-white"
                            : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
                        }`}
                      >
                        {p.name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")}
                      </div>
                      <div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => onShowDetail?.(p.id, p.meetingId)}
                            className="text-sm font-semibold text-slate-900 dark:text-white truncate hover:text-amber-500 dark:hover:text-amber-400 transition-colors cursor-pointer text-left"
                          >
                            {p.name}
                          </button>
                          {p.isProjectedWinner && (
                            <IconStar className="w-3 h-3 text-amber-400" />
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300 truncate">
                    {p.meetingName}
                  </td>
                  <td className="px-2 py-3 text-sm font-semibold text-slate-900 dark:text-white text-right">
                    ${p.aiPrice.toFixed(2)}
                  </td>
                  <td className="px-2 py-3 text-sm text-slate-600 dark:text-slate-300 text-right">
                    {p.winProbability}%
                  </td>
                  <td className="px-2 py-3 text-sm font-bold text-slate-900 dark:text-white text-right">
                    {p.currentPoints}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="md:hidden space-y-3">
        {sorted.map((p) => (
          <div
            key={p.id + "-mobile"}
            className="bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/50 rounded-xl p-4 hover:shadow-lg hover:shadow-slate-900/5 dark:hover:shadow-black/20 hover:border-amber-500/30 dark:hover:border-amber-500/30 transition-all duration-200 group cursor-pointer"
            onClick={() => onShowDetail?.(p.id, p.meetingId)}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div
                  className={`w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold ${
                    p.isProjectedWinner
                      ? "bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-md shadow-amber-500/20"
                      : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
                  }`}
                >
                  {p.name.split(" ").map((n) => n[0]).join("")}
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-semibold text-slate-900 dark:text-white">
                      {p.name}
                    </span>
                    {p.isProjectedWinner && (
                      <IconStar className="w-3.5 h-3.5 text-amber-400" />
                    )}
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {p.meetingName}
                  </p>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  AI Price
                </p>
                <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
                  ${p.aiPrice.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Win %
                </p>
                <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
                  {p.winProbability}%
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Points
                </p>
                <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
                  {p.currentPoints}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
