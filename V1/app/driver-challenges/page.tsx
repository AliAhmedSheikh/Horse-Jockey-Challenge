"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Participant } from "@/data/types";
import ChallengeTable from "@/components/ChallengeTable";
import ParticipantDetailModal from "@/components/ParticipantDetailModal";
import { IconChevronRight, IconArrowLeft } from "@/data/icons";

export default function DriverChallengesPage() {
  const { data, error, isLoading } = useSWR<{ drivers: Participant[] }>("/api/dashboard", fetcher, { refreshInterval: 30000 });
  const drivers = data?.drivers ?? [];
  const [selectedMeeting, setSelectedMeeting] = useState<string | null>(null);
  const [detailModal, setDetailModal] = useState<{ participantId: string; meetingId: string } | null>(null);

  const byMeeting: Record<string, Participant[]> = {};
  for (const d of drivers) {
    if (!byMeeting[d.meetingName]) byMeeting[d.meetingName] = [];
    byMeeting[d.meetingName].push(d);
  }

  const meetings = Object.entries(byMeeting).map(([name, parts]) => ({
    name,
    meetingId: parts[0]?.meetingId ?? "",
    count: parts.length,
    valuePicks: parts.filter((p) => p.status === "value").length,
    leader: parts.reduce((best, p) => (p.currentPoints > best.currentPoints ? p : best), parts[0]),
  }));

  const totalValue = drivers.filter((d) => d.status === "value").length;
  const selectedParts = selectedMeeting ? byMeeting[selectedMeeting] ?? [] : [];

  if (isLoading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading driver challenges...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Failed to load driver challenges.</p>
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
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{selectedParts.length} drivers</p>
            </div>
          </div>
        ) : (
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">Driver Challenges</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Select a meeting to view driver analysis</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-4">
        <div className="card p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Total Drivers</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">{drivers.length}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Value Picks</p>
          <p className="text-2xl font-bold text-amber-500">{totalValue}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Avg Overlay</p>
          <p className="text-2xl font-bold text-emerald-500">
            {drivers.length > 0 ? `+${(drivers.reduce((s, d) => s + d.overlayPercent, 0) / drivers.length).toFixed(1)}%` : "+0.0%"}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Meetings</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">{meetings.length}</p>
        </div>
      </div>

      {!selectedMeeting ? (
        meetings.length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">No driver challenges available</p>
          </div>
        ) : (
          <div className="space-y-2">
            {meetings.map((m) => (
              <button
                key={m.name}
                onClick={() => setSelectedMeeting(m.name)}
                className="card w-full p-4 text-left hover:border-amber-500/50 transition-all group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">{m.name}</h3>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                      <span>{m.count} drivers</span>
                      <span>{m.valuePicks} value picks</span>
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
          <ChallengeTable participants={selectedParts} type="driver" onShowDetail={(pid, mid) => setDetailModal({ participantId: pid, meetingId: mid })} />
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
