from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class LeaderboardEntry(BaseModel):
    name: str
    points: float
    rank: int


class LatestUpdate(BaseModel):
    participant: str
    pointsAdded: float
    time: str


class MeetingOut(BaseModel):
    id: str
    name: str
    type: str
    status: str
    completedRaces: int
    totalRaces: int
    leaderboard: List[LeaderboardEntry]
    latestUpdates: List[LatestUpdate]
    projectedWinner: str
    scheduledTime: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ParticipantOut(BaseModel):
    id: str
    name: str
    meetingName: str
    meetingId: str
    bookmakerPrice: float
    bookmakerPrices: dict[str, float]
    aiPrice: float
    overlayPercent: float
    valueRating: str
    currentPoints: float
    projectedFinalPoints: float
    status: str
    isProjectedWinner: bool


class PriceOut(BaseModel):
    id: int
    participant_id: str
    bookmaker_name: str
    price: float
    timestamp: datetime


class ResultOut(BaseModel):
    id: int
    participant_id: str
    participant_name: Optional[str] = None
    final_points: float
    position: Optional[int]
    race_number: Optional[int] = None
    points_added: Optional[float] = None


class RaceResultOut(BaseModel):
    id: str
    meetingName: str
    raceNumber: int
    participant: str
    pointsAdded: float
    updatedAiPrice: float
    updatedOverlay: float
    timeUpdated: str
    type: str


class DashboardCards(BaseModel):
    todayMeetings: int
    activeJockeyChallenges: int
    activeDriverChallenges: int
    totalParticipants: int


class PodiumEntry(BaseModel):
    participant_name: str
    final_points: float
    position: int


class FormulaSettingsOut(BaseModel):
    settings: dict[str, float]


class DashboardOut(BaseModel):
    meetings: List[MeetingOut]
    jockeys: List[ParticipantOut]
    drivers: List[ParticipantOut]
    recentResults: List[RaceResultOut]
    dashboardCards: DashboardCards


class BetCreate(BaseModel):
    participantId: str
    meetingId: str
    participantName: str
    meetingName: str
    betType: str = "win"
    stake: float
    odds: float


class BetUpdate(BaseModel):
    stake: Optional[float] = None
    odds: Optional[float] = None
    result: Optional[str] = None
    betType: Optional[str] = None


class BetOut(BaseModel):
    id: int
    participantId: str
    meetingId: str
    participantName: str
    meetingName: str
    betType: str
    stake: float
    odds: float
    potentialReturn: float
    result: str
    pnl: float
    createdAt: str
    updatedAt: str

    model_config = ConfigDict(from_attributes=True)


class BetStats(BaseModel):
    totalBets: int
    totalStaked: float
    totalReturned: float
    totalPnl: float
    roi: float
    winCount: int
    lossCount: int
    pendingCount: int
    winRate: float


class RideDetail(BaseModel):
    raceNumber: int
    horseName: str
    odds: float
    bestBookmaker: str
    bestPrice: float
    expectedPoints: float
    winProbability: float
    status: str
    position: Optional[int] = None
    pointsAwarded: Optional[float] = None


class ParticipantDetail(BaseModel):
    id: str
    name: str
    meetingName: str
    meetingType: str
    currentPoints: float
    projectedFinalPoints: float
    projectedAdditionalPoints: float
    aiPrice: float
    bookmakerPrice: float
    overlayPercent: float
    winProbability: float
    valueRating: str
    remainingRides: int
    totalRaces: int
    completedRaces: int
    rides: List[RideDetail]
