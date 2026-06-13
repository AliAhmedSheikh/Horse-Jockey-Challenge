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
            if meeting.status == MeetingStatus.UPCOMING.value:
                meeting.status = MeetingStatus.LIVE.value
                logger.info(f"Meeting {meeting.name} -> LIVE")

            elif meeting.status == MeetingStatus.LIVE.value:
                participants = db.query(Participant).filter(
                    Participant.meeting_id == meeting.id
                ).all()
                n = len(participants)
                by_race = {}
                for p in participants:
                    if p.completed_races < meeting.total_races:
                        if random.random() < 0.3:
                            p.completed_races += 1
                            p.remaining_races = meeting.total_races - p.completed_races
                            added = random.randint(1, 5)
                            p.current_points += added
                            by_race.setdefault(p.completed_races, []).append((p, added))

                for race_num, racers in by_race.items():
                    if racers:
                        positions = random.sample(range(1, max(n, len(racers)) + 1), len(racers))
                        meeting.completed_races = max(
                            meeting.completed_races,
                            max(pp.completed_races for pp in participants)
                        )
                        for (p, added), pos in zip(racers, positions):
                            result = Result(
                                meeting_id=meeting.id,
                                participant_id=p.id,
                                final_points=p.current_points,
                                position=pos,
                                race_number=race_num,
                                points_added=added,
                                timestamp=datetime.now(timezone.utc),
                            )
                            db.add(result)

                all_done = all(
                    p.completed_races >= meeting.total_races
                    for p in participants
                )
                if all_done:
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
    invalidate_cache()
    db = SessionLocal()
    try:
        meetings = db.query(Meeting).filter(
            Meeting.status == MeetingStatus.LIVE.value
        ).all()
        if not meetings:
            logger.info("No live meetings to update, skipping scrape")
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
