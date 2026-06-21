"""Status updater: handles meeting state transitions.

Responsibilities:
- UPCOMING → LIVE (when scheduled time reached or API shows race 1 complete)
- LIVE → UPCOMING (revert if scheduled time not yet reached and no API results)
- Auto-finish when all races complete
- One-time repair of FINISHED meetings with incomplete results

Does NOT fetch race results or calculate points — that's results_ingestor's job.
"""
import logging
import threading
from datetime import datetime, timezone, timedelta

from database import SessionLocal
from models import Meeting, Participant, Result, MeetingStatus
from time_utils import AU_TZ, today_aus
from resolvers import MeetingResolver, RaceResolver

logger = logging.getLogger(__name__)

# Track meetings we've already repaired to avoid repeated resets
_already_repaired = set()

# Lock to prevent concurrent auto-seed calls
_seed_lock = threading.Lock()


def update_meeting_statuses():
    """Check all meetings and update their status based on time and race progress.

    This is a READ-heavy operation — it checks times and existing results
    but does NOT fetch from external APIs or write new results.
    """
    now_aus = datetime.now(AU_TZ)
    db = SessionLocal()

    try:
        # Auto-seed if no meetings exist for today
        today = today_aus()
        today_count = db.query(Meeting).filter(Meeting.date == today).count()
        if today_count == 0:
            if _seed_lock.acquire(blocking=False):
                try:
                    logger.info("No meetings for today — running auto-seed")
                    from seed_data import seed_database
                    seed_database(db)
                finally:
                    _seed_lock.release()
            else:
                logger.info("Auto-seed already in progress, skipping")

        meetings = db.query(Meeting).all()
        resolver = MeetingResolver(db)
        race_resolver = RaceResolver(db)

        for meeting in meetings:
            _update_single_meeting(db, meeting, now_aus, race_resolver)

        db.commit()
    except Exception as e:
        logger.error(f"Status update failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def _update_single_meeting(db, meeting, now_aus, race_resolver):
    """Update status for a single meeting."""
    st = meeting.scheduled_time
    if st is not None and st.tzinfo is None:
        st = st.replace(tzinfo=AU_TZ)
    scheduled_reached = st is not None and now_aus >= st

    if meeting.status == MeetingStatus.UPCOMING.value:
        _handle_upcoming(db, meeting, scheduled_reached, st, race_resolver)

    elif meeting.status == MeetingStatus.LIVE.value:
        _handle_live(db, meeting, scheduled_reached, st, race_resolver)

    elif meeting.status in (MeetingStatus.FINISHED.value, "Completed"):
        _handle_finished_repair(db, meeting)


def _handle_upcoming(db, meeting, scheduled_reached, st, race_resolver):
    """Handle UPCOMING meeting transitions."""
    if scheduled_reached or (not meeting.scheduled_time and meeting.completed_races > 0):
        meeting.status = MeetingStatus.LIVE.value
        if meeting.completed_races == 0:
            meeting.completed_races = 0
        logger.info(f"Meeting {meeting.name} -> LIVE")


def _handle_live(db, meeting, scheduled_reached, st, race_resolver):
    """Handle LIVE meeting — check if it should revert or finish."""
    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting.id
    ).all()
    n = len(participants)
    if n == 0:
        return

    # Revert LIVE→UPCOMING if scheduled time hasn't arrived yet
    # Only check if meeting was recently transitioned (within 5 min) —
    # skip the expensive API call for meetings that have been LIVE for a while
    api_shows_results = False
    if st is not None and not scheduled_reached and not meeting.id.startswith("dyn_"):
        # If meeting has completed races or was created more than 5 min ago, skip revert check
        if meeting.completed_races > 0:
            pass
        elif meeting.created_at:
            age_minutes = (datetime.now(timezone.utc) - meeting.created_at).total_seconds() / 60
            if age_minutes < 5:
                from scrapers.base import fetch_single_race_results
                race_data = fetch_single_race_results(meeting.name, 1)
                api_shows_results = race_data and race_data.get("status") in ("Final", "Interim")
    if st is not None and not scheduled_reached and not api_shows_results and meeting.completed_races == 0:
        meeting.status = MeetingStatus.UPCOMING.value
        for p in participants:
            p.current_points = 0
            p.completed_races = 0
            p.remaining_races = meeting.total_races
        db.query(Result).filter(Result.meeting_id == meeting.id).delete()
        logger.info(f"Meeting {meeting.name} -> UPCOMING (reverted)")
        return

    # Recalculate participant state from confirmed Results
    _recalculate_participant_state(db, meeting, participants)

    # Check if all races are done
    next_race = meeting.completed_races + 1
    if next_race > meeting.total_races:
        meeting.status = MeetingStatus.FINISHED.value
        for p in participants:
            p.remaining_races = 0
        logger.info(f"Meeting {meeting.name} -> FINISHED")

    # Auto-finish if last race results already exist
    if next_race == meeting.total_races:
        last_race_results = db.query(Result).filter(
            Result.meeting_id == meeting.id,
            Result.race_number == next_race,
        ).count()
        if last_race_results > 0:
            meeting.status = MeetingStatus.FINISHED.value
            for p in participants:
                p.remaining_races = 0
            logger.info(f"Meeting {meeting.name} -> FINISHED (last race results exist)")


def _recalculate_participant_state(db, meeting, participants):
    """Recalculate participant points/completed from DB Results table."""
    max_race = db.query(Result.race_number).filter(
        Result.meeting_id == meeting.id,
    ).order_by(Result.race_number.desc()).first()
    if max_race:
        meeting.completed_races = max_race[0]
    next_race = meeting.completed_races + 1
    for p in participants:
        prev_results = db.query(Result).filter(
            Result.participant_id == p.id,
            Result.race_number < next_race,
        ).all()
        p.current_points = sum(r.points_added for r in prev_results)
        p.completed_races = len(set(r.race_number for r in prev_results))
        p.remaining_races = meeting.total_races - p.completed_races


def _handle_finished_repair(db, meeting):
    """One-time repair: reset FINISHED meetings with incomplete results."""
    if meeting.id in _already_repaired:
        return

    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting.id
    ).all()
    if not participants or len(participants) < 3:
        return

    participants_with_results = db.query(Result.participant_id).filter(
        Result.meeting_id == meeting.id,
    ).distinct().count()

    result_count = db.query(Result).filter(
        Result.meeting_id == meeting.id,
    ).count()

    participant_ratio = participants_with_results / len(participants) if participants else 0
    result_ratio = result_count / len(participants) if participants else 0

    if participant_ratio < 0.5 or (meeting.total_races > 3 and result_ratio < 2):
        logger.info(
            f"Repair: {meeting.name} has {participants_with_results}/{len(participants)} "
            f"participants with results, {result_count} total — resetting"
        )
        db.query(Result).filter(Result.meeting_id == meeting.id).delete()
        for p in participants:
            p.current_points = 0
            p.completed_races = 0
            p.remaining_races = meeting.total_races
        meeting.completed_races = 0
        meeting.status = MeetingStatus.LIVE.value
        _already_repaired.add(meeting.id)
        db.commit()
    else:
        _already_repaired.add(meeting.id)
