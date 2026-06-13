export interface Participant {
  id: string;
  name: string;
  meetingName: string;
  meetingId: string;
  bookmakerPrice: number;
  aiPrice: number;
  overlayPercent: number;
  valueRating: "Strong Value" | "Value" | "Neutral" | "Avoid";
  currentPoints: number;
  projectedFinalPoints: number;
  status: "value" | "neutral" | "avoid";
  isProjectedWinner: boolean;
}

export interface Meeting {
  id: string;
  name: string;
  type: "Jockey" | "Driver";
  status: "Not Started" | "Live" | "Completed";
  completedRaces: number;
  totalRaces: number;
  leaderboard: { name: string; points: number; rank: number }[];
  latestUpdates: { participant: string; pointsAdded: number; time: string }[];
  projectedWinner: string;
}

export interface RaceResult {
  id: string;
  meetingName: string;
  raceNumber: number;
  participant: string;
  pointsAdded: number;
  updatedAiPrice: number;
  updatedOverlay: number;
  timeUpdated: string;
  type: string;
}
