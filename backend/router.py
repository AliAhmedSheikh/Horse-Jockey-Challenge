import functools
import json
import logging
import math
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
from schemas import (
    MeetingOut,
    ParticipantOut,
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
    ParticipantDetail,
    RideDetail,
)

router = APIRouter()

logger = logging.getLogger(__name__)

_cache = {}
CACHE_TTL = 30


# ---------------------------------------------------------------------------
# NEW: Probability-based AI price model (no bookmaker odds dependency)
# ---------------------------------------------------------------------------

def _compute_win_probability(
    current_points: float,
    completed_races: int,
    total_races: int,
    all_participant_points: Optional[List[float]] = None,
    participant_index: Optional[int] = None,
    total_participants: Optional[int] = None,
) -> float:
    """Compute win probability from performance data only.

    The model uses:
      1. Points-per-race rate (primary signal)
      2. Data confidence (more completed races = more confident)
      3. Remaining races (more remaining = flatter probabilities)
      4. Relative standing vs field (normalised within the meeting)

    Returns a probability between 0.01 and 0.95.
    """
    remaining = total_races - completed_races
    n_participants = len(all_participant_points) if all_participant_points else (total_participants or 12)

    # --- 1. Base rate: average points per race ---
    if completed_races > 0:
        pts_per_race = current_points / completed_races
    elif participant_index is not None and total_participants and total_participants > 1:
        rank_ratio = participant_index / max(total_participants - 1, 1)
        pts_per_race = 0.3 + (1.0 - rank_ratio) * 1.8
    else:
        pts_per_race = 0.0

    # --- 2. Normalise within the field ---
    if all_participant_points and len(all_participant_points) > 1:
        max_pts = max(all_participant_points) if all_participant_points else 0
        total_field_pts = sum(all_participant_points)
        avg_field_pts = total_field_pts / len(all_participant_points)

        if max_pts > 0:
            relative = (current_points - avg_field_pts) / max(max_pts, 1)
        else:
            if participant_index is not None and total_participants and total_participants > 1:
                relative = (0.5 - participant_index / max(total_participants - 1, 1))
            else:
                relative = 0.0
    else:
        relative = 0.0

    # --- 3. Data confidence factor ---
    if total_races > 0:
        data_confidence = completed_races / total_races
    else:
        data_confidence = 0.0

    # --- 4. Remaining races factor ---
    if total_races > 0:
        remaining_factor = remaining / total_races
    else:
        remaining_factor = 1.0

    # --- 5. Combine into probability ---
    flat_prior = 1.0 / max(n_participants, 2)

    perf_signal = min(pts_per_race / 3.0, 1.0) if pts_per_race > 0 else 0.0

    if completed_races > 0:
        combined = flat_prior + data_confidence * (perf_signal - flat_prior) * 0.8
    else:
        combined = flat_prior + 0.4 * (perf_signal - flat_prior)

    relative_boost = relative * 0.20 * max(data_confidence, 0.4 if completed_races == 0 else 0)
    combined += relative_boost

    return max(0.01, min(0.95, combined))


def _compute_ai_price_from_probability(probability: float) -> float:
    """Convert probability to odds price: AI Price = 1 / probability."""
    if probability <= 0:
        return 100.0
    price = 1.0 / probability
    return round(max(1.50, min(100.0, price)), 2)


def _compute_ai_price(
    current_points: float,
    completed_races: int,
    total_races: int,
    all_participant_points: Optional[List[float]] = None,
    participant_index: Optional[int] = None,
    total_participants: Optional[int] = None,
) -> tuple:
    """Compute AI price and win probability from performance data only.

    Returns (ai_price, win_probability).
    """
    win_prob = _compute_win_probability(
        current_points, completed_races, total_races, all_participant_points,
        participant_index, total_participants
    )
    ai_price = _compute_ai_price_from_probability(win_prob)
    return ai_price, round(win_prob * 100, 1)


# ---------------------------------------------------------------------------
# Frontend converters
# ---------------------------------------------------------------------------

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

    sorted_ps = sorted(participants, key=lambda p: (-p.current_points, p.name))
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


