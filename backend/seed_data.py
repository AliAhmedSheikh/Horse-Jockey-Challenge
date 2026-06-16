from datetime import datetime, timezone, timedelta
import random
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
                logger.info(f"Database already has {today_count} meetings for today ({today}) with {participant_count} participants")
                return
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

    logger.info("Seeding database with Ladbrokes API data...")
    api = LadbrokesAPIScraper()
    api_jockey = api.fetch_jockey_challenge_meetings()
    api_driver = api.fetch_driver_challenge_meetings()
    api.close()
    invalidate_cache()

    if api_jockey or api_driver:
        _seed_from_api(db, api_jockey, api_driver)
    else:
        logger.critical(
            "LADBROKES API RETURNED NO DATA — USING HARDCODED FALLBACK. "
            "All data shown is SYNTHETIC (fake meetings, fake participants, fake prices). "
            "Check network connectivity and API availability."
        )
        _seed_from_fallback(db)


def _seed_from_api(db: Session, api_jockey: list, api_driver: list):
    now = datetime.now(timezone.utc)
    aus_date = today_aus()
    now_aus = datetime.now(AU_TZ)
    counter = 0
    meeting_races_map = {}

    for market_list, mtype in [(api_jockey, "jockey"), (api_driver, "driver")]:
        for market in market_list:
            counter += 1
            mid = f"m{counter}"
            meeting_name = market["meeting_name"]
            participants = market.get("participants", [])

            total_races = market.get("total_races", 8)

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
                scheduled = now_aus + timedelta(hours=1 + counter)

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

            for i, p in enumerate(participants):
                pid = f"{mid}_{p['name'].lower().replace(' ', '_')}"
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

                db.add(Price(
                        participant_id=pid,
                        meeting_id=mid,
                        bookmaker_name="Ladbrokes",
                        price=round(max(MIN_PRICE, min(MAX_PRICE, p["price"])), 2),
                        timestamp=now,
                    ))

    db.commit()
    _simulate_live_data(db, meeting_races_map)
    logger.info(f"Seeded {counter} meetings from API data")


def _seed_from_fallback(db: Session):
    aus_date = today_aus()
    now_utc = datetime.now(timezone.utc)
    now_aus = datetime.now(AU_TZ)
    # Assign staggered times relative to now: some past (live), some future (upcoming)
    # Offsets in hours: -3, -1, +1, +3, +5, +7
    time_offsets = [-3, -1, 1, 3, 5, 7]
    for i, meeting_data in enumerate(ALL_MEETINGS):
        offset_h = time_offsets[i] if i < len(time_offsets) else i * 2
        scheduled = now_aus + timedelta(hours=offset_h)
        meeting = Meeting(
            id=meeting_data["id"],
            name=meeting_data["name"],
            date=aus_date,
            status=MeetingStatus.UPCOMING.value,
            type=meeting_data["type"],
            total_races=meeting_data["total_races"],
            completed_races=0,
            scheduled_time=scheduled,
        )
        db.add(meeting)
        db.flush()

        for p_data in meeting_data["participants"]:
            pid = f"{meeting_data['id']}_{p_data['name'].lower().replace(' ', '_')}"
            price_variation = random.uniform(-0.3, 0.3)
            bookmaker_price = round(p_data["price"] * (1 + price_variation), 2)
            if bookmaker_price < 1.5:
                bookmaker_price = 1.5 + random.uniform(0, 2)

            participant = Participant(
                id=pid,
                meeting_id=meeting.id,
                name=p_data["name"],
                current_points=0,
                completed_races=0,
                remaining_races=meeting_data["total_races"],
            )
            db.add(participant)
            db.flush()

            db.add(Price(
                    participant_id=participant.id,
                    meeting_id=meeting.id,
                    bookmaker_name="Ladbrokes",
                    price=round(max(MIN_PRICE, min(MAX_PRICE, bookmaker_price)), 2),
                    timestamp=now_utc,
                ))

    db.commit()

    _simulate_live_data(db)


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
                        horse_parts = set(horse_name.lower().split())
                        pname_parts = set(p.name.lower().split())
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
    now_aus = datetime.now(AU_TZ)
    meetings = db.query(Meeting).all()
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

        if races_data:
            # API-seeded meeting: determine completed races from real status
            completed = [r for r in races_data if r.get("status") in ("Final", "Interim")]
            initial = max((r.get("race_number", 0) for r in completed), default=0)
            use_real = True
        else:
            # Fallback meeting: random initial simulation
            initial = min(random.randint(2, 6), meeting.total_races)
            completed = []
            use_real = False

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

        if use_real:
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
                            timestamp=datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 30)),
                        )
                        db.add(result)
                for p in participants:
                    if p.id not in placed_ids:
                        result = Result(
                            meeting_id=meeting.id,
                            participant_id=p.id,
                            final_points=cumulative_points[p.id],
                            position=99,
                            race_number=rn,
                            points_added=0,
                            timestamp=datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 30)),
                        )
                        db.add(result)
        else:
            for rn in range(1, initial + 1):
                shuffled = utils_weighted_shuffle(participants, db, meeting.id) if meeting.total_races > 0 else list(participants)
                riders = min(len(shuffled), random.randint(3, max(3, meeting.total_races)))
                for pos, p in enumerate(shuffled, 1):
                    if pos <= riders:
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
                        )
                    else:
                        result = Result(
                            meeting_id=meeting.id,
                            participant_id=p.id,
                            final_points=cumulative_points[p.id],
                            position=99,
                            race_number=rn,
                            points_added=0,
                        )
                    db.add(result)

        for p in participants:
            p.current_points = cumulative_points[p.id]
            p.completed_races = race_counts[p.id]
            p.remaining_races = meeting.total_races - race_counts[p.id]

        db.commit()
