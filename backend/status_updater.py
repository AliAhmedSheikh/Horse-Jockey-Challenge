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
from models import Meeting, Participant, Result, MeetingStatus, Price, Bet
from time_utils import AU_TZ, today_aus
from resolvers import MeetingResolver, RaceResolver

logger = logging.getLogger(__name__)

# Track meetings we've already repaired to avoid repeated resets
_already_repaired = set()

# Lock to prevent concurrent auto-seed calls
_seed_lock = threading.Lock()
_last_seed_time = None
_SEED_COOLDOWN = 3600  # Re-seed every hour to pick up new meetings (e.g. driver challenges appearing later)


def update_meeting_statuses():
    """Check all meetings and update their status based on time and race progress.

    This is a READ-heavy operation — it checks times and existing results
    but does NOT fetch from external APIs or write new results.
    """
    now_aus = datetime.now(AU_TZ)
    db = SessionLocal()

    try:
        today = today_aus()

        # Cleanup: remove meetings from previous days entirely
        _cleanup_old_meetings(db, today)

        # Auto-seed if no meetings exist for today, or periodically to pick up new ones
        global _last_seed_time
        today_count = db.query(Meeting).filter(Meeting.date == today).count()
        should_seed = today_count == 0
        if not should_seed and _last_seed_time is not None:
            elapsed = (now_aus - _last_seed_time).total_seconds()
            if elapsed > _SEED_COOLDOWN:
                should_seed = True
        if not should_seed and _last_seed_time is None:
            should_seed = True

        if should_seed:
            if _seed_lock.acquire(blocking=False):
                try:
                    logger.info("Running auto-seed to discover meetings")
                    from seed_data import seed_database
                    seed_database(db)
                    _last_seed_time = now_aus
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


def _cleanup_old_meetings(db, today):
    """Delete completed/old meetings so they don't clutter the UI."""
    old_meetings = db.query(Meeting).filter(Meeting.date < today).all()
    finished_today = db.query(Meeting).filter(
        Meeting.date == today,
        Meeting.status == MeetingStatus.FINISHED.value,
    ).all()
    # Also clean stale meetings: all races done but still marked UPCOMING (jockey only)
    # Driver meetings default to 17:30 but may have stale API results — don't delete them
    stale_completed = db.query(Meeting).filter(
        Meeting.date == today,
        Meeting.status == MeetingStatus.UPCOMING.value,
        Meeting.completed_races >= Meeting.total_races,
        Meeting.total_races > 0,
        Meeting.type == "jockey",
    ).all()
    # Also clean LIVE driver meetings with all races done (stale from yesterday's API)
    stale_live_drivers = db.query(Meeting).filter(
        Meeting.date == today,
        Meeting.status == MeetingStatus.LIVE.value,
        Meeting.completed_races >= Meeting.total_races,
        Meeting.total_races > 0,
        Meeting.type == "driver",
    ).all()
    to_delete = old_meetings + finished_today + stale_completed + stale_live_drivers
    if to_delete:
        for m in to_delete:
            mid = m.id
            db.query(Bet).filter(Bet.meeting_id == mid).delete(synchronize_session="fetch")
            db.query(Price).filter(Price.meeting_id == mid).delete(synchronize_session="fetch")
            db.query(Result).filter(Result.meeting_id == mid).delete(synchronize_session="fetch")
            db.query(Participant).filter(Participant.meeting_id == mid).delete(synchronize_session="fetch")
            db.delete(m)
        logger.info(f"Cleaned up {len(to_delete)} old/finished meeting(s)")
        db.commit()


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
    if scheduled_reached or meeting.completed_races > 0:
        meeting.status = MeetingStatus.LIVE.value
        logger.info(f"Meeting {meeting.name} -> LIVE (scheduled={scheduled_reached}, completed={meeting.completed_races})")


def _handle_live(db, meeting, scheduled_reached, st, race_resolver):
    """Handle LIVE meeting — check if it should revert or finish."""
    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting.id
    ).all()
    n = len(participants)
    if n == 0:
        return

    # Force-finish stale LIVE meetings
    # Use updated_at (when status changed to LIVE) rather than created_at
    # to avoid immediately killing meetings that just transitioned from UPCOMING
    reference_time = meeting.updated_at or meeting.created_at
    if reference_time:
        ref = reference_time
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - ref).total_seconds() / 60
        # Stale if >30 min old with no progress at all
        if age_minutes > 30 and meeting.completed_races == 0:
            meeting.status = MeetingStatus.FINISHED.value
            for p in participants:
                p.remaining_races = 0
            logger.info(f"Meeting {meeting.name} -> FINISHED (stale: {age_minutes:.0f}min, no progress)")
            return
        # Also stale if >60 min old with partial progress (stuck mid-meeting)
        if age_minutes > 60 and meeting.completed_races > 0 and meeting.completed_races < meeting.total_races:
            meeting.status = MeetingStatus.FINISHED.value
            for p in participants:
                p.remaining_races = meeting.total_races - p.completed_races
            logger.info(f"Meeting {meeting.name} -> FINISHED (stale: {age_minutes:.0f}min, stuck at {meeting.completed_races}/{meeting.total_races})")
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
            created = meeting.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - created).total_seconds() / 60
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