def _participant_to_frontend_with_data(
    p: Participant,
    meeting: Optional[Meeting],
    all_participant_points: Optional[List[float]] = None,
    is_projected_winner: bool = False,
    participant_index: Optional[int] = None,
    total_participants: Optional[int] = None,
) -> ParticipantOut:
    total_races = meeting.total_races if meeting else 8
    ai_price, win_prob = _compute_ai_price(
        p.current_points, p.completed_races, total_races, all_participant_points,
        participant_index, total_participants
    )

    remaining = total_races - p.completed_races if meeting else 0
    if p.completed_races == 0:
        projected = round(0.5 * total_races, 1) if total_races else 0
    else:
        avg_per_race = p.current_points / p.completed_races
        meeting_completed = meeting.completed_races if meeting else 0
        if meeting_completed > 0:
            participation_rate = min(p.completed_races / meeting_completed, 1.0)
            estimated_remaining_rides = round(remaining * participation_rate, 1)
        else:
            estimated_remaining_rides = remaining
        projected = round(p.current_points + avg_per_race * estimated_remaining_rides, 1)

    return ParticipantOut(
        id=p.id, name=p.name, meetingName=meeting.name if meeting else "", meetingId=p.meeting_id,
        aiPrice=ai_price, winProbability=win_prob,
        currentPoints=p.current_points, projectedFinalPoints=projected,
        isProjectedWinner=is_projected_winner,
    )


def _participant_to_frontend(p: Participant, db: Session, all_participant_points: Optional[List[float]] = None, is_projected_winner: bool = False, participant_index: Optional[int] = None, total_participants: Optional[int] = None) -> ParticipantOut:
    meeting = db.query(Meeting).filter(Meeting.id == p.meeting_id).first()
    total_races = meeting.total_races if meeting else 8
    ai_price, win_prob = _compute_ai_price(
        p.current_points, p.completed_races, total_races, all_participant_points, participant_index, total_participants
    )

    remaining = total_races - p.completed_races if meeting else 0
    if p.completed_races == 0:
        projected = round(0.5 * total_races, 1) if total_races else 0
    else:
        avg_per_race = p.current_points / p.completed_races
        meeting_completed = meeting.completed_races if meeting else 0
        if meeting_completed > 0:
            participation_rate = min(p.completed_races / meeting_completed, 1.0)
            estimated_remaining_rides = round(remaining * participation_rate, 1)
        else:
            estimated_remaining_rides = remaining
        projected = round(p.current_points + avg_per_race * estimated_remaining_rides, 1)

    return ParticipantOut(
        id=p.id,
        name=p.name,
        meetingName=meeting.name if meeting else "",
        meetingId=p.meeting_id,
        aiPrice=ai_price,
        winProbability=win_prob,
        currentPoints=p.current_points,
        projectedFinalPoints=projected,
        isProjectedWinner=is_projected_winner,
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

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
    ).all()

    participants.sort(key=lambda p: (-p.current_points, p.name))

    all_pts = [p.current_points for p in participants]

    result = []
    for i, p in enumerate(participants):
        result.append(_participant_to_frontend(p, db, all_pts, participant_index=i, total_participants=len(participants)))

    if result:
        result[0].isProjectedWinner = True

    return result


