from datetime import datetime, timezone, timedelta
import json
import logging

from sqlalchemy.orm import Session
from models import Meeting, Participant, Price, Result, MeetingStatus, MeetingType
from scrapers.base import LadbrokesAPIScraper, invalidate_cache
from time_utils import today_aus, AU_TZ
from utils import normalise_name, names_match, names_lastname_fallback, compute_value_rating, compute_status, weighted_shuffle as utils_weighted_shuffle, race_points, MIN_PRICE, MAX_PRICE

logger = logging.getLogger(__name__)

JOCKEY_MEETINGS = [
    {
        "id": "m1",
        "name": "Randwick",
        "type": "jockey",
        "total_races": 10,
        "participants": [
            {"name": "James McDonald", "price": 2.75},
            {"name": "Craig Williams", "price": 3.20},
            {"name": "Blake Shinn", "price": 5.50},
            {"name": "Damian Lane", "price": 7.50},
            {"name": "Kerrin McEvoy", "price": 10.00},
            {"name": "Nash Rawiller", "price": 4.20},
            {"name": "Hugh Bowman", "price": 6.00},
        ],
    },
    {
        "id": "m2",
        "name": "Flemington",
        "type": "jockey",
        "total_races": 8,
        "participants": [
            {"name": "Blake Shinn", "price": 4.80},
            {"name": "Nash Rawiller", "price": 3.60},
            {"name": "Damian Lane", "price": 6.50},
            {"name": "James McDonald", "price": 2.90},
            {"name": "Craig Williams", "price": 5.00},
            {"name": "Kerrin McEvoy", "price": 8.00},
        ],
    },
    {
        "id": "m3",
        "name": "Eagle Farm",
        "type": "jockey",
        "total_races": 8,
        "participants": [
            {"name": "Damian Lane", "price": 6.50},
            {"name": "Hugh Bowman", "price": 7.80},
            {"name": "Nash Rawiller", "price": 4.50},
            {"name": "James McDonald", "price": 3.10},
            {"name": "Blake Shinn", "price": 5.60},
        ],
    },
]

DRIVER_MEETINGS = [
    {
        "id": "m4",
        "name": "Albion Park",
        "type": "driver",
        "total_races": 8,
        "participants": [
            {"name": "Amanda Turnbull", "price": 4.10},
            {"name": "Kate Gath", "price": 6.00},
            {"name": "Nathan Jack", "price": 2.60},
            {"name": "Pete McMullen", "price": 8.50},
            {"name": "Shane Graham", "price": 12.00},
            {"name": "Luke McCarthy", "price": 2.90},
            {"name": "Chris Alford", "price": 3.80},
        ],
    },
    {
        "id": "m5",
        "name": "Menangle",
        "type": "driver",
        "total_races": 10,
        "participants": [
            {"name": "Luke McCarthy", "price": 2.90},
            {"name": "Nathan Jack", "price": 2.60},
            {"name": "Chris Alford", "price": 3.80},
            {"name": "Amanda Turnbull", "price": 4.10},
            {"name": "Kate Gath", "price": 6.00},
            {"name": "Greg Sugars", "price": 7.80},
        ],
    },
    {
        "id": "m6",
        "name": "Melton",
        "type": "driver",
        "total_races": 10,
        "participants": [
            {"name": "Chris Alford", "price": 3.80},
            {"name": "Greg Sugars", "price": 7.80},
            {"name": "Nathan Jack", "price": 2.60},
            {"name": "Kate Gath", "price": 6.00},
            {"name": "Amanda Turnbull", "price": 4.10},
            {"name": "Luke McCarthy", "price": 2.90},
        ],
    },
]

ALL_MEETINGS = JOCKEY_MEETINGS + DRIVER_MEETINGS


