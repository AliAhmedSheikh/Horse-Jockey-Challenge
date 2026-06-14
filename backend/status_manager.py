import logging
import random
import threading
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from database import SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus
from time_utils import AU_TZ

from utils import weighted_shuffle, race_points

_refresh_lock = threading.Lock()
_scrape_lock = threading.Lock()

from scrapers.base import fetch_single_race_results
from seed_data import _get_real_race_positions

from scrapers import (
    LadbrokesScraper,
    TABScraper,
    SportsbetScraper,
    PointsBetScraper,
    TABtouchScraper,
)

def _race_points(pos, all_positions=None):
    """3-2-1 scoring with dead heat sharing per official TAB rules."""
    if pos > 3:
        return 0
    base = {1: 3, 2: 2, 3: 1}[pos]
    if not all_positions:
        return base
    count = sum(1 for p in all_positions if p == pos)
    if count > 1:
        total = sum({1: 3, 2: 2, 3: 1}.get(pos + i, 0) for i in range(count))
        return total / count
    return base

logger = logging.getLogger(__name__)

BOOKMAKER_SCRAPERS = [
    ("Ladbrokes", LadbrokesScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TAB", TABScraper, ["scrape_daily_challenge_meetings"]),
    ("Sportsbet", SportsbetScraper, ["scrape_challenge_prices"]),
    ("PointsBet", PointsBetScraper, ["scrape_challenge_markets"]),
    ("TABtouch", TABtouchScraper, ["scrape_challenge_markets"]),
]


def _simulate_initial_races(meeting, participants, db):
    """Simulate 2-6 races for a meeting that just went LIVE."""
    initial = min(random.randint(2, 6), meeting.total_races)
    meeting.completed_races = initial
    cumulative_points = {p.id: 0 for p in participants}
    race_counts = {p.id: 0 for p in participants}
    for rn in range(1, initial + 1):
        shuffled = weighted_shuffle(participants, db, meeting.id) if meeting.total_races > 0 else list(participants)
        for pos, p in enumerate(shuffled, 1):
            added = {1: 3, 2: 2, 3: 1}.get(pos, 0)
            cumulative_points[p.id] += added
            race_counts[p.id] += 1
            result = Result(
                meeting_id=meeting.id,
                participant_id=p.id,
                final_points=cumulative_points[p.id],
                position=pos,
                race_number=rn,
                points_added=added,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 5)),
            )
            db.add(result)
    for p in participants:
        p.current_points = cumulative_points[p.id]
        p.completed_races = race_counts[p.id]
        p.remaining_races = meeting.total_races - race_counts[p.id]


def refresh_meeting_status():
    if not _refresh_lock.acquire(blocking=False):
        logger.info("Previous refresh still in progress, skipping")
        return
    try:
        logger.info("Refreshing meeting status...")
        now_aus = datetime.now(AU_TZ)
        db = SessionLocal()
        meetings = db.query(Meeting).all()
        for meeting in meetings:
            st = meeting.scheduled_time
            if st is not None and st.tzinfo is None:
                st = st.replace(tzinfo=AU_TZ)
            scheduled_reached = st is not None and now_aus >= st

            if meeting.status == MeetingStatus.UPCOMING.value:
                if scheduled_reached:
                    meeting.status = MeetingStatus.LIVE.value
                    participants = db.query(Participant).filter(
                        Participant.meeting_id == meeting.id
                    ).all()
                    _simulate_initial_races(meeting, participants, db)
                    logger.info(f"Meeting {meeting.name} -> LIVE (scheduled time reached)")
                elif not meeting.scheduled_time and meeting.completed_races > 0:
                    meeting.status = MeetingStatus.LIVE.value
                    logger.info(f"Meeting {meeting.name} -> LIVE (legacy fallback)")
                elif meeting.scheduled_time:
                    # Check API race 1 to see if meeting has already started
                    race_data = fetch_single_race_results(meeting.name, 1)
                    if race_data and race_data.get("status") in ("Final", "Interim"):
                        meeting.status = MeetingStatus.LIVE.value
                        participants = db.query(Participant).filter(
                            Participant.meeting_id == meeting.id
                        ).all()
                        _simulate_initial_races(meeting, participants, db)
                        logger.info(f"Meeting {meeting.name} -> LIVE (API race 1 completed)")

            if meeting.status == MeetingStatus.LIVE.value:
                # Revert LIVE→UPCOMING if scheduled time hasn't arrived yet
                # (only if API doesn't show race results either)
                api_shows_results = False
                if st is not None and not scheduled_reached:
                    race_data = fetch_single_race_results(meeting.name, 1)
                    api_shows_results = race_data and race_data.get("status") in ("Final", "Interim")
                if st is not None and not scheduled_reached and not api_shows_results:
                    meeting.status = MeetingStatus.UPCOMING.value
                    participants = db.query(Participant).filter(
                        Participant.meeting_id == meeting.id
                    ).all()
                    for p in participants:
                        p.current_points = 0
                        p.completed_races = 0
                        p.remaining_races = meeting.total_races
                    logger.info(f"Meeting {meeting.name} -> UPCOMING (reverted, scheduled time not yet reached)")
                    continue
                participants = db.query(Participant).filter(
                    Participant.meeting_id == meeting.id
                ).all()
                n = len(participants)
                if n == 0:
                    continue

                next_race = meeting.completed_races + 1
                if next_race > meeting.total_races:
                    meeting.status = MeetingStatus.FINISHED.value
                    for p in participants:
                        p.remaining_races = 0
                    logger.info(f"Meeting {meeting.name} -> FINISHED")
                    continue

                race_data = fetch_single_race_results(meeting.name, next_race)

                if race_data is None:
                    # API failure - weighted shuffle fallback (for fully simulated meetings)
                    shuffled = weighted_shuffle(participants, db, meeting.id)
                    for pos, p in enumerate(shuffled, 1):
                        added = {1: 3, 2: 2, 3: 1}.get(pos, 0)
                        p.completed_races = next_race
                        p.remaining_races = meeting.total_races - next_race
                        p.current_points += added
                        result = Result(
                            meeting_id=meeting.id,
                            participant_id=p.id,
                            final_points=p.current_points,
                            position=pos,
                            race_number=next_race,
                            points_added=added,
                            timestamp=datetime.now(timezone.utc),
                        )
                        db.add(result)
                    meeting.completed_races = next_race
                    logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} (weighted shuffle)")
                else:
                    status = race_data.get("status", "")
                    if status not in ("Final", "Interim"):
                        # Race not ready yet - skip this cycle
                        logger.info(f"Meeting {meeting.name} - Race {next_race} not ready (status={status})")
                        continue

                    real_positions = _get_real_race_positions(race_data, participants) if race_data else None

                    placed_ids = set()
                    if real_positions:
                        race_positions = [pos for _, pos in real_positions]
                        for p, pos in real_positions:
                            added = race_points(pos, race_positions)
                            p.completed_races += 1
                            p.remaining_races = meeting.total_races - p.completed_races
                            p.current_points += added
                            placed_ids.add(p.id)
                            result = Result(
                                meeting_id=meeting.id,
                                participant_id=p.id,
                                final_points=p.current_points,
                                position=pos,
                                race_number=next_race,
                                points_added=added,
                                timestamp=datetime.now(timezone.utc),
                            )
                            db.add(result)
                    # Non-placed participants get position=99, points_added=0
                    for p in participants:
                        if p.id not in placed_ids:
                            p.completed_races += 1
                            p.remaining_races = meeting.total_races - p.completed_races
                            result = Result(
                                meeting_id=meeting.id,
                                participant_id=p.id,
                                final_points=p.current_points,
                                position=99,
                                race_number=next_race,
                                points_added=0,
                                timestamp=datetime.now(timezone.utc),
                            )
                            db.add(result)
                    meeting.completed_races = next_race
                    logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} (REAL results)")
                logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} completed")

                if next_race >= meeting.total_races:
                    meeting.status = MeetingStatus.FINISHED.value
                    for p in participants:
                        p.remaining_races = 0
                    logger.info(f"Meeting {meeting.name} -> FINISHED")

        db.commit()
    except Exception as e:
        logger.error(f"Status refresh failed: {e}")
        db.rollback()
    finally:
        db.close()
        _refresh_lock.release()


