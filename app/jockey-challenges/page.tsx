"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Participant } from "@/data/types";
import ChallengeTable from "@/components/ChallengeTable";
import DataCard from "@/components/DataCard";
import { IconUser, IconTrendingUp, IconChevronRight } from "@/data/icons";

export default function JockeyChallengesPage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<{ jockeys: Participant[] }>("/api/dashboard", fetcher, { refreshInterval: 30000 });
  const jockeys = data?.jockeys ?? [];

  const byMeeting: Record<string, Participant[]> = {};
  for (const j of jockeys) {
    if (!byMeeting[j.meetingName]) byMeeting[j.meetingName] = [];
    byMeeting[j.meetingName].push(j);
  }

  const totalValue = jockeys.filter((j) => j.status === "value").length;

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading jockey challenges...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Failed to load jockey challenges.</p>
      </div>
    );
  }

  return (
    <div className="page-transition space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">Jockey Challenges</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">AI-powered analysis grouped by meeting</p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-4">
        <DataCard title="Total Jockeys" value={jockeys.length} subtitle="Tracked participants" icon={<IconUser className="w-5 h-5" />} />
        <DataCard title="Value Picks" value={totalValue} subtitle="Strong value opportunities" icon={<IconTrendingUp className="w-5 h-5" />} accent />
        <DataCard title="Avg Overlay" value={jockeys.length > 0 ? `+${(jockeys.reduce((s, j) => s + j.overlayPercent, 0) / jockeys.length).toFixed(1)}%` : "+0.0%"} subtitle="Average value overlay" trend="up" trendLabel="Positive edge" />
        <DataCard title="Meetings" value={Object.keys(byMeeting).length} subtitle="Active jockey meetings" />
      </div>

      {Object.entries(byMeeting).map(([meetingName, participants]) => {
        const meetingId = participants[0]?.meetingId;
        return (
          <div key={meetingName} className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">{meetingName}</h2>
              {meetingId && (
                <button onClick={() => router.push(`/meetings/${meetingId}`)} className="flex items-center gap-1 text-xs text-amber-500 hover:text-amber-400 transition-colors">
                  View Details <IconChevronRight className="w-3 h-3" />
                </button>
              )}
            </div>
            <ChallengeTable participants={participants} type="jockey" />
          </div>
        );
      })}
    </div>
  );
}
