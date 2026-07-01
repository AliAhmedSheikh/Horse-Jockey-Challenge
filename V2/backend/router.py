# ===========================================================================
# OSYSTIC ROUTER VERSION: v2-FIXES (elimination + pre-match equal + horse odds)
# If this marker is missing from the deployed file, the OLD version is running.
# Verify after deploy: GET /api/version should return this string.
# ===========================================================================
ROUTER_VERSION = "v3-MONTE-CARLO-AI-2026-06-28"

import functools
import json
import logging
import math
import random
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, func

from database import get_db, SessionLocal, commit_lock
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

try:
    from monte_carlo import build_race_data_from_participants, simulate_race, calibrate_prob
except Exception:  # keep backend alive if monte_carlo.py is missing during deploy
    build_race_data_from_participants = None
    simulate_race = None
    calibrate_prob = None

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/version")
def get_version():
    """Returns the deployed router version so we can confirm the right file is live."""
    return {"routerVersion": ROUTER_VERSION}

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

    if completed_races == 0:
        return 1.0 / max(n_participants, 2)

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
        scoring_pts = [p for p in all_participant_points if p > 0]
        if scoring_pts:
            avg_field_pts = sum(scoring_pts) / len(scoring_pts)
        else:
            avg_field_pts = 0

        # --- Mathematical elimination ---
        # Max points a jockey/driver can earn in one race is 3 (a win).
        # If this participant's best possible final score cannot even reach the
        # current leader's points, they are mathematically out of contention and
        # must receive the floor probability (longest price), regardless of form.
        max_possible_final = current_points + remaining * 3.0
        if max_pts > 0 and max_possible_final < max_pts:
            return 0.01

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

    # Read formula weights from DB settings (defaults: 0.80, 0.20)
    try:
        from models import FormulaSetting
        settings = {r.id: r.value for r in SessionLocal().query(FormulaSetting).all()}
    except Exception:
        settings = {}

    pts_weight = settings.get("currentPointsWeight", 25.0) / 100.0  # 0.25 → scale to 0-1 range
    rel_weight = settings.get("remainingRacesWeight", 20.0) / 100.0
    # completed_races_weight used for data confidence scaling
    completed_weight = settings.get("completedRacesWeight", 10.0) / 100.0

    # Map slider values to actual multipliers:
    # currentPointsWeight controls performance signal strength (higher = more weight on form)
    perf_multiplier = 0.4 + pts_weight * 2.0  # range: 0.4 (low) to ~0.9 (max 25%)
    # remainingRacesWeight controls relative boost strength
    boost_multiplier = 0.05 + rel_weight * 0.75  # range: 0.05 (low) to ~0.20 (max 20%)
    # completedRacesWeight adds a confidence bonus
    confidence_bonus = completed_weight * 0.3

    if completed_races > 0:
        combined = flat_prior + data_confidence * (perf_signal - flat_prior) * perf_multiplier
    else:
        combined = flat_prior + 0.4 * (perf_signal - flat_prior)

    relative_boost = relative * boost_multiplier * (data_confidence + confidence_bonus)
    combined += relative_boost

    return max(0.01, min(0.95, combined))


def _compute_tied_indices(participants):
    """For participants sorted by (-points, name), compute average index for tied groups.

    Participants with the same points AND same completed_races share an average
    index so they receive identical AI prices.
    When ALL participants have 0 completed races (pre-race), everyone is tied with
    no data to separate them, so they all share the same average index and therefore
    receive identical AI prices.
    """
    n = len(participants)
    if n == 0:
        return {}
    all_pre_race = all(p.completed_races == 0 for p in participants)
    idx_map = {}
    if all_pre_race:
        avg_idx = (n - 1) / 2.0
        for k in range(n):
            idx_map[participants[k].id] = avg_idx
        return idx_map
    i = 0
    while i < n:
        j = i
        pts_i = participants[i].current_points
        cr_i = participants[i].completed_races
        while j < n and participants[j].current_points == pts_i and participants[j].completed_races == cr_i:
            j += 1
        if (j - i) == 1:
            for k in range(i, j):
                idx_map[participants[k].id] = float(k)
        else:
            avg_idx = (i + j - 1) / 2.0
            for k in range(i, j):
                idx_map[participants[k].id] = avg_idx
        i = j
    return idx_map


