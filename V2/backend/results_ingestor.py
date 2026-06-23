"""Results ingestor: fetch race results from APIs and create Result records.

Responsibilities:
- For each LIVE meeting, fetch the next race's results from Ladbrokes API
- Match API jockey/driver names to DB participants
- Create Result records for placed and declared participants
- Skip races that aren't ready yet (non-Final status)
- Auto-finish meetings when API has no more race data
- NEVER generate fake/simulated results

Uses:
- Race-level cache to avoid redundant API calls
- Global thread pool for concurrent fetches
- db_writer for atomic batch inserts
"""
import json
import logging
import time
from datetime import datetime, timezone

from database import SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus
from resolvers import ParticipantResolver, RaceResolver
from scrapers.base import fetch_single_race_results
from scrapers.shared import get_race_cache, set_race_cache
from utils import race_points, names_match, names_lastname_fallback
from seed_data import _get_real_race_positions

logger = logging.getLogger(__name__)

# Track consecutive API misses per meeting to auto-finish stale meetings
_api_miss_counts = {}
_AUTO_FINISH_THRESHOLD = 6


def ingest_race_results():
    """Process one race per LIVE meeting.

    Called every 30s by the scheduler. For each LIVE meeting:
    1. Determine next race number
    2. Fetch results from Ladbrokes API (with cache)
    3. Match jockey names to DB participants
    4. Create Result records atomically
    """
    db = SessionLocal()

    try:
        meetings = db.query(Meeting).filter(
            Meeting.status.in_([MeetingStatus.LIVE.value])
        ).all()

        if not meetings:
            return

        race_resolver = RaceResolver(db)
        participant_resolver = ParticipantResolver(db)

        for meeting in meetings:
            _process_meeting_race(db, meeting, race_resolver, participant_resolver)

    except Exception as e:
        logger.error(f"Results ingest failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def _process_meeting_race(db, meeting, race_resolver, participant_resolver):
    """Fetch and process results for the next race of a meeting."""
    participants = db.query(Participant).filter(
        Participant.meeting_id == meeting.id
    ).all()
    if not participants:
        return

    # Auto-correct total_races from API if we can
    _maybe_update_race_count(meeting)

    next_race = race_resolver.get_next_race(meeting.id, meeting.total_races)
    if next_race is None:
        # All races complete — status_updater will handle FINISHED transition
        return

    # Check if race already has results (idempotency)
    if race_resolver.is_race_complete(meeting.id, next_race):
        meeting.completed_races = max(meeting.completed_races, next_race)
        return

    # Check race-level cache first
    cached = get_race_cache("ladbrokes", meeting.name, next_race)
    if cached:
        race_data = cached
    else:
        race_data = fetch_single_race_results(meeting.name, next_race)
        if race_data is None:
            # Track consecutive misses — auto-finish if too many
            _api_miss_counts[meeting.id] = _api_miss_counts.get(meeting.id, 0) + 1
            if _api_miss_counts[meeting.id] >= _AUTO_FINISH_THRESHOLD and meeting.completed_races > 0:
                logger.info(
                    f"Meeting {meeting.name}: {meeting.completed_races}/{meeting.total_races} races "
                    f"completed, {_api_miss_counts[meeting.id]} consecutive API misses — auto-finishing"
                )
                meeting.status = MeetingStatus.FINISHED.value
                for p in participants:
                    p.remaining_races = 0
                _api_miss_counts.pop(meeting.id, None)
                return
            logger.warning(
                f"Meeting {meeting.name} - Race {next_race}: "
                f"API returned no data, skipping (retry next cycle, "
                f"miss {_api_miss_counts.get(meeting.id, 0)}/{_AUTO_FINISH_THRESHOLD})"
            )
            return
        set_race_cache("ladbrokes", meeting.name, next_race, race_data)
    _api_miss_counts.pop(meeting.id, None)

    # Check race status
    status = race_data.get("status", "")
    if status in ("Abandoned", "Scratched", "Washout"):
        logger.info(
            f"Meeting {meeting.name} - Race {next_race} "
            f"status='{status}' — skipping (0 pts for all)"
        )
        for p in participants:
            existing = db.query(Result).filter(
                Result.meeting_id == meeting.id,
                Result.participant_id == p.id,
                Result.race_number == next_race,
            ).first()
            if not existing:
                db.add(Result(
                    meeting_id=meeting.id,
                    participant_id=p.id,
                    race_number=next_race,
                    position=99,
                    points_added=0,
                    final_points=0,
                    timestamp=datetime.now(timezone.utc),
                ))
        meeting.completed_races = next_race
        for attempt in range(5):
            try:
                db.commit()
                break
            except Exception as e:
                if "database is locked" in str(e) and attempt < 4:
                    db.rollback()
                    time.sleep(1)
                else:
                    raise
        return
    if status not in ("Final", "Interim", "Closed", "Results"):
        logger.info(
            f"Meeting {meeting.name} - Race {next_race} not ready "
            f"(status='{status}', waiting)"
        )
        return

    # Delete existing results for this race to handle re-runs
    db.query(Result).filter(
        Result.meeting_id == meeting.id,
        Result.race_number == next_race,
    ).delete()

    # Match API results to DB participants
    pids = [p.id for p in participants]
    price_rows = db.query(Price).filter(
        Price.participant_id.in_(pids),
        Price.bookmaker_name == "Ladbrokes",
    ).all()
    price_map = {pr.participant_id: pr.price for pr in price_rows}

    real_positions = _get_real_race_positions(race_data, participants, price_map)

    results_batch = []
    placed_ids = set()
    all_matched_pids = set()

    if real_positions:
        race_positions = [pos for _, pos in real_positions]
        for p, pos in real_positions:
            added = race_points(pos, race_positions)
            placed_ids.add(p.id)
            all_matched_pids.add(p.id)
            results_batch.append({
                "meeting_id": meeting.id,
                "participant_id": p.id,
                "race_number": next_race,
                "position": pos,
                "points_added": added,
                "final_points": 0,  # Will be calculated by points_calculator
            })

    if real_positions:
        for p2, _ in real_positions:
            all_matched_pids.add(p2.id)

    # Determine who has Ladbrokes odds for this race (declared to ride)
    odds_declared_pids = set()
    for pr in price_rows:
        if pr.race_odds_json:
            try:
                rd = json.loads(pr.race_odds_json)
                if isinstance(rd, dict):
                    for k in rd.keys():
                        if int(k) == next_race:
                            odds_declared_pids.add(pr.participant_id)
                            break
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    # If name matching completely failed, skip this race
    if not real_positions:
        if not odds_declared_pids and not all_matched_pids:
            logger.warning(
                f"Meeting {meeting.name} - Race {next_race}: "
                f"could not match any API results to participants "
                f"and no odds data — skipping (advancing)"
            )
            meeting.completed_races = next_race
            for attempt in range(5):
                try:
                    db.commit()
                    break
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 4:
                        db.rollback()
                        time.sleep(1)
                    else:
                        raise
            return
        logger.warning(
            f"Meeting {meeting.name} - Race {next_race}: "
            f"API name matching failed but {len(odds_declared_pids)} "
            f"have odds data — recording as non-placed"
        )

    # Create zero-point results for ALL participants not already placed
    # Every participant in a meeting rode in every race — they deserve a result record
    for p in participants:
        if p.id in placed_ids:
            continue
        results_batch.append({
            "meeting_id": meeting.id,
            "participant_id": p.id,
            "race_number": next_race,
            "position": 99,
            "points_added": 0,
            "final_points": 0,
        })

    # Batch insert results atomically (direct to own session, not db_writer)
    if results_batch:
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)
        for r in results_batch:
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

    matched_count = len(placed_ids)
    odds_count = len(odds_declared_pids)
    total_count = len(results_batch) - matched_count
    meeting.completed_races = next_race

    for attempt in range(5):
        try:
            db.commit()
            break
        except Exception as e:
            if "database is locked" in str(e) and attempt < 4:
                db.rollback()
                time.sleep(1)
            else:
                raise

    logger.info(
        f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} "
        f"({matched_count} placed, {odds_count} odds, {total_count} additional)"
    )


