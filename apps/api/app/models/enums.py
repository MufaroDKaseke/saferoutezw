"""Allowed values for workflow and classification columns.

Stored as VARCHAR with CHECK constraints (not PostgreSQL ENUM types) so values
can be added by a normal migration and downgrades stay simple. Each enum here
is the single source of truth for its CHECK constraint.
"""

from enum import StrEnum


class SourceKind(StrEnum):
    RSS = "rss"
    OFFICIAL = "official"
    WHATSAPP = "whatsapp"
    SOCIAL = "social"
    MANUAL = "manual"


class VerificationTier(StrEnum):
    OFFICIAL = "official"
    ESTABLISHED_MEDIA = "established_media"
    COMMUNITY = "community"
    UNVERIFIED = "unverified"


class IngestionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DISCARDED = "discarded"


class IncidentType(StrEnum):
    COLLISION = "collision"
    PEDESTRIAN_STRIKE = "pedestrian_strike"
    ROLLOVER = "rollover"
    VEHICLE_FIRE = "vehicle_fire"
    BREAKDOWN = "breakdown"
    ROAD_HAZARD = "road_hazard"
    OTHER = "other"


class Severity(StrEnum):
    UNKNOWN = "unknown"
    MINOR = "minor"
    SERIOUS = "serious"
    FATAL = "fatal"


class ReviewPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class IncidentStatus(StrEnum):
    CANDIDATE = "candidate"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class EvidenceRole(StrEnum):
    PRIMARY = "primary"
    CORROBORATING = "corroborating"
    CONTRADICTING = "contradicting"
    CONTEXT = "context"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    CONTRIBUTOR = "contributor"
    SERVICE = "service"  # automated/AI accounts: can draft, can never review


# Roles that may record an editorial decision. Mirrored by the database triggers.
REVIEWER_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class AlertStatus(StrEnum):
    READY = "ready"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class ChannelKind(StrEnum):
    WEB = "web"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    WEBHOOK = "webhook"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def check_in(column: str, enum: type[StrEnum]) -> str:
    """SQL text for ``column IN (<enum values>)``."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
