"""Geospatial intelligence: historical blackspots and incident matches.

No blackspot rows are ever seeded by the application. Every record must come
from a real, cited source (``source_name`` / ``source_reference``).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import RiskLevel, check_in
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.incident import Incident


class Blackspot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A historically high-risk location with documented provenance."""

    __tablename__ = "blackspots"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[WKBElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
        comment="WGS84 point; WKT order is POINT(longitude latitude).",
    )
    source_name: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Who published the blackspot data (provenance)."
    )
    source_reference: Mapped[str | None] = mapped_column(
        Text, comment="Report, table or URL the record was taken from."
    )
    observation_period_start: Mapped[date | None] = mapped_column(Date)
    observation_period_end: Mapped[date | None] = mapped_column(Date)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)

    matches: Mapped[list[IncidentBlackspotMatch]] = relationship(
        back_populates="blackspot", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(check_in("risk_level", RiskLevel), name="risk_level_valid"),
        CheckConstraint(
            "observation_period_start IS NULL OR observation_period_end IS NULL "
            "OR observation_period_end >= observation_period_start",
            name="observation_period_ordered",
        ),
        CheckConstraint("length(btrim(source_name)) > 0", name="source_name_not_blank"),
        Index("ix_blackspots_geom", "geom", postgresql_using="gist"),
        Index("ix_blackspots_risk_level", "risk_level"),
    )


class IncidentBlackspotMatch(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Derived link: an incident lies within range of a historical blackspot.

    Rows are recomputable from geometry (``ST_DWithin``), so they cascade with
    their parents, unlike editorial records.
    """

    __tablename__ = "incident_blackspot_matches"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    blackspot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("blackspots.id", ondelete="CASCADE"), nullable=False
    )
    distance_meters: Mapped[float] = mapped_column(Float, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="blackspot_matches")
    blackspot: Mapped[Blackspot] = relationship(back_populates="matches")

    __table_args__ = (
        UniqueConstraint(
            "incident_id",
            "blackspot_id",
            name="uq_incident_blackspot_matches_incident_id_blackspot_id",
        ),
        CheckConstraint("distance_meters >= 0", name="distance_non_negative"),
        Index("ix_incident_blackspot_matches_blackspot_id", "blackspot_id"),
    )
