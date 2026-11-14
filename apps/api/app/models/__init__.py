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
from app.models.intelligence import (
    IntelligenceRecord,
    IntelligenceReview,
    IntelligenceVersion,
    PublicationOutput,
    StatisticalObservation,
)
from app.models.radio import RadioBulletin, RadioBulletinDecision, RadioBulletinItem, RadioBulletinRevision
from app.models.review import BulletinVersion, EditorialReview
from app.models.subscription import (
    AlertSubscriber,
    SubscriberDelivery,
    SubscriptionConsent,
    SubscriptionToken,
    SubscriptionPreference,
    SubscriptionChallenge,
)
from app.models.social import SocialQuarantine, SocialSource
from app.models.source import IngestionRun, Source, SourceItem
from app.models.story import Story, StoryReview, StoryScript
from app.models.user import User
from app.models.whatsapp import WhatsAppConversation, WhatsAppInbound, WhatsAppOutbound

__all__ = [
    "WhatsAppConversation",
    "WhatsAppInbound",
    "WhatsAppOutbound",
    "SocialQuarantine",
    "SocialSource",
    "AlertSubscriber",
    "SubscriberDelivery",
    "SubscriptionConsent",
    "SubscriptionToken",
    "SubscriptionPreference",
    "SubscriptionChallenge",
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
    "IntelligenceRecord",
    "IntelligenceReview",
    "IntelligenceVersion",
    "PublicationOutput",
    "StatisticalObservation",
    "IngestionRun",
    "LoginAttempt",
    "NotificationOutbox",
    "PublicAlert",
    "RadioBulletin",
    "RadioBulletinDecision",
    "RadioBulletinItem",
    "RadioBulletinRevision",
    "Source",
    "SourceItem",
    "Story",
    "StoryReview",
    "StoryScript",
    "User",
    "UserSession",
]
