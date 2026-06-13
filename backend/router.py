from datetime import datetime, timezone, timedelta
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus
from schemas import (
    MeetingOut,
    ParticipantOut,
    PriceOut,
    ResultOut,
    RaceResultOut,
    LeaderboardEntry,
    LatestUpdate,
    DashboardCards,
    DashboardOut,
)

router = APIRouter()


def _compute_value_rating(bookmaker_price: float, ai_price: float) -> str:
    if bookmaker_price == 0 or ai_price == 0:
        return "Neutral"
    overlay = (bookmaker_price - ai_price) / ai_price * 100
    if overlay > 15:
        return "Strong Value"
    elif overlay > 5:
        return "Value"
    elif overlay > -5:
        return "Neutral"
    else:
        return "Avoid"


def _compute_status(bookmaker_price: float, ai_price: float) -> str:
    rating = _compute_value_rating(bookmaker_price, ai_price)
    if rating in ("Strong Value", "Value"):
        return "value"
    elif rating == "Neutral":
        return "neutral"
    else:
        return "avoid"


def _meeting_to_frontend(meeting: Meeting, db: Session) -> MeetingOut:
    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting.id
    ).all()

    sorted_ps = sorted(participants, key=lambda p: p.current_points, reverse=True)
    leaderboard = [
        LeaderboardEntry(name=p.name, points=p.current_points, rank=i + 1)
        for i, p in enumerate(sorted_ps)
    ]

    recent_results = db.query(Result).filter(
        Result.meeting_id == meeting.id
    ).order_by(desc(Result.timestamp)).limit(5).all()

    latest_updates = []
    for r in recent_results:
        p = db.query(Participant).filter(Participant.id == r.participant_id).first()
        if p:
            minutes_ago = int(
                (datetime.now(timezone.utc) - r.timestamp.replace(tzinfo=timezone.utc)).total_seconds() / 60
            ) if r.timestamp else 0
            time_str = f"{max(1, minutes_ago)}m ago"
            latest_updates.append(
                LatestUpdate(participant=p.name, pointsAdded=r.points_added, time=time_str)
            )

    projected = sorted_ps[0].name if sorted_ps else ""
    status_map = {
        MeetingStatus.UPCOMING.value: "Not Started",
        MeetingStatus.LIVE.value: "Live",
        MeetingStatus.FINISHED.value: "Completed",
    }

    return MeetingOut(
        id=meeting.id,
        name=meeting.name,
        type="Jockey" if meeting.type == "jockey" else "Driver",
        status=status_map.get(meeting.status, "Not Started"),
        completedRaces=meeting.completed_races,
        totalRaces=meeting.total_races,
        leaderboard=leaderboard,
        latestUpdates=latest_updates,
        projectedWinner=projected,
    )


def _participant_to_frontend(p: Participant, db: Session) -> ParticipantOut:
    prices = db.query(Price).filter(Price.participant_id == p.id).all()
    meeting = db.query(Meeting).filter(Meeting.id == p.meeting_id).first()

    bookmaker_prices = [pr.price for pr in prices]
    avg_bookmaker = sum(bookmaker_prices) / len(bookmaker_prices) if bookmaker_prices else 3.0

    ai_price = round(avg_bookmaker * random.uniform(0.85, 1.05), 2)
    overlay = round((avg_bookmaker - ai_price) / ai_price * 100, 1)

    remaining = meeting.total_races - p.completed_races if meeting else 0
    avg_per_race = p.current_points / max(p.completed_races, 1)
    projected = p.current_points + int(avg_per_race * remaining)

    value_rating = _compute_value_rating(avg_bookmaker, ai_price)

    return ParticipantOut(
        id=p.id,
        name=p.name,
        meetingName=meeting.name if meeting else "",
        meetingId=p.meeting_id,
        bookmakerPrice=round(avg_bookmaker, 2),
        aiPrice=ai_price,
        overlayPercent=overlay,
        valueRating=value_rating,
        currentPoints=p.current_points,
        projectedFinalPoints=projected,
        status=_compute_status(avg_bookmaker, ai_price),
        isProjectedWinner=False,
    )


@router.get("/meetings/today")
def get_todays_meetings(db: Session = Depends(get_db)):
    meetings = db.query(Meeting).all()
    return [_meeting_to_frontend(m, db) for m in meetings]


@router.get("/meetings/live")
def get_live_meetings(db: Session = Depends(get_db)):
    meetings = db.query(Meeting).filter(
        Meeting.status == MeetingStatus.LIVE.value
    ).all()
    return [_meeting_to_frontend(m, db) for m in meetings]


