"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Bet, BetStats, Meeting, Participant } from "@/data/types";
import { IconPlus, IconTrash, IconRefresh, IconTrendingUp, IconTrendingDown } from "@/data/icons";

const SELECT_STYLE = "mt-1 w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent";
const INPUT_STYLE = "mt-1 w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent";

export default function BetsPage() {
  const { data: bets, mutate: mutateBets } = useSWR<Bet[]>("/api/bets", fetcher, { refreshInterval: 30000 });
  const { data: stats, mutate: mutateStats } = useSWR<BetStats>("/api/bets/stats", fetcher, { refreshInterval: 30000 });
  const { data: meetings } = useSWR<Meeting[]>("/api/meetings/today", fetcher, { refreshInterval: 60000 });

  const [showForm, setShowForm] = useState(false);
  const [editingBet, setEditingBet] = useState<Bet | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "won" | "lost">("all");

  const [selectedMeetingId, setSelectedMeetingId] = useState("");
  const [selectedParticipantId, setSelectedParticipantId] = useState("");
  const [manualName, setManualName] = useState("");
  const [stake, setStake] = useState("");
  const [odds, setOdds] = useState("");
  const [betType, setBetType] = useState("win");

  const [meetingParticipants, setMeetingParticipants] = useState<Participant[]>([]);
  const [loadingParticipants, setLoadingParticipants] = useState(false);

  const refreshData = useCallback(() => {
    mutateBets();
    mutateStats();
  }, [mutateBets, mutateStats]);

  useEffect(() => {
    const handleStorage = () => refreshData();
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [refreshData]);

  useEffect(() => {
    if (!selectedMeetingId) {
      setMeetingParticipants([]);
      setSelectedParticipantId("");
      return;
    }
    setLoadingParticipants(true);
    setSelectedParticipantId("");
    setOdds("");
    fetch(`/api/meetings/${selectedMeetingId}/participants`)
      .then((r) => r.json())
      .then((data: Participant[]) => {
        setMeetingParticipants(data);
        setLoadingParticipants(false);
      })
      .catch(() => setLoadingParticipants(false));
  }, [selectedMeetingId]);

  const sortedMeetings = [...(meetings || [])].sort((a, b) => {
    const statusOrder: Record<string, number> = { "Not Started": 0, "Live": 1, "Completed": 2 };
    return (statusOrder[a.status] ?? 3) - (statusOrder[b.status] ?? 3);
  });

  const getParticipantName = () => {
    if (selectedParticipantId) {
      const p = meetingParticipants.find((x) => x.id === selectedParticipantId);
      return p?.name || manualName;
    }
    return manualName;
  };

  const getMeetingName = () => {
    const m = meetings?.find((x) => x.id === selectedMeetingId);
    return m?.name || "Manual Bet";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const pname = getParticipantName();
    if (!pname || !stake || !odds) {
      alert("Please fill in all required fields: participant name, stake, and odds.");
      return;
    }
    if (parseFloat(stake) <= 0) {
      alert("Stake must be greater than 0.");
      return;
    }
    if (parseFloat(odds) < 1.01) {
      alert("Odds must be at least 1.01.");
      return;
    }
    try {
      if (editingBet) {
        await fetch(`/api/bets/${editingBet.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stake: parseFloat(stake), odds: parseFloat(odds), betType }),
        });
      } else {
        await fetch("/api/bets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            participantId: selectedParticipantId || "manual",
            meetingId: selectedMeetingId || "manual",
            participantName: pname,
            meetingName: getMeetingName(),
            betType,
            stake: parseFloat(stake),
            odds: parseFloat(odds),
          }),
        });
      }
      resetForm();
      refreshData();
    } catch {
      alert("Failed to save bet");
    }
  };

  const resetForm = () => {
    setShowForm(false);
    setEditingBet(null);
    setSelectedMeetingId("");
    setSelectedParticipantId("");
    setManualName("");
    setStake("");
    setOdds("");
    setBetType("win");
  };

  const startEdit = (bet: Bet) => {
    setEditingBet(bet);
    setShowForm(true);
    setSelectedMeetingId(bet.meetingId !== "manual" ? bet.meetingId : "");
    setSelectedParticipantId(bet.participantId !== "manual" ? bet.participantId : "");
    setManualName(bet.participantName);
    setStake(String(bet.stake));
    setOdds(String(bet.odds));
    setBetType(bet.betType);
  };

  const handleSettle = async (betId: number, result: "won" | "lost" | "void") => {
    try {
      await fetch(`/api/bets/${betId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result }),
      });
      refreshData();
    } catch (err) {
      alert("Failed to settle bet");
    }
  };

  const handleDelete = async (betId: number) => {
    if (!confirm("Delete this bet?")) return;
    try {
      await fetch(`/api/bets/${betId}`, { method: "DELETE" });
      refreshData();
    } catch (err) {
      alert("Failed to delete bet");
    }
  };

  const filteredBets = bets?.filter((b) => filter === "all" || b.result === filter) || [];

  return (
    <div className="page-transition space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">Bet Tracker</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Track your bets, P&L and ROI</p>
        </div>
        <button onClick={() => { setEditingBet(null); setSelectedMeetingId(""); setSelectedParticipantId(""); setManualName(""); setStake(""); setOdds(""); setBetType("win"); setShowForm(true); }} className="btn-primary flex items-center gap-2">
          <IconPlus className="w-4 h-4" />
          <span className="hidden sm:inline">Add Bet</span>
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="card p-4 md:p-6 space-y-4">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">{editingBet ? "Edit Bet" : "New Bet"}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Meeting</label>
              <select value={selectedMeetingId} onChange={(e) => setSelectedMeetingId(e.target.value)} className={SELECT_STYLE}>
                <option value="">Select a meeting...</option>
                {sortedMeetings.map((m) => (
                  <option key={m.id} value={m.id}>{m.name} ({m.type}) — {m.status}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Participant</label>
              {selectedMeetingId ? (
                <select value={selectedParticipantId} onChange={(e) => setSelectedParticipantId(e.target.value)} className={SELECT_STYLE} disabled={loadingParticipants}>
                  <option value="">{loadingParticipants ? "Loading..." : "Select a participant..."}</option>
                  {meetingParticipants.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              ) : (
                <input type="text" value={manualName} onChange={(e) => setManualName(e.target.value)} className={INPUT_STYLE} placeholder="Or type a name manually..." />
              )}
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Bet Type</label>
              <select value={betType} onChange={(e) => setBetType(e.target.value)} className={SELECT_STYLE}>
                <option value="win">Win</option>
                <option value="place">Place</option>
                <option value="each-way">Each Way</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Stake ($)</label>
              <input type="number" step="0.01" min="0.01" value={stake} onChange={(e) => setStake(e.target.value)} className={INPUT_STYLE} placeholder="10.00" required />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Odds</label>
              <input type="number" step="0.01" min="1.01" value={odds} onChange={(e) => setOdds(e.target.value)} className={INPUT_STYLE} placeholder="Enter odds manually" required />
            </div>
          </div>
          {stake && odds && (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Potential return: <span className="font-semibold text-amber-500">${(parseFloat(stake) * parseFloat(odds)).toFixed(2)}</span>
            </p>
          )}
          <div className="flex items-center gap-3">
            <button type="submit" className="btn-primary">{editingBet ? "Update Bet" : "Place Bet"}</button>
            <button type="button" onClick={resetForm} className="btn-secondary">Cancel</button>
          </div>
        </form>
      )}

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 md:gap-4">
          <div className="card p-4">
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">Total Bets</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{stats.totalBets}</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{stats.winCount}W / {stats.lossCount}L / {stats.pendingCount}P</p>
          </div>
          <div className="card p-4">
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">Total Staked</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">${stats.totalStaked.toFixed(2)}</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">Returned: ${stats.totalReturned.toFixed(2)}</p>
          </div>
          <div className="card p-4">
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">Profit / Loss</p>
            <p className={`text-2xl font-bold mt-1 ${stats.totalPnl >= 0 ? "text-emerald-500" : "text-red-500"}`}>
              {stats.totalPnl >= 0 ? "+" : ""}{stats.totalPnl.toFixed(2)}
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">Win rate: {stats.winRate.toFixed(1)}%</p>
          </div>
          <div className="card p-4">
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">ROI</p>
            <p className={`text-2xl font-bold mt-1 ${stats.roi >= 0 ? "text-emerald-500" : "text-red-500"}`}>
              {stats.roi >= 0 ? "+" : ""}{stats.roi.toFixed(2)}%
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{stats.totalBets} bets placed</p>
          </div>
        </div>
      )}

      {!stats && (
        <div className="flex items-center justify-center h-32 text-sm text-slate-400">
          Loading bet statistics...
        </div>
      )}

      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {(["all", "pending", "won", "lost"] as const).map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors whitespace-nowrap ${filter === f ? "bg-amber-500 text-white" : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"}`}>
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <div className="card overflow-hidden">
        {filteredBets.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
            No bets yet. Click &quot;Add Bet&quot; to start tracking.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-800/80">
                  <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Participant</th>
                  <th className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Meeting</th>
                  <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Stake</th>
                  <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Odds</th>
                  <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Return</th>
                  <th className="text-right px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">P&L</th>
                  <th className="text-center px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Status</th>
                  <th className="text-center px-4 py-3 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/30">
                {filteredBets.map((bet) => (
                  <tr key={bet.id} className="bg-white dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                    <td className="px-4 py-3 text-sm font-semibold text-slate-900 dark:text-white">{bet.participantName}</td>
                    <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300">{bet.meetingName}</td>
                    <td className="px-4 py-3 text-sm text-right text-slate-900 dark:text-white">${bet.stake.toFixed(2)}</td>
                    <td className="px-4 py-3 text-sm text-right text-slate-900 dark:text-white">{bet.odds.toFixed(2)}</td>
                    <td className="px-4 py-3 text-sm text-right text-slate-600 dark:text-slate-300">${bet.potentialReturn.toFixed(2)}</td>
                    <td className={`px-4 py-3 text-sm text-right font-semibold ${bet.pnl > 0 ? "text-emerald-500" : bet.pnl < 0 ? "text-red-500" : "text-slate-400"}`}>
                      {bet.result === "pending" ? "—" : `${bet.pnl >= 0 ? "+" : ""}${bet.pnl.toFixed(2)}`}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                        bet.result === "won" ? "badge-value" : bet.result === "lost" ? "badge-avoid" : bet.result === "void" ? "badge-upcoming" : "badge-neutral"
                      }`}>
                        {bet.result === "won" ? "Won" : bet.result === "lost" ? "Lost" : bet.result === "void" ? "Void" : "Pending"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-1">
                        {bet.result === "pending" && (
                          <>
                            <button onClick={() => handleSettle(bet.id, "won")} className="px-2 py-1 text-[10px] font-semibold rounded bg-emerald-50 text-emerald-600 hover:bg-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-400">Win</button>
                            <button onClick={() => handleSettle(bet.id, "lost")} className="px-2 py-1 text-[10px] font-semibold rounded bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400">Loss</button>
                            <button onClick={() => handleSettle(bet.id, "void")} className="px-2 py-1 text-[10px] font-semibold rounded bg-slate-50 text-slate-600 hover:bg-slate-100 dark:bg-slate-500/10 dark:text-slate-400">Void</button>
                          </>
                        )}
                        <button onClick={() => startEdit(bet)} className="px-2 py-1 text-[10px] font-semibold rounded bg-amber-50 text-amber-600 hover:bg-amber-100 dark:bg-amber-500/10 dark:text-amber-400">
                          <IconRefresh className="w-3 h-3" />
                        </button>
                        <button onClick={() => handleDelete(bet.id)} className="px-2 py-1 text-[10px] font-semibold rounded bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400">
                          <IconTrash className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {stats && stats.totalBets > 0 && (
        <div className="card p-4 md:p-5">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-4">P&L Summary</h2>
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              {stats.totalPnl >= 0 ? <IconTrendingUp className="w-5 h-5 text-emerald-500" /> : <IconTrendingDown className="w-5 h-5 text-red-500" />}
              <div>
                <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.totalPnl >= 0 ? "+" : ""}${stats.totalPnl.toFixed(2)}</p>
                <p className="text-xs text-slate-400">Overall P&L</p>
              </div>
            </div>
            <div className="h-8 w-px bg-slate-200 dark:bg-slate-700" />
            <div>
              <p className="text-lg font-bold text-slate-900 dark:text-white">{stats.winRate}%</p>
              <p className="text-xs text-slate-400">Win Rate</p>
            </div>
            <div className="h-8 w-px bg-slate-200 dark:bg-slate-700" />
            <div>
              <p className={`text-lg font-bold ${stats.roi >= 0 ? "text-emerald-500" : "text-red-500"}`}>{stats.roi >= 0 ? "+" : ""}{stats.roi.toFixed(2)}%</p>
              <p className="text-xs text-slate-400">ROI</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
