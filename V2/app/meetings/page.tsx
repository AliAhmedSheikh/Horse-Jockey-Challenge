"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Meeting, Participant } from "@/data/types";
import DataCard from "@/components/DataCard";
import ChallengeTable from "@/components/ChallengeTable";
import ParticipantDetailModal from "@/components/ParticipantDetailModal";
import { IconCalendar, IconUser, IconCar, IconChevronRight, IconArrowLeft } from "@/data/icons";

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
  const { data, error, isLoading } = useSWR<DashboardData>("/api/dashboard", fetcher, { refreshInterval: 30000 });
  const { data: meetingsData, error: meetingsError } = useSWR<Meeting[]>("/api/meetings/today", fetcher, { refreshInterval: 30000 });

  const [selectedMeeting, setSelectedMeeting] = useState<string | null>(null);
  const [detailModal, setDetailModal] = useState<{ participantId: string; meetingId: string } | null>(null);

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

  const allByMeeting: Record<string, Participant[]> = { ...jockeyByMeeting, ...driverByMeeting };
  const selectedParts = selectedMeeting ? allByMeeting[selectedMeeting] ?? [] : [];
  const selectedMeetingObj = meetings.find((m) => m.name === selectedMeeting);
  const selectedMeetingType = selectedParts[0]?.meetingId
    ? meetings.find((m) => m.id === selectedParts[0].meetingId)?.type
    : undefined;

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

  const meetingList = Object.entries(allByMeeting).map(([name, parts]) => {
    const mObj = meetings.find((m) => m.name === name);
    const leader = parts.reduce((best, p) => (p.currentPoints > best.currentPoints ? p : best), parts[0]);
    return {
      name,
      meetingId: parts[0]?.meetingId ?? "",
      count: parts.length,
      type: mObj?.type ?? "Jockey",
      status: mObj?.status ?? "Not Started",
      completedRaces: mObj?.completedRaces ?? 0,
      totalRaces: mObj?.totalRaces ?? 0,
      projectedWinner: mObj?.projectedWinner ?? leader.name,
      leader,
    };
  });

  return (
    <div className="page-transition space-y-6">
      <div>
        {selectedMeeting ? (
          <div className="flex items-center gap-3">
            <button onClick={() => setSelectedMeeting(null)} className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
              <IconArrowLeft className="w-4 h-4 text-slate-600 dark:text-slate-400" />
            </button>
            <div>
              <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">{selectedMeeting}</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                {selectedMeetingType === "Jockey" ? "Jockey" : "Driver"} Challenge — {selectedParts.length} participants
                {selectedMeetingObj && ` — ${selectedMeetingObj.completedRaces}/${selectedMeetingObj.totalRaces} races`}
              </p>
            </div>
          </div>
        ) : (
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">Meetings</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              Track all Jockey and Driver race meetings
            </p>
          </div>
        )}
      </div>

      {!selectedMeeting && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:gap-4">
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
        </div>
      )}

      {!selectedMeeting ? (
        meetingList.length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">No meetings available today</p>
          </div>
        ) : (
          <>
            {meetingList.filter((m) => m.status !== "Completed").length > 0 && (
              <div className="space-y-2">
                {meetingList.filter((m) => m.status !== "Completed").map((m) => (
                  <button
                    key={m.name}
                    onClick={() => setSelectedMeeting(m.name)}
                    className="card w-full p-4 text-left hover:border-amber-500/50 transition-all group"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          {m.type === "Jockey" ? (
                            <IconUser className="w-4 h-4 text-blue-500 flex-shrink-0" />
                          ) : (
                            <IconCar className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                          )}
                          <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">{m.name}</h3>
                          <span className={`${statusStyles[m.status]} flex-shrink-0`}>{statusLabels[m.status] || m.status}</span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400 ml-6">
                          <span>{m.completedRaces}/{m.totalRaces} races</span>
                          <span>{m.count} participants</span>
                          <span>Leader: {m.leader.name} ({m.leader.currentPoints}pts)</span>
                        </div>
                      </div>
                      <IconChevronRight className="w-4 h-4 text-slate-400 group-hover:text-amber-500 transition-colors flex-shrink-0 ml-2" />
                    </div>
                    {m.status === "Live" && (
                      <div className="flex items-center gap-2 mt-2 ml-6">
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                        </span>
                        <span className="text-[10px] font-medium text-emerald-500">Live</span>
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}
            {meetingList.filter((m) => m.status === "Completed").length > 0 && (
              <div className="space-y-2 mt-4">
                <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider px-1">Completed</p>
                {meetingList.filter((m) => m.status === "Completed").map((m) => (
                  <button
                    key={m.name}
                    onClick={() => setSelectedMeeting(m.name)}
                    className="card w-full p-4 text-left hover:border-slate-300 dark:hover:border-slate-600 transition-all group opacity-60"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          {m.type === "Jockey" ? (
                            <IconUser className="w-4 h-4 text-slate-400 flex-shrink-0" />
                          ) : (
                            <IconCar className="w-4 h-4 text-slate-400 flex-shrink-0" />
                          )}
                          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">{m.name}</h3>
                          <span className="badge-completed flex-shrink-0">Completed</span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-slate-400 dark:text-slate-500 ml-6">
                          <span>{m.completedRaces}/{m.totalRaces} races</span>
                          <span>{m.count} participants</span>
                          <span>Winner: {m.leader.name} ({m.leader.currentPoints}pts)</span>
                        </div>
                      </div>
                      <IconChevronRight className="w-4 h-4 text-slate-300 group-hover:text-slate-400 transition-colors flex-shrink-0 ml-2" />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )
      ) : (
        <div className="card p-4 md:p-5">
          <ChallengeTable
            participants={selectedParts}
            type={selectedMeetingType === "Driver" ? "driver" : "jockey"}
            onShowDetail={(pid, mid) => setDetailModal({ participantId: pid, meetingId: mid })}
          />
        </div>
      )}

      {detailModal && (
        <ParticipantDetailModal
          participantId={detailModal.participantId}
          meetingId={detailModal.meetingId}
          onClose={() => setDetailModal(null)}
        />
      )}
    </div>
  );
}
