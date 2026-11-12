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


class SocialPlatform(StrEnum):
    FACEBOOK = "facebook"
    X = "x"
    TIKTOK = "tiktok"


class CollectionStatus(StrEnum):
    IDLE = "idle"  # never polled
    OK = "ok"
    ERROR = "error"
    BLOCKED = "blocked"  # the platform refused the account (private, removed, security check)


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
    """Where a source item is in the RSS -> article -> AI pipeline.

    pending -> filtered | screened -> fetch_failed | fetched -> processed | discarded | failed
    """

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DISCARDED = "discarded"
    FILTERED = "filtered"  # keyword screen: not road-related, never fetched
    SCREENED = "screened"  # keyword screen: possibly relevant, article not fetched yet
    FETCHED = "fetched"  # full article fetched, redacted and stored; waiting for extraction
    FETCH_FAILED = "fetch_failed"  # article could not be retrieved or read; never sent to AI


class FetchStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class IncidentType(StrEnum):
    COLLISION = "collision"
    PEDESTRIAN_STRIKE = "pedestrian_strike"
    ROLLOVER = "rollover"
    VEHICLE_FIRE = "vehicle_fire"
    BREAKDOWN = "breakdown"
    ROAD_HAZARD = "road_hazard"
    ROAD_CLOSURE = "road_closure"  # added with the transport-intelligence expansion
    TRAFFIC_DISRUPTION = "traffic_disruption"
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
    ANALYST = "analyst"  # read-only access to internal incidents, evidence and geography
    REPORTER = "reporter"  # NUST FM newsroom: writes and submits stories, can never approve anything
    CONTRIBUTOR = "contributor"
    SERVICE = "service"  # automated/AI accounts: can draft, can never review


# Roles that may record an editorial decision. Mirrored by the database triggers.
REVIEWER_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


class LocationStatus(StrEnum):
    """How firmly an incident's position is known. Only the last two may drive map markers."""

    UNRESOLVED = "unresolved"  # no usable position; geom stays NULL
    AMBIGUOUS = "ambiguous"  # several or imprecise candidates; geom stays NULL
    RESOLVED = "resolved"  # one precise proposal from a geographic reference (not human-checked)
    EDITOR_CONFIRMED = "editor_confirmed"  # an editor accepted or supplied the position


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class StoryStage(StrEnum):
    """NUST FM story lifecycle. ``broadcast`` is set when a bulletin carrying the story goes to air."""

    ASSIGNED = "assigned"
    DRAFTING = "drafting"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    BROADCAST = "broadcast"
    DROPPED = "dropped"


# Stages in which a story still counts as the one live story for its article.
CLOSED_STORY_STAGES = (StoryStage.BROADCAST, StoryStage.DROPPED)


class ScriptOrigin(StrEnum):
    HUMAN = "human"
    AI_DRAFT = "ai_draft"  # drafted by the model on a reporter's request; always edited by a person


class StoryDecision(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class RevisionState(StrEnum):
    """A radio bulletin revision: draft -> pending_approval -> approved | rejected; approved -> superseded."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class BulletinDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


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
