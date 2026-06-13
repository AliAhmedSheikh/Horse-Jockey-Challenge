from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class LeaderboardEntry(BaseModel):
    name: str
    points: int
    rank: int


class LatestUpdate(BaseModel):
    participant: str
    pointsAdded: int
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

    model_config = ConfigDict(from_attributes=True)


class ParticipantOut(BaseModel):
    id: str
    name: str
    meetingName: str
    meetingId: str
    bookmakerPrice: float
    aiPrice: float
    overlayPercent: float
    valueRating: str
    currentPoints: int
    projectedFinalPoints: int
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
    final_points: int
    position: Optional[int]


class RaceResultOut(BaseModel):
    id: str
    meetingName: str
    raceNumber: int
    participant: str
    pointsAdded: int
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
    final_points: int
    position: int


class DashboardOut(BaseModel):
    meetings: List[MeetingOut]
    jockeys: List[ParticipantOut]
    drivers: List[ParticipantOut]
    recentResults: List[RaceResultOut]
    dashboardCards: DashboardCards
