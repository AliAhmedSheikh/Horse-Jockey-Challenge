import logging
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from database import SessionLocal
from models import Meeting, Participant, Result, MeetingStatus
from scrapers import (
    LadbrokesScraper,
    TABScraper,
    SportsbetScraper,
    PointsBetScraper,
    TABtouchScraper,
)

logger = logging.getLogger(__name__)

BOOKMAKER_SCRAPERS = [
    ("Ladbrokes", LadbrokesScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TAB", TABScraper, ["scrape_daily_challenge_meetings"]),
    ("Sportsbet", SportsbetScraper, ["scrape_challenge_prices"]),
    ("PointsBet", PointsBetScraper, ["scrape_challenge_markets"]),
    ("TABtouch", TABtouchScraper, ["scrape_challenge_markets"]),
]


def refresh_meeting_status():
    logger.info("Refreshing meeting status...")
    db = SessionLocal()
    try:
        meetings = db.query(Meeting).all()
        for meeting in meetings:
            if meeting.status == MeetingStatus.UPCOMING.value and meeting.completed_races > 0:
                meeting.status = MeetingStatus.LIVE.value
                logger.info(f"Meeting {meeting.name} -> LIVE")

            elif meeting.status == MeetingStatus.LIVE.value:
                participants = db.query(Participant).filter(
                    Participant.meeting_id == meeting.id
                ).all()
                n = len(participants)
                if n == 0:
                    continue

                next_race = meeting.completed_races + 1
                if next_race > meeting.total_races:
                    meeting.status = MeetingStatus.FINISHED.value
                    logger.info(f"Meeting {meeting.name} -> FINISHED")
                    continue

                shuffled = list(participants)
                random.shuffle(shuffled)
                for pos, p in enumerate(shuffled, 1):
                    added = max(1, 6 - pos)
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
                logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} completed")

                if next_race >= meeting.total_races:
                    meeting.status = MeetingStatus.FINISHED.value
                    logger.info(f"Meeting {meeting.name} -> FINISHED")

        db.commit()
    except Exception as e:
        logger.error(f"Status refresh failed: {e}")
        db.rollback()
    finally:
        db.close()


def scrape_all_bookmakers():
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
    logger.info("Bookmaker scrape cycle complete")


def _update_prices_from_markets(db, meetings, markets, bookmaker_name):
    from models import Price

    for market in markets:
        meeting_name = market.get("meeting_name", "").lower()
        matching = [
            m for m in meetings
            if m.name.lower() in meeting_name or meeting_name in m.name.lower()
        ]
        for meeting in matching:
            participants = db.query(Participant).filter(
                Participant.meeting_id == meeting.id
            ).all()
            for p_data in market.get("participants", []):
                p_name = p_data.get("name", "").lower()
                for p in participants:
                    if p.name.lower() == p_name:
                        existing = db.query(Price).filter(
                            Price.participant_id == p.id,
                            Price.bookmaker_name == bookmaker_name,
                        ).first()
                        if existing:
                            existing.price = p_data.get("price", existing.price)
                            existing.timestamp = datetime.now(timezone.utc)
                        else:
                            db.add(Price(
                                participant_id=p.id,
                                meeting_id=meeting.id,
                                bookmaker_name=bookmaker_name,
                                price=p_data.get("price", 0.0),
                                timestamp=datetime.now(timezone.utc),
                            ))
                        break
