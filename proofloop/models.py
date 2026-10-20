from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_answer: Mapped[str] = mapped_column(Text, nullable=False)
    current_answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    decision_status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    sources: Mapped[list["Source"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    claims: Mapped[list["Claim"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    revisions: Mapped[list["Revision"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    runs: Mapped[list["VerificationRun"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    decisions: Mapped[list["HumanDecision"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    events: Mapped[list["AuditEvent"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship(back_populates="sources")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship(back_populates="claims")


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    parent_revision_id: Mapped[str] = mapped_column(String(32), nullable=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    revision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship(back_populates="revisions")


class VerificationRun(Base):
    __tablename__ = "verification_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    revision_id: Mapped[str] = mapped_column(String(32), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    results_json: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship(back_populates="runs")


class HumanDecision(Base):
    __tablename__ = "human_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    revision_id: Mapped[str] = mapped_column(String(32), nullable=True)
    verification_run_id: Mapped[str] = mapped_column(String(32), nullable=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship(back_populates="decisions")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    event_data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship(back_populates="events")