@router.get("/meetings/{meeting_id}/participants/{participant_id}/detail")
def get_participant_detail(meeting_id: str, participant_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    participant = db.query(Participant).filter(
        Participant.id == participant_id,
        Participant.meeting_id == meeting_id,
    ).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    all_parts = db.query(Participant).filter(Participant.meeting_id == meeting_id).all()
    all_pts = [p.current_points for p in all_parts]
    p_idx = next((i for i, pp in enumerate(all_parts) if pp.id == participant.id), None)

    total_races = meeting.total_races or 8
    ai_price, win_prob = _compute_ai_price(
        participant.current_points, participant.completed_races, total_races, all_pts, p_idx, len(all_parts)
    )

    remaining = total_races - participant.completed_races
    if participant.completed_races == 0:
        projected = round(0.5 * total_races, 1) if total_races else 0
    else:
        avg_per_race = participant.current_points / participant.completed_races
        meeting_completed = meeting.completed_races if meeting else 0
        if meeting_completed > 0:
            participation_rate = min(participant.completed_races / meeting_completed, 1.0)
            estimated_remaining_rides = round(remaining * participation_rate, 1)
        else:
            estimated_remaining_rides = remaining
        projected = round(participant.current_points + avg_per_race * estimated_remaining_rides, 1)

    existing_results = db.query(Result).filter(
        Result.meeting_id == meeting_id,
        Result.participant_id == participant_id,
    ).all()
    results_map = {r.race_number: r for r in existing_results}

    rides = []
    for race_num in range(1, total_races + 1):
        result = results_map.get(race_num)
        if result and result.position is not None:
            if result.position == 1:
                status = "Won"
            elif result.position == 2:
                status = "2nd"
            elif result.position == 3:
                status = "3rd"
            elif result.position <= 4:
                status = "Placed"
            else:
                status = "Unplaced"
        elif race_num <= meeting.completed_races:
            status = "Completed"
        else:
            status = "Upcoming"

        # Per-race expected points: if participant has odds in this race
        # (no bookmaker data, so we derive from meeting-level probability)
        race_expected_pts = None
        race_win_prob = None

        rides.append(RideDetail(
            raceNumber=race_num,
            horseName="",
            expectedPoints=race_expected_pts,
            winProbability=race_win_prob,
            status=status,
            position=result.position if result and result.position else None,
            pointsAwarded=result.points_added if result and result.points_added else None,
        ))

    return ParticipantDetail(
        id=participant_id,
        name=participant.name,
        meetingName=meeting.name,
        meetingType=meeting.type.value if hasattr(meeting.type, 'value') else meeting.type,
        currentPoints=participant.current_points,
        projectedFinalPoints=projected,
        projectedAdditionalPoints=round(projected - participant.current_points, 1),
        aiPrice=round(ai_price, 2),
        winProbability=win_prob,
        remainingRides=remaining,
        totalRaces=total_races,
        completedRaces=participant.completed_races,
        rides=rides,
    )


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

    rows = db.query(
        Participant.name,
        func.sum(Result.points_added).label("total_points"),
    ).join(
        Participant, Result.participant_id == Participant.id
    ).filter(
        Result.meeting_id == meeting_id,
        Result.points_added > 0,
    ).group_by(
        Result.participant_id, Participant.name
    ).order_by(
        desc(func.sum(Result.points_added))
    ).limit(3).all()

    return [
        PodiumEntry(participant_name=name, final_points=round(total or 0, 1), position=i + 1)
        for i, (name, total) in enumerate(rows)
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
    meetings = db.query(Meeting).filter(
        Meeting.date == today,
    ).options(
        joinedload(Meeting.participants)
    ).all()

    meeting_ids = [m.id for m in meetings]
    if not meeting_ids:
        return DashboardOut(meetings=[], jockeys=[], drivers=[], recentResults=[], dashboardCards=DashboardCards(todayMeetings=0, activeJockeyChallenges=0, activeDriverChallenges=0, totalParticipants=0))

    all_participants = db.query(Participant).filter(
        Participant.meeting_id.in_(meeting_ids)
    ).all() if meeting_ids else []
    participant_map = {p.id: p for p in all_participants}

    participants_by_meeting = {}
    for p in all_participants:
        participants_by_meeting.setdefault(p.meeting_id, []).append(p)

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

    for p in all_participants:
        meeting = meeting_map.get(p.meeting_id)
        mtg_parts = participants_by_meeting.get(p.meeting_id, [])
        mtg_parts.sort(key=lambda pp: (-pp.current_points, pp.name))
        all_pts = [pp.current_points for pp in mtg_parts]
        p_idx = next((i for i, pp in enumerate(mtg_parts) if pp.id == p.id), None)
        fp = _participant_to_frontend_with_data(p, meeting, all_pts, participant_index=p_idx, total_participants=len(mtg_parts))
        if meeting and meeting.type == "jockey":
            jockeys.append(fp)
        else:
            drivers.append(fp)

    # Mark projected winners per meeting
    meeting_best = {}
    for fp in jockeys + drivers:
        if fp.meetingId not in meeting_best or (-fp.currentPoints, fp.name) < (-meeting_best[fp.meetingId].currentPoints, meeting_best[fp.meetingId].name):
            meeting_best[fp.meetingId] = fp
    for fp in meeting_best.values():
        fp.isProjectedWinner = True

    race_results = []
    for r in (sorted(all_results, key=lambda x: x.timestamp or datetime.now(timezone.utc), reverse=True)[:30]):
        p = participant_map.get(r.participant_id)
        m = meeting_map.get(r.meeting_id)
        if p and m:
            all_pts = [pp.current_points for pp in participants_by_meeting.get(m.id, [])]
            ai_price, _ = _compute_ai_price(p.current_points, p.completed_races, m.total_races, all_pts, 0, len(all_pts))

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
                timeUpdated=f"{max(1, minutes_ago)}m ago",
                type="Jockey" if m.type == "jockey" else "Driver",
            ))

    today_meetings = len(frontend_meetings)
    active_jockey = sum(1 for m in frontend_meetings if m.type == "Jockey")
    active_driver = sum(1 for m in frontend_meetings if m.type == "Driver")

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
    "currentPointsWeight": 25.0,
    "remainingRacesWeight": 20.0,
    "completedRacesWeight": 10.0,
}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(FormulaSetting).all()
    result = DEFAULT_SETTINGS.copy()
    for row in rows:
        if row.id in DEFAULT_SETTINGS:
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
    import threading
    def _bg_refresh():
        from status_updater import update_meeting_statuses
        from points_calculator import recalculate_all_points
        from seed_data import seed_database
        db = SessionLocal()
        try:
            seed_database(db)
            update_meeting_statuses()
            recalculate_all_points()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Background refresh failed: {e}", exc_info=True)
        finally:
            db.close()
            _cache.clear()
    t = threading.Thread(target=_bg_refresh, daemon=True)
    t.start()
    return {"status": "ok", "message": "Refresh started"}