def _compute_ai_price_from_probability(probability: float) -> float:
    """Convert probability to odds price: AI Price = 1 / probability.

    Note: this is the old fallback model (no race odds available for Monte Carlo).
    The Monte Carlo path applies its own calibration in _run_remaining_race_simulation,
    so this function uses raw price conversion without calibration.
    """
    if probability <= 0:
        return 100.0
    price = 1.0 / max(probability, 0.001)
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
# Monte Carlo challenge-pricing bridge
# ---------------------------------------------------------------------------
# The scraper stores individual horse/runner win odds in Price.race_odds_json.
# These are NOT bookmaker Jockey/Driver Challenge prices. They are inputs for
# our own AI challenge model. This bridge converts those race odds into:
#   horse odds -> expected 3-2-1 points -> challenge win probability -> AI price

AI_SIMULATIONS = 12000
AI_PRICE_MARGIN = 0.175


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _normalise_race_odds(raw) -> Dict[str, Dict[str, Any]]:
    """Return clean {race_number: {horse, odds}} race odds map."""
    if not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        try:
            race_num = int(k)
        except (ValueError, TypeError):
            continue
        horse = (v.get("horse") or "").strip()
        odds = _safe_float(v.get("odds"), 0.0)
        if race_num > 0 and horse and odds > 0:
            cleaned[str(race_num)] = {"horse": horse, "odds": odds}
    return cleaned


