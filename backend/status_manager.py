import logging
import re
import random
import threading
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from database import SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus
from time_utils import AU_TZ

from utils import weighted_shuffle, race_points, normalise_name, names_match

_refresh_lock = threading.Lock()
_scrape_lock = threading.Lock()

from scrapers.base import fetch_single_race_results
from seed_data import _get_real_race_positions
from scrapers import LadbrokesScraper, TABScraper, SportsbetScraper, PointsBetScraper, TABtouchScraper


logger = logging.getLogger(__name__)

BOOKMAKER_SCRAPERS = [
    ("Ladbrokes", LadbrokesScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TAB", TABScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("Sportsbet", SportsbetScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("PointsBet", PointsBetScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TABtouch", TABtouchScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
]


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
                if scheduled_reached or (not meeting.scheduled_time and meeting.completed_races > 0):
                    meeting.status = MeetingStatus.LIVE.value
                    meeting.completed_races = 0
                    logger.info(f"Meeting {meeting.name} -> LIVE")
                elif meeting.scheduled_time:
                    # Check API race 1 to see if meeting has already started
                    race_data = fetch_single_race_results(meeting.name, 1)
                    if race_data and race_data.get("status") in ("Final", "Interim"):
                        meeting.status = MeetingStatus.LIVE.value
                        meeting.completed_races = 0
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
                    # Delete stale results when reverting to UPCOMING
                    db.query(Result).filter(
                        Result.meeting_id == meeting.id
                    ).delete()
                    logger.info(f"Meeting {meeting.name} -> UPCOMING (reverted, scheduled time not yet reached)")
                    db.commit()
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
                    db.commit()
                    continue

                # Recalculate participant state from confirmed Results (not participant table)
                # This prevents double-counting if weighted-shuffle was used on a previous cycle
                for p in participants:
                    prev_results = db.query(Result).filter(
                        Result.participant_id == p.id,
                        Result.race_number < next_race,
                    ).all()
                    p.current_points = sum(r.points_added for r in prev_results)
                    p.completed_races = len(set(r.race_number for r in prev_results if r.points_added > 0))
                    p.remaining_races = meeting.total_races - p.completed_races

                # Delete existing results for this race to handle re-runs cleanly
                db.query(Result).filter(
                    Result.meeting_id == meeting.id,
                    Result.race_number == next_race,
                ).delete()

                race_data = fetch_single_race_results(meeting.name, next_race)

                if race_data is None:
                    # API failure - weighted shuffle fallback
                    # Only select a random subset of participants (like real racing where
                    # not every jockey has a ride in every race)
                    shuffled = weighted_shuffle(participants, db, meeting.id)
                    riders = min(len(shuffled), random.randint(3, max(3, meeting.total_races)))
                    for pos in range(1, len(shuffled) + 1):
                        p = shuffled[pos - 1]
                        if pos <= riders:
                            added = {1: 3, 2: 2, 3: 1}.get(pos, 0)
                            p.completed_races += 1
                            p.remaining_races = meeting.total_races - p.completed_races
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
                        else:
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
                    logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} ({riders} riders, weighted shuffle)")
                else:
                    status = race_data.get("status", "")
                    if status not in ("Final", "Interim"):
                        # Race not ready yet - skip this cycle
                        logger.info(f"Meeting {meeting.name} - Race {next_race} not ready (status={status})")
                        continue

                    pids = [p.id for p in participants]
                    price_rows = db.query(Price).filter(
                        Price.participant_id.in_(pids),
                        Price.bookmaker_name == "Ladbrokes",
                    ).all()
                    price_map = {pr.participant_id: pr.price for pr in price_rows}
                    real_positions = _get_real_race_positions(race_data, participants, price_map) if race_data else None

                    if real_positions is None and race_data.get("results"):
                        logger.warning(
                            f"Meeting {meeting.name} - Race {next_race}: API has {len(race_data.get('results',[]))} "
                            f"results but still could not match via any strategy. Skipping."
                        )
                        continue

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
                    # Non-placed participants: no runner in this race, so no completed_races increment
                    for p in participants:
                        if p.id not in placed_ids:
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
    from models import Price
    invalidate_cache()
    db = SessionLocal()
    today = today_aus()
    try:
        meetings = db.query(Meeting).filter(
            Meeting.date == today,
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

    # Delete existing prices for this bookmaker before inserting fresh data
    meeting_ids = [m.id for m in meetings]
    deleted = db.query(Price).filter(
        Price.meeting_id.in_(meeting_ids),
        Price.bookmaker_name == bookmaker_name,
    ).delete(synchronize_session=False)
    if deleted:
        logger.info(f"Cleared {deleted} stale {bookmaker_name} prices")

    unmatched_meetings = []
    for market in markets:
        meeting_name = normalise_name(market.get("meeting_name", ""))
        matching = [
            m for m in meetings
            if normalise_name(m.name) == meeting_name or meeting_name in normalise_name(m.name) or normalise_name(m.name) in meeting_name
        ]
        if not matching:
            unmatched_meetings.append(market.get("meeting_name", "?"))
        for meeting in matching:
            participants = db.query(Participant).filter(
                Participant.meeting_id == meeting.id
            ).all()
            unmatched_participants = []
            for p_data in market.get("participants", []):
                p_name = p_data.get("name", "")
                matched = False
                for p in participants:
                    if names_match(p.name, p_name):
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
                        matched = True
                        break
                if not matched:
                    unmatched_participants.append(p_name)
            if unmatched_participants:
                logger.warning(
                    f"{bookmaker_name} / {market.get('meeting_name', '?')}: "
                    f"{len(unmatched_participants)} participants unmatched: {unmatched_participants[:5]}"
                )

    if unmatched_meetings:
        logger.warning(
            f"{bookmaker_name}: {len(unmatched_meetings)} meetings unmatched: {unmatched_meetings[:5]}"
        )