def seed_database(db: Session, force: bool = False):
    existing = db.query(Meeting).count()
    today = today_aus()
    if existing > 0 and not force:
        today_count = db.query(Meeting).filter(Meeting.date == today).count()
        if today_count > 0:
            from models import Participant as ParticipantModel
            participant_count = db.query(ParticipantModel).filter(
                ParticipantModel.meeting_id.in_(
                    db.query(Meeting.id).filter(Meeting.date == today)
                )
            ).count()
            if participant_count > 0:
                # Don't return early — check if all TAB challenge meetings are present.
                # The TAB scraper may find meetings that haven't been seeded yet
                # (e.g. jockey challenges added after initial seed).
                # We still log and continue to the seed logic below, which will
                # skip existing meetings and only add missing ones.
                logger.info(
                    f"Database has {today_count} meetings for today ({today}) "
                    f"with {participant_count} participants — checking for missing meetings"
                )
            else:
                logger.warning(
                    f"Found {today_count} meetings for today but 0 participants — "
                    f"clearing and re-seeding for {today}"
                )
                db.query(Result).filter(Result.meeting_id.in_(
                    db.query(Meeting.id).filter(Meeting.date == today)
                )).delete(synchronize_session='fetch')
                db.query(Price).filter(Price.meeting_id.in_(
                    db.query(Meeting.id).filter(Meeting.date == today)
                )).delete(synchronize_session='fetch')
                db.query(ParticipantModel).filter(ParticipantModel.meeting_id.in_(
                    db.query(Meeting.id).filter(Meeting.date == today)
                )).delete(synchronize_session='fetch')
                db.query(Meeting).filter(Meeting.date == today).delete()
                db.commit()
        else:
            logger.info(f"Existing data is from a previous day, clearing and re-seeding for {today}")
            db.query(Result).filter(Result.meeting_id.in_(
                db.query(Meeting.id).filter(Meeting.date != today)
            )).delete(synchronize_session='fetch')
            db.query(Price).filter(Price.meeting_id.in_(
                db.query(Meeting.id).filter(Meeting.date != today)
            )).delete(synchronize_session='fetch')
            db.query(Participant).filter(Participant.meeting_id.in_(
                db.query(Meeting.id).filter(Meeting.date != today)
            )).delete(synchronize_session='fetch')
            db.query(Meeting).filter(Meeting.date != today).delete()
            db.commit()

    aus_date = today_aus()

    # Step 1: Run TAB scraper to discover real challenge meetings.
    # TABtouch has dedicated challenge endpoints that only list actual challenges.
    tab_jockey = []
    tab_driver = []
    try:
        from scrapers.tab import TABScraper
        tab = TABScraper()
        tab_jockey = tab.scrape_jockey_challenges()
        tab_driver = tab.scrape_driver_challenges()
        tab.close()
        real_jockey_names = {normalise_name(m["meeting_name"]) for m in tab_jockey}
        real_driver_names = {normalise_name(m["meeting_name"]) for m in tab_driver}
        logger.info(f"TAB challenge scraper found: {len(real_jockey_names)} jockey, {len(real_driver_names)} driver")
        if real_jockey_names:
            logger.info(f"  Jockey challenges: {sorted(real_jockey_names)}")
        if real_driver_names:
            logger.info(f"  Driver challenges: {sorted(real_driver_names)}")
    except Exception as e:
        logger.warning(f"TAB challenge scraper failed: {e}")

    # Step 2: Fetch all meetings from Ladbrokes API for pricing data
    logger.info("Fetching meetings from Ladbrokes API...")
    api = LadbrokesAPIScraper()
    api_jockey = api.fetch_jockey_challenge_meetings()
    api_driver = api.fetch_driver_challenge_meetings()
    api.close()
    invalidate_cache()

    # Step 3: Filter Ladbrokes data to only real challenge meetings (known from TAB)
    all_real_names = set()
    try:
        all_real_names = {normalise_name(m["meeting_name"]) for m in tab_jockey + tab_driver}
    except Exception:
        pass

    if all_real_names:
        filtered_jockey = [m for m in api_jockey if normalise_name(m["meeting_name"]) in all_real_names]
        filtered_driver = [m for m in api_driver if normalise_name(m["meeting_name"]) in all_real_names]
        dropped_jockey = [m["meeting_name"] for m in api_jockey if normalise_name(m["meeting_name"]) not in all_real_names]
        dropped_driver = [m["meeting_name"] for m in api_driver if normalise_name(m["meeting_name"]) not in all_real_names]
        if dropped_jockey:
            logger.info(f"Filtered out non-challenge jockey meetings: {dropped_jockey}")
        if dropped_driver:
            logger.info(f"Filtered out non-challenge driver meetings: {dropped_driver}")
        api_jockey = filtered_jockey
        api_driver = filtered_driver

    # Step 4: Merge Ladbrokes + TAB sources — Ladbrokes first (better pricing),
    # then TAB for meetings Ladbrokes doesn't have (e.g. NZ meetings)
    all_lad_jockey_names = {normalise_name(m["meeting_name"]) for m in api_jockey}
    all_lad_driver_names = {normalise_name(m["meeting_name"]) for m in api_driver}
    tab_only_jockey = [m for m in tab_jockey if normalise_name(m["meeting_name"]) not in all_lad_jockey_names]
    tab_only_driver = [m for m in tab_driver if normalise_name(m["meeting_name"]) not in all_lad_driver_names]
    jockey_to_seed = api_jockey + tab_only_jockey
    driver_to_seed = api_driver + tab_only_driver

    if jockey_to_seed or driver_to_seed:
        _seed_from_api(db, jockey_to_seed, driver_to_seed)
    else:
        logger.critical(
            "NO CHALLENGE MEETINGS FOUND from any source. "
            "No meetings will be created — dashboard will show empty state. "
            "Check TAB scraper and Ladbrokes API connectivity."
        )
        # Do NOT seed hardcoded fake meetings — they cause fake data in the UI
        return

    # NOTE: _seed_tab_meetings disabled — it creates meetings from TAB data that don't
    # exist in Ladbrokes. These meetings can never get race results (ingestor uses Ladbrokes API)
    # and get stuck at 0/N completed races forever. All real challenge meetings are already
    # seeded from the Ladbrokes API (filtered by TAB-known names above).

    # NOTE: _seed_driver_meetings_from_listing removed — it created fake driver meetings
    # from TAB race listings that weren't real challenges. Only Ladbrokes API meetings
    # are real jockey/driver challenges.