def _load_race_odds_by_participant(db: Session, meeting_id: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load saved runner odds per participant from Price.race_odds_json.

    Prefer Ladbrokes rows because base.py stores the richest per-race horse odds
    there. If another bookmaker row has race_odds_json and Ladbrokes is missing,
    use that as fallback.
    """
    rows = db.query(Price).filter(
        Price.meeting_id == meeting_id,
        Price.race_odds_json.isnot(None),
    ).all()

    by_pid: Dict[str, Dict[str, Dict[str, Any]]] = {}
    source_rank = {"Ladbrokes": 0, "TAB": 1, "TABtouch": 2, "TABtouch_PreRace": 3}
    best_rank: Dict[str, int] = {}

    for row in rows:
        if not row.race_odds_json:
            continue
        try:
            parsed = json.loads(row.race_odds_json)
        except (ValueError, TypeError):
            continue
        cleaned = _normalise_race_odds(parsed)
        if not cleaned:
            continue
        rank = source_rank.get(row.bookmaker_name, 9)
        if row.participant_id not in by_pid or rank < best_rank.get(row.participant_id, 99):
            by_pid[row.participant_id] = cleaned
            best_rank[row.participant_id] = rank
    return by_pid


def _fallback_projection(p: Participant, meeting: Optional[Meeting], all_pts=None, idx=None, n=None) -> Dict[str, float]:
    total_races = meeting.total_races if meeting else 8
    ai_price, win_prob = _compute_ai_price(
        p.current_points,
        p.completed_races,
        total_races,
        all_pts,
        idx,
        n,
    )
    remaining = max(0, total_races - (meeting.completed_races if meeting else p.completed_races))
    if p.completed_races == 0:
        projected = round(0.5 * total_races, 1) if total_races else 0.0
    else:
        avg_per_race = p.current_points / max(p.completed_races, 1)
        meeting_completed = meeting.completed_races if meeting else p.completed_races
        participation_rate = min(p.completed_races / max(meeting_completed, 1), 1.0)
        projected = round(p.current_points + avg_per_race * remaining * participation_rate, 1)
    return {
        "ai_price": ai_price,
        "win_probability": win_prob,
        "projected_final": projected,
        "remaining_rides": remaining,
    }


def _run_remaining_race_simulation(
    participants: List[Participant],
    meeting: Meeting,
    race_odds_by_pid: Dict[str, Dict[str, Dict[str, Any]]],
    n_simulations: int = AI_SIMULATIONS,
    margin: float = AI_PRICE_MARGIN,
) -> Dict[str, Dict[str, float]]:
    """Simulate only remaining races and combine with current locked points."""
    if not participants:
        return {}

    participant_payload = []
    for p in participants:
        participant_payload.append({
            "id": p.id,
            "name": p.name,
            "race_odds": race_odds_by_pid.get(p.id, {}),
        })

    total_races = meeting.total_races or 0
    completed_races = meeting.completed_races or 0

    # build_race_data_from_participants strips overround and prepares per-race runners
    if build_race_data_from_participants is None or simulate_race is None:
        return {}

    race_data = build_race_data_from_participants(participant_payload, total_races)
    remaining_race_data = {
        rn: runners for rn, runners in race_data.items()
        if rn > completed_races and len(runners) >= 3
    }

    names = [p.name for p in participants]
    current_points = {p.name: float(p.current_points or 0.0) for p in participants}
    name_to_pid = {p.name: p.id for p in participants}

    # If no future race odds are available, use current standings only.
    if not remaining_race_data:
        max_pts = max(current_points.values()) if current_points else 0.0
        leaders = [name for name, pts in current_points.items() if abs(pts - max_pts) < 0.01]
        share = 1.0 / max(len(leaders), 1)
        cal_power = 0.50
        result = {}
        for p in participants:
            prob = share if p.name in leaders and max_pts > 0 else (1.0 / max(len(participants), 2) if max_pts <= 0 else 0.0)
            prob = max(0.001, min(0.95, prob))
            cal_prob = calibrate_prob(prob, cal_power) if calibrate_prob is not None else prob ** cal_power
            ai_price = 1.0 / cal_prob if cal_prob > 0 else 100.0
            result[p.id] = {
                "ai_price": round(max(1.50, min(100.0, ai_price)), 2),
                "win_probability": round(prob * 100.0, 1),
                "projected_final": round(float(p.current_points or 0.0), 1),
                "remaining_rides": 0,
            }
        return result

    rng = random.Random(42 + int(completed_races) + len(participants) + total_races)
    win_counts: Dict[str, float] = defaultdict(float)
    final_points_sum: Dict[str, float] = defaultdict(float)

    for _ in range(max(1000, int(n_simulations))):
        sim_points = dict(current_points)
        for race_num in sorted(remaining_race_data.keys()):
            runners = remaining_race_data[race_num]
            winner, second, third = simulate_race(runners, rng)
            if winner:
                sim_points[winner["jockey"]] = sim_points.get(winner["jockey"], 0.0) + 3.0
            if second:
                sim_points[second["jockey"]] = sim_points.get(second["jockey"], 0.0) + 2.0
            if third:
                sim_points[third["jockey"]] = sim_points.get(third["jockey"], 0.0) + 1.0

        # Ensure participants with no remaining ride still exist in final points.
        for name in names:
            sim_points.setdefault(name, current_points.get(name, 0.0))

        max_pts = max(sim_points.values()) if sim_points else 0.0
        winners = [name for name, pts in sim_points.items() if name in name_to_pid and abs(pts - max_pts) < 0.01]
        share = 1.0 / max(len(winners), 1)
        for name in winners:
            win_counts[name] += share
        for name in names:
            final_points_sum[name] += sim_points.get(name, 0.0)

    total_runs = float(max(1000, int(n_simulations)))
    result: Dict[str, Dict[str, float]] = {}
    leader_points = max(current_points.values()) if current_points else 0.0

    cal_power = 0.50
    for p in participants:
        race_odds = race_odds_by_pid.get(p.id, {})
        remaining_rides = sum(1 for rn in race_odds.keys() if int(rn) > completed_races)
        max_possible = float(p.current_points or 0.0) + remaining_rides * 3.0

        # Mathematical elimination with actual remaining rides, not all remaining meeting races.
        if leader_points > 0 and max_possible < leader_points:
            prob = 0.01
        else:
            prob = win_counts.get(p.name, 0.0) / total_runs
            # Floor at 0.001 so no one exceeds $100 after calibration
            prob = max(0.001, min(0.95, prob))

        # Calibrated price: apply power compression, no margin needed
        if calibrate_prob is not None:
            cal_prob = calibrate_prob(prob, cal_power)
        else:
            cal_prob = prob ** cal_power
        ai_price = 1.0 / cal_prob if cal_prob > 0 else 100.0
        win_pct = round(prob * 100.0, 1)
        result[p.id] = {
            "ai_price": round(max(1.50, min(100.0, ai_price)), 2),
            "win_probability": win_pct,
            "projected_final": round(final_points_sum.get(p.name, p.current_points or 0.0) / total_runs, 1),
            "remaining_rides": int(remaining_rides),
        }

    return result


def _get_meeting_ai_model(db: Session, meeting: Optional[Meeting], participants: Optional[List[Participant]] = None) -> Dict[str, Dict[str, float]]:
    """Return AI model output for all participants in a meeting.

    Uses Monte Carlo if race_odds_json exists, otherwise falls back to old
    points-only model so API never breaks.
    """
    if not meeting:
        return {}
    if participants is None:
        participants = db.query(Participant).filter(Participant.meeting_id == meeting.id).all()
    if not participants:
        return {}

    race_odds_by_pid = _load_race_odds_by_participant(db, meeting.id)
    has_any_odds = any(bool(v) for v in race_odds_by_pid.values())

    if has_any_odds:
        try:
            mc = _run_remaining_race_simulation(participants, meeting, race_odds_by_pid)
            if mc:
                return mc
        except Exception as e:
            logger.warning(f"Monte Carlo AI model failed for {meeting.name}: {e}", exc_info=True)

    # Fallback: old points-only model
    sorted_ps = sorted(participants, key=lambda pp: (-pp.current_points, pp.name))
    all_pts = [pp.current_points for pp in sorted_ps]
    avg_idx_map = _compute_tied_indices(sorted_ps)
    fallback = {}
    for p in sorted_ps:
        fallback[p.id] = _fallback_projection(
            p,
            meeting,
            all_pts,
            avg_idx_map.get(p.id, 0),
            len(sorted_ps),
        )
    return fallback


def _remaining_rides_from_odds(db: Session, meeting: Meeting, participant_id: str) -> int:
    race_odds = _load_race_odds_by_participant(db, meeting.id).get(participant_id, {})
    if race_odds:
        return sum(1 for rn in race_odds.keys() if int(rn) > (meeting.completed_races or 0))
    return max(0, (meeting.total_races or 0) - (meeting.completed_races or 0))


def _race_input_probability_for_detail(
    race_odds_by_pid: Dict[str, Dict[str, Dict[str, Any]]],
    participant_id: str,
    race_num: int,
) -> tuple[Optional[float], Optional[float]]:
    """Approximate race win probability and expected 3-2-1 points for modal display."""
    entries = []
    for pid, race_odds in race_odds_by_pid.items():
        rd = race_odds.get(str(race_num))
        if not isinstance(rd, dict):
            continue
        odds = _safe_float(rd.get("odds"), 0.0)
        if odds > 0:
            entries.append((pid, odds, 1.0 / odds))
    total = sum(x[2] for x in entries)
    if total <= 0:
        return None, None
    for pid, odds, implied in entries:
        if pid == participant_id:
            win_prob = implied / total
            # Conservative expected-points estimate for display only.
            expected_points = win_prob * 3.0
            return round(win_prob * 100.0, 1), round(expected_points, 2)
    return None, None


# ---------------------------------------------------------------------------
# Frontend converters
# ---------------------------------------------------------------------------

def _meeting_type_value(meeting_or_value) -> str:
    val = meeting_or_value
    if hasattr(meeting_or_value, "type"):
        val = meeting_or_value.type
    if hasattr(val, "value"):
        return str(val.value).lower()
    return str(val).lower()

def _meeting_type_label(meeting_or_value) -> str:
    return "Jockey" if _meeting_type_value(meeting_or_value) == "jockey" else "Driver"

def _meeting_to_frontend(meeting: Meeting, db: Session,
                          _participants: Optional[List[Participant]] = None,
                          _results: Optional[List[Result]] = None,
                          _participant_map: Optional[dict] = None,
                          _ai_model: Optional[dict] = None) -> MeetingOut:
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

    if _ai_model is None:
        _ai_model = _get_meeting_ai_model(db, meeting, participants)

    projected = ""
    if participants and _ai_model:
        best = max(participants, key=lambda p: _ai_model.get(p.id, {}).get("win_probability", 0.0))
        projected = best.name if best else ""
    elif sorted_ps and meeting.completed_races > 0:
        projected = sorted_ps[0].name

    status_map = {
        MeetingStatus.UPCOMING.value: "Not Started",
        MeetingStatus.LIVE.value: "Live",
        MeetingStatus.FINISHED.value: "Completed",
    }

    return MeetingOut(
        id=meeting.id,
        name=meeting.name,
        type=_meeting_type_label(meeting),
        status=status_map.get(meeting.status, "Not Started"),
        completedRaces=meeting.completed_races,
        totalRaces=meeting.total_races,
        leaderboard=leaderboard,
        latestUpdates=latest_updates,
        projectedWinner=projected,
        scheduledTime=meeting.scheduled_time.isoformat() if meeting.scheduled_time else None,
    )

def _get_tabtouch_price(db: Session, participant_id: str) -> Optional[float]:
    price_row = db.query(Price).filter(
        Price.participant_id == participant_id,
        Price.bookmaker_name == "TABtouch_PreRace",
    ).first()
    if price_row:
        return price_row.price
    return None


def _participant_to_frontend_with_data(
    p: Participant,
    meeting: Optional[Meeting],
    all_participant_points: Optional[List[float]] = None,
    is_projected_winner: bool = False,
    participant_index: Optional[int] = None,
    total_participants: Optional[int] = None,
    db: Optional[Session] = None,
    ai_model: Optional[dict] = None,
) -> ParticipantOut:
    total_races = meeting.total_races if meeting else 8

    model_row = ai_model.get(p.id) if ai_model else None
    if model_row:
        ai_price = float(model_row.get("ai_price", 100.0))
        win_prob = float(model_row.get("win_probability", 0.0))
        projected = float(model_row.get("projected_final", p.current_points or 0.0))
    else:
        ai_price, win_prob = _compute_ai_price(
            p.current_points, p.completed_races, total_races, all_participant_points,
            participant_index, total_participants
        )
        fallback = _fallback_projection(p, meeting, all_participant_points, participant_index, total_participants)
        projected = fallback["projected_final"]

    tabtouch_price = _get_tabtouch_price(db, p.id) if db else None

    return ParticipantOut(
        id=p.id, name=p.name, meetingName=meeting.name if meeting else "", meetingId=p.meeting_id,
        aiPrice=round(ai_price, 2), winProbability=round(win_prob, 1),
        currentPoints=p.current_points, projectedFinalPoints=round(projected, 1),
        isProjectedWinner=is_projected_winner,
        tabtouchPrice=tabtouch_price,
    )


def _participant_to_frontend(
    p: Participant,
    db: Session,
    all_participant_points: Optional[List[float]] = None,
    is_projected_winner: bool = False,
    participant_index: Optional[int] = None,
    total_participants: Optional[int] = None,
    ai_model: Optional[dict] = None,
) -> ParticipantOut:
    meeting = db.query(Meeting).filter(Meeting.id == p.meeting_id).first()
    if ai_model is None and meeting is not None:
        parts = db.query(Participant).filter(Participant.meeting_id == meeting.id).all()
        ai_model = _get_meeting_ai_model(db, meeting, parts)
    return _participant_to_frontend_with_data(
        p,
        meeting,
        all_participant_points,
        is_projected_winner,
        participant_index,
        total_participants,
        db,
        ai_model,
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
    avg_idx_map = _compute_tied_indices(participants)
    ai_model = _get_meeting_ai_model(db, meeting, participants)

    result = []
    for p in participants:
        fp = _participant_to_frontend(
            p,
            db,
            all_pts,
            participant_index=avg_idx_map.get(p.id, 0),
            total_participants=len(participants),
            ai_model=ai_model,
        )
        result.append(fp)

    # Client asked for shortest price to longest price.
    result.sort(key=lambda x: (x.aiPrice, -x.winProbability, x.name))
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
    all_parts.sort(key=lambda p: (-p.current_points, p.name))

    ai_model = _get_meeting_ai_model(db, meeting, all_parts)
    model_row = ai_model.get(participant.id, {})

    total_races = meeting.total_races or 8
    ai_price = float(model_row.get("ai_price", 100.0)) if model_row else _compute_ai_price(
        participant.current_points, participant.completed_races, total_races
    )[0]
    win_prob = float(model_row.get("win_probability", 0.0)) if model_row else _compute_ai_price(
        participant.current_points, participant.completed_races, total_races
    )[1]
    projected = float(model_row.get("projected_final", participant.current_points or 0.0)) if model_row else participant.current_points or 0.0

    existing_results = db.query(Result).filter(
        Result.meeting_id == meeting_id,
        Result.participant_id == participant_id,
    ).all()
    results_map = {r.race_number: r for r in existing_results}

    # Load all participants' actual declared rides/drives from Price.race_odds_json.
    # These are race runner odds used as AI inputs, not true bookmaker challenge prices.
    race_odds_by_pid = _load_race_odds_by_participant(db, meeting_id)
    race_odds_map = race_odds_by_pid.get(participant_id, {})

    completed_cutoff = meeting.completed_races or 0
    remaining = int(model_row.get("remaining_rides", 0)) if model_row else sum(
        1 for rn in race_odds_map.keys() if int(rn) > completed_cutoff
    )

    rides = []
    race_nums = sorted({int(k) for k in race_odds_map.keys()} | set(results_map.keys()))
    for race_num in race_nums:
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
        elif race_num <= completed_cutoff:
            status = "Completed"
        else:
            status = "Upcoming"

        ride_odds_info = race_odds_map.get(str(race_num), {})
        horse_name = ride_odds_info.get("horse", "") or ""
        race_odds_val = _safe_float(ride_odds_info.get("odds"), 0.0)
        race_odds_val = race_odds_val if race_odds_val > 0 else None

        race_win_prob, race_expected_pts = _race_input_probability_for_detail(
            race_odds_by_pid, participant_id, race_num
        )

        rides.append(RideDetail(
            raceNumber=race_num,
            horseName=horse_name,
            raceOdds=race_odds_val,
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
        meetingType=_meeting_type_value(meeting),
        currentPoints=participant.current_points,
        projectedFinalPoints=round(projected, 1),
        projectedAdditionalPoints=round(projected - (participant.current_points or 0.0), 1),
        aiPrice=round(ai_price, 2),
        winProbability=round(win_prob, 1),
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

    ai_models_by_meeting = {}
    for m in meetings:
        mtg_participants = participants_by_meeting.get(m.id, [])
        ai_models_by_meeting[m.id] = _get_meeting_ai_model(db, m, mtg_participants)

    frontend_meetings = []
    for m in meetings:
        mtg_participants = participants_by_meeting.get(m.id, [])
        mtg_results = (results_by_meeting.get(m.id, [])[:5])
        frontend_meetings.append(_meeting_to_frontend(
            m, db,
            _participants=mtg_participants,
            _results=mtg_results,
            _participant_map=participant_map,
            _ai_model=ai_models_by_meeting.get(m.id),
        ))

    jockeys = []
    drivers = []

    for p in all_participants:
        meeting = meeting_map.get(p.meeting_id)
        mtg_parts = participants_by_meeting.get(p.meeting_id, [])
        mtg_parts.sort(key=lambda pp: (-pp.current_points, pp.name))
        all_pts = [pp.current_points for pp in mtg_parts]
        avg_idx_map = _compute_tied_indices(mtg_parts)
        p_idx = avg_idx_map.get(p.id, 0)
        fp = _participant_to_frontend_with_data(
            p,
            meeting,
            all_pts,
            participant_index=p_idx,
            total_participants=len(mtg_parts),
            db=db,
            ai_model=ai_models_by_meeting.get(p.meeting_id),
        )
        if meeting and _meeting_type_value(meeting) == "jockey":
            jockeys.append(fp)
        else:
            drivers.append(fp)

    # Sort by meeting then shortest AI price first.
    jockeys.sort(key=lambda x: (x.meetingName, x.aiPrice, -x.winProbability, x.name))
    drivers.sort(key=lambda x: (x.meetingName, x.aiPrice, -x.winProbability, x.name))

    # Mark projected winners per meeting by highest AI win probability, even pre-match.
    meeting_best = {}
    for fp in jockeys + drivers:
        if fp.meetingId not in meeting_best or fp.winProbability > meeting_best[fp.meetingId].winProbability:
            meeting_best[fp.meetingId] = fp
    for fp in meeting_best.values():
        fp.isProjectedWinner = True

    race_results = []
    for r in (sorted(all_results, key=lambda x: x.timestamp or datetime.now(timezone.utc), reverse=True)[:30]):
        p = participant_map.get(r.participant_id)
        m = meeting_map.get(r.meeting_id)
        if p and m:
            model_row = ai_models_by_meeting.get(m.id, {}).get(p.id, {})
            ai_price = model_row.get("ai_price")
            if ai_price is None:
                mtg_parts = participants_by_meeting.get(m.id, [])
                mtg_parts_s = sorted(mtg_parts, key=lambda pp: (-pp.current_points, pp.name))
                all_pts = [pp.current_points for pp in mtg_parts_s]
                avg_idx = _compute_tied_indices(mtg_parts_s)
                ai_price, _ = _compute_ai_price(p.current_points, p.completed_races, m.total_races, all_pts, avg_idx.get(p.id, 0), len(all_pts))

            minutes_ago = int(
                (datetime.now(timezone.utc) - (r.timestamp if r.timestamp and r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc))).total_seconds() / 60
            ) if r.timestamp else 0

            race_results.append(RaceResultOut(
                id=f"r{r.id}",
                meetingName=m.name,
                raceNumber=r.race_number,
                participant=p.name,
                pointsAdded=r.points_added,
                updatedAiPrice=round(float(ai_price), 2),
                timeUpdated=f"{max(1, minutes_ago)}m ago",
                type=_meeting_type_label(m),
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
    with commit_lock:
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
            with commit_lock:
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
    ai_model = _get_meeting_ai_model(db, meeting, participants)

    predictions = []
    for p in participants:
        model_row = ai_model.get(p.id, {})
        remaining = int(model_row.get("remaining_rides", _remaining_rides_from_odds(db, meeting, p.id)))
        predictions.append({
            "id": p.id,
            "name": p.name,
            "currentPoints": p.current_points,
            "completedRaces": p.completed_races,
            "remainingRaces": remaining,
            "winProbability": round(float(model_row.get("win_probability", 0.0)), 1),
            "estimatedFinalPoints": round(float(model_row.get("projected_final", p.current_points or 0.0)), 1),
            "aiPrice": round(float(model_row.get("ai_price", 100.0)), 2),
        })

    # Highest win probability first; this also gives a projected winner before Race 1.
    predictions.sort(key=lambda x: (-x["winProbability"], x["aiPrice"], x["name"]))

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
    with commit_lock:
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
    with commit_lock:
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
    with commit_lock:
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


@router.post("/admin/pull-prerace")
def pull_prerace(db: Session = Depends(get_db)):
    """Admin endpoint to pull pre-race TABtouch odds."""
    from scrapers.tabtouch_prerace import pull_all_prerace_for_today

    total = pull_all_prerace_for_today(db)

    return {
        "status": "success",
        "prices_inserted": total
    }
