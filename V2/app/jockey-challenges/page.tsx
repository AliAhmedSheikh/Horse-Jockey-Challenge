"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Participant, Meeting } from "@/data/types";
import ChallengeTable from "@/components/ChallengeTable";
import ParticipantDetailModal from "@/components/ParticipantDetailModal";
import { IconChevronRight, IconArrowLeft } from "@/data/icons";

export default function JockeyChallengesPage() {
  const { data, error, isLoading } = useSWR<{ jockeys: Participant[] }>("/api/dashboard", fetcher, { refreshInterval: 30000 });
  const { data: meetingsData } = useSWR<Meeting[]>("/api/meetings/today", fetcher, { refreshInterval: 30000 });
  const allJockeys = data?.jockeys ?? [];
  const meetings = meetingsData ?? [];
  const [selectedMeeting, setSelectedMeeting] = useState<string | null>(null);
  const [detailModal, setDetailModal] = useState<{ participantId: string; meetingId: string } | null>(null);

  const completedMeetingNames = new Set(meetings.filter((m) => m.status === "Completed").map((m) => m.name));
  const jockeys = allJockeys.filter((j) => !completedMeetingNames.has(j.meetingName));

  const byMeeting: Record<string, Participant[]> = {};
  for (const j of jockeys) {
    if (!byMeeting[j.meetingName]) byMeeting[j.meetingName] = [];
    byMeeting[j.meetingName].push(j);
  }

  const meetingsList = Object.entries(byMeeting).map(([name, parts]) => ({
    name,
    meetingId: parts[0]?.meetingId ?? "",
    count: parts.length,
    leader: parts.reduce((best, p) => (p.currentPoints > best.currentPoints ? p : best), parts[0]),
    status: meetings.find((m) => m.name === name)?.status ?? "Not Started",
  }));

  const selectedParts = selectedMeeting ? byMeeting[selectedMeeting] ?? [] : [];

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
        {selectedMeeting ? (
          <div className="flex items-center gap-3">
            <button onClick={() => setSelectedMeeting(null)} className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
              <IconArrowLeft className="w-4 h-4 text-slate-600 dark:text-slate-400" />
            </button>
            <div>
              <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">{selectedMeeting}</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{selectedParts.length} jockeys</p>
            </div>
          </div>
        ) : (
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">Jockey Challenges</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Active and upcoming jockey meetings</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-2 gap-3 md:gap-4">
        <div className="card p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Total Jockeys</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">{jockeys.length}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Meetings</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">{meetingsList.length}</p>
        </div>
      </div>

      {!selectedMeeting ? (
        meetingsList.length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">No active jockey challenges</p>
          </div>
        ) : (
          <div className="space-y-2">
            {meetingsList.map((m) => (
              <button
                key={m.name}
                onClick={() => setSelectedMeeting(m.name)}
                className="card w-full p-4 text-left hover:border-amber-500/50 transition-all group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">{m.name}</h3>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                        m.status === "Live" ? "badge-value" : "badge-upcoming"
                      }`}>
                        {m.status === "Live" ? "Live" : "Upcoming"}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                      <span>{m.count} jockeys</span>
                      <span>Leader: {m.leader.name} ({m.leader.currentPoints}pts)</span>
                    </div>
                  </div>
                  <IconChevronRight className="w-4 h-4 text-slate-400 group-hover:text-amber-500 transition-colors flex-shrink-0 ml-2" />
                </div>
              </button>
            ))}
          </div>
        )
      ) : (
        <div className="card p-4 md:p-5">
          <ChallengeTable participants={selectedParts} type="jockey" onShowDetail={(pid, mid) => setDetailModal({ participantId: pid, meetingId: mid })} />
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
