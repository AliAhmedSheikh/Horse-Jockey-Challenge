"use client";

import type { Participant } from "@/data/types";
import { BOOKMAKERS, ACCURATE_BOOKMAKERS } from "@/data/types";
import { IconStar, IconInfo } from "@/data/icons";
import ChallengeCard from "./ChallengeCard";

interface ChallengeTableProps {
  participants: Participant[];
  type: "jockey" | "driver";
  onShowDetail?: (participantId: string, meetingId: string) => void;
}

const statusBadge = (status: string) => {
  switch (status) {
    case "value":
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20">
          Value
        </span>
      );
    case "neutral":
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 border-amber-200 dark:border-amber-500/20">
          Neutral
        </span>
      );
    case "avoid":
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 border-red-200 dark:border-red-500/20">
          No Bet
        </span>
      );
    default:
      return null;
  }
};

export default function ChallengeTable({
  participants,
  type,
  onShowDetail,
}: ChallengeTableProps) {
  const sorted = [...participants].sort((a, b) => b.currentPoints - a.currentPoints);

  const activeBookmakers = BOOKMAKERS.filter((bm) =>
    participants.some((p) => p.bookmakerPrices?.[bm] != null)
  );

  return (
    <>
      <div className="hidden md:block overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700/50">
        <div className="overflow-x-auto">
          <table className="w-full">
            <colgroup>
              <col />
              <col className="w-[100px]" />
              {activeBookmakers.map(bm => <col key={bm} className="w-[80px]" />)}
              <col className="w-[72px]" />
              <col className="w-[64px]" />
              <col className="w-[64px]" />
              <col className="w-[60px]" />
              <col className="w-[80px]" />
              <col className="w-[60px]" />
            </colgroup>
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800/80">
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Participant
                </th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Meeting
                </th>
                {activeBookmakers.map((bm) => (
                  <th key={bm} className="text-center px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider whitespace-nowrap">
                    {bm}
                  </th>
                ))}
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  AI
                </th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Ovl
                </th>
                <th className="text-center px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Value
                </th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Pts
                </th>
                <th className="text-right px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Proj
                </th>
                <th className="text-center px-2 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/30">
              {sorted.map((p, i) => {
                const isPositive = p.overlayPercent > 0;
                return (
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
                              className="text-sm font-semibold text-slate-900 dark:text-white truncate max-w-[140px] hover:text-amber-500 dark:hover:text-amber-400 transition-colors cursor-pointer text-left"
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
                    <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300 truncate max-w-[120px]">
                      {p.meetingName}
                    </td>
                    {activeBookmakers.map((bm) => {
                      const bp = p.bookmakerPrices?.[bm] ?? null;
                      return (
                        <td key={bm} className="px-2 py-3 text-sm text-right font-semibold text-slate-900 dark:text-white">
                          {bp != null ? `$${bp.toFixed(2)}` : "—"}
                        </td>
                      );
                    })}
                    <td className="px-2 py-3 text-sm font-semibold text-slate-900 dark:text-white text-right">
                      ${p.aiPrice.toFixed(2)}
                    </td>
                    <td
                      className={`px-2 py-3 text-sm font-semibold text-right ${
                        isPositive ? "text-emerald-500" : "text-red-500"
                      }`}
                    >
                      {isPositive ? "+" : ""}
                      {p.overlayPercent.toFixed(1)}%
                    </td>
                    <td className="px-2 py-3 text-center">
                      <span
                        className={`text-xs font-semibold ${
                          p.valueRating === "Strong Value"
                            ? "text-emerald-500"
                            : p.valueRating === "Value"
                            ? "text-emerald-400"
                            : p.valueRating === "Neutral"
                            ? "text-amber-400"
                            : "text-red-400"
                        }`}
                      >
                        {p.valueRating}
                      </span>
                    </td>
                    <td className="px-2 py-3 text-sm font-semibold text-slate-900 dark:text-white text-right">
                      {p.currentPoints}
                    </td>
                    <td className="px-2 py-3 text-sm text-slate-600 dark:text-slate-300 text-right">
                      {p.projectedFinalPoints}
                    </td>
                    <td className="px-2 py-3 text-center">
                      {statusBadge(p.status)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-3 px-4 py-2.5 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-700/50">
        <div className="flex items-start gap-2">
          <IconInfo className="w-4 h-4 text-slate-400 dark:text-slate-500 mt-0.5 shrink-0" />
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            <span className="font-semibold text-slate-600 dark:text-slate-300">Ladbrokes</span> — live scraped prices.
            <span className="font-semibold text-slate-600 dark:text-slate-300"> TAB</span>, <span className="font-semibold text-slate-600 dark:text-slate-300">TABtouch</span>, <span className="font-semibold text-slate-600 dark:text-slate-300">Sportsbet</span>, <span className="font-semibold text-slate-600 dark:text-slate-300">PointsBet</span> — via PuntersEdge derivation.
          </p>
        </div>
      </div>

      <div className="md:hidden space-y-3">
        {sorted.map((p) => (
          <ChallengeCard key={p.id + "-mobile"} participant={p} type={type} onShowDetail={onShowDetail} />
        ))}
      </div>
    </>
  );
}