@router.get("/meetings/finished")
def get_finished_meetings(db: Session = Depends(get_db)):
    meetings = db.query(Meeting).filter(
        Meeting.status == MeetingStatus.FINISHED.value
    ).all()
    return [_meeting_to_frontend(m, db) for m in meetings]


@router.get("/meetings/{meeting_id}/participants")
def get_meeting_participants(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting_id
    ).all()

    result = [_participant_to_frontend(p, db) for p in participants]
    winner = max(result, key=lambda x: x.currentPoints) if result else None
    for r in result:
        r.isProjectedWinner = (r.id == winner.id) if winner else False

    return result


@router.get("/meetings/{meeting_id}/prices")
def get_meeting_prices(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    prices = db.query(Price).filter(Price.meeting_id == meeting_id).all()
    return [
        PriceOut(
            id=p.id,
            participant_id=p.participant_id,
            bookmaker_name=p.bookmaker_name,
            price=p.price,
            timestamp=p.timestamp,
        )
        for p in prices
    ]


@router.get("/meetings/{meeting_id}/results")
def get_meeting_results(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    results = db.query(Result).filter(
        Result.meeting_id == meeting_id
    ).order_by(desc(Result.race_number)).all()

    return [
        ResultOut(
            id=r.id,
            participant_id=r.participant_id,
            final_points=r.final_points,
            position=r.position,
        )
        for r in results
    ]


@router.get("/meetings/{meeting_id}")
def get_meeting_detail(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return _meeting_to_frontend(meeting, db)


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    meetings = db.query(Meeting).all()
    frontend_meetings = [_meeting_to_frontend(m, db) for m in meetings]

    all_participants = db.query(Participant).all()
    jockeys = []
    drivers = []
    for p in all_participants:
        meeting = db.query(Meeting).filter(Meeting.id == p.meeting_id).first()
        fp = _participant_to_frontend(p, db)
        if meeting and meeting.type == "jockey":
            jockeys.append(fp)
        else:
            drivers.append(fp)

    recent_results = db.query(Result).order_by(desc(Result.timestamp)).limit(10).all()
    race_results = []
    for r in recent_results:
        p = db.query(Participant).filter(Participant.id == r.participant_id).first()
        m = db.query(Meeting).filter(Meeting.id == r.meeting_id).first()
        if p and m:
            prices = db.query(Price).filter(Price.participant_id == p.id).all()
            avg_bm = sum(pr.price for pr in prices) / len(prices) if prices else 3.0
            ai_price = round(avg_bm * random.uniform(0.85, 1.05), 2)
            overlay = round((avg_bm - ai_price) / ai_price * 100, 1)

            minutes_ago = int(
                (datetime.now(timezone.utc) - r.timestamp.replace(tzinfo=timezone.utc)).total_seconds() / 60
            ) if r.timestamp else 0

            race_results.append(RaceResultOut(
                id=f"r{r.id}",
                meetingName=m.name,
                raceNumber=r.race_number,
                participant=p.name,
                pointsAdded=r.points_added,
                updatedAiPrice=ai_price,
                updatedOverlay=overlay,
                timeUpdated=f"{max(1, minutes_ago)}m ago",
                type=m.type,
            ))

    today_meetings = sum(1 for m in frontend_meetings if m.status != "Completed")
    active_jockey = sum(1 for m in frontend_meetings if m.type == "Jockey" and m.status == "Live")
    active_driver = sum(1 for m in frontend_meetings if m.type == "Driver" and m.status == "Live")

    # Set projected winners per meeting
    meeting_best = {}
    for fp in jockeys + drivers:
        if fp.meetingId not in meeting_best or fp.currentPoints > meeting_best[fp.meetingId].currentPoints:
            meeting_best[fp.meetingId] = fp
    for fp in meeting_best.values():
        fp.isProjectedWinner = True

    return DashboardOut(
        meetings=frontend_meetings,
        jockeys=jockeys,
        drivers=drivers,
        recentResults=race_results,
        dashboardCards=DashboardCards(
            todayMeetings=today_meetings,
            activeJockeyChallenges=active_jockey,
            activeDriverChallenges=active_driver,
            totalParticipants=len(jockeys) + len(drivers),
        ),
    )


@router.post("/refresh")
def refresh_data():
    from status_manager import refresh_meeting_status, scrape_all_bookmakers
    from seed_data import seed_database
    db = SessionLocal()
    try:
        scrape_all_bookmakers()
        refresh_meeting_status()
        seed_database(db)
        return {"status": "ok", "message": "Data refreshed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