def _maybe_update_race_count(meeting):
    """Auto-correct total_races from Ladbrokes API if seed default was wrong."""
    from scrapers.base import _get_client, API_BASE
    from time_utils import today_aus
    from datetime import date as _date, timedelta
    from utils import normalise_name

    today = today_aus()
    today_date = _date.fromisoformat(today)
    dates = [
        today,
        (today_date - timedelta(days=1)).isoformat(),
        (today_date + timedelta(days=1)).isoformat(),
    ]

    client = _get_client()
    for d in dates:
        try:
            r = client.get(
                f"{API_BASE}/racing/meetings",
                params={"date_from": d, "date_to": d, "country": "AUS", "type": " ", "limit": 200},
            )
            if r.status_code != 200:
                continue
            api_meetings = r.json().get("data", {}).get("meetings", [])
            for api_m in api_meetings:
                if normalise_name(api_m.get("name", "")) == normalise_name(meeting.name):
                    actual = len([race for race in api_m.get("races", [])
                                  if race.get("race_number", 0) > 0])
                    if 0 < actual != meeting.total_races:
                        logger.info(
                            f"Correcting {meeting.name} total_races: "
                            f"{meeting.total_races} -> {actual}"
                        )
                        meeting.total_races = actual
                    return
        except Exception:
            pass
