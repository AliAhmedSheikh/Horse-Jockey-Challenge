"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import DataCard from "@/components/DataCard";
import type { Meeting, Participant } from "@/data/types";
import {
  IconUser,
  IconCar,
  IconCalendar,
  IconTrendingUp,
  IconRefresh,
  IconChevronRight,
} from "@/data/icons";
import { useState, useEffect } from "react";

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

function useAustralianTime() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const fmt = () => {
      const d = new Date();
      const opts: Intl.DateTimeFormatOptions = {
        timeZone: "Australia/Sydney",
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      };
      setTime(new Intl.DateTimeFormat("en-AU", opts).format(d));
    };
    fmt();
    const id = setInterval(fmt, 30000);
    return () => clearInterval(id);
  }, []);
  return time;
}

export default function DashboardPage() {
  const router = useRouter();
  const now = useAustralianTime();
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

  const { meetings, jockeys, drivers, dashboardCards } = data;
  const liveCount = meetings.filter((m) => m.status === "Live").length;

  return (
    <div className="page-transition space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
            Dashboard
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {now || "Loading..."}
          </p>
        </div>
        <button
          onClick={async () => { try { const r = await fetch("/api/refresh", { method: "POST" }); if (!r.ok) throw new Error("Refresh failed"); mutate(); } catch (e) { alert("Refresh failed. Is the backend running?"); } }}
          className="btn-secondary flex items-center gap-2"
        >
          <IconRefresh className="w-4 h-4" />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 md:gap-4">
        <DataCard
          title="Today's Meetings"
          value={dashboardCards.todayMeetings}
          subtitle={`${liveCount} live now`}
          icon={<IconCalendar className="w-5 h-5" />}
          trend={liveCount > 0 ? "up" : "neutral"}
          trendLabel={liveCount > 0 ? "Live" : "No live"}
          onClick={() => router.push("/meetings")}
        />
        <DataCard
          title="Jockey Challenges"
          value={dashboardCards.activeJockeyChallenges}
          subtitle={`${jockeys.length} total jockeys`}
          icon={<IconUser className="w-5 h-5" />}
          trend={meetings.some((m) => m.type === "Jockey" && m.status === "Live") ? "up" : "neutral"}
          trendLabel={meetings.some((m) => m.type === "Jockey" && m.status === "Live") ? "Live" : "All completed"}
          onClick={() => router.push("/jockey-challenges")}
        />
        <DataCard
          title="Driver Challenges"
          value={dashboardCards.activeDriverChallenges}
          subtitle={`${drivers.length} total drivers`}
          icon={<IconCar className="w-5 h-5" />}
          trend={meetings.some((m) => m.type === "Driver" && m.status === "Live") ? "up" : "neutral"}
          trendLabel={meetings.some((m) => m.type === "Driver" && m.status === "Live") ? "Live" : "All completed"}
          onClick={() => router.push("/driver-challenges")}
        />
        <DataCard
          title="Total Participants"
          value={dashboardCards.totalParticipants}
          subtitle="Tracked across all meetings"
          icon={<IconTrendingUp className="w-5 h-5" />}
          accent
          onClick={() => router.push("/meetings")}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4 md:p-5">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Quick Links</h2>
          <div className="space-y-2">
            {[
              { label: "View Meetings", href: "/meetings", icon: IconCalendar },
              { label: "Live Now", href: "/live", icon: IconTrendingUp },
              { label: "Results", href: "/results", icon: IconTrendingUp },
            ].map((link) => (
              <button
                key={link.href}
                onClick={() => router.push(link.href)}
                className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors text-sm text-slate-700 dark:text-slate-300"
              >
                <span className="flex items-center gap-2.5">
                  <link.icon className="w-4 h-4 text-slate-400" />
                  {link.label}
                </span>
                <IconChevronRight className="w-4 h-4 text-slate-400" />
              </button>
            ))}
          </div>
        </div>

        <div className="card p-4 md:p-5 md:col-span-2">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Today&apos;s Meetings</h2>
          <div className="space-y-2">
            {meetings.filter((m) => m.status !== "Completed").length === 0 && (
              <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-4">No active meetings today</p>
            )}
            {meetings.filter((m) => m.status !== "Completed").map((m) => (
              <div
                key={m.id}
                onClick={() => router.push(`/meetings/${m.id}`)}
                className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/30 cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-2.5">
                  {m.type === "Jockey" ? (
                    <IconUser className="w-4 h-4 text-slate-400" />
                  ) : (
                    <IconCar className="w-4 h-4 text-slate-400" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-white">{m.name}</p>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">{m.type} — {m.completedRaces}/{m.totalRaces} races</p>
                  </div>
                </div>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                  m.status === "Live" ? "badge-value" : "badge-upcoming"
                }`}>
                  {m.status === "Not Started" ? "Upcoming" : m.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
