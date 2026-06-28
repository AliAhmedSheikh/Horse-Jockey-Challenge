"""Centralized identity resolution for meetings, participants, and races.

All name matching and identity resolution goes through here.
Provides canonical keys for deduplication and cross-source matching.

Canonical key format:
  meeting:   normalise_name(name) + "|" + date + "|" + type
  participant: normalise_name(name) + "|" + meeting_canonical_key
  race:      meeting_canonical_key + "|race|" + str(race_number)
"""
import hashlib
import logging
import re
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from utils import normalise_name, names_match, names_lastname_fallback

logger = logging.getLogger(__name__)


def _strip_parens(name: str) -> str:
    return re.sub(r'\s*\([^)]*\)', '', name).strip()


def canonical_meeting_key(name: str, date: str, meeting_type: str) -> str:
    """Canonical key for a meeting: name|date|type."""
    norm = normalise_name(_strip_parens(name))
    return f"{norm}|{date}|{meeting_type}"


def canonical_participant_key(name: str, meeting_key: str) -> str:
    """Canonical key for a participant within a meeting."""
    norm = normalise_name(_strip_parens(name))
    return f"{norm}|{meeting_key}"


def canonical_race_key(meeting_key: str, race_number: int) -> str:
    """Canonical key for a race within a meeting."""
    return f"{meeting_key}|race|{race_number}"


def external_id_hash(source: str, source_id: str) -> str:
    """Hash an external ID for storage."""
    return hashlib.sha256(f"{source}:{source_id}".encode()).hexdigest()[:16]


class MeetingResolver:
    """Resolve meetings across different data sources (TAB, Ladbrokes, etc)."""

    def __init__(self, db: Session):
        self.db = db
        self._cache = {}  # canonical_key -> Meeting

    def find_meeting(self, name: str, date: str, meeting_type: str = None) -> Optional['Meeting']:
        """Find an existing meeting by name and date."""
        from models import Meeting
        key = canonical_meeting_key(name, date, meeting_type or "")
        if key in self._cache:
            return self._cache[key]

        norm = normalise_name(name)
        query = self.db.query(Meeting).filter(
            Meeting.date == date,
        )
        if meeting_type:
            query = query.filter(Meeting.type == meeting_type)

        for m in query.all():
            if normalise_name(m.name) == norm:
                self._cache[key] = m
                return m
            # Bidirectional substring match
            mn = normalise_name(m.name)
            if norm in mn or mn in norm:
                self._cache[key] = m
                return m
        return None

    def get_all_for_date(self, date: str) -> list:
        """Get all meetings for a date."""
        from models import Meeting
        return self.db.query(Meeting).filter(Meeting.date == date).all()


class ParticipantResolver:
    """Resolve participants within meetings across different data sources."""

    def __init__(self, db: Session):
        self.db = db
        self._cache = {}  # canonical_key -> Participant

    def find_participant(self, name: str, meeting_key: str) -> Optional['Participant']:
        """Find an existing participant by name within a meeting context."""
        from models import Participant
        key = canonical_participant_key(name, meeting_key)
        if key in self._cache:
            return self._cache[key]

        norm = normalise_name(name)

        # Extract meeting_id from meeting_key (format: "norm_name|date|type")
        meeting_norm = meeting_key.split("|")[0]
        meeting_date = meeting_key.split("|")[1] if "|" in meeting_key else ""

        from models import Meeting
        meetings = self.db.query(Meeting).filter(Meeting.date == meeting_date).all()

        for meeting in meetings:
            if normalise_name(meeting.name) != meeting_norm and \
               normalise_name(meeting.name) not in norm and \
               norm not in normalise_name(meeting.name):
                continue

            for p in self.db.query(Participant).filter(
                Participant.meeting_id == meeting.id
            ).all():
                if names_match(p.name, name):
                    self._cache[key] = p
                    return p
                if names_lastname_fallback(p.name, name):
                    self._cache[key] = p
                    return p
        return None

    def find_participant_in_meeting(self, name: str, meeting_id: str) -> Optional['Participant']:
        """Find participant directly within a specific meeting ID."""
        from models import Participant
        cache_key = f"{name}|{meeting_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        for p in self.db.query(Participant).filter(
            Participant.meeting_id == meeting_id
        ).all():
            if names_match(p.name, name):
                self._cache[cache_key] = p
                return p
            if names_lastname_fallback(p.name, name):
                self._cache[cache_key] = p
                return p
        return None


class RaceResolver:
    """Resolve race data from external sources with caching."""

    def __init__(self, db: Session):
        self.db = db

    def get_completed_race_numbers(self, meeting_id: str) -> set:
        """Get set of race numbers that already have results in DB."""
        from models import Result
        results = self.db.query(Result.race_number).filter(
            Result.meeting_id == meeting_id
        ).distinct().all()
        return {r[0] for r in results}

    def get_next_race(self, meeting_id: str, total_races: int) -> Optional[int]:
        """Get the next race number to process, or None if all done."""
        completed = self.get_completed_race_numbers(meeting_id)
        for rn in range(1, total_races + 1):
            if rn not in completed:
                return rn
        return None

    def is_race_complete(self, meeting_id: str, race_number: int) -> bool:
        """Check if a race already has results."""
        from models import Result
        count = self.db.query(Result).filter(
            Result.meeting_id == meeting_id,
            Result.race_number == race_number,
        ).count()
        return count > 0
