"""Bookmaker price scraper coordinator.

Responsibilities:
- Scrape all bookmaker prices for today's meetings
- Update Price records in DB
- Invalidate caches between cycles

Status processing has been moved to:
- status_updater.py (meeting state transitions)
- results_ingestor.py (race result fetching)
- points_calculator.py (participant point calculations)
"""
import json
import logging
import re
import threading
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from database import SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus
from time_utils import AU_TZ, today_aus

from utils import normalise_name, names_match, MIN_PRICE, MAX_PRICE

_scrape_lock = threading.Lock()

from scrapers.base import invalidate_cache
from scrapers import LadbrokesScraper, TABScraper, SportsbetScraper, PointsBetScraper, TABtouchScraper

logger = logging.getLogger(__name__)

BOOKMAKER_SCRAPERS = [
    ("Ladbrokes", LadbrokesScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TAB", TABScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("Sportsbet", SportsbetScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("PointsBet", PointsBetScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TABtouch", TABtouchScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
]

ACCURATE_SCRAPERS = {"Ladbrokes", "TAB", "Sportsbet", "PointsBet", "TABtouch"}


def scrape_all_bookmakers():
    if not _scrape_lock.acquire(blocking=False):
        logger.info("Previous scrape still in progress, skipping")
        return
    logger.info("Starting bookmaker scrape cycle...")
    invalidate_cache()
    try:
        from scrapers.tab import _event_cache as tab_event_cache, _event_cache_lock as tab_lock
        with tab_lock:
            tab_event_cache.clear()
    except Exception:
        pass
    try:
        from scrapers.tabtouch import _event_cache as tt_event_cache, _event_cache_lock as tt_lock
        with tt_lock:
            tt_event_cache.clear()
    except Exception:
        pass
    try:
        from scrapers.pointsbet import _cache as pb_cache, _cache_lock as pb_lock
        with pb_lock:
            pb_cache.clear()
    except Exception:
        pass
    try:
        from scrapers.sportsbet import _cache as sb_cache, _cache_lock as sb_lock
        with sb_lock:
            sb_cache.clear()
    except Exception:
        pass
    try:
        from scrapers.puntersedge import _shared_cache_lock as pe_lock
        import scrapers.puntersedge as pe_mod
        with pe_lock:
            pe_mod._shared_cache = None
            pe_mod._shared_cache_time = 0
    except Exception:
        pass
    try:
        from router import _cache as router_cache
        router_cache.clear()
    except Exception:
        pass

    db = None
    today = today_aus()
    try:
        db = SessionLocal()
        meetings = db.query(Meeting).filter(
            Meeting.date == today,
        ).all()

        if not meetings:
            logger.info("No meetings to update, skipping scrape")
            return

        meeting_ids = [m.id for m in meetings]

        # Time-based price eviction: remove prices older than 24 hours
        old_prices = db.query(Price).filter(
            Price.meeting_id.in_(meeting_ids),
            Price.timestamp < datetime.now(timezone.utc) - timedelta(hours=24),
        ).delete(synchronize_session=False)
        if old_prices:
            logger.info(f"Cleared {old_prices} price records older than 24 hours")

        stale_bookmakers = [bm for bm, _, _ in BOOKMAKER_SCRAPERS if bm not in ACCURATE_SCRAPERS]
        if stale_bookmakers:
            deleted = db.query(Price).filter(
                Price.meeting_id.in_(meeting_ids),
                Price.bookmaker_name.in_(stale_bookmakers),
            ).delete(synchronize_session=False)
            if deleted:
                logger.info(f"Cleared {deleted} stale price records for {stale_bookmakers}")

        for bm_name, scraper_cls, methods in BOOKMAKER_SCRAPERS:
            if bm_name not in ACCURATE_SCRAPERS:
                continue
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
                    logger.info(f"{bm_name}: prices updated for {len(meetings)} meetings")
                else:
                    logger.info(f"{bm_name}: no markets returned")

                db.commit()
            except Exception as e:
                logger.warning(f"{bm_name} scrape failed: {e}, rolling back")
                db.rollback()
            finally:
                scraper.close()

        orphan_participants = db.query(Participant).filter(
            Participant.meeting_id.in_(meeting_ids)
        ).all()
        orphan_count = 0
        for op in orphan_participants:
            op_prices = db.query(Price).filter(Price.participant_id == op.id).count()
            if op_prices == 0:
                db.query(Result).filter(Result.participant_id == op.id).delete(synchronize_session=False)
                db.delete(op)
                orphan_count += 1
        if orphan_count:
            db.commit()
            logger.info(f"Removed {orphan_count} orphan participants with no bookmaker prices")

    except Exception as e:
        logger.error(f"Bookmaker scrape cycle failed: {e}", exc_info=True)
        if db:
            db.rollback()
    finally:
        if db:
            db.close()
        _scrape_lock.release()
    logger.info("Bookmaker scrape cycle complete")


def _update_prices_from_markets(db, meetings, markets, bookmaker_name):
    _NON_RIDER_RE = re.compile(
        r'^(n\.?r\.?|not\s+(riding|declared)|scratched|n\.?d\.?|late\s+scratching|reserve|emergency|unknown)\s*$',
        re.IGNORECASE
    )

    processed_prices = set()

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
            added_count = 0
            for p_data in market.get("participants", []):
                p_name = p_data.get("name", "").strip()
                try:
                    new_price = float(p_data.get("price", 0) or 0)
                except (ValueError, TypeError):
                    continue
                if not p_name or new_price <= 0 or _NON_RIDER_RE.match(p_name) or p_name.lower() in ("unknown", ""):
                    continue
                new_price = round(max(MIN_PRICE, min(MAX_PRICE, new_price)), 2)
                race_odds = p_data.get("race_odds", {})
                race_odds_json_val = json.dumps(race_odds) if race_odds else None
                matched = False
                pid = None
                for p in participants:
                    if names_match(p.name, p_name):
                        pid = p.id
                        matched = True
                        break
                if not matched:
                    pid = f"{meeting.id}_{p_name.lower().replace(' ', '_')}"
                    existing_p = None
                    for ep in participants:
                        if ep.id == pid:
                            existing_p = ep
                            break
                    if not existing_p:
                        existing_p = db.query(Participant).filter(Participant.id == pid).first()
                    if not existing_p:
                        if bookmaker_name in ("Ladbrokes", "TAB", "TABtouch", "PointsBet"):
                            new_p = Participant(
                                id=pid,
                                meeting_id=meeting.id,
                                name=p_name,
                                current_points=0,
                                completed_races=0,
                                remaining_races=meeting.total_races,
                            )
                            db.add(new_p)
                            db.flush()
                            participants.append(new_p)
                            added_count += 1
                        else:
                            continue

                price_key = (pid, bookmaker_name)
                if price_key in processed_prices:
                    existing = db.query(Price).filter(
                        Price.participant_id == pid,
                        Price.bookmaker_name == bookmaker_name,
                    ).first()
                    if existing:
                        existing.price = new_price
                        if race_odds_json_val:
                            existing.race_odds_json = race_odds_json_val
                        existing.timestamp = datetime.now(timezone.utc)
                    continue

                processed_prices.add(price_key)
                db.query(Price).filter(
                    Price.participant_id == pid,
                    Price.bookmaker_name == bookmaker_name,
                ).delete()
                db.add(Price(
                    participant_id=pid,
                    meeting_id=meeting.id,
                    bookmaker_name=bookmaker_name,
                    price=new_price,
                    race_odds_json=race_odds_json_val,
                    timestamp=datetime.now(timezone.utc),
                ))
            if added_count:
                logger.info(
                    f"{bookmaker_name} / {market.get('meeting_name', '?')}: "
                    f"added {added_count} new participant(s)"
                )

    if unmatched_meetings:
        logger.info(
            f"{bookmaker_name}: {len(unmatched_meetings)} meetings not in DB, skipping "
            f"(dynamic meeting creation disabled to prevent false matches)"
        )
