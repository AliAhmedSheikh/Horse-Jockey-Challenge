export interface Participant {
  id: string;
  name: string;
  meetingName: string;
  meetingId: string;
  bookmakerPrice: number;
  bookmakerPrices: Record<string, number>;
  aiPrice: number;
  overlayPercent: number;
  valueRating: "Strong Value" | "Value" | "Neutral" | "Avoid";
  currentPoints: number;
  projectedFinalPoints: number;
  status: "value" | "neutral" | "avoid";
  isProjectedWinner: boolean;
}

export const BOOKMAKERS = ["Ladbrokes", "TAB", "Sportsbet", "PointsBet", "TABtouch"] as const;
export const ACCURATE_BOOKMAKERS: readonly string[] = ["Ladbrokes", "TAB", "Sportsbet", "PointsBet", "TABtouch"];

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
  scheduledTime?: string;
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
  type: "Jockey" | "Driver";
}

export interface PodiumEntry {
  participant_name: string;
  final_points: number;
  position: number;
}

export interface Bet {
  id: number;
  participantId: string;
  meetingId: string;
  participantName: string;
  meetingName: string;
  betType: string;
  stake: number;
  odds: number;
  potentialReturn: number;
  result: "pending" | "won" | "lost" | "void";
  pnl: number;
  createdAt: string;
  updatedAt: string;
}

export interface BetStats {
  totalBets: number;
  totalStaked: number;
  totalReturned: number;
  totalPnl: number;
  roi: number;
  winCount: number;
  lossCount: number;
  pendingCount: number;
  winRate: number;
}

export interface Prediction {
  id: string;
  name: string;
  currentPoints: number;
  completedRaces: number;
  remainingRaces: number;
  bookmakerPrice: number;
  winProbability: number;
  estimatedFinalPoints: number;
}

export interface MeetingPrediction {
  meetingId: string;
  meetingName: string;
  status: string;
  completedRaces: number;
  totalRaces: number;
  projectedWinner: string;
  predictions: Prediction[];
}

export interface RideDetail {
  raceNumber: number;
  horseName: string;
  odds: number;
  bestBookmaker: string;
  bestPrice: number;
  expectedPoints: number;
  winProbability: number;
  status: string;
  position: number | null;
  pointsAwarded: number | null;
}

export interface ParticipantDetail {
  id: string;
  name: string;
  meetingName: string;
  meetingType: string;
  currentPoints: number;
  projectedFinalPoints: number;
  projectedAdditionalPoints: number;
  aiPrice: number;
  bookmakerPrice: number;
  overlayPercent: number;
  winProbability: number;
  valueRating: string;
  remainingRides: number;
  totalRaces: number;
  completedRaces: number;
  rides: RideDetail[];
}