def _seed_driver_meetings_from_listing(db: Session):
    """Create harness driver meetings from TAB racing listing even without prices."""
    from time_utils import today_aus
    from scrapers.tab import _get_todays_meetings, _get_client, BASE
    import re

    aus_date = today_aus()
    existing = {normalise_name(m.name) for m in db.query(Meeting).filter(Meeting.date == aus_date, Meeting.type == "driver").all()}
    todays = _get_todays_meetings()
    if not todays:
        return

    counter = db.query(Meeting).count()
    now_aus = datetime.now(AU_TZ)
    client = _get_client()

    for mtg in todays:
        if mtg["type"] != "driver":
            continue
        if normalise_name(mtg["meeting_name"]) in existing:
            continue

        # Scrape race pages to discover driver names
        driver_names = set()
        for ri in mtg["races"]:
            rn = ri["race_number"]
            url = f"{BASE}/racing/{aus_date}/{mtg['meeting_id'].lower()}/{rn}"
            try:
                r = client.get(url)
                if r.status_code != 200:
                    continue
                pattern = re.compile(r'var model = ({.*?});\s*\n', re.DOTALL)
                m = pattern.search(r.text)
                if not m:
                    continue
                model = json.loads(m.group(1))
                starters = model.get("allStarters", [])
                if not starters:
                    legs = model.get("pool", {}).get("legs", [])
                    if legs:
                        starters = legs[0].get("starters", [])
                for s in starters:
                    if s.get("isScratched") or s.get("isFobScratched"):
                        continue
                    driver = (s.get("associatedName") or s.get("rider") or "").strip()
                    if not driver or driver.lower() in ("unknown", "n/a", "not declared", "n.r", "nr", "not riding", "scratching", ""):
                        continue
                    driver_names.add(driver.title())
            except Exception:
                continue

        if not driver_names:
            logger.info(f"Discovered driver meeting {mtg['meeting_name']} but no participants found yet")
            # Still create the meeting — participants will populate when prices become available
            driver_names.add("Unknown")

        counter += 1
        mid = f"m{counter}"
        total_races = len(mtg["races"])
        meeting = Meeting(
            id=mid, name=mtg["meeting_name"], date=aus_date,
            status=MeetingStatus.UPCOMING.value, type="driver",
            total_races=total_races, completed_races=0,
            scheduled_time=datetime(now_aus.year, now_aus.month, now_aus.day, 17, 30, 0, tzinfo=AU_TZ),
        )
        db.add(meeting)
        db.flush()

        for name in driver_names:
            if name == "Unknown":
                continue
            pid = f"{mid}_{name.lower().replace(' ', '_')}"
            db.add(Participant(
                id=pid, meeting_id=mid, name=name,
                current_points=0, completed_races=0, remaining_races=total_races,
            ))
            db.flush()

        existing.add(normalise_name(mtg["meeting_name"]))
        logger.info(f"Created driver meeting {mtg['meeting_name']} with {len(driver_names)} participants")

    db.commit()


