"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import DataCard from "@/components/DataCard";
import ChallengeCard from "@/components/ChallengeCard";
import type { Participant, Meeting, RaceResult } from "@/data/types";
import {
  IconUser,
  IconCar,
  IconCalendar,
  IconTrendingUp,
  IconList,
  IconStar,
  IconRefresh,
  IconClock,
  IconChevronRight,
} from "@/data/icons";

const statusStyles: Record<string, string> = {
  Live: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20",
  "Not Started":
    "bg-slate-50 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400 border-slate-200 dark:border-slate-500/20",
  Completed:
    "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 border-blue-200 dark:border-blue-500/20",
};

interface DashboardData {
  jockeys: Participant[];
  drivers: Participant[];
  meetings: Meeting[];
  recentResults: RaceResult[];
  dashboardCards: {
    todayMeetings: number;
    activeJockeyChallenges: number;
    activeDriverChallenges: number;
    totalParticipants: number;
  };
}

export default function DashboardPage() {
  const router = useRouter();
  const { data, error, isLoading, mutate } = useSWR<DashboardData>("/api/dashboard", fetcher, { refreshInterval: 30000 });

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading dashboard...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Failed to load dashboard data. Is the backend running?</p>
      </div>
    );
  }

  const { jockeys, drivers, meetings, recentResults, dashboardCards } = data;
  const latestResults = recentResults.slice(0, 3);
  const allParticipants = [...jockeys, ...drivers];
  const topProjected =
    allParticipants.find((p) => p.isProjectedWinner && p.status === "value") || allParticipants[0] || null;
  const bestOverlay = allParticipants.length > 0
    ? allParticipants.reduce((best, curr) => curr.overlayPercent > best.overlayPercent ? curr : best)
    : null;
  const liveJockeys = jockeys.filter((j) => j.status === "value").slice(0, 3);
  const liveDrivers = drivers.filter((d) => d.status === "value").slice(0, 3);

  return (
    <div className="page-transition space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
            Dashboard
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            AI-powered insights for Jockey & Driver Challenges
          </p>
        </div>
        <button
          onClick={() => mutate()}
          className="btn-secondary flex items-center gap-2"
        >
          <IconRefresh className="w-4 h-4" />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <DataCard
          title="Today's Meetings"
          value={dashboardCards.todayMeetings}
          subtitle="Active race meetings"
          icon={<IconCalendar className="w-5 h-5" />}
          trend={dashboardCards.todayMeetings > 0 ? "up" : "neutral"}
          trendLabel={dashboardCards.todayMeetings > 0 ? "Active" : "No meetings"}
          onClick={() => router.push("/meetings")}
        />
        <DataCard
          title="Jockey Challenges"
          value={dashboardCards.activeJockeyChallenges}
          subtitle="Active challenges"
          icon={<IconUser className="w-5 h-5" />}
          trend={dashboardCards.activeJockeyChallenges > 0 ? "up" : "neutral"}
          trendLabel={
            dashboardCards.activeJockeyChallenges > 0 ? "Live now" : "No active"
          }
          onClick={() => router.push("/jockey-challenges")}
        />
        <DataCard
          title="Driver Challenges"
          value={dashboardCards.activeDriverChallenges}
          subtitle="Active challenges"
          icon={<IconCar className="w-5 h-5" />}
          trend={dashboardCards.activeDriverChallenges > 0 ? "up" : "neutral"}
          trendLabel={
            dashboardCards.activeDriverChallenges > 0 ? "Live now" : "No active"
          }
          onClick={() => router.push("/driver-challenges")}
        />
        <DataCard
          title="Value Opportunities"
          value={dashboardCards.totalParticipants}
          subtitle="Total tracked participants"
          icon={<IconTrendingUp className="w-5 h-5" />}
          accent
          onClick={() => router.push("/jockey-challenges")}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        <div className="lg:col-span-2 space-y-4">
          {topProjected && (
          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Top Projected Winner
              </h2>
              <IconStar className="w-4 h-4 text-amber-400" />
            </div>
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-amber-500/20">
                {topProjected.name
                  .split(" ")
                  .map((n) => n[0])
                  .join("")}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                    {topProjected.name}
                  </h3>
                  <span className="text-[10px] font-medium text-slate-500 dark:text-slate-400 uppercase bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded">
                    {topProjected.meetingName}
                  </span>
                </div>
                <div className="flex items-center gap-4 mt-2">
                  <div>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      Projected Points
                    </p>
                    <p className="text-sm font-bold text-emerald-500">
                      {topProjected.projectedFinalPoints}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      AI Price
                    </p>
                    <p className="text-sm font-bold text-slate-900 dark:text-white">
                      ${topProjected.aiPrice.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      Overlay
                    </p>
                    <p className="text-sm font-bold text-emerald-500">
                      +{topProjected.overlayPercent.toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          )}

          {bestOverlay && (
          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Best Overlay / Value Pick
              </h2>
              <IconTrendingUp className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500 font-bold text-lg">
                {bestOverlay.name
                  .split(" ")
                  .map((n) => n[0])
                  .join("")}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                    {bestOverlay.name}
                  </h3>
                  <span className="text-[10px] font-medium text-slate-500 dark:text-slate-400 uppercase bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded">
                    {bestOverlay.meetingName}
                  </span>
                </div>
                <div className="flex items-center gap-4 mt-2">
                  <div>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      Bookmaker
                    </p>
                    <p className="text-sm font-bold text-slate-900 dark:text-white">
                      ${bestOverlay.bookmakerPrice.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      AI Price
                    </p>
                    <p className="text-sm font-bold text-slate-900 dark:text-white">
                      ${bestOverlay.aiPrice.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      Overlay
                    </p>
                    <p className="text-2xl font-bold text-emerald-500">
                      +{bestOverlay.overlayPercent.toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          )}

          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Recent Results
              </h2>
              <button
                onClick={() => router.push("/results")}
                className="text-xs font-medium text-amber-500 hover:text-amber-400 transition-colors"
              >
                View all
              </button>
            </div>
            <div className="space-y-3">
              {latestResults.map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-700/30 last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-xs font-bold text-slate-600 dark:text-slate-300">
                      {r.meetingName.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900 dark:text-white">
                        {r.meetingName} R{r.raceNumber}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {r.participant}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-emerald-500">
                      +{r.pointsAdded} pts
                    </p>
                    <p className="text-[10px] text-slate-400">{r.timeUpdated}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Active Jockey Challenges
              </h2>
              <button
                onClick={() => router.push("/jockey-challenges")}
                className="text-xs font-medium text-amber-500 hover:text-amber-400"
              >
                View all
              </button>
            </div>
            {liveJockeys.length > 0 ? (
              <div className="space-y-3">
                {liveJockeys.map((j) => (
                  <ChallengeCard
                    key={j.id}
                    participant={j}
                    type="jockey"
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-6">
                No active jockey challenges
              </p>
            )}
          </div>

          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Active Driver Challenges
              </h2>
              <button
                onClick={() => router.push("/driver-challenges")}
                className="text-xs font-medium text-amber-500 hover:text-amber-400"
              >
                View all
              </button>
            </div>
            {liveDrivers.length > 0 ? (
              <div className="space-y-3">
                {liveDrivers.map((d) => (
                  <ChallengeCard
                    key={d.id}
                    participant={d}
                    type="driver"
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-6">
                No active driver challenges
              </p>
            )}
          </div>

          <div className="card p-4 md:p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Upcoming Meetings
              </h2>
              <button
                onClick={() => router.push("/meetings")}
                className="text-xs font-medium text-amber-500 hover:text-amber-400"
              >
                View all
              </button>
            </div>
            <div className="space-y-2">
              {meetings
                .filter((m) => m.status !== "Completed")
                .slice(0, 4)
                .map((m) => (
                  <div
                    key={m.id}
                    onClick={() => router.push(`/meetings/${m.id}`)}
                    className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/30 cursor-pointer transition-colors"
                  >
                    <div className="flex items-center gap-2.5">
                      {m.type === "Jockey" ? (
                        <IconUser className="w-4 h-4 text-slate-400" />
                      ) : (
                        <IconCar className="w-4 h-4 text-slate-400" />
                      )}
                      <div>
                        <p className="text-sm font-medium text-slate-900 dark:text-white">
                          {m.name}
                        </p>
                        <p className="text-[10px] text-slate-500 dark:text-slate-400">
                          {m.completedRaces}/{m.totalRaces} races
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                          statusStyles[m.status]
                        }`}
                      >
                        {m.status === "Not Started" ? "Upcoming" : m.status}
                      </span>
                      <IconChevronRight className="w-4 h-4 text-slate-400" />
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
