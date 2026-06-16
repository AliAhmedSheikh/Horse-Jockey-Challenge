import functools
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, func

from database import get_db, SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus, FormulaSetting, Bet
from time_utils import today_aus
from utils import compute_value_rating, compute_status, MIN_PRICE
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
    PodiumEntry,
    FormulaSettingsOut,
    BetCreate,
    BetUpdate,
    BetOut,
    BetStats,
)

router = APIRouter()

logger = logging.getLogger(__name__)

ACCURATE_BOOKMAKERS = {"Ladbrokes"}

_cache = {}
CACHE_TTL = 30


def _compute_ai_price(avg_bookmaker: float, current_points: float, completed_races: int, total_races: int) -> float:
    if avg_bookmaker <= 0:
        return 3.0

    if completed_races == 0:
        return round(avg_bookmaker, 2)

    race_progress = completed_races / max(total_races, 1)

    # Expected points per race based on bookmaker price (market expectation)
    implied_prob = 1.0 / max(avg_bookmaker, MIN_PRICE)
    top3_prob = min(0.85, implied_prob * 1.5)
    expected_pts_per_race = top3_prob * 2.0

    expected_points = expected_pts_per_race * completed_races
    perf_ratio = current_points / max(expected_points, 0.01)
    perf_ratio = max(0.2, min(5.0, perf_ratio))

    # Confidence in performance signal grows as more races are completed
    perf_confidence = min(0.7, race_progress * 0.8)

    # Performance-adjusted price: outperforming → shorter, underperforming → longer
    if perf_ratio > 1.0:
        price_adj = 1.0 - (perf_ratio - 1.0) * 0.15
    else:
        price_adj = 1.0 + (1.0 - perf_ratio) * 0.25

    performance_price = avg_bookmaker * max(0.5, price_adj)

    # Blend bookmaker baseline with performance-adjusted price
    ai_price = avg_bookmaker * (1 - perf_confidence) + performance_price * perf_confidence

    # At full completion, price is purely performance-based
    if race_progress >= 1.0:
        ai_price = performance_price

    return round(max(MIN_PRICE, ai_price), 2)


def _meeting_to_frontend(meeting: Meeting, db: Session,
                          _participants: Optional[List[Participant]] = None,
                          _results: Optional[List[Result]] = None,
                          _participant_map: Optional[dict] = None) -> MeetingOut:
    if _participants is not None:
        participants = _participants
    else:
        participants = db.query(Participant).filter(
            Participant.meeting_id == meeting.id
        ).all()

    sorted_ps = sorted(participants, key=lambda p: p.current_points, reverse=True)
    leaderboard = [
        LeaderboardEntry(name=p.name, points=p.current_points, rank=i + 1)
        for i, p in enumerate(sorted_ps)
    ]

    if _results is not None:
        recent_results = _results
    else:
        recent_results = db.query(Result).filter(
            Result.meeting_id == meeting.id,
            Result.points_added > 0
        ).order_by(desc(Result.timestamp)).limit(5).all()

    latest_updates = []
    for r in recent_results:
        if _participant_map is not None:
            p = _participant_map.get(r.participant_id)
        else:
            p = db.query(Participant).filter(Participant.id == r.participant_id).first()
        if p:
            minutes_ago = int(
                (datetime.now(timezone.utc) - (r.timestamp if r.timestamp and r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc))).total_seconds() / 60
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
        scheduledTime=meeting.scheduled_time.isoformat() if meeting.scheduled_time else None,
    )


def _load_value_threshold(db: Session) -> float:
    from models import FormulaSetting
    row = db.query(FormulaSetting).filter(FormulaSetting.id == "valueThreshold").first()
    return row.value if row else DEFAULT_SETTINGS.get("valueThreshold", 15.0)