def scrape_all_bookmakers():
    if not _scrape_lock.acquire(blocking=False):
        logger.info("Previous scrape still in progress, skipping")
        return
    logger.info("Starting bookmaker scrape cycle...")
    from scrapers.base import invalidate_cache
    from time_utils import today_aus
    invalidate_cache()
    db = SessionLocal()
    today = today_aus()
    try:
        meetings = db.query(Meeting).filter(
            Meeting.date == today,
            Meeting.status.in_([MeetingStatus.LIVE.value, MeetingStatus.FINISHED.value])
        ).all()
        if not meetings:
            logger.info("No meetings to update, skipping scrape")
            return

        for bm_name, scraper_cls, methods in BOOKMAKER_SCRAPERS:
            scraper = scraper_cls()
            try:
                all_markets = []
                for method_name in methods:
                    method = getattr(scraper, method_name, None)
                    if method:
                        try:
                            data = method()
                            if data:
                                all_markets.extend(data)
                                logger.info(f"{bm_name}: {len(data)} markets from {method_name}")
                        except Exception as e:
                            logger.warning(f"{bm_name}.{method_name} failed: {e}")

                if all_markets:
                    _update_prices_from_markets(db, meetings, all_markets, bm_name)

            except Exception as e:
                logger.warning(f"{bm_name} scrape failed: {e}")
            finally:
                scraper.close()

        db.commit()
    except Exception as e:
        logger.error(f"Bookmaker scrape cycle failed: {e}")
        db.rollback()
    finally:
        db.close()
        _scrape_lock.release()
    logger.info("Bookmaker scrape cycle complete")


def _update_prices_from_markets(db, meetings, markets, bookmaker_name):
    from models import Price

    for market in markets:
        meeting_name = market.get("meeting_name", "").lower()
        matching = [
            m for m in meetings
            if m.name.lower() == meeting_name
        ]
        for meeting in matching:
            participants = db.query(Participant).filter(
                Participant.meeting_id == meeting.id
            ).all()
            for p_data in market.get("participants", []):
                p_name = p_data.get("name", "").strip().lower()
                for p in participants:
                    if p.name.strip().lower() == p_name:
                        existing = db.query(Price).filter(
                            Price.participant_id == p.id,
                            Price.bookmaker_name == bookmaker_name,
                        ).first()
                        if existing:
                            new_price = p_data.get("price", 0.0)
                            if new_price > 0:
                                existing.price = new_price
                                existing.timestamp = datetime.now(timezone.utc)
                            elif existing.price <= 0:
                                existing.price = 1.5
                                existing.timestamp = datetime.now(timezone.utc)
                        else:
                            new_price = p_data.get("price", 0.0)
                            if new_price <= 0:
                                new_price = 1.5
                            db.add(Price(
                                participant_id=p.id,
                                meeting_id=meeting.id,
                                bookmaker_name=bookmaker_name,
                                price=new_price,
                                timestamp=datetime.now(timezone.utc),
                            ))
                        break
