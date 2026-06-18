import json
import logging
import re
import random
import threading
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from database import SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus
from time_utils import AU_TZ, today_aus

from utils import weighted_shuffle, race_points, normalise_name, names_match, MIN_PRICE, MAX_PRICE

_refresh_lock = threading.Lock()
_scrape_lock = threading.Lock()

from scrapers.base import fetch_single_race_results, invalidate_cache
from seed_data import _get_real_race_positions, seed_database
from scrapers import LadbrokesScraper, TABScraper, SportsbetScraper, PointsBetScraper, TABtouchScraper, NedsScraper


def _broadcast_race_update(meeting_id: str, meeting_name: str, race_number: int, completed_races: int, total_races: int):
    try:
        from router import broadcast_sse
        broadcast_sse("race_completed", {
            "meetingId": meeting_id,
            "meetingName": meeting_name,
            "raceNumber": race_number,
            "completedRaces": completed_races,
            "totalRaces": total_races,
        })
    except Exception:
        pass


logger = logging.getLogger(__name__)

BOOKMAKER_SCRAPERS = [
    ("Ladbrokes", LadbrokesScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TAB", TABScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("Sportsbet", SportsbetScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("PointsBet", PointsBetScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("TABtouch", TABtouchScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
    ("Neds", NedsScraper, ["scrape_jockey_challenges", "scrape_driver_challenges"]),
]

ACCURATE_SCRAPERS = {"Ladbrokes", "TAB", "Sportsbet", "PointsBet", "TABtouch", "Neds"}


def refresh_meeting_status():
    if not _refresh_lock.acquire(blocking=False):
        logger.info("Previous refresh still in progress, skipping")
        return
    db = None
    try:
        logger.info("Refreshing meeting status...")
        now_aus = datetime.now(AU_TZ)
        db = SessionLocal()

        # Auto-seed if no meetings exist for today (handles day transitions)
        today = today_aus()
        today_count = db.query(Meeting).filter(Meeting.date == today).count()
        if today_count == 0:
            logger.info("No meetings for today — running auto-seed")
            seed_database(db)

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
                elif meeting.scheduled_time and not meeting.id.startswith("dyn_"):
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
                if st is not None and not scheduled_reached and not meeting.id.startswith("dyn_"):
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
                    # Count ALL races the participant has a result for (scored or not)
                    # This gives the true number of races they participated in
                    p.completed_races = len(set(r.race_number for r in prev_results))
                    p.remaining_races = meeting.total_races - p.completed_races

                # Delete existing results for this race to handle re-runs cleanly
                db.query(Result).filter(
                    Result.meeting_id == meeting.id,
                    Result.race_number == next_race,
                ).delete()

                # Check if last race results already exist in DB (auto-finish)
                if next_race == meeting.total_races:
                    last_race_results = db.query(Result).filter(
                        Result.meeting_id == meeting.id,
                        Result.race_number == next_race,
                    ).count()
                    if last_race_results > 0:
                        meeting.status = MeetingStatus.FINISHED.value
                        for p in participants:
                            p.remaining_races = 0
                        logger.info(f"Meeting {meeting.name} -> FINISHED (last race results exist in DB)")
                        db.commit()
                        continue

                race_data = fetch_single_race_results(meeting.name, next_race)

                if race_data is None:
                    # API failure - weighted shuffle fallback
                    # Only select a random subset of participants (like real racing where
                    # not every jockey has a ride in every race)
                    shuffled = weighted_shuffle(participants, db, meeting.id)
                    riders = min(len(shuffled), random.randint(3, max(3, meeting.total_races)))
                    for pos in range(1, len(shuffled) + 1):
                        p = shuffled[pos - 1]
                        p.completed_races += 1
                        p.remaining_races = meeting.total_races - p.completed_races
                        if pos <= riders:
                            added = {1: 3, 2: 2, 3: 1}.get(pos, 0)
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
                    _broadcast_race_update(meeting.id, meeting.name, next_race, meeting.completed_races, meeting.total_races)
                    logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} ({riders} riders, weighted shuffle)")
                else:
                    status = race_data.get("status", "")
                    if status not in ("Final", "Interim", "Closed", "Results"):
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
                    # Get all participant IDs that were matched to API results in this race
                    from seed_data import _get_real_race_positions as _grrp
                    # Re-fetch to get all matched participants, not just placed ones
                    all_matched_race = _get_real_race_positions(race_data, participants, {})
                    all_matched_pids = set()
                    if all_matched_race:
                        for p2, pos2 in all_matched_race:
                            all_matched_pids.add(p2.id)
                    
                    # Non-placed participants who DID have a runner in this race
                    for p in participants:
                        if p.id not in placed_ids and p.id in all_matched_pids:
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
                    _broadcast_race_update(meeting.id, meeting.name, next_race, meeting.completed_races, meeting.total_races)
                    logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} (REAL results)")
                logger.info(f"Meeting {meeting.name} - Race {next_race}/{meeting.total_races} completed")

                if next_race >= meeting.total_races:
                    meeting.status = MeetingStatus.FINISHED.value
                    for p in participants:
                        p.remaining_races = 0
                    logger.info(f"Meeting {meeting.name} -> FINISHED")

                db.commit()
    except Exception as e:
        logger.error(f"Status refresh failed: {e}", exc_info=True)
        if db:
            db.rollback()
    finally:
        if db:
            db.close()
        _refresh_lock.release()


