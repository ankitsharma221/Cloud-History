"""SQLAlchemy database models for Cloud Resource Archaeologist."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class DBResource(Base):
    """Stores discovered cloud resources."""
    __tablename__ = "resources"

    id = Column(String(128), primary_key=True, index=True)
    name = Column(String(256), nullable=True, index=True)
    resource_type = Column(String(64), nullable=False, index=True)
    region = Column(String(64), default="us-east-1")
    created_at = Column(DateTime, nullable=True)
    tags_json = Column(Text, default="{}")
    state = Column(String(64), default="running")
    cost_per_month = Column(Float, default=0.0)
    details_json = Column(Text, default="{}")
    attached_to_json = Column(Text, default="[]")
    dependencies_json = Column(Text, default="[]")
    created_in_db = Column(DateTime, default=datetime.utcnow)

    # Relationships
    events = relationship("DBEvent", back_populates="resource", cascade="all, delete-orphan")
    owner = relationship("DBOwner", back_populates="resource", uselist=False, cascade="all, delete-orphan")
    verdicts = relationship("DBRiskVerdict", back_populates="resource", cascade="all, delete-orphan")
    quarantines = relationship("DBQuarantine", back_populates="resource", cascade="all, delete-orphan")

    @property
    def tags(self) -> Dict[str, str]:
        return json.loads(self.tags_json or "{}")

    @tags.setter
    def tags(self, val: Dict[str, str]):
        self.tags_json = json.dumps(val)

    @property
    def details(self) -> Dict[str, Any]:
        return json.loads(self.details_json or "{}")

    @details.setter
    def details(self, val: Dict[str, Any]):
        self.details_json = json.dumps(val)

    @property
    def attached_to(self) -> List[str]:
        return json.loads(self.attached_to_json or "[]")

    @attached_to.setter
    def attached_to(self, val: List[str]):
        self.attached_to_json = json.dumps(val)

    @property
    def dependencies(self) -> List[str]:
        return json.loads(self.dependencies_json or "[]")

    @dependencies.setter
    def dependencies(self, val: List[str]):
        self.dependencies_json = json.dumps(val)


class DBEvent(Base):
    """Stores lifecycle and audit events."""
    __tablename__ = "events"

    id = Column(String(128), primary_key=True, index=True)
    resource_id = Column(String(128), ForeignKey("resources.id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    actor = Column(String(256), nullable=False)
    source = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    metadata_json = Column(Text, default="{}")

    resource = relationship("DBResource", back_populates="events")

    @property
    def metadata_dict(self) -> Dict[str, Any]:
        return json.loads(self.metadata_json or "{}")

    @metadata_dict.setter
    def metadata_dict(self, val: Dict[str, Any]):
        self.metadata_json = json.dumps(val)


class DBOwner(Base):
    """Stores resolved ownership information with ground-truth confirmation."""
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(String(128), ForeignKey("resources.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    name = Column(String(256), nullable=False)
    team = Column(String(256), nullable=True)
    email = Column(String(256), nullable=True)
    confidence = Column(String(32), nullable=False)
    source = Column(String(64), nullable=False)
    explanation = Column(Text, nullable=False)
    confirmed_by_user = Column(Boolean, default=False)
    user_correction = Column(String(256), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resource = relationship("DBResource", back_populates="owner")


class DBRiskVerdict(Base):
    """Stores risk assessment records."""
    __tablename__ = "risk_verdicts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(String(128), ForeignKey("resources.id", ondelete="CASCADE"), index=True, nullable=False)
    risk_level = Column(String(32), nullable=False)
    monthly_savings = Column(Float, default=0.0)
    evidence_for_json = Column(Text, default="[]")
    evidence_against_json = Column(Text, default="[]")
    missing_evidence_json = Column(Text, default="[]")
    verdict_blocked = Column(Boolean, default=False)
    block_reason = Column(Text, nullable=True)
    required_actions_json = Column(Text, default="[]")
    assessed_at = Column(DateTime, default=datetime.utcnow)

    resource = relationship("DBResource", back_populates="verdicts")

    @property
    def evidence_for(self) -> List[str]:
        return json.loads(self.evidence_for_json or "[]")

    @evidence_for.setter
    def evidence_for(self, val: List[str]):
        self.evidence_for_json = json.dumps(val)

    @property
    def evidence_against(self) -> List[str]:
        return json.loads(self.evidence_against_json or "[]")

    @evidence_against.setter
    def evidence_against(self, val: List[str]):
        self.evidence_against_json = json.dumps(val)

    @property
    def missing_evidence(self) -> List[str]:
        return json.loads(self.missing_evidence_json or "[]")

    @missing_evidence.setter
    def missing_evidence(self, val: List[str]):
        self.missing_evidence_json = json.dumps(val)

    @property
    def required_actions(self) -> List[str]:
        return json.loads(self.required_actions_json or "[]")

    @required_actions.setter
    def required_actions(self, val: List[str]):
        self.required_actions_json = json.dumps(val)


class DBQuarantine(Base):
    """Stores reversible decommissioning status and watch history."""
    __tablename__ = "quarantines"

    id = Column(String(128), primary_key=True, index=True)
    resource_id = Column(String(128), ForeignKey("resources.id", ondelete="CASCADE"), index=True, nullable=False)
    status = Column(String(64), default="none")
    initiated_at = Column(DateTime, default=datetime.utcnow)
    approved_by = Column(String(256), nullable=False)
    snapshot_id = Column(String(128), nullable=True)
    previous_state_json = Column(Text, default="{}")
    watch_period_days = Column(Integer, default=14)
    watch_until = Column(DateTime, nullable=True)
    problem_detected = Column(Boolean, default=False)
    problem_details = Column(Text, nullable=True)
    logs_json = Column(Text, default="[]")

    resource = relationship("DBResource", back_populates="quarantines")

    @property
    def previous_state(self) -> Dict[str, Any]:
        return json.loads(self.previous_state_json or "{}")

    @previous_state.setter
    def previous_state(self, val: Dict[str, Any]):
        self.previous_state_json = json.dumps(val)

    @property
    def logs(self) -> List[str]:
        return json.loads(self.logs_json or "[]")

    @logs.setter
    def logs(self, val: List[str]):
        self.logs_json = json.dumps(val)