def _seed_from_api(db: Session, api_jockey: list, api_driver: list):
    now = datetime.now(timezone.utc)
    aus_date = today_aus()
    now_aus = datetime.now(AU_TZ)
    counter = 0
    meeting_races_map = {}

    # Skip meetings that already exist in DB for today
    existing_names = {normalise_name(m.name) for m in db.query(Meeting).filter(Meeting.date == aus_date).all()}
    # Start counter from max existing numeric ID to avoid collisions
    existing_ids = [m.id for m in db.query(Meeting).all()]
    max_num = 0
    for eid in existing_ids:
        try:
            num = int(eid.lstrip('m'))
            max_num = max(max_num, num)
        except (ValueError, AttributeError):
            pass
    counter = max_num

    for market_list, mtype in [(api_jockey, "jockey"), (api_driver, "driver")]:
        for market in market_list:
            meeting_name = market["meeting_name"]
            if normalise_name(meeting_name) in existing_names:
                logger.debug(f"Skipping {meeting_name} — already in DB")
                continue
            counter += 1
            mid = f"m{counter}"
            participants = market.get("participants", [])

            total_races = market.get("total_races", 0)
            if total_races <= 0:
                races = market.get("races", [])
                total_races = len([r for r in races if r.get("race_number", 0) > 0])
                if total_races <= 0:
                    logger.info(
                        f"Meeting {meeting_name}: no race count from API yet, "
                        f"creating meeting anyway (race data may arrive later)"
                    )
                    total_races = 10

            def _parse_dt(s: str) -> datetime | None:
                try:
                    return datetime.fromisoformat(s)
                except (ValueError, TypeError):
                    pass
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                            "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S.%f"):
                    try:
                        return datetime.strptime(s, fmt)
                    except (ValueError, TypeError):
                        continue
                try:
                    return datetime.fromtimestamp(int(s), tz=AU_TZ)
                except (ValueError, TypeError, OSError):
                    pass
                return None

            races = market.get("races", [])
            scheduled = None
            if races:
                st = races[0].get("start_time", "")
                if st:
                    scheduled = _parse_dt(st)
            if scheduled is None:
                from datetime import date as _date
                try:
                    _d = datetime.strptime(aus_date, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    _d = today_aus()
                scheduled = datetime(_d.year, _d.month, _d.day, 17, 30, 0, tzinfo=AU_TZ)

            meeting = Meeting(
                id=mid,
                name=meeting_name,
                date=aus_date,
                status=MeetingStatus.UPCOMING.value,
                type=mtype,
                total_races=total_races,
                completed_races=0,
                scheduled_time=scheduled,
            )
            db.add(meeting)
            db.flush()
            meeting_races_map[mid] = races

            # Deduplicate participants by name (API sometimes returns duplicates)
            seen_pids = set()
            for i, p in enumerate(participants):
                pid = f"{mid}_{p['name'].lower().replace(' ', '_')}"
                if pid in seen_pids:
                    continue
                seen_pids.add(pid)
                participant = Participant(
                    id=pid,
                    meeting_id=mid,
                    name=p["name"],
                    current_points=0,
                    completed_races=0,
                    remaining_races=total_races,
                )
                db.add(participant)
                db.flush()

                race_odds = p.get("race_odds", {})
                db.add(Price(
                        participant_id=pid,
                        meeting_id=mid,
                        bookmaker_name="Ladbrokes",
                        price=round(max(MIN_PRICE, min(MAX_PRICE, p["price"])), 2),
                        race_odds_json=json.dumps(race_odds) if race_odds else None,
                        timestamp=now,
                    ))

    db.commit()
    _simulate_live_data(db, meeting_races_map)
    logger.info(f"Seeded {counter} meetings from API data")


def _seed_tab_meetings(db: Session, tab_jockey: list, tab_driver: list):
    """Seed meetings from TAB/TABtouch jockey challenges if they don't already exist."""
    from time_utils import today_aus
    aus_date = today_aus()
    now = datetime.now(timezone.utc)
    now_aus = datetime.now(AU_TZ)

    existing_names = {normalise_name(m.name) for m in db.query(Meeting).filter(Meeting.date == aus_date).all()}
    counter = db.query(Meeting).count()

    for market_list, mtype in [(tab_jockey, "jockey"), (tab_driver, "driver")]:
        for market in market_list:
            meeting_name = market["meeting_name"]
            if normalise_name(meeting_name) in existing_names:
                continue

            counter += 1
            mid = f"m{counter}"
            total_races = market.get("total_races", 0)
            if total_races <= 0:
                total_races = 8
                logger.warning(f"TAB meeting {meeting_name}: no race count, defaulting to 8")
            participants = market.get("participants", [])

            meeting = Meeting(
                id=mid,
                name=meeting_name,
                date=aus_date,
                status=MeetingStatus.UPCOMING.value,
                type=mtype,
                total_races=total_races,
                completed_races=0,
                scheduled_time=datetime(now_aus.year, now_aus.month, now_aus.day, 17, 30, 0, tzinfo=AU_TZ),
            )
            db.add(meeting)
            db.flush()

            seen_pids = set()
            for p in participants:
                pid = f"{mid}_{p['name'].lower().replace(' ', '_')}"
                if pid in seen_pids:
                    continue
                seen_pids.add(pid)
                participant = Participant(
                    id=pid,
                    meeting_id=mid,
                    name=p["name"],
                    current_points=0,
                    completed_races=0,
                    remaining_races=total_races,
                )
                db.add(participant)
                db.flush()

                race_odds = p.get("race_odds", {})
                db.add(Price(
                    participant_id=pid,
                    meeting_id=mid,
                    bookmaker_name="TAB",
                    price=round(max(MIN_PRICE, min(MAX_PRICE, p["price"])), 2),
                    race_odds_json=json.dumps(race_odds) if race_odds else None,
                    timestamp=now,
                ))

            existing_names.add(normalise_name(meeting_name))
            logger.info(f"Seeded TAB meeting: {meeting_name} ({len(participants)} participants)")

    db.commit()


def _get_real_race_positions(race_data: dict, participants: list, price_map: dict = None):
    if not race_data or race_data.get("status") not in ("Final", "Interim"):
        return None

    placed = []
    used_pids = set()
    unmatched_results = []

    def _try_match(candidate_name, pos, debug_context=""):
        if not candidate_name:
            return None
        candidate_name = candidate_name.strip()
        for p in participants:
            if p.id in used_pids:
                continue
            if names_match(p.name, candidate_name):
                placed.append((p, pos))
                used_pids.add(p.id)
                return p
        for p in participants:
            if p.id in used_pids:
                continue
            if names_lastname_fallback(p.name, candidate_name):
                placed.append((p, pos))
                used_pids.add(p.id)
                return p
        return None

    def _extract_jockey_from_runner(runner):
        for field in ("jockey", "rider", "jockey_name", "driver", "driver_name",
                       "licence_name", "person_name", "athlete_name"):
            val = runner.get(field)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return None

    def _extract_jockey_from_result(res):
        comp = res.get("competitor") if isinstance(res.get("competitor"), dict) else {}
        for field in ("jockey", "rider", "driver", "name", "jockey_name", "driver_name"):
            val = comp.get(field)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        for field in ("jockey", "rider", "driver"):
            val = res.get(field)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return None

    def _norm_rn(val):
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return str(val).strip()

    runner_map_norm = {}
    competitor_map_norm = {}
    raw_runners = []
    for runner in race_data.get("runners", []):
        raw_rn = runner.get("runner_number")
        rn = _norm_rn(raw_rn)
        if rn is None:
            continue
        jn = _extract_jockey_from_runner(runner)
        if jn and jn.lower() not in ("unknown", "n/a", "not declared", ""):
            runner_map_norm[rn] = jn
        cn = runner.get("competitor_name") or runner.get("horse_name") or runner.get("horse") or ""
        if not cn:
            comp = runner.get("competitor")
            if isinstance(comp, dict):
                cn = comp.get("name") or comp.get("competitor_name") or ""
        if cn:
            competitor_map_norm[rn] = cn.strip()
        raw_runners.append(runner)

    race_number = race_data.get("race_number", "?")

    for res in race_data.get("results", []):
        pos = res.get("position", 99)
        raw_rn = res.get("runner_number")
        rn = _norm_rn(raw_rn)
        runner_name = runner_map_norm.get(rn) if rn is not None else None
        if runner_name:
            if not _try_match(runner_name, pos, f"runner_map(rn={rn})"):
                unmatched_results.append((rn, pos, runner_name, "runner_map"))
                logger.warning(
                    f"Race {race_number}: Could not match API name '{runner_name}' "
                    f"(rn={rn}, pos={pos}) to any seeded participant"
                )
        else:
            resolved_name = None
            for runner in raw_runners:
                if _norm_rn(runner.get("runner_number")) == rn:
                    resolved_name = _extract_jockey_from_runner(runner)
                    break
            if resolved_name:
                if not _try_match(resolved_name, pos, f"raw_runner(rn={rn})"):
                    unmatched_results.append((rn, pos, resolved_name, "raw_runner"))
                    logger.warning(
                        f"Race {race_number}: Could not match raw runner name '{resolved_name}' "
                        f"(rn={rn}, pos={pos}) to any seeded participant"
                    )
            else:
                resolved_name = _extract_jockey_from_result(res)
                if resolved_name:
                    if not _try_match(resolved_name, pos, f"result_competitor(rn={rn})"):
                        unmatched_results.append((rn, pos, resolved_name, "result_competitor"))
                        logger.warning(
                            f"Race {race_number}: Could not match result name '{resolved_name}' "
                            f"(rn={rn}, pos={pos}) to any seeded participant"
                        )
                else:
                    unmatched_results.append((rn, pos, None, "no_name"))
                    logger.warning(
                        f"Race {race_number}: No jockey/driver name found for rn={rn}, pos={pos}"
                    )

    if unmatched_results:
        retry_count = 0
        for rn, pos, name, source in list(unmatched_results):
            if name:
                for p in participants:
                    if p.id in used_pids:
                        continue
                    if names_lastname_fallback(p.name, name):
                        placed.append((p, pos))
                        used_pids.add(p.id)
                        retry_count += 1
                        unmatched_results = [u for u in unmatched_results if u != (rn, pos, name, source)]
                        break
            else:
                horse_name = competitor_map_norm.get(rn)
                if horse_name:
                    for p in participants:
                        if p.id in used_pids:
                            continue
                        horse_parts = {w for w in horse_name.lower().split() if len(w) >= 3}
                        pname_parts = {w for w in p.name.lower().split() if len(w) >= 3}
                        if horse_parts & pname_parts:
                            placed.append((p, pos))
                            used_pids.add(p.id)
                            retry_count += 1
                            unmatched_results = [u for u in unmatched_results if u != (rn, pos, name, source)]
                            break
        if retry_count:
            logger.info(
                f"Race {race_number}: Retry matched {retry_count} more participants"
            )

    if unmatched_results:
        api_names = [(r[1], r[2]) for r in unmatched_results if r[2]]
        seeded_names = [p.name for p in participants if p.id not in used_pids]
        logger.warning(
            f"Race {race_number}: {len(unmatched_results)} unmatched results: "
            f"api_names={api_names[:5]}, available_seeded={seeded_names[:5]}"
        )

    if placed:
        placed.sort(key=lambda x: x[1])
        return placed

    logger.warning(
        f"Race {race_number}: Could not match any of {len(race_data.get('results',[]))} results "
        f"to {len(participants)} participants."
    )
    return None


def _simulate_live_data(db: Session, meeting_races_map: dict = None):
    """Process meetings using ONLY real API data. Never generate fake results.

    For meetings with real race data from Ladbrokes API: create Result records
    from actual race outcomes. For meetings without API data: leave as UPCOMING
    so the status_manager can fetch results when they become available.
    Only processes today's meetings.
    """
    now_aus = datetime.now(AU_TZ)
    aus_date = today_aus()
    meetings = db.query(Meeting).filter(Meeting.date == aus_date).all()
    for meeting in meetings:
        participants = db.query(Participant).filter(
            Participant.meeting_id == meeting.id
        ).all()

        races_data = (meeting_races_map or {}).get(meeting.id, [])

        # Check if API race data shows any races already completed
        api_has_results = any(
            r.get("status") in ("Final", "Interim") for r in races_data
        ) if races_data else False

        # Determine if meeting should stay UPCOMING
        st = meeting.scheduled_time
        if st is not None:
            if st.tzinfo is None:
                st = st.replace(tzinfo=AU_TZ)
            time_upcoming = now_aus < st
        else:
            time_upcoming = False  # No scheduled time → legacy LIVE assumption
        should_be_upcoming = not api_has_results and time_upcoming

        if should_be_upcoming:
            meeting.status = MeetingStatus.UPCOMING.value
            for p in participants:
                p.current_points = 0
                p.completed_races = 0
                p.remaining_races = meeting.total_races
            db.query(Result).filter(Result.meeting_id == meeting.id).delete()
            db.commit()
            continue

        if not races_data:
            existing_results = db.query(Result).filter(Result.meeting_id == meeting.id).count()
            if existing_results > 0:
                logger.info(
                    f"Meeting {meeting.name}: no API race data but has {existing_results} results — keeping"
                )
                continue
            meeting.status = MeetingStatus.UPCOMING.value
            for p in participants:
                p.current_points = 0
                p.completed_races = 0
                p.remaining_races = meeting.total_races
            logger.info(
                f"Meeting {meeting.name}: no API race data, set to UPCOMING "
                f"(status_manager will fetch results when available)"
            )
            db.commit()
            continue

        # API-seeded meeting: determine completed races from real status
        completed = [r for r in races_data if r.get("status") in ("Final", "Interim")]
        initial = max((r.get("race_number", 0) for r in completed), default=0)

        if initial == 0:
            # No completed races yet — set to LIVE with 0 completed
            meeting.status = MeetingStatus.LIVE.value
            meeting.completed_races = 0
            db.commit()
            continue

        meeting.status = MeetingStatus.LIVE.value
        meeting.completed_races = initial

        # Delete any stale results before re-creating
        db.query(Result).filter(Result.meeting_id == meeting.id).delete()

        cumulative_points = {p.id: 0 for p in participants}
        race_counts = {p.id: 0 for p in participants}
        price_map = {}
        try:
            pids = [p.id for p in participants]
            price_rows = db.query(Price).filter(
                Price.participant_id.in_(pids),
                Price.bookmaker_name == "Ladbrokes",
            ).all()
            price_map = {pr.participant_id: pr.price for pr in price_rows}
        except Exception as e:
            logger.warning(f"Could not load price_map for meeting {meeting.name}: {e}")

        # Load Ladbrokes race_odds_json for determining who declared in each race
        lad_price_rows = db.query(Price).filter(
            Price.meeting_id == meeting.id,
            Price.bookmaker_name == "Ladbrokes",
        ).all()
        lad_odds_by_pid = {}
        for lpr in lad_price_rows:
            if lpr.race_odds_json:
                try:
                    lad_odds_by_pid[lpr.participant_id] = json.loads(lpr.race_odds_json)
                except (json.JSONDecodeError, ValueError):
                    lad_odds_by_pid[lpr.participant_id] = {}

        for race_info in sorted(completed, key=lambda x: x.get("race_number", 0)):
            rn = race_info.get("race_number")
            real_positions = _get_real_race_positions(race_info, participants, price_map)
            placed_ids = set()
            if real_positions:
                race_positions = [pos for _, pos in real_positions]
                for p, pos in real_positions:
                    added = race_points(pos, race_positions)
                    cumulative_points[p.id] += added
                    race_counts[p.id] += 1
                    placed_ids.add(p.id)
                    result = Result(
                        meeting_id=meeting.id,
                        participant_id=p.id,
                        final_points=cumulative_points[p.id],
                        position=pos,
                        race_number=rn,
                        points_added=added,
                        timestamp=datetime.now(timezone.utc),
                    )
                    db.add(result)
            # Determine which participants have Ladbrokes odds for this race
            odds_declared_pids = set()
            for pid, race_odds in lad_odds_by_pid.items():
                if isinstance(race_odds, dict):
                    for k in race_odds.keys():
                        if int(k) == rn:
                            odds_declared_pids.add(pid)
                            break
            # Create result records for participants with odds but not yet matched
            for p in participants:
                if p.id in placed_ids:
                    continue
                if p.id in odds_declared_pids:
                    race_counts[p.id] += 1
                    result = Result(
                        meeting_id=meeting.id,
                        participant_id=p.id,
                        final_points=cumulative_points[p.id],
                        position=99,
                        race_number=rn,
                        points_added=0,
                        timestamp=datetime.now(timezone.utc),
                    )
                    db.add(result)

        for p in participants:
            p.current_points = cumulative_points[p.id]
            p.completed_races = race_counts[p.id]
            p.remaining_races = meeting.total_races - race_counts[p.id]

        db.commit()
