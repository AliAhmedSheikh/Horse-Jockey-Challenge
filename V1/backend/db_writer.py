"""Single writer pattern for database operations.

All DB writes go through a serialized queue to prevent race conditions
from concurrent jobs (status_updater, results_ingestor, scraper).

Reads are still allowed concurrently via SQLAlchemy session-per-request.
"""
import threading
import queue
import logging
from typing import Callable, Any, Optional
from database import SessionLocal

logger = logging.getLogger(__name__)

# Command queue for serialized writes
_write_queue: queue.Queue = queue.Queue()
_writer_thread: Optional[threading.Thread] = None
_writer_lock = threading.Lock()
_running = True


def _writer_loop():
    """Background thread that processes DB write commands sequentially."""
    global _running
    while _running:
        try:
            cmd, args, kwargs, result_event, result_container = _write_queue.get(timeout=1)
        except queue.Empty:
            continue

        db = SessionLocal()
        try:
            result = cmd(db, *args, **kwargs)
            result_container["result"] = result
            result_container["error"] = None
        except Exception as e:
            result_container["result"] = None
            result_container["error"] = e
            logger.error(f"DB write failed: {e}", exc_info=True)
        finally:
            try:
                db.close()
            except Exception:
                pass
            result_event.set()


def start_writer():
    """Start the background writer thread."""
    global _writer_thread, _running
    with _writer_lock:
        if _writer_thread is None or not _writer_thread.is_alive():
            _running = True
            _writer_thread = threading.Thread(target=_writer_loop, daemon=True, name="db-writer")
            _writer_thread.start()
            logger.info("DB writer thread started")


def stop_writer():
    """Stop the background writer thread."""
    global _running
    _running = False


def write_sync(func: Callable, *args, **kwargs) -> Any:
    """Submit a write operation and wait for result.

    Usage:
        def do_write(db, meeting_id, status):
            db.query(Meeting).filter(Meeting.id == meeting_id).update({"status": status})
            db.commit()

        write_sync(do_write, "m1", "FINISHED")
    """
    start_writer()
    result_event = threading.Event()
    result_container = {"result": None, "error": None}
    _write_queue.put((func, args, kwargs, result_event, result_container))
    result_event.wait(timeout=30)

    if result_container["error"]:
        raise result_container["error"]
    return result_container["result"]


def write_async(func: Callable, *args, **kwargs):
    """Submit a write operation without waiting for result (fire-and-forget)."""
    start_writer()
    result_event = threading.Event()
    result_container = {"result": None, "error": None}
    _write_queue.put((func, args, kwargs, result_event, result_container))


# ---- Common write operations ----

def update_meeting_status(meeting_id: str, status: str, completed_races: int = None):
    """Update meeting status atomically."""
    def _do(db, mid, st, cr):
        from models import Meeting
        update = {"status": st, "updated_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc)}
        if cr is not None:
            update["completed_races"] = cr
        db.query(Meeting).filter(Meeting.id == mid).update(update)
        db.commit()
    write_sync(_do, meeting_id, status, completed_races)


def upsert_result(meeting_id: str, participant_id: str, race_number: int,
                  position: int, points_added: float, final_points: float):
    """Insert or update a result record atomically."""
    def _do(db, mid, pid, rn, pos, pa, fp):
        from models import Result
        from datetime import datetime, timezone
        existing = db.query(Result).filter(
            Result.meeting_id == mid,
            Result.participant_id == pid,
            Result.race_number == rn,
        ).first()
        if existing:
            existing.position = pos
            existing.points_added = pa
            existing.final_points = fp
            existing.timestamp = datetime.now(timezone.utc)
        else:
            db.add(Result(
                meeting_id=mid, participant_id=pid, race_number=rn,
                position=pos, points_added=pa, final_points=fp,
                timestamp=datetime.now(timezone.utc),
            ))
        db.commit()
    write_sync(_do, meeting_id, participant_id, race_number, position, points_added, final_points)


def batch_upsert_results(results: list):
    """Insert multiple results atomically in one transaction.

    results: list of dicts with keys:
        meeting_id, participant_id, race_number, position, points_added, final_points
    """
    def _do(db, res_list):
        from models import Result
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for r in res_list:
            existing = db.query(Result).filter(
                Result.meeting_id == r["meeting_id"],
                Result.participant_id == r["participant_id"],
                Result.race_number == r["race_number"],
            ).first()
            if existing:
                existing.position = r["position"]
                existing.points_added = r["points_added"]
                existing.final_points = r["final_points"]
                existing.timestamp = now
            else:
                db.add(Result(
                    meeting_id=r["meeting_id"],
                    participant_id=r["participant_id"],
                    race_number=r["race_number"],
                    position=r["position"],
                    points_added=r["points_added"],
                    final_points=r["final_points"],
                    timestamp=now,
                ))
        db.commit()
    write_sync(_do, results)


def update_participant_points(meeting_id: str, updates: list):
    """Batch update participant points atomically.

    updates: list of dicts with keys:
        participant_id, current_points, completed_races, remaining_races
    """
    def _do(db, mid, upd_list):
        from models import Participant
        for u in upd_list:
            db.query(Participant).filter(
                Participant.id == u["participant_id"],
                Participant.meeting_id == mid,
            ).update({
                "current_points": u["current_points"],
                "completed_races": u["completed_races"],
                "remaining_races": u["remaining_races"],
            })
        db.commit()
    write_sync(_do, meeting_id, updates)


def upsert_price(participant_id: str, meeting_id: str, bookmaker_name: str,
                 price: float, race_odds_json: str = None):
    """Insert or update a price record atomically."""
    def _do(db, pid, mid, bm, pr, roj):
        from models import Price
        from datetime import datetime, timezone
        existing = db.query(Price).filter(
            Price.participant_id == pid,
            Price.bookmaker_name == bm,
        ).first()
        if existing:
            existing.price = pr
            if roj:
                existing.race_odds_json = roj
            existing.timestamp = datetime.now(timezone.utc)
        else:
            db.add(Price(
                participant_id=pid, meeting_id=mid,
                bookmaker_name=bm, price=pr,
                race_odds_json=roj,
                timestamp=datetime.now(timezone.utc),
            ))
        db.commit()
    write_sync(_do, participant_id, meeting_id, bookmaker_name, price, race_odds_json)
