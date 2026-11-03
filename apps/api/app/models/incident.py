"""Incident intelligence: structured incident records."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import CheckConstraint, DateTime, Float, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    IncidentStatus,
    IncidentType,
    ReviewPriority,
    Severity,
    check_in,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.alert import PublicAlert
    from app.models.blackspot import IncidentBlackspotMatch
    from app.models.evidence import IncidentEvidence
    from app.models.review import BulletinVersion, EditorialReview


class Incident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A structured road incident, built from one or more source items.

    ``status`` only reaches ``approved``/``published`` after a human editor has
    recorded an approving review; a database trigger enforces this.
    ``credibility_score`` and ``geographic_risk_score`` are decision aids for
    reviewers (0..1). They never replace human verification.
    """

    __tablename__ = "incidents"

    reference_code: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{Severity.UNKNOWN.value}'")
    )
    location_text: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        comment="WGS84 point; WKT order is POINT(longitude latitude).",
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credibility_score: Mapped[float | None] = mapped_column(Float)
    geographic_risk_score: Mapped[float | None] = mapped_column(Float)
    review_priority: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ReviewPriority.NORMAL.value}'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{IncidentStatus.CANDIDATE.value}'")
    )

    evidence: Mapped[list[IncidentEvidence]] = relationship(
        back_populates="incident", passive_deletes="all"
    )
    blackspot_matches: Mapped[list[IncidentBlackspotMatch]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )
    bulletin_versions: Mapped[list[BulletinVersion]] = relationship(
        back_populates="incident", passive_deletes="all"
    )
    reviews: Mapped[list[EditorialReview]] = relationship(
        back_populates="incident", passive_deletes="all"
    )
    public_alerts: Mapped[list[PublicAlert]] = relationship(
        back_populates="incident", passive_deletes="all"
    )

    __table_args__ = (
        UniqueConstraint("reference_code", name="uq_incidents_reference_code"),
        CheckConstraint(check_in("incident_type", IncidentType), name="incident_type_valid"),
        CheckConstraint(check_in("severity", Severity), name="severity_valid"),
        CheckConstraint(check_in("review_priority", ReviewPriority), name="review_priority_valid"),
        CheckConstraint(check_in("status", IncidentStatus), name="status_valid"),
        CheckConstraint(
            "credibility_score IS NULL OR credibility_score BETWEEN 0 AND 1",
            name="credibility_score_range",
        ),
        CheckConstraint(
            "geographic_risk_score IS NULL OR geographic_risk_score BETWEEN 0 AND 1",
            name="geographic_risk_score_range",
        ),
        CheckConstraint("length(btrim(reference_code)) > 0", name="reference_code_not_blank"),
        Index("ix_incidents_geom", "geom", postgresql_using="gist"),
        Index("ix_incidents_status_review_priority", "status", "review_priority"),
        Index("ix_incidents_occurred_at", "occurred_at"),
    )