def _apply_micro_fluctuation():
    """Apply small random price adjustments to simulate real market movement.
    
    Only adjusts prices for live/upcoming meetings. Magnitude increases
    as race time approaches and varies by price level (longshots move more).
    """
    db = SessionLocal()
    try:
        today = today_aus()
        meetings = db.query(Meeting).filter(
            Meeting.date == today,
            Meeting.status.in_([MeetingStatus.LIVE.value, MeetingStatus.UPCOMING.value]),
        ).all()
        if not meetings:
            return

        meeting_ids = [m.id for m in meetings]
        all_prices = db.query(Price).filter(
            Price.meeting_id.in_(meeting_ids),
            Price.bookmaker_name.in_(ACCURATE_SCRAPERS),
        ).all()
        if not all_prices:
            return

        changed = 0
        now = datetime.now(timezone.utc)
        for price in all_prices:
            if price.bookmaker_name == "Ladbrokes":
                continue
            if price.price <= 0:
                continue

            age_minutes = (now - price.timestamp.replace(tzinfo=timezone.utc)).total_seconds() / 60 if price.timestamp else 30

            if age_minutes < 2:
                base_pct = 0.008
            elif age_minutes < 5:
                base_pct = 0.015
            else:
                base_pct = 0.025

            if price.price <= 3.0:
                factor = 0.6
            elif price.price <= 8.0:
                factor = 1.0
            else:
                factor = 1.5

            delta_pct = base_pct * factor
            direction = random.choice([-1, 1])
            adjustment = 1.0 + (direction * delta_pct * random.uniform(0.3, 1.0))
            new_price = round(max(MIN_PRICE, min(MAX_PRICE, price.price * adjustment)), 2)

            if new_price != price.price:
                price.price = new_price
                price.timestamp = now
                changed += 1

        if changed > 0:
            db.commit()
            logger.info(f"Micro-fluctuation: adjusted {changed} prices across {len(meetings)} meetings")
    except Exception as e:
        logger.warning(f"Micro-fluctuation error: {e}")
        db.rollback()
    finally:
        db.close()


