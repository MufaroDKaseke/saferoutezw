"""Internal publication endpoints. Only editors and admins; the request never carries approval state."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.deps import DbSession, Editor
from app.api.errors import ERROR_RESPONSES
from app.schemas.common import ApiModel, UtcDatetime
from app.services import publishing

router = APIRouter(tags=["publishing"], responses=ERROR_RESPONSES)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bulletin_version_id: uuid.UUID
    province: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    road_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None


class UnpublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class PublicationOut(ApiModel):
    alert_id: uuid.UUID
    incident_id: uuid.UUID
    bulletin_version_id: uuid.UUID
    status: str
    published_at: UtcDatetime | None
    withdrawn_at: UtcDatetime | None


def _out(alert) -> PublicationOut:
    return PublicationOut(
        alert_id=alert.id,
        incident_id=alert.incident_id,
        bulletin_version_id=alert.bulletin_version_id,
        status=alert.status,
        published_at=alert.published_at,
        withdrawn_at=alert.withdrawn_at,
    )


@router.post("/incidents/{incident_id}/publish", response_model=PublicationOut)
def publish_incident_alert(
    incident_id: uuid.UUID, body: PublishRequest, auth: Editor, db: DbSession
) -> PublicationOut:
    """Publish the exact approved, latest bulletin version. Never happens automatically."""
    alert = publishing.publish_alert(
        db, auth.user, incident_id, body.bulletin_version_id, province=body.province, road_name=body.road_name
    )
    return _out(alert)


@router.post("/incidents/{incident_id}/unpublish", response_model=PublicationOut)
def unpublish_incident_alert(
    incident_id: uuid.UUID, body: UnpublishRequest, auth: Editor, db: DbSession
) -> PublicationOut:
    alert = publishing.unpublish_alert(db, auth.user, incident_id, body.reason)
    return _out(alert)
