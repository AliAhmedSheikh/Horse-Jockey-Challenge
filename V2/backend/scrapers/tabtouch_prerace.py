import logging
from typing import Dict, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Meeting, Participant, Price, MeetingStatus
from scrapers.tabtouch import _get_jockey_challenge_events, _fetch_jockey_challenge_event, _fetch_event_from_html
from time_utils import today_aus

logger = logging.getLogger(__name__)


def _match_meeting_to_event(meeting: dict, events: list):
    """Match a meeting to a TABtouch event using fuzzy name matching."""
    meeting_name = meeting.name.lower().strip()

    for e in events:
        event_name = e.get("event_name", "").lower().strip()

        if meeting_name == event_name:
            return e

        if meeting_name in event_name or event_name in meeting_name:
            return e

        meeting_words = set(meeting_name.split())
        event_words = set(event_name.split())
        if meeting_words & event_words and len(meeting_words & event_words) >= min(len(meeting_words), len(event_words)):
            return e

    return None


def pull_prerace_odds(db: Session, meeting_id: str, date_str: str) -> int:
    """
    Pull TABtouch pre-race jockey challenge odds for a meeting.
    Returns: number of prices inserted.
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        logger.warning(f"Meeting {meeting_id} not found")
        return 0

    events = _get_jockey_challenge_events(date_str)
    event = _match_meeting_to_event(meeting, events)
    if not event:
        event_names = [e.get("event_name", "") for e in events]
        logger.warning(f"No TABtouch event found for {meeting.name} ({meeting_id}). Available: {event_names}")
        return 0

    event_id = event.get("event_id")
    data = _fetch_jockey_challenge_event(event_id, date_str)
    if not data:
        data = _fetch_event_from_html(event_id, date_str)
    if not data:
        logger.warning(f"No TABtouch data for event {event_id} ({event.get('event_name', '')})")
        return 0

    propositions = data.get("propositions", [])
    if not propositions:
        logger.warning(f"Event {event_id}: no propositions found")
        return 0

    inserted = 0
    for prop in propositions:
        name = (prop.get("name") or "").strip()
        if not name or "/" in name or "Any Other" in name:
            continue

        participant = db.query(Participant).filter(
            Participant.meeting_id == meeting_id,
            Participant.name == name
        ).first()

        if not participant:
            participant = Participant(
                id=f"{meeting_id}_{name}",
                meeting_id=meeting_id,
                name=name
            )
            db.add(participant)
            db.commit()

        price = prop.get("winDividendText") or prop.get("price")
        if not price:
            continue

        try:
            price_float = float(price)
        except (ValueError, TypeError):
            continue

        existing = db.query(Price).filter(
            Price.participant_id == participant.id,
            Price.bookmaker_name == "TABtouch_PreRace"
        ).first()

        if existing:
            existing.price = price_float
            existing.meeting_id = meeting_id
            existing.timestamp = datetime.now(timezone.utc)
        else:
            price_record = Price(
                participant_id=participant.id,
                meeting_id=meeting_id,
                bookmaker_name="TABtouch_PreRace",
                price=price_float
            )
            db.add(price_record)
        inserted += 1

    db.commit()
    logger.info(f"Inserted {inserted} pre-race prices for {meeting.name} ({meeting_id})")
    return inserted


def pull_all_prerace_for_today(db: Session):
    """Pull pre-race odds for all upcoming meetings today."""
    date_str = today_aus()

    meetings = db.query(Meeting).filter(
        Meeting.date == date_str,
        Meeting.status == MeetingStatus.UPCOMING.value
    ).all()

    total = 0
    for meeting in meetings:
        count = pull_prerace_odds(db, meeting.id, date_str)
        total += count

    logger.info(f"Pre-race: {total} prices pulled for {len(meetings)} meetings")
    return total