def _participant_to_frontend_with_data(p: Participant, meeting: Optional[Meeting], prices: List, value_threshold: float = 15.0) -> ParticipantOut:
    accurate_prices = [pr for pr in prices if pr.bookmaker_name in ACCURATE_BOOKMAKERS]
    bookmaker_prices = [pr.price for pr in accurate_prices]
    avg_bookmaker = sum(bookmaker_prices) / len(bookmaker_prices) if bookmaker_prices else 3.0
    total_races = meeting.total_races if meeting else 8
    ai_price = _compute_ai_price(avg_bookmaker, p.current_points, p.completed_races, total_races)
    overlay = round((avg_bookmaker - ai_price) / ai_price * 100, 1)
    remaining = meeting.total_races - p.completed_races if meeting else 0
    if p.completed_races == 0:
        implied = 1.0 / max(avg_bookmaker, 1.01)
        top3_prob = min(0.85, implied * 1.5)
        projected = round(top3_prob * 2.0 * total_races, 1)
    else:
        avg_per_race = p.current_points / p.completed_races
        meeting_completed = meeting.completed_races if meeting else 0
        if meeting_completed > 0:
            participation_rate = min(p.completed_races / meeting_completed, 1.0)
            estimated_remaining_rides = round(remaining * participation_rate, 1)
        else:
            estimated_remaining_rides = remaining
        projected = round(p.current_points + avg_per_race * estimated_remaining_rides, 1)
    value_rating = compute_value_rating(avg_bookmaker, ai_price, value_threshold)
    bookmaker_prices_dict = {pr.bookmaker_name: round(pr.price, 2) for pr in accurate_prices}
    return ParticipantOut(
        id=p.id, name=p.name, meetingName=meeting.name if meeting else "", meetingId=p.meeting_id,
        bookmakerPrice=round(avg_bookmaker, 2), bookmakerPrices=bookmaker_prices_dict, aiPrice=ai_price, overlayPercent=overlay,
        valueRating=value_rating, currentPoints=p.current_points, projectedFinalPoints=projected,
        status=compute_status(avg_bookmaker, ai_price, value_threshold), isProjectedWinner=False,
    )


def _participant_to_frontend(p: Participant, db: Session, value_threshold: float = 15.0) -> ParticipantOut:
    prices = db.query(Price).filter(Price.participant_id == p.id).all()
    meeting = db.query(Meeting).filter(Meeting.id == p.meeting_id).first()

    accurate_prices = [pr for pr in prices if pr.bookmaker_name in ACCURATE_BOOKMAKERS]
    bookmaker_prices = [pr.price for pr in accurate_prices]
    avg_bookmaker = sum(bookmaker_prices) / len(bookmaker_prices) if bookmaker_prices else 3.0

    total = meeting.total_races if meeting else 8
    ai_price = _compute_ai_price(avg_bookmaker, p.current_points, p.completed_races, total)
    overlay = round((avg_bookmaker - ai_price) / ai_price * 100, 1)

    remaining = meeting.total_races - p.completed_races if meeting else 0
    if p.completed_races == 0:
        implied = 1.0 / max(avg_bookmaker, 1.01)
        top3_prob = min(0.85, implied * 1.5)
        projected = round(top3_prob * 2.0 * total, 1)
    else:
        avg_per_race = p.current_points / p.completed_races
        meeting_completed = meeting.completed_races if meeting else 0
        if meeting_completed > 0:
            participation_rate = min(p.completed_races / meeting_completed, 1.0)
            estimated_remaining_rides = round(remaining * participation_rate, 1)
        else:
            estimated_remaining_rides = remaining
        projected = round(p.current_points + avg_per_race * estimated_remaining_rides, 1)

    value_rating = compute_value_rating(avg_bookmaker, ai_price, value_threshold)
    bookmaker_prices_dict = {pr.bookmaker_name: round(pr.price, 2) for pr in accurate_prices}

    return ParticipantOut(
        id=p.id,
        name=p.name,
        meetingName=meeting.name if meeting else "",
        meetingId=p.meeting_id,
        bookmakerPrice=round(avg_bookmaker, 2),
        bookmakerPrices=bookmaker_prices_dict,
        aiPrice=ai_price,
        overlayPercent=overlay,
        valueRating=value_rating,
        currentPoints=p.current_points,
        projectedFinalPoints=projected,
        status=compute_status(avg_bookmaker, ai_price, value_threshold),
        isProjectedWinner=False,
    )


