"""Evidence links between incidents and source items, and AI extraction runs."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EvidenceRole, ExtractionStatus, check_in
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.source import SourceItem


class IncidentEvidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Links an incident to a supporting (or contradicting) source item."""

    __tablename__ = "incident_evidence"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    source_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("source_items.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_role: Mapped[str] = mapped_column(String(16), nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="evidence")
    source_item: Mapped[SourceItem] = relationship(back_populates="evidence_links")

    __table_args__ = (
        UniqueConstraint(
            "incident_id", "source_item_id", name="uq_incident_evidence_incident_id_source_item_id"
        ),
        CheckConstraint(check_in("evidence_role", EvidenceRole), name="evidence_role_valid"),
        Index("ix_incident_evidence_source_item_id", "source_item_id"),
    )


class ExtractionRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One AI extraction attempt over a source item.

    ``extraction_confidence`` is the model's self-reported confidence. It does
    NOT establish that an incident occurred; only human review does.
    """

    __tablename__ = "extraction_runs"

    source_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("source_items.id", ondelete="RESTRICT"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str | None] = mapped_column(Text)
    extraction_output: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    extraction_confidence: Mapped[float | None] = mapped_column(
        Float, comment="Model-reported confidence in [0, 1]; not proof an incident occurred."
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ExtractionStatus.PENDING.value}'")
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    source_item: Mapped[SourceItem] = relationship(back_populates="extraction_runs")

    __table_args__ = (
        CheckConstraint(check_in("status", ExtractionStatus), name="status_valid"),
        CheckConstraint(
            "extraction_confidence IS NULL OR extraction_confidence BETWEEN 0 AND 1",
            name="extraction_confidence_range",
        ),
        Index("ix_extraction_runs_source_item_id_created_at", "source_item_id", "created_at"),
        Index("ix_extraction_runs_status", "status"),
    )
