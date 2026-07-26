"""SQLAlchemy ORM models for the campaign database layer.

Tables
------
- ``campaigns``          – one record per campaign (single source of truth)
- ``campaign_updates``   – append-only audit log of every WhatsApp change
- ``calendar_days``      – one row per day (Gregorian + Hijri + prayer times)
- ``uploaded_files``     – tracking of imported Excel / calendar files
- ``visitor_questions``  – every visitor question asked to the chatbot

Design notes
------------
- **No separate prayer-times table.**  Prayer times are columns on
  ``calendar_days`` because they belong to each day.
- **Append-only history.**  ``campaign_updates`` never overwrites; every
  modification is a new row.
- **Foreign keys** are enforced via the PRAGMA set in :mod:`db.base`.
- **Timestamps** use timezone-aware UTC datetimes.
- **Unique constraint** on ``campaigns.campaign_name`` prevents duplicates.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, utc_now

# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class TimestampMixin:
    """Provides ``created_at`` / ``updated_at`` columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------


class Campaign(TimestampMixin, Base):
    """A single campaign record.

    This is the **single source of truth** for campaign information.
    WhatsApp conversations update this table (via ``CampaignUpdate``
    rows) and AI answers are always generated from it.
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)

    campaign_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships ---------------------------------------------------------
    updates: Mapped[List["CampaignUpdate"]] = relationship(
        "CampaignUpdate",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignUpdate.created_at.desc()",
    )

    visitor_questions: Mapped[List["VisitorQuestion"]] = relationship(
        "VisitorQuestion",
        back_populates="campaign",
        order_by="VisitorQuestion.created_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("campaign_name", name="uq_campaigns_campaign_name"),
        Index("ix_campaigns_status", "status"),
        Index("ix_campaigns_campaign_type", "campaign_type"),
        Index("ix_campaigns_start_date", "start_date"),
        Index("ix_campaigns_end_date", "end_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Campaign(id={self.id}, campaign_name={self.campaign_name!r}, "
            f"status={self.status!r})>"
        )


# ---------------------------------------------------------------------------
# Campaign Update (append-only audit log)
# ---------------------------------------------------------------------------


class CampaignUpdate(Base):
    """Append-only record of every WhatsApp modification to a campaign.

    History is **never** overwritten.  Each change is a new row capturing
    the old value, new value, source, and the original message text.
    """

    __tablename__ = "campaign_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )

    update_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g. "create", "field_change", "status_change", "note_added"

    changed_field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(50), nullable=False, default="whatsapp")
    # e.g. "whatsapp", "excel_import", "admin"

    message_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The original WhatsApp message that triggered the change.

    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Phone number or identifier of the person who made the change.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships ---------------------------------------------------------
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="updates")

    __table_args__ = (
        Index("ix_campaign_updates_campaign_id", "campaign_id"),
        Index("ix_campaign_updates_update_type", "update_type"),
        Index("ix_campaign_updates_source", "source"),
        Index("ix_campaign_updates_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CampaignUpdate(id={self.id}, campaign_id={self.campaign_id}, "
            f"update_type={self.update_type!r})>"
        )


# ---------------------------------------------------------------------------
# Calendar Day
# ---------------------------------------------------------------------------


class CalendarDay(Base):
    """One row per calendar day.

    This table **replaces** the need for a separate prayer-times table.
    Each day contains its own prayer times, Hijri date, Ramadan / Eid
    flags, Islamic occasions, and public events.
    """

    __tablename__ = "calendar_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    gregorian_date: Mapped[date] = mapped_column(Date, nullable=False)

    hijri_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Stored as "YYYY-MM-DD" (Hijri) for flexibility.

    weekday: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # e.g. "Saturday", "السبت"

    # Prayer times (HH:MM) -------------------------------------------------
    fajr: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    dhuhr: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    asr: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    maghrib: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    isha: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Ramadan / Eid ---------------------------------------------------------
    is_ramadan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ramadan_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_eid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Occasions / events ----------------------------------------------------
    islamic_event: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    public_event: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("gregorian_date", name="uq_calendar_days_gregorian_date"),
        Index("ix_calendar_days_gregorian_date", "gregorian_date"),
        Index("ix_calendar_days_hijri_date", "hijri_date"),
        Index("ix_calendar_days_is_ramadan", "is_ramadan"),
        Index("ix_calendar_days_is_eid", "is_eid"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CalendarDay(id={self.id}, gregorian_date={self.gregorian_date})>"


# ---------------------------------------------------------------------------
# Uploaded File
# ---------------------------------------------------------------------------


class UploadedFile(Base):
    """Track imported files (campaign Excel, calendar file, etc.)."""

    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g. "campaign_excel", "calendar", "campaign_list"

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    imported_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # SHA-256 hex digest to detect duplicate / unchanged re-uploads.

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="imported")
    # e.g. "imported", "failed", "pending"

    __table_args__ = (
        UniqueConstraint("filename", "file_type", name="uq_uploaded_files_filename_type"),
        Index("ix_uploaded_files_file_type", "file_type"),
        Index("ix_uploaded_files_status", "status"),
        Index("ix_uploaded_files_uploaded_at", "uploaded_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UploadedFile(id={self.id}, filename={self.filename!r})>"


# ---------------------------------------------------------------------------
# Visitor Question
# ---------------------------------------------------------------------------


class VisitorQuestion(Base):
    """Store every visitor question asked to the chatbot."""

    __tablename__ = "visitor_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # WhatsApp number if the question came via WhatsApp; ``None`` for web.

    question: Mapped[str] = mapped_column(Text, nullable=False)

    detected_campaign: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Name of the campaign the question was detected to relate to.

    ai_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Optional FK to campaigns (nullable because not every question
    # relates to a campaign).
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships ---------------------------------------------------------
    campaign: Mapped[Optional["Campaign"]] = relationship(
        "Campaign", back_populates="visitor_questions"
    )

    __table_args__ = (
        Index("ix_visitor_questions_phone_number", "phone_number"),
        Index("ix_visitor_questions_answered", "answered"),
        Index("ix_visitor_questions_created_at", "created_at"),
        Index("ix_visitor_questions_campaign_id", "campaign_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VisitorQuestion(id={self.id}, answered={self.answered})>"
        )


# ---------------------------------------------------------------------------
# Campaign Visitor (imported from Excel)
# ---------------------------------------------------------------------------


class CampaignVisitor(TimestampMixin, Base):
    """A visitor imported from the Campaign List Excel file.

    Each row in the uploaded campaign Excel becomes one record here.
    The data is used downstream by WhatsApp Campaign Detection,
    Campaign Update Extraction, AI Context Builder, and Reports.
    """

    __tablename__ = "campaign_visitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)

    visitor_name: Mapped[str] = mapped_column(String(255), nullable=False)

    phone_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )

    __table_args__ = (
        Index("ix_campaign_visitors_phone_number", "phone_number"),
        Index("ix_campaign_visitors_campaign_name", "campaign_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CampaignVisitor(id={self.id}, campaign_name={self.campaign_name!r}, "
            f"visitor_name={self.visitor_name!r}, phone_number={self.phone_number!r})>"
        )