@router.get("/meetings/today")
def get_todays_meetings(db: Session = Depends(get_db)):
    today = today_aus()
    meetings = db.query(Meeting).filter(Meeting.date == today).all()
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
    ).order_by(desc(Participant.current_points)).all()

    value_threshold = _load_value_threshold(db)
    result = [_participant_to_frontend(p, db, value_threshold) for p in participants]
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

    rows = db.query(Result, Participant).join(
        Participant, Result.participant_id == Participant.id
    ).filter(
        Result.meeting_id == meeting_id
    ).order_by(desc(Result.race_number)).all()

    return [
        ResultOut(
            id=r.id,
            participant_id=r.participant_id,
            participant_name=p.name,
            final_points=r.final_points,
            position=r.position,
            race_number=r.race_number,
            points_added=r.points_added,
        )
        for r, p in rows
    ]


@router.get("/meetings/{meeting_id}/podium")
def get_meeting_podium(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    max_race = db.query(func.max(Result.race_number)).filter(Result.meeting_id == meeting_id).scalar()
    if max_race is None:
        return []

    rows = db.query(Result, Participant).join(
        Participant, Result.participant_id == Participant.id
    ).filter(
        Result.meeting_id == meeting_id,
        Result.race_number == max_race,
        Result.position.in_([1, 2, 3]),
    ).order_by(asc(Result.position)).all()

    return [
        PodiumEntry(participant_name=p.name, final_points=r.points_added, position=r.position)
        for r, p in rows
    ]


@router.get("/meetings/{meeting_id}")
def get_meeting_detail(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return _meeting_to_frontend(meeting, db)


def _cached(key: str, ttl: int = CACHE_TTL):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            if key in _cache and now - _cache[key]["ts"] < ttl:
                return _cache[key]["data"]
            try:
                result = func(*args, **kwargs)
                _cache[key] = {"data": result, "ts": now}
                return result
            except Exception as e:
                logger.warning(f"Cache miss for '{key}', error: {e}")
                # Serve stale cache if available (better than crashing/retry loop)
                if key in _cache:
                    logger.info(f"Serving stale '{key}' cache")
                    return _cache[key]["data"]
                # No stale cache — return empty to avoid frontend retry loops
                if key == "dashboard":
                    from schemas import DashboardOut, DashboardCards
                    return DashboardOut(meetings=[], jockeys=[], drivers=[], recentResults=[], dashboardCards=DashboardCards(todayMeetings=0, activeJockeyChallenges=0, activeDriverChallenges=0, totalParticipants=0))
                raise
        return wrapper
    return decorator


@router.get("/dashboard")
@_cached("dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    today = today_aus()
    meetings = db.query(Meeting).filter(Meeting.date == today).options(
        joinedload(Meeting.participants)
    ).all()

    meeting_ids = [m.id for m in meetings]
    if not meeting_ids:
        return DashboardOut(meetings=[], jockeys=[], drivers=[], recentResults=[], dashboardCards=DashboardCards(todayMeetings=0, activeJockeyChallenges=0, activeDriverChallenges=0, totalParticipants=0))

    # Pre-load participants, prices, and results in batch
    all_participants = db.query(Participant).filter(
        Participant.meeting_id.in_(meeting_ids)
    ).all() if meeting_ids else []
    participant_map = {p.id: p for p in all_participants}

    participants_by_meeting = {}
    for p in all_participants:
        participants_by_meeting.setdefault(p.meeting_id, []).append(p)

    all_prices = db.query(Price).filter(
        Price.meeting_id.in_(meeting_ids)
    ).all() if meeting_ids else []
    prices_by_participant = {}
    for pr in all_prices:
        prices_by_participant.setdefault(pr.participant_id, []).append(pr)

    all_results = db.query(Result).filter(
        Result.meeting_id.in_(meeting_ids),
        Result.points_added > 0
    ).order_by(desc(Result.timestamp)).all() if meeting_ids else []
    results_by_meeting = {}
    for r in all_results:
        results_by_meeting.setdefault(r.meeting_id, []).append(r)

    meeting_map = {m.id: m for m in meetings}
    frontend_meetings = []
    for m in meetings:
        mtg_participants = participants_by_meeting.get(m.id, [])
        mtg_results = (results_by_meeting.get(m.id, [])[:5])
        frontend_meetings.append(_meeting_to_frontend(
            m, db,
            _participants=mtg_participants,
            _results=mtg_results,
            _participant_map=participant_map,
        ))

    jockeys = []
    drivers = []
    value_threshold = _load_value_threshold(db)
    for p in all_participants:
        meeting = meeting_map.get(p.meeting_id)
        prs = prices_by_participant.get(p.id, [])
        fp = _participant_to_frontend_with_data(p, meeting, prs, value_threshold)
        if meeting and meeting.type == "jockey":
            jockeys.append(fp)
        else:
            drivers.append(fp)

    race_results = []
    for r in (sorted(all_results, key=lambda x: x.timestamp or datetime.now(timezone.utc), reverse=True)[:30]):
        p = participant_map.get(r.participant_id)
        m = meeting_map.get(r.meeting_id)
        if p and m:
            prs = [pr for pr in prices_by_participant.get(p.id, []) if pr.bookmaker_name in ACCURATE_BOOKMAKERS]
            avg_bm = sum(pr.price for pr in prs) / len(prs) if prs else 3.0
            ai_price = _compute_ai_price(avg_bm, p.current_points, p.completed_races, m.total_races)
            overlay = round((avg_bm - ai_price) / ai_price * 100, 1)

            minutes_ago = int(
                (datetime.now(timezone.utc) - (r.timestamp if r.timestamp and r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc))).total_seconds() / 60
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
                type="Jockey" if m.type == "jockey" else "Driver",
            ))

    today_meetings = sum(1 for m in frontend_meetings if m.status != "Completed")
    active_jockey = sum(1 for m in frontend_meetings if m.type == "Jockey" and m.status in ("Live", "Not Started"))
    active_driver = sum(1 for m in frontend_meetings if m.type == "Driver" and m.status in ("Live", "Not Started"))

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


DEFAULT_SETTINGS = {
    "bookmakerWeight": 35.0,
    "currentPointsWeight": 25.0,
    "remainingRacesWeight": 20.0,
    "completedRacesWeight": 10.0,
    "priceMovementWeight": 10.0,
    "valueThreshold": 10.0,
}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(FormulaSetting).all()
    result = DEFAULT_SETTINGS.copy()
    for row in rows:
        result[row.id] = row.value
    return FormulaSettingsOut(settings=result)


@router.put("/settings")
def put_settings(payload: FormulaSettingsOut, db: Session = Depends(get_db)):
    for key, val in payload.settings.items():
        if key not in DEFAULT_SETTINGS:
            continue
        existing = db.query(FormulaSetting).filter(FormulaSetting.id == key).first()
        if existing:
            existing.value = val
        else:
            db.add(FormulaSetting(id=key, value=val))
    db.commit()
    return {"status": "ok", "message": "Settings saved"}


@router.post("/refresh")
def refresh_data():
    from status_manager import refresh_meeting_status, scrape_all_bookmakers
    from seed_data import seed_database
    db = SessionLocal()
    try:
        scrape_all_bookmakers()
        refresh_meeting_status()
        seed_database(db)
        _cache.clear()
        return {"status": "ok", "message": "Data refreshed"}
    except Exception as e:
        db.rollback()
        _cache.clear()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/reseed")
def reseed_data():
    from status_manager import refresh_meeting_status, scrape_all_bookmakers
    from seed_data import seed_database
    db = SessionLocal()
    try:
        db.query(Result).delete()
        db.query(Price).delete()
        db.query(Bet).delete()
        db.query(Participant).delete()
        db.query(Meeting).delete()
        db.commit()
        _cache.clear()
        seed_database(db, force=True)
        scrape_all_bookmakers()
        refresh_meeting_status()
        _cache.clear()
        meetings = db.query(Meeting).all()
        participants = db.query(Participant).all()
        return {
            "status": "ok",
            "message": f"Re-seeded: {len(meetings)} meetings, {len(participants)} participants",
        }
    except Exception as e:
        db.rollback()
        _cache.clear()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


from fastapi.responses import StreamingResponse
import json
import time as _time

_sse_clients: list = []
_sse_lock = threading.Lock()


def broadcast_sse(event: str, data: dict):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.append(msg)
            except Exception:
                dead.append(q)
        for d in dead:
            _sse_clients.remove(d)


@router.get("/events")
async def sse_events():
    import asyncio
    queue: list = []
    with _sse_lock:
        _sse_clients.append(queue)

    async def stream():
        try:
            while True:
                while queue:
                    msg = queue.pop(0)
                    yield msg
                yield ": keepalive\n\n"
                await asyncio.sleep(1)
        finally:
            with _sse_lock:
                if queue in _sse_clients:
                    _sse_clients.remove(queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


@router.get("/meetings/{meeting_id}/prediction")
def get_meeting_prediction(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting_id
    ).all()

    value_threshold = _load_value_threshold(db)

    pids = [p.id for p in participants]
    all_prices = db.query(Price).filter(Price.participant_id.in_(pids)).all() if pids else []
    prices_by_pid = {}
    for pr in all_prices:
        prices_by_pid.setdefault(pr.participant_id, []).append(pr)

    predictions = []
    for p in participants:
        prs = prices_by_pid.get(p.id, [])
        accurate_prices = [pr for pr in prs if pr.bookmaker_name in ACCURATE_BOOKMAKERS]
        bp_list = [pr.price for pr in accurate_prices]
        avg_bm = sum(bp_list) / len(bp_list) if bp_list else 3.0

        implied_prob = 1.0 / max(avg_bm, MIN_PRICE)
        win_prob = min(0.85, implied_prob * 1.2)

        remaining = meeting.total_races - meeting.completed_races
        if meeting.completed_races == 0:
            expected_pts_per_race = win_prob * 2.0
            estimated_final = round(expected_pts_per_race * meeting.total_races, 1)
        else:
            avg_per_race = p.current_points / max(p.completed_races, 1)
            participation_rate = min(p.completed_races / meeting.completed_races, 1.0)
            estimated_remaining_rides = round(remaining * participation_rate, 1)
            estimated_final = round(p.current_points + avg_per_race * estimated_remaining_rides, 1)

        predictions.append({
            "id": p.id,
            "name": p.name,
            "currentPoints": p.current_points,
            "completedRaces": p.completed_races,
            "remainingRaces": remaining,
            "bookmakerPrice": round(avg_bm, 2),
            "winProbability": round(win_prob * 100, 1),
            "estimatedFinalPoints": estimated_final,
        })

    predictions.sort(key=lambda x: x["estimatedFinalPoints"], reverse=True)

    return {
        "meetingId": meeting.id,
        "meetingName": meeting.name,
        "status": meeting.status,
        "completedRaces": meeting.completed_races,
        "totalRaces": meeting.total_races,
        "projectedWinner": predictions[0]["name"] if predictions else "",
        "predictions": predictions,
    }


@router.get("/bets")
def get_bets(db: Session = Depends(get_db)):
    bets = db.query(Bet).order_by(Bet.created_at.desc()).all()
    return [
        BetOut(
            id=b.id,
            participantId=b.participant_id,
            meetingId=b.meeting_id,
            participantName=b.participant_name,
            meetingName=b.meeting_name,
            betType=b.bet_type,
            stake=b.stake,
            odds=b.odds,
            potentialReturn=b.potential_return,
            result=b.result,
            pnl=b.pnl,
            createdAt=b.created_at.isoformat() if b.created_at else "",
            updatedAt=b.updated_at.isoformat() if b.updated_at else "",
        )
        for b in bets
    ]


@router.post("/bets")
def create_bet(payload: BetCreate, db: Session = Depends(get_db)):
    potential_return = round(payload.stake * payload.odds, 2)
    bet = Bet(
        participant_id=payload.participantId,
        meeting_id=payload.meetingId,
        participant_name=payload.participantName,
        meeting_name=payload.meetingName,
        bet_type=payload.betType,
        stake=payload.stake,
        odds=payload.odds,
        potential_return=potential_return,
        result="pending",
        pnl=0.0,
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return BetOut(
        id=bet.id,
        participantId=bet.participant_id,
        meetingId=bet.meeting_id,
        participantName=bet.participant_name,
        meetingName=bet.meeting_name,
        betType=bet.bet_type,
        stake=bet.stake,
        odds=bet.odds,
        potentialReturn=bet.potential_return,
        result=bet.result,
        pnl=bet.pnl,
        createdAt=bet.created_at.isoformat() if bet.created_at else "",
        updatedAt=bet.updated_at.isoformat() if bet.updated_at else "",
    )


@router.put("/bets/{bet_id}")
def update_bet(bet_id: int, payload: BetUpdate, db: Session = Depends(get_db)):
    bet = db.query(Bet).filter(Bet.id == bet_id).first()
    if not bet:
        raise HTTPException(status_code=404, detail="Bet not found")

    if payload.stake is not None:
        bet.stake = payload.stake
        bet.potential_return = round(bet.stake * bet.odds, 2)
    if payload.odds is not None:
        bet.odds = payload.odds
        bet.potential_return = round(bet.stake * bet.odds, 2)
    if payload.betType is not None:
        bet.bet_type = payload.betType
    if payload.result is not None:
        bet.result = payload.result
        if payload.result == "won":
            bet.pnl = round(bet.potential_return - bet.stake, 2)
            bet.settled_at = datetime.now(timezone.utc)
        elif payload.result == "lost":
            bet.pnl = -bet.stake
            bet.settled_at = datetime.now(timezone.utc)
        elif payload.result == "void":
            bet.pnl = 0.0
            bet.settled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bet)
    return BetOut(
        id=bet.id,
        participantId=bet.participant_id,
        meetingId=bet.meeting_id,
        participantName=bet.participant_name,
        meetingName=bet.meeting_name,
        betType=bet.bet_type,
        stake=bet.stake,
        odds=bet.odds,
        potentialReturn=bet.potential_return,
        result=bet.result,
        pnl=bet.pnl,
        createdAt=bet.created_at.isoformat() if bet.created_at else "",
        updatedAt=bet.updated_at.isoformat() if bet.updated_at else "",
    )


@router.delete("/bets/{bet_id}")
def delete_bet(bet_id: int, db: Session = Depends(get_db)):
    bet = db.query(Bet).filter(Bet.id == bet_id).first()
    if not bet:
        raise HTTPException(status_code=404, detail="Bet not found")
    db.delete(bet)
    db.commit()
    return {"status": "ok", "message": "Bet deleted"}


@router.get("/bets/stats")
def get_bet_stats(db: Session = Depends(get_db)):
    bets = db.query(Bet).all()
    total_bets = len(bets)
    total_staked = sum(b.stake for b in bets)
    total_returned = sum(b.potential_return for b in bets if b.result == "won")
    total_pnl = sum(b.pnl for b in bets)
    win_count = sum(1 for b in bets if b.result == "won")
    loss_count = sum(1 for b in bets if b.result == "lost")
    pending_count = sum(1 for b in bets if b.result == "pending")
    settled = win_count + loss_count
    win_rate = (win_count / settled * 100) if settled > 0 else 0.0
    roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0.0

    pnl_by_day = {}
    for b in bets:
        if b.result in ("won", "lost", "void") and b.settled_at:
            day = b.settled_at.strftime("%Y-%m-%d")
            pnl_by_day[day] = pnl_by_day.get(day, 0.0) + b.pnl

    cumulative_pnl = []
    running = 0.0
    for day in sorted(pnl_by_day.keys()):
        running += pnl_by_day[day]
        cumulative_pnl.append({"date": day, "pnl": round(running, 2)})

    return BetStats(
        totalBets=total_bets,
        totalStaked=round(total_staked, 2),
        totalReturned=round(total_returned, 2),
        totalPnl=round(total_pnl, 2),
        roi=round(roi, 1),
        winCount=win_count,
        lossCount=loss_count,
        pendingCount=pending_count,
        winRate=round(win_rate, 1),
    )
