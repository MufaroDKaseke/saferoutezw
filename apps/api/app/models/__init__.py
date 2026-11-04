"""SQLAlchemy ORM models.

Every model is imported here so that ``Base.metadata`` is complete for Alembic.
Importing this package does not open a database connection.
"""

from app.core.database import Base
from app.models.alert import DeliveryAttempt, DeliveryChannel, NotificationOutbox, PublicAlert
from app.models.audit import AuditEvent
from app.models.auth import LoginAttempt, UserSession
from app.models.blackspot import Blackspot, IncidentBlackspotMatch
from app.models.evidence import ExtractionRun, IncidentEvidence
from app.models.incident import Incident
from app.models.review import BulletinVersion, EditorialReview
from app.models.source import IngestionRun, Source, SourceItem
from app.models.user import User

__all__ = [
    "AuditEvent",
    "Base",
    "Blackspot",
    "BulletinVersion",
    "DeliveryAttempt",
    "DeliveryChannel",
    "EditorialReview",
    "ExtractionRun",
    "Incident",
    "IncidentBlackspotMatch",
    "IncidentEvidence",
    "IngestionRun",
    "LoginAttempt",
    "NotificationOutbox",
    "PublicAlert",
    "Source",
    "SourceItem",
    "User",
    "UserSession",
]
