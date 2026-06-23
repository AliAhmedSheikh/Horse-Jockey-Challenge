"""Points calculator: update participant points from Result records.

Responsibilities:
- Recalculate current_points, completed_races, remaining_races for all participants
- Based solely on DB Result records (source of truth)
- Runs after results_ingestor to ensure points are up to date

This is separated from status_updater because:
- Status transitions are time-based (check scheduled_time)
- Points are result-based (check Result table)
- They can run at different frequencies if needed
"""
import logging
from datetime import datetime, timezone

from database import SessionLocal, commit_lock
from models import Meeting, Participant, Result, MeetingStatus
from db_writer import update_participant_points

logger = logging.getLogger(__name__)


def recalculate_all_points():
    """Recalculate points for all LIVE and UPCOMING meetings.

    Called after results_ingestor. Reads Result table and updates
    participant aggregates.
    """
    db = SessionLocal()

    try:
        meetings = db.query(Meeting).filter(
            Meeting.status.in_([
                MeetingStatus.LIVE.value,
                MeetingStatus.UPCOMING.value,
            ])
        ).all()

        for meeting in meetings:
            _recalculate_meeting_points(db, meeting)

        with commit_lock:
            db.commit()
    except Exception as e:
        logger.error(f"Points calculation failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def _recalculate_meeting_points(db, meeting):
    """Recalculate points for all participants in a meeting."""
    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting.id
    ).all()

    updates = []
    for p in participants:
        # Get all results for this participant, ordered by race_number
        results = db.query(Result).filter(
            Result.participant_id == p.id,
            Result.meeting_id == meeting.id,
        ).order_by(Result.race_number).all()

        total_points = sum(r.points_added for r in results)
        completed = len(set(r.race_number for r in results))
        remaining = meeting.total_races - completed

        updates.append({
            "participant_id": p.id,
            "current_points": total_points,
            "completed_races": completed,
            "remaining_races": remaining,
        })

    if updates:
        update_participant_points(meeting.id, updates)
