from datetime import datetime, timezone, timedelta
import random
import logging

from sqlalchemy.orm import Session
from models import Meeting, Participant, Price, Result, MeetingStatus, MeetingType
from scrapers.base import LadbrokesAPIScraper, invalidate_cache
from time_utils import today_aus

MIN_PRICE = 1.50

def _weighted_shuffle(participants, db, meeting_id):
    """Sort participants by Ladbrokes price with randomness, so favorites perform better."""
    shuffled = list(participants)
    weights = {}
    for p in shuffled:
        price_row = db.query(Price).filter(
            Price.participant_id == p.id,
            Price.bookmaker_name == "Ladbrokes",
        ).first()
        price = price_row.price if price_row else 3.0
        weight = 1.0 / max(price, MIN_PRICE)
        weight *= random.uniform(0.6, 1.4)
        weights[p.id] = weight
    shuffled.sort(key=lambda p: weights[p.id], reverse=True)
    return shuffled

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

BOOKMAKERS = ["Ladbrokes", "TAB", "Sportsbet", "PointsBet", "TABtouch"]


def _compute_value_rating(bookmaker_price: float, ai_price: float) -> str:
    if bookmaker_price == 0 or ai_price == 0:
        return "Neutral"
    overlay = (bookmaker_price - ai_price) / ai_price * 100
    if overlay > 15:
        return "Strong Value"
    elif overlay > 5:
        return "Value"
    elif overlay > -5:
        return "Neutral"
    else:
        return "Avoid"


def _compute_status(bookmaker_price: float, ai_price: float) -> str:
    rating = _compute_value_rating(bookmaker_price, ai_price)
    if rating in ("Strong Value", "Value"):
        return "value"
    elif rating == "Neutral":
        return "neutral"
    else:
        return "avoid"


def seed_database(db: Session):
    existing = db.query(Meeting).count()
    today = today_aus()
    if existing > 0:
        today_count = db.query(Meeting).filter(Meeting.date == today).count()
        if today_count > 0:
            logger.info(f"Database already has {today_count} meetings for today ({today})")
            return
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
        logger.warning("API returned no data, using fallback seed data")
        _seed_from_fallback(db)


def _seed_from_api(db: Session, api_jockey: list, api_driver: list):
    now = datetime.now(timezone.utc)
    aus_date = today_aus()
    counter = 0
    meeting_races_map = {}

    for market_list, mtype in [(api_jockey, "jockey"), (api_driver, "driver")]:
        for market in market_list:
            counter += 1
            mid = f"m{counter}"
            meeting_name = market["meeting_name"]
            participants = market.get("participants", [])

            total_races = market.get("total_races", 8)
            meeting = Meeting(
                id=mid,
                name=meeting_name,
                date=aus_date,
                status=MeetingStatus.UPCOMING.value,
                type=mtype,
                total_races=total_races,
                completed_races=0,
            )
            db.add(meeting)
            db.flush()
            meeting_races_map[mid] = market.get("races", [])

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

                for bm in ["Ladbrokes", "TAB", "Sportsbet", "PointsBet", "TABtouch"]:
                    variation = 0.0 if bm == "Ladbrokes" else random.uniform(-0.12, 0.12)
                    bm_price = round(max(p["price"] * (1 + variation), 1.5), 2)
                    db.add(Price(
                        participant_id=pid,
                        meeting_id=mid,
                        bookmaker_name=bm,
                        price=bm_price,
                        timestamp=now,
                    ))

    db.commit()
    _simulate_live_data(db, meeting_races_map)
    logger.info(f"Seeded {counter} meetings from API data")


def _seed_from_fallback(db: Session):
    aus_date = today_aus()
    for meeting_data in ALL_MEETINGS:
        now = datetime.now(timezone.utc)
        meeting = Meeting(
            id=meeting_data["id"],
            name=meeting_data["name"],
            date=aus_date,
            status=MeetingStatus.UPCOMING.value,
            type=meeting_data["type"],
            total_races=meeting_data["total_races"],
            completed_races=0,
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

            for bm in BOOKMAKERS:
                bm_variation = random.uniform(-0.15, 0.15)
                bm_price = round(bookmaker_price * (1 + bm_variation), 2)
                if bm_price < 1.5:
                    bm_price = 1.5 + random.uniform(0, 1)
                price = Price(
                    participant_id=participant.id,
                    meeting_id=meeting.id,
                    bookmaker_name=bm,
                    price=bm_price,
                    timestamp=now,
                )
                db.add(price)

    db.commit()

    _simulate_live_data(db)


def _get_real_race_positions(race_data: dict, participants: list):
    """Map Ladbrokes race results to challenge participants.

    Returns sorted list of (participant, position) or None if no real results.
    """
    if not race_data or race_data.get("status") not in ("Final", "Interim"):
        return None

    runner_map = {}
    for runner in race_data.get("runners", []):
        rn = runner.get("runner_number")
        jn = (runner.get("jockey") or "").strip() or (runner.get("driver") or "").strip()
        if rn and jn and jn.lower() not in ("unknown", "n/a", "not declared"):
            runner_map[rn] = jn.strip().lower()

    participant_map = {p.name.strip().lower(): p for p in participants}

    placed = []
    for res in race_data.get("results", []):
        pos = res.get("position", 99)
        jockey_name = runner_map.get(res.get("runner_number"))
        if jockey_name and jockey_name in participant_map:
            placed.append((participant_map[jockey_name], pos))

    if not placed:
        return None

    placed.sort(key=lambda x: x[1])
    return placed


def _simulate_live_data(db: Session, meeting_races_map: dict = None):
    meetings = db.query(Meeting).all()
    for meeting in meetings:
        participants = db.query(Participant).filter(
            Participant.meeting_id == meeting.id
        ).all()

        races_data = (meeting_races_map or {}).get(meeting.id, [])

        if races_data:
            # API-seeded meeting: determine completed races from real status
            completed = [r for r in races_data if r.get("status") in ("Final", "Interim")]
            initial = len(completed)
            use_real = True
        else:
            # Fallback meeting: random initial simulation
            initial = min(random.randint(2, 6), meeting.total_races)
            completed = []
            use_real = False

        meeting.status = MeetingStatus.LIVE.value
        meeting.completed_races = initial

        cumulative_points = {p.id: 0 for p in participants}
        race_counts = {p.id: 0 for p in participants}

        def race_points(pos, all_pos=None):
            if pos > 3:
                return 0
            base = {1: 3, 2: 2, 3: 1}[pos]
            if not all_pos:
                return base
            count = sum(1 for p in all_pos if p == pos)
            if count > 1:
                total = sum({1: 3, 2: 2, 3: 1}.get(pos + i, 0) for i in range(count))
                return total / count
            return base

        if use_real:
            for race_info in sorted(completed, key=lambda x: x.get("race_number", 0)):
                rn = race_info.get("race_number")
                real_positions = _get_real_race_positions(race_info, participants)
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
                shuffled = _weighted_shuffle(participants, db, meeting.id) if meeting.total_races > 0 else list(participants)
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
                        timestamp=datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 30)),
                    )
                    db.add(result)

        for p in participants:
            p.current_points = cumulative_points[p.id]
            p.completed_races = race_counts[p.id]
            p.remaining_races = meeting.total_races - race_counts[p.id]

        db.commit()
