from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from database import Base


class MeetingStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    LIVE = "live"
    FINISHED = "finished"


class MeetingType(str, enum.Enum):
    JOCKEY = "jockey"
    DRIVER = "driver"


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    date = Column(String, nullable=False)
    status = Column(String, default=MeetingStatus.UPCOMING.value)
    type = Column(SAEnum(MeetingType), nullable=False)
    total_races = Column(Integer, default=0)
    completed_races = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    participants = relationship("Participant", back_populates="meeting", cascade="all, delete-orphan")
    prices = relationship("Price", back_populates="meeting", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="meeting", cascade="all, delete-orphan")


class Participant(Base):
    __tablename__ = "participants"

    id = Column(String, primary_key=True)
    meeting_id = Column(String, ForeignKey("meetings.id"), nullable=False)
    name = Column(String, nullable=False)
    current_points = Column(Float, default=0.0)
    completed_races = Column(Integer, default=0)
    remaining_races = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    meeting = relationship("Meeting", back_populates="participants")
    prices = relationship("Price", back_populates="participant", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="participant", cascade="all, delete-orphan")


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(String, ForeignKey("participants.id"), nullable=False)
    meeting_id = Column(String, ForeignKey("meetings.id"), nullable=False)
    bookmaker_name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    participant = relationship("Participant", back_populates="prices")
    meeting = relationship("Meeting", back_populates="prices")


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(String, ForeignKey("meetings.id"), nullable=False)
    participant_id = Column(String, ForeignKey("participants.id"), nullable=False)
    final_points = Column(Float, default=0.0)
    position = Column(Integer, nullable=True)
    race_number = Column(Integer, default=0)
    points_added = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    participant = relationship("Participant", back_populates="results")
    meeting = relationship("Meeting", back_populates="results")
