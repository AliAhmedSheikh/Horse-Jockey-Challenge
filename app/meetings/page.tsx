"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Meeting, Participant } from "@/data/types";
import DataCard from "@/components/DataCard";
import ChallengeTable from "@/components/ChallengeTable";
import { IconCalendar, IconUser, IconCar, IconChevronRight, IconTrendingUp } from "@/data/icons";

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

interface DashboardData {
  meetings: Meeting[];
  jockeys: Participant[];
  drivers: Participant[];
  dashboardCards: {
    todayMeetings: number;
    activeJockeyChallenges: number;
    activeDriverChallenges: number;
    totalParticipants: number;
  };
}

export default function MeetingsPage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<DashboardData>("/api/dashboard", fetcher, { refreshInterval: 30000 });
  const { data: meetingsData, error: meetingsError } = useSWR<Meeting[]>("/api/meetings/today", fetcher, { refreshInterval: 30000 });

  const jockeys = data?.jockeys ?? [];
  const drivers = data?.drivers ?? [];
  const meetings = meetingsData ?? [];

  const jockeyByMeeting: Record<string, Participant[]> = {};
  for (const j of jockeys) {
    if (!jockeyByMeeting[j.meetingName]) jockeyByMeeting[j.meetingName] = [];
    jockeyByMeeting[j.meetingName].push(j);
  }

  const driverByMeeting: Record<string, Participant[]> = {};
  for (const d of drivers) {
    if (!driverByMeeting[d.meetingName]) driverByMeeting[d.meetingName] = [];
    driverByMeeting[d.meetingName].push(d);
  }

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading meetings...</p>
      </div>
    );
  }

  if (error || meetingsError) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Failed to load meetings. Is the backend running?</p>
      </div>
    );
  }

  return (
    <div className="page-transition space-y-8">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
          Meetings
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Track all Jockey and Driver race meetings
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
        <DataCard
          title="Total Meetings"
          value={meetings.length}
          subtitle="All race meetings"
          icon={<IconCalendar className="w-5 h-5" />}
        />
        <DataCard
          title="Live Now"
          value={meetings.filter((m) => m.status === "Live").length}
          subtitle="Currently in progress"
          trend="up"
          trendLabel="Active"
        />
        <DataCard
          title="Completed Today"
          value={meetings.filter((m) => m.status === "Completed").length}
          subtitle="Finalized meetings"
        />
      </div>

      {/* Jockey Challenges */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <IconUser className="w-5 h-5 text-blue-500" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Jockey Challenges</h2>
        </div>

        {Object.keys(jockeyByMeeting).length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">No jockey challenges available</p>
          </div>
        ) : (
          <div className="space-y-4">
            {Object.entries(jockeyByMeeting).map(([meetingName, participants]) => {
              const meetingId = participants[0]?.meetingId;
              return (
                <div key={meetingName} className="card p-4 md:p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">{meetingName}</h3>
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
        )}
      </section>

      {/* Driver Challenges */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <IconCar className="w-5 h-5 text-emerald-500" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Driver Challenges</h2>
        </div>

        {Object.keys(driverByMeeting).length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">No driver challenges available</p>
          </div>
        ) : (
          <div className="space-y-4">
            {Object.entries(driverByMeeting).map(([meetingName, participants]) => {
              const meetingId = participants[0]?.meetingId;
              return (
                <div key={meetingName} className="card p-4 md:p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">{meetingName}</h3>
                    {meetingId && (
                      <button onClick={() => router.push(`/meetings/${meetingId}`)} className="flex items-center gap-1 text-xs text-amber-500 hover:text-amber-400 transition-colors">
                        View Details <IconChevronRight className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                  <ChallengeTable participants={participants} type="driver" />
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Meeting Cards */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <IconCalendar className="w-5 h-5 text-slate-500" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">All Meetings</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {meetings.map((m) => (
            <div
              key={m.id}
              onClick={() => router.push(`/meetings/${m.id}`)}
              className="card p-4 md:p-5 card-hover cursor-pointer group"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                      m.type === "Jockey"
                        ? "bg-blue-50 dark:bg-blue-500/10 text-blue-500"
                        : "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500"
                    }`}
                  >
                    {m.type === "Jockey" ? (
                      <IconUser className="w-5 h-5" />
                    ) : (
                      <IconCar className="w-5 h-5" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-slate-900 dark:text-white">
                      {m.name}
                    </h3>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className={statusStyles[m.status]}>{statusLabels[m.status] || m.status}</span>
                      <span className="text-[10px] text-slate-400">{m.type} Challenge</span>
                    </div>
                  </div>
                </div>
                <IconChevronRight className="w-5 h-5 text-slate-400 group-hover:text-amber-500 transition-colors" />
              </div>

              <div className="flex items-center gap-4 text-sm">
                <div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">Races</p>
                  <p className="font-semibold text-slate-900 dark:text-white mt-0.5">{m.completedRaces}/{m.totalRaces}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">Leader</p>
                  <p className="font-semibold text-slate-900 dark:text-white mt-0.5">{m.leaderboard[0]?.name || "—"}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase">Projected</p>
                  <p className="font-semibold text-amber-500 mt-0.5">{m.projectedWinner || "—"}</p>
                </div>
              </div>

              {m.status === "Live" && (
                <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/50">
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                    <span className="text-xs font-medium text-emerald-500">
                      Live — {m.latestUpdates.length} update{m.latestUpdates.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
