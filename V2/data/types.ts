export interface Participant {
  id: string;
  name: string;
  meetingName: string;
  meetingId: string;
  aiPrice: number;
  winProbability: number;
  currentPoints: number;
  projectedFinalPoints: number;
  isProjectedWinner: boolean;
}

export interface Meeting {
  id: string;
  name: string;
  type: "Jockey" | "Driver";
  status: "Not Started" | "Live" | "Completed" | "Abandoned";
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
  expectedPoints: number | null;
  winProbability: number | null;
  status: string;
  position: number | null;
  pointsAwarded: number | null;
  raceOdds: number | null;
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
  winProbability: number;
  remainingRides: number;
  totalRaces: number;
  completedRaces: number;
  rides: RideDetail[];
}
