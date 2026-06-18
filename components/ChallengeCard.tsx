"use client";

import { BOOKMAKERS, ACCURATE_BOOKMAKERS, type Participant } from "@/data/types";
import { IconStar, IconTrendingUp, IconInfo } from "@/data/icons";
import { useRouter } from "next/navigation";

interface ChallengeCardProps {
  participant: Participant;
  type: "jockey" | "driver";
  onShowDetail?: (participantId: string, meetingId: string) => void;
}

const statusColors = {
  value:
    "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20",
  neutral:
    "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 border-amber-200 dark:border-amber-500/20",
  avoid:
    "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 border-red-200 dark:border-red-500/20",
};

export default function ChallengeCard({
  participant,
  type,
  onShowDetail,
}: ChallengeCardProps) {
  const router = useRouter();
  const isPositive = participant.overlayPercent > 0;

  const handleCardClick = () => {
    router.push(`/meetings/${participant.meetingId}`);
  };

  return (
    <div
      className="bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/50 rounded-xl p-4 hover:shadow-lg hover:shadow-slate-900/5 dark:hover:shadow-black/20 hover:border-amber-500/30 dark:hover:border-amber-500/30 transition-all duration-200 group cursor-pointer"
      onClick={handleCardClick}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div
            className={`w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold ${
              participant.isProjectedWinner
                ? "bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-md shadow-amber-500/20"
                : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
            }`}
          >
            {participant.name
              .split(" ")
              .map((n) => n[0])
              .join("")}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onShowDetail?.(participant.id, participant.meetingId);
                }}
                className="text-sm font-semibold text-slate-900 dark:text-white hover:text-amber-500 dark:hover:text-amber-400 transition-colors cursor-pointer"
              >
                {participant.name}
              </button>
              {participant.isProjectedWinner && (
                <IconStar className="w-3.5 h-3.5 text-amber-400" />
              )}
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {participant.meetingName}
            </p>
          </div>
        </div>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
            statusColors[participant.status]
          }`}
        >
          {participant.status === "value" ? "Value" : participant.status === "avoid" ? "Avoid" : "Neutral"}
        </span>
      </div>

      <div className="flex items-center gap-1.5 mb-3 px-1">
        <IconInfo className="w-3 h-3 text-slate-400 dark:text-slate-500 mt-0.5 shrink-0" />
        <p className="text-[10px] text-slate-400 dark:text-slate-500 leading-tight">
          Ladbrokes — live. TAB, TABtouch, Sportsbet, PointsBet — via PuntersEdge.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            AI Price
          </p>
          <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
            ${participant.aiPrice.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            Book Avg
          </p>
          <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
            ${participant.bookmakerPrice.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            Overlay
          </p>
          <p className={`text-sm font-bold mt-0.5 ${isPositive ? "text-emerald-500" : "text-red-500"}`}>
            {isPositive ? "+" : ""}{participant.overlayPercent.toFixed(1)}%
          </p>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            Points
          </p>
          <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
            {participant.currentPoints}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            Projected
          </p>
          <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
            {participant.projectedFinalPoints}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            Value
          </p>
          <p
            className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${
              participant.valueRating === "Strong Value"
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20"
                : participant.valueRating === "Value"
                ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 border-blue-200 dark:border-blue-500/20"
                : participant.valueRating === "Avoid"
                ? "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 border-red-200 dark:border-red-500/20"
                : "bg-slate-50 text-slate-700 dark:bg-slate-500/10 dark:text-slate-400 border-slate-200 dark:border-slate-500/20"
            }`}
          >
            {participant.valueRating}
          </p>
        </div>
        {participant.status === "value" && (
          <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-500">
            <IconTrendingUp className="w-4 h-4" />
          </div>
        )}
      </div>
    </div>
  );
}
