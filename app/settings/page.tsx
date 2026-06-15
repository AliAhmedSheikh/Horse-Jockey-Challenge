"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import DataCard from "@/components/DataCard";
import { IconSettings as IconSettingsIcon, IconRefresh } from "@/data/icons";

interface SliderSetting {
  id: string;
  label: string;
  description: string;
  min: number;
  max: number;
  step: number;
  default: number;
  unit: string;
}

const settings: SliderSetting[] = [
  {
    id: "bookmakerWeight",
    label: "Bookmaker Implied Probability Weight",
    description: "How much weight the bookmaker odds carry in the AI model",
    min: 0,
    max: 100,
    step: 1,
    default: 35,
    unit: "%",
  },
  {
    id: "currentPointsWeight",
    label: "Current Points Weight",
    description: "Importance of current challenge standings in projections",
    min: 0,
    max: 100,
    step: 1,
    default: 25,
    unit: "%",
  },
  {
    id: "remainingRacesWeight",
    label: "Remaining Races / Rides Weight",
    description: "Weight given to the number of remaining opportunities",
    min: 0,
    max: 100,
    step: 1,
    default: 20,
    unit: "%",
  },
  {
    id: "completedRacesWeight",
    label: "Completed Races Weight",
    description: "Influence of already-completed race results",
    min: 0,
    max: 100,
    step: 1,
    default: 10,
    unit: "%",
  },
  {
    id: "priceMovementWeight",
    label: "Price Movement Weight",
    description: "How much recent price fluctuations affect the prediction",
    min: 0,
    max: 100,
    step: 1,
    default: 10,
    unit: "%",
  },
  {
    id: "valueThreshold",
    label: "Value Threshold",
    description: "Minimum overlay percentage required for a 'Strong Value' rating",
    min: 0,
    max: 50,
    step: 0.5,
    default: 10,
    unit: "%",
  },
];

export default function SettingsPage() {
  const { data: apiData, mutate: mutateSettings } = useSWR<{ settings: Record<string, number> }>("/api/settings", fetcher, { refreshInterval: 30000 });

  const [values, setValues] = useState<Record<string, number>>(() => {
    const initial: Record<string, number> = {};
    settings.forEach((s) => {
      initial[s.id] = s.default;
    });
    return initial;
  });

  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (apiData?.settings) {
      setValues((prev) => {
        const merged = { ...prev };
        for (const [key, val] of Object.entries(apiData.settings)) {
          if (key in merged) {
            merged[key] = val;
          }
        }
        return merged;
      });
    }
  }, [apiData]);

  const handleSave = async () => {
    try {
      const r = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: values }),
      });
      if (!r.ok) throw new Error("Save failed");
      mutateSettings();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      alert("Failed to save settings. Is the backend running?");
    }
  };

  const handleReset = async () => {
    const reset: Record<string, number> = {};
    settings.forEach((s) => {
      reset[s.id] = s.default;
    });
    try {
      const r = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: reset }),
      });
      if (!r.ok) throw new Error("Reset failed");
      mutateSettings();
      setValues(reset);
    } catch (e) {
      alert("Failed to reset settings. Is the backend running?");
    }
  };

  return (
    <div className="page-transition space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white">
            Formula Settings
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Configure AI model weights and value thresholds
          </p>
        </div>
        <button
          onClick={handleReset}
          className="btn-secondary flex items-center gap-2"
        >
          <IconRefresh className="w-4 h-4" />
          <span className="hidden sm:inline">Reset</span>
        </button>
      </div>

      <div className="card p-4 md:p-5 flex items-center gap-4">
        <div className="flex-shrink-0 p-2.5 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-400 dark:text-slate-300">
          <IconSettingsIcon className="w-5 h-5" />
        </div>
        <div>
          <h2 className="text-base font-bold text-slate-900 dark:text-white">AI Model Configuration</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Configure AI model weights and value thresholds</p>
        </div>
      </div>

      <div className="card p-4 md:p-6">
        <div className="space-y-6">
          {settings.map((setting) => (
            <div key={setting.id}>
              <div className="flex items-center justify-between mb-1.5">
                <div>
                  <label
                    htmlFor={setting.id}
                    className="text-sm font-semibold text-slate-900 dark:text-white"
                  >
                    {setting.label}
                  </label>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    {setting.description}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-amber-500 min-w-[3ch] text-right">
                    {values[setting.id]}
                    {setting.unit}
                  </span>
                </div>
              </div>
              <div className="relative">
                <input
                  type="range"
                  id={setting.id}
                  min={setting.min}
                  max={setting.max}
                  step={setting.step}
                  value={values[setting.id]}
                  onChange={(e) =>
                    setValues((prev) => ({
                      ...prev,
                      [setting.id]: parseFloat(e.target.value),
                    }))
                  }
                  className="input-range"
                  style={{
                    background: `linear-gradient(to right, #f59e0b ${
                      ((values[setting.id] - setting.min) /
                        (setting.max - setting.min)) *
                      100
                    }%, #e2e8f0 ${
                      ((values[setting.id] - setting.min) /
                        (setting.max - setting.min)) *
                      100
                    }%)`,
                  }}
                />
                <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                  <span>{setting.min}{setting.unit}</span>
                  <span>{setting.max}{setting.unit}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-8 pt-6 border-t border-slate-200 dark:border-slate-700/50 flex items-center justify-between">
          <div>
            {saved && (
              <div className="flex items-center gap-2 text-emerald-500 text-sm font-medium animate-fade-in">
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                Settings saved successfully
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => apiData?.settings && setValues(apiData.settings)} className="btn-secondary">
              Cancel
            </button>
            <button onClick={handleSave} className="btn-primary">
              {saved ? "Saved!" : "Save Settings"}
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}