@router.post("/reseed")
def reseed_data():
    import threading
    def _bg_reseed():
        from status_updater import update_meeting_statuses
        from points_calculator import recalculate_all_points
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
            update_meeting_statuses()
            recalculate_all_points()
            _cache.clear()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Background reseed failed: {e}", exc_info=True)
            _cache.clear()
        finally:
            db.close()
    t = threading.Thread(target=_bg_reseed, daemon=True)
    t.start()
    return {"status": "ok", "message": "Re-seed started"}


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

    participants.sort(key=lambda p: (-p.current_points, p.name))

    all_pts = [p.current_points for p in participants]

    predictions = []
    total_parts = len(participants)
    for i, p in enumerate(participants):
        remaining = meeting.total_races - meeting.completed_races
        ai_price, win_prob = _compute_ai_price(
            p.current_points, p.completed_races, meeting.total_races, all_pts,
            participant_index=i, total_participants=total_parts
        )

        if meeting.completed_races > 0:
            avg_per_race = p.current_points / max(p.completed_races, 1)
            participation_rate = min(p.completed_races / meeting.completed_races, 1.0)
            estimated_remaining_rides = round(remaining * participation_rate, 1)
            estimated_final = round(p.current_points + avg_per_race * estimated_remaining_rides, 1)
        else:
            rank_ratio = i / max(total_parts - 1, 1) if total_parts > 1 else 0.5
            base = 6.0 / max(total_parts, 1)
            pts_per_race = base + (1.0 - rank_ratio) * base * 1.5
            estimated_final = round(pts_per_race * meeting.total_races, 1)

        predictions.append({
            "id": p.id,
            "name": p.name,
            "currentPoints": p.current_points,
            "completedRaces": p.completed_races,
            "remainingRaces": remaining,
            "winProbability": win_prob,
            "estimatedFinalPoints": estimated_final,
        })

    predictions.sort(key=lambda x: (-x["estimatedFinalPoints"]))

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
        createdAt=bet.created_at.isoformat() if b.created_at else "",
        updatedAt=bet.updated_at.isoformat() if b.updated_at else "",
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
        createdAt=bet.created_at.isoformat() if b.created_at else "",
        updatedAt=bet.updated_at.isoformat() if b.updated_at else "",
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
    settled_bets = [b for b in bets if b.result in ("won", "lost")]
    settled_staked = sum(b.stake for b in settled_bets)
    total_pnl = sum(b.pnl for b in bets)
    win_count = sum(1 for b in bets if b.result == "won")
    loss_count = sum(1 for b in bets if b.result == "lost")
    pending_count = sum(1 for b in bets if b.result == "pending")
    settled = win_count + loss_count
    win_rate = (win_count / settled * 100) if settled > 0 else 0.0
    roi = (total_pnl / settled_staked * 100) if settled_staked > 0 else 0.0

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
        totalStaked=round(settled_staked, 2),
        totalReturned=round(sum(b.potential_return for b in settled_bets), 2),
        totalPnl=round(total_pnl, 2),
        roi=round(roi, 1),
        winCount=win_count,
        lossCount=loss_count,
        pendingCount=pending_count,
        winRate=round(win_rate, 1),
    )


