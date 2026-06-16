"use client";

import { BOOKMAKERS, type Participant } from "@/data/types";
import { IconStar, IconTrendingUp, IconInfo } from "@/data/icons";

const ACCURATE_BOOKMAKERS = new Set(["Ladbrokes"]);
import Link from "next/link";

interface ChallengeCardProps {
  participant: Participant;
  type: "jockey" | "driver";
}

const statusColors = {
  value:
    "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20",
  neutral:
    "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 border-amber-200 dark:border-amber-500/20",
  avoid:
    "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 border-red-200 dark:border-red-500/20",
};

const ratingColors = {
  "Strong Value": "text-emerald-500",
  Value: "text-emerald-400",
  Neutral: "text-amber-400",
  Avoid: "text-red-400",
};

export default function ChallengeCard({
  participant,
  type,
}: ChallengeCardProps) {
  const isPositive = participant.overlayPercent > 0;
  const detailPath = `/meetings/${participant.meetingId}`;

  return (
    <Link href={detailPath}>
      <div className="bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/50 rounded-xl p-4 hover:shadow-lg hover:shadow-slate-900/5 dark:hover:shadow-black/20 hover:border-amber-500/30 dark:hover:border-amber-500/30 transition-all duration-200 group">
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
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {participant.name}
                </h3>
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
            {participant.status === "value"
              ? "Value"
              : participant.status === "avoid"
              ? "Avoid"
              : "Neutral"}
          </span>
        </div>

        <div className="grid grid-cols-5 gap-1 mb-3 text-center">
          {BOOKMAKERS.map((bm) => {
            const isAccurate = ACCURATE_BOOKMAKERS.has(bm);
            return (
              <div key={bm} className={`min-h-[36px] flex flex-col items-center justify-center rounded-lg p-1 ${isAccurate ? "bg-slate-50 dark:bg-slate-800/50" : "bg-slate-100/50 dark:bg-slate-800/30"}`}>
                <p className={`text-[8px] uppercase tracking-wider truncate w-full leading-tight ${isAccurate ? "text-slate-500 dark:text-slate-400" : "text-slate-400 dark:text-slate-500"}`}>
                  {bm}
                </p>
                <p className={`text-xs leading-tight ${isAccurate ? "font-semibold text-slate-900 dark:text-white" : "font-normal text-slate-400 dark:text-slate-500"}`}>
                  {participant.bookmakerPrices?.[bm] != null ? `$${participant.bookmakerPrices[bm].toFixed(2)}` : "—"}
                </p>
              </div>
            );
          })}
        </div>
        <div className="flex items-start gap-1.5 mb-3 px-1">
          <IconInfo className="w-3 h-3 text-slate-400 dark:text-slate-500 mt-0.5 shrink-0" />
          <p className="text-[10px] text-slate-400 dark:text-slate-500 leading-tight">
            Ladbrokes is live. Other columns pending Australian server validation.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              AI Price
            </p>
            <p className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">
              ${participant.aiPrice.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Overlay
            </p>
            <p
              className={`text-sm font-semibold mt-0.5 ${
                isPositive ? "text-emerald-500" : "text-red-500"
              }`}
            >
              {isPositive ? "+" : ""}
              {participant.overlayPercent.toFixed(1)}%
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-700/50">
          <div className="flex items-center gap-3">
            <div>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">
                Points
              </p>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {participant.currentPoints}
                <span className="text-slate-400 dark:text-slate-500 font-normal">
                  {" "}
                  / {participant.projectedFinalPoints}
                </span>
              </p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">
                Value
              </p>
              <p
                className={`text-sm font-semibold ${
                  ratingColors[participant.valueRating]
                }`}
              >
                {participant.valueRating}
              </p>
            </div>
          </div>
          {participant.status === "value" && (
            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-500">
              <IconTrendingUp className="w-4 h-4" />
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
