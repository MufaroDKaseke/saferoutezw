"""Small factories for building valid rows in database tests.

All values are synthetic test data. They are written only to the disposable
test database and are truncated before every test.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    BulletinVersion,
    EditorialReview,
    Incident,
    PublicAlert,
    Source,
    SourceItem,
    User,
)


def _token() -> str:
    return uuid.uuid4().hex[:10]


def make_user(session: Session, role: str = "editor", is_active: bool = True) -> User:
    token = _token()
    user = User(
        email=f"{role}-{token}@example.test",
        display_name=f"Test {role} {token}",
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def make_source(session: Session, kind: str = "rss") -> Source:
    token = _token()
    source = Source(
        name=f"Test source {token}",
        kind=kind,
        feed_url=f"https://example.test/{token}/feed" if kind == "rss" else None,
    )
    session.add(source)
    session.flush()
    return source


def make_source_item(session: Session, source: Source, **overrides) -> SourceItem:
    token = _token()
    values = {
        "source_id": source.id,
        "external_id": f"guid-{token}",
        "canonical_url": f"https://example.test/{token}",
        "title_redacted": f"Synthetic headline {token}",
    }
    values.update(overrides)
    item = SourceItem(**values)
    session.add(item)
    session.flush()
    return item


def make_incident(session: Session, **overrides) -> Incident:
    values = {"reference_code": f"TEST-{_token()}", "incident_type": "collision"}
    values.update(overrides)
    incident = Incident(**values)
    session.add(incident)
    session.flush()
    return incident


def make_bulletin(
    session: Session, incident: Incident, author: User, version_number: int = 1
) -> BulletinVersion:
    bulletin = BulletinVersion(
        incident_id=incident.id,
        version_number=version_number,
        headline=f"Synthetic headline v{version_number}",
        body="Synthetic body text for tests.",
        created_by=author.id,
    )
    session.add(bulletin)
    session.flush()
    return bulletin


def make_review(
    session: Session,
    incident: Incident,
    bulletin: BulletinVersion | None,
    reviewer: User,
    decision: str = "approved",
    reviewed_at: datetime | None = None,
) -> EditorialReview:
    values = {
        "incident_id": incident.id,
        "bulletin_version_id": bulletin.id if bulletin else None,
        "reviewer_id": reviewer.id,
        "decision": decision,
    }
    if reviewed_at is not None:
        values["reviewed_at"] = reviewed_at
    review = EditorialReview(**values)
    session.add(review)
    session.flush()
    return review


def make_alert(
    session: Session,
    incident: Incident,
    bulletin: BulletinVersion,
    approval: EditorialReview,
    **overrides,
) -> PublicAlert:
    alert = PublicAlert(
        incident_id=incident.id,
        bulletin_version_id=bulletin.id,
        approval_review_id=approval.id,
        **overrides,
    )
    session.add(alert)
    session.flush()
    return alert