@router.get("/audit")
def run_audit(db: Session = Depends(get_db)):
    """Comprehensive audit: check all meetings for data integrity issues."""
    issues = []
    meetings = db.query(Meeting).filter(
        Meeting.status.in_([MeetingStatus.LIVE.value, MeetingStatus.FINISHED.value])
    ).all()

    for meeting in meetings:
        participants = db.query(Participant).filter(
            Participant.meeting_id == meeting.id
        ).all()
        results = db.query(Result).filter(
            Result.meeting_id == meeting.id
        ).order_by(Result.race_number, Result.position).all()

        p_map = {p.id: p for p in participants}

        for p in participants:
            result_sum = sum(
                r.points_added for r in results
                if r.participant_id == p.id and r.points_added > 0
            )
            if abs(result_sum - p.current_points) > 0.01:
                issues.append({
                    "meeting": meeting.name,
                    "meetingId": meeting.id,
                    "type": "points_mismatch",
                    "participant": p.name,
                    "participantId": p.id,
                    "detail": f"DB points={p.current_points}, sum(results)={result_sum}",
                    "severity": "high",
                })

        for race_num in range(1, meeting.completed_races + 1):
            race_results = [r for r in results if r.race_number == race_num]
            pos_counts = {}
            for r in race_results:
                if r.position < 99:
                    pos_counts[r.position] = pos_counts.get(r.position, 0) + 1
            for pos, count in pos_counts.items():
                if count > 1 and pos <= 3:
                    names = [p_map[r.participant_id].name for r in race_results if r.position == pos and r.participant_id in p_map]
                    issues.append({
                        "meeting": meeting.name,
                        "meetingId": meeting.id,
                        "type": "duplicate_position",
                        "detail": f"Race {race_num}: {count} participants in position {pos}: {names}",
                        "severity": "medium",
                    })

        for p in participants:
            race_results = [r for r in results if r.participant_id == p.id]
            if meeting.completed_races > 0 and len(race_results) == 0:
                issues.append({
                    "meeting": meeting.name,
                    "meetingId": meeting.id,
                    "type": "no_results",
                    "participant": p.name,
                    "detail": f"No result records at all for {meeting.completed_races} completed races",
                    "severity": "high",
                })
            elif meeting.completed_races > 0:
                unplaced_races = [r for r in race_results if r.position == 99]
                if len(unplaced_races) >= meeting.completed_races * 0.5 and meeting.completed_races >= 3:
                    issues.append({
                        "meeting": meeting.name,
                        "meetingId": meeting.id,
                        "type": "frequent_unmatched",
                        "participant": p.name,
                        "detail": f"Unmatched in {len(unplaced_races)}/{len(race_results)} races (possible name matching issue)",
                        "severity": "high",
                    })

        expected_results = meeting.completed_races * len(participants)
        actual_results = len(results)
        if actual_results != expected_results and expected_results > 0:
            issues.append({
                "meeting": meeting.name,
                "meetingId": meeting.id,
                "type": "result_count_mismatch",
                "detail": f"Expected {expected_results} results ({meeting.completed_races} races x {len(participants)} participants), got {actual_results}",
                "severity": "medium",
            })

        for r in results:
            if r.position > 3 and r.points_added > 0:
                issues.append({
                    "meeting": meeting.name,
                    "meetingId": meeting.id,
                    "type": "invalid_scoring",
                    "detail": f"Race {r.race_number}: position {r.position} has {r.points_added} points (should be 0)",
                    "severity": "high",
                })

    total_meetings = len(meetings)
    high_severity = sum(1 for i in issues if i["severity"] == "high")
    medium_severity = sum(1 for i in issues if i["severity"] == "medium")

    return {
        "totalMeetings": total_meetings,
        "totalIssues": len(issues),
        "highSeverity": high_severity,
        "mediumSeverity": medium_severity,
        "issues": issues,
    }