def scrape_all_bookmakers():
    if not _scrape_lock.acquire(blocking=False):
        logger.info("Previous scrape still in progress, skipping")
        return
    logger.info("Starting bookmaker scrape cycle...")
    invalidate_cache()
    from scrapers.neds import invalidate_cache as invalidate_neds_cache
    try:
        invalidate_neds_cache()
    except Exception:
        pass
    # Invalidate TAB scraper caches
    try:
        from scrapers.tab import _event_cache as tab_event_cache, _event_cache_lock as tab_lock
        with tab_lock:
            tab_event_cache.clear()
    except Exception:
        pass
    # Invalidate TABtouch scraper caches
    try:
        from scrapers.tabtouch import _event_cache as tt_event_cache, _event_cache_lock as tt_lock
        with tt_lock:
            tt_event_cache.clear()
    except Exception:
        pass
    # Invalidate PointsBet scraper cache
    try:
        from scrapers.pointsbet import _cache as pb_cache, _cache_lock as pb_lock
        with pb_lock:
            pb_cache.clear()
    except Exception:
        pass
    # Invalidate Sportsbet scraper cache
    try:
        from scrapers.sportsbet import _cache as sb_cache, _cache_lock as sb_lock
        with sb_lock:
            sb_cache.clear()
    except Exception:
        pass
    # Invalidate PuntersEdge cache
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

        has_live = any(
            m.status == MeetingStatus.LIVE.value for m in meetings
        )

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

    except Exception as e:
        logger.error(f"Bookmaker scrape cycle failed: {e}", exc_info=True)
        if db:
            db.rollback()
    finally:
        if db:
            db.close()
        _scrape_lock.release()

    try:
        _apply_micro_fluctuation()
    except Exception as e:
        logger.warning(f"Micro-fluctuation failed: {e}")
    logger.info("Bookmaker scrape cycle complete")


def _add_dynamic_meetings(db, unmatched_names, markets, bookmaker_name):
    from models import MeetingStatus, MeetingType
    now_aus = datetime.now(AU_TZ)
    for market in markets:
        mn = normalise_name(market.get("meeting_name", ""))
        if mn not in [normalise_name(u) for u in unmatched_names]:
            continue
        existing = db.query(Meeting).filter(
            Meeting.date == today_aus(),
            Meeting.name.ilike(f"%{market.get('meeting_name', '')}%")
        ).first()
        if existing:
            continue
        mtype = MeetingType.DRIVER.value if market.get("type") == "driver" else MeetingType.JOCKEY.value
        mid = f"dyn_{mtype}_{mn.replace(' ', '_')}"
        scheduled = now_aus + timedelta(hours=1)
        meeting = Meeting(
            id=mid,
            name=market["meeting_name"],
            date=today_aus(),
            status=MeetingStatus.UPCOMING.value,
            type=mtype,
            total_races=market.get("total_races", 8),
            completed_races=0,
            scheduled_time=scheduled,
        )
        db.add(meeting)
        db.flush()
        for p_data in market.get("participants", []):
            p_name = p_data.get("name", "").strip()
            if not p_name or p_name.lower() in ("unknown", ""):
                continue
            pid = f"{mid}_{p_name.lower().replace(' ', '_')}"
            db.add(Participant(
                id=pid, meeting_id=mid, name=p_name,
                current_points=0, completed_races=0, remaining_races=meeting.total_races,
            ))
            db.flush()
            race_odds = p_data.get("race_odds", {})
            db.add(Price(
                participant_id=pid, meeting_id=mid,
                bookmaker_name=bookmaker_name,
                price=round(max(MIN_PRICE, min(MAX_PRICE, float(p_data.get("price", 0) or 0))), 2),
                race_odds_json=json.dumps(race_odds) if race_odds else None,
                timestamp=datetime.now(timezone.utc),
            ))
        logger.info(f"Added dynamic meeting '{market['meeting_name']}' from {bookmaker_name}")
    db.commit()


def _update_prices_from_markets(db, meetings, markets, bookmaker_name):
    from models import Price

    _NON_RIDER_RE = re.compile(
        r'^(n\.?r\.?|not\s+(riding|declared)|scratched|n\.?d\.?|late\s+scratching|reserve|emergency|unknown)\s*$',
        re.IGNORECASE
    )

    # Track which prices have been added in this call to prevent duplicates
    # when multiple markets match the same meeting (e.g. jockey + driver markets)
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

                # Skip if this exact (participant_id, bookmaker_name) was already processed
                price_key = (pid, bookmaker_name)
                if price_key in processed_prices:
                    # Update price instead of insert
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
        if bookmaker_name in ("Ladbrokes", "TAB", "TABtouch", "PointsBet"):
            logger.info(
                f"{bookmaker_name}: {len(unmatched_meetings)} meetings added dynamically"
            )
            _add_dynamic_meetings(db, unmatched_meetings, markets, bookmaker_name)
        else:
            logger.info(
                f"{bookmaker_name}: {len(unmatched_meetings)} meetings not in DB, skipping"
            )
