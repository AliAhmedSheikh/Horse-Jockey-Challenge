"use client";

import { type Participant } from "@/data/types";
import { IconStar } from "@/data/icons";
import { useRouter } from "next/navigation";

interface ChallengeCardProps {
  participant: Participant;
  type: "jockey" | "driver";
  onShowDetail?: (participantId: string, meetingId: string) => void;
}

export default function ChallengeCard({
  participant,
  type,
  onShowDetail,
}: ChallengeCardProps) {
  const router = useRouter();

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
            {participant.name.split(" ").map((n) => n[0]).join("")}
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
      </div>

      <div className="grid grid-cols-2 gap-3">
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
            Points
          </p>
          <p className="text-sm font-bold text-slate-900 dark:text-white mt-0.5">
            {participant.currentPoints}
          </p>
        </div>
      </div>
    </div>
  );
}
