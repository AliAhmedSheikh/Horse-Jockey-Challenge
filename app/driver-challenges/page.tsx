"use client";

import { useState, useEffect } from "react";
import type { Participant } from "@/data/types";
import ChallengeTable from "@/components/ChallengeTable";
import DataCard from "@/components/DataCard";
import { IconCar, IconTrendingUp } from "@/data/icons";

type SortKey =
  | "name"
  | "overlayPercent"
  | "currentPoints"
  | "projectedFinalPoints"
  | "valueRating";
type FilterStatus = "all" | "value" | "neutral" | "avoid";

export default function DriverChallengesPage() {
  const [drivers, setDrivers] = useState<Participant[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("overlayPercent");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/dashboard");
        const json = await res.json();
        setDrivers(json.drivers);
      } catch (e) {
        console.error("Failed to fetch drivers:", e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  let filtered = [...drivers];
  if (filterStatus !== "all") {
    filtered = filtered.filter((d) => d.status === filterStatus);
  }

  filtered.sort((a, b) => {
    switch (sortKey) {
      case "name":
        return a.name.localeCompare(b.name);
      case "overlayPercent":
        return b.overlayPercent - a.overlayPercent;
      case "currentPoints":
        return b.currentPoints - a.currentPoints;
      case "projectedFinalPoints":
        return b.projectedFinalPoints - a.projectedFinalPoints;
      case "valueRating": {
        const order = ["Strong Value", "Value", "Neutral", "Avoid"];
        return order.indexOf(a.valueRating) - order.indexOf(b.valueRating);
      }
      default:
        return 0;
    }
  });

  const totalValue = filtered.filter((d) => d.status === "value").length;

  if (loading) {
    return (
      <div className="page-transition text-center py-20">
        <p className="text-slate-500 dark:text-slate-400">Loading driver challenges...</p>
      </div>
    );
  }

  return (
    <div className="page-transition space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
          Driver Challenges
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          AI-powered analysis and projections for Australian Driver Challenges
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <DataCard
          title="Total Drivers"
          value={drivers.length}
          subtitle="Tracked participants"
          icon={<IconCar className="w-5 h-5" />}
        />
        <DataCard
          title="Value Picks"
          value={totalValue}
          subtitle="Strong value opportunities"
          icon={<IconTrendingUp className="w-5 h-5" />}
          accent
        />
        <DataCard
          title="Avg Overlay"
          value={`+${(
            drivers.reduce((s, d) => s + d.overlayPercent, 0) / drivers.length
          ).toFixed(1)}%`}
          subtitle="Average value overlay"
          trend="up"
          trendLabel="Positive edge"
        />
        <DataCard
          title="Projected Winners"
          value={drivers.filter((d) => d.isProjectedWinner).length}
          subtitle="AI projected winners"
        />
      </div>

      <div className="card p-4 md:p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">
            All Driver Challenges
          </h2>
          <div className="flex items-center gap-2">
            <div className="flex bg-slate-100 dark:bg-slate-700 rounded-lg p-0.5">
              {(["all", "value", "neutral", "avoid"] as FilterStatus[]).map(
                (f) => (
                  <button
                    key={f}
                    onClick={() => setFilterStatus(f)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                      filterStatus === f
                        ? "bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm"
                        : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                    }`}
                  >
                    {f === "all"
                      ? "All"
                      : f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                )
              )}
            </div>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="text-xs bg-slate-100 dark:bg-slate-700 border-0 rounded-lg px-3 py-1.5 text-slate-600 dark:text-slate-300 font-medium cursor-pointer focus:ring-2 focus:ring-amber-500/30"
            >
              <option value="overlayPercent">Sort: Overlay</option>
              <option value="currentPoints">Sort: Points</option>
              <option value="projectedFinalPoints">Sort: Projected</option>
              <option value="name">Sort: Name</option>
              <option value="valueRating">Sort: Value</option>
            </select>
          </div>
        </div>
        <ChallengeTable participants={filtered} type="driver" />
      </div>
    </div>
  );
}
