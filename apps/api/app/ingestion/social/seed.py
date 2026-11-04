"""The administrator's allowlist: ``config/social_sources.yaml`` -> ``sources`` + ``social_sources``.

The file is the declaration of *which accounts may be collected*. Syncing it creates or updates
the configuration columns of each listed account and never touches collection state (cursor,
last poll, status). Accounts missing from the file are left exactly as they are in the
database; disable one there (``enabled: false`` in the file, or the ``sources`` table).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import REPOSITORY_ROOT
from app.ingestion.social.facebook import account_key, canonical_account_url, is_facebook_url
from app.ingestion.social.registry import get_adapter
from app.models import SocialSource, Source
from app.models.enums import SocialPlatform, SourceKind, VerificationTier

DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "config" / "social_sources.yaml"
MAX_POSTS_PER_PAGE = 15  # policy cap on the newest posts read per poll (default below)
DEFAULT_POSTS_PER_PAGE = 5
MAX_PAGES = 10  # policy: size of the allowlist
MIN_POLL_INTERVAL_MINUTES = 15  # each poll is a paid Actor run
ACTOR_ID = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RIGHTS_NOTE = "Public posts of an allow-listed account, collected through Apify. Reuse is subject to the platform's terms."


class SocialSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=200)
    platform: SocialPlatform
    account_url: str
    platform_account_id: str | None = None
    actor_id: str
    enabled: bool = False
    poll_interval_minutes: int = Field(default=120, ge=MIN_POLL_INTERVAL_MINUTES, le=7 * 24 * 60)
    max_posts_per_run: int = Field(default=DEFAULT_POSTS_PER_PAGE, ge=1, le=MAX_POSTS_PER_PAGE)
    verification_tier: VerificationTier = VerificationTier.UNVERIFIED

    @field_validator("actor_id")
    @classmethod
    def _actor(cls, value: str) -> str:
        if not ACTOR_ID.match(value.strip()):
            raise ValueError("actor_id must look like owner/actor-name")
        return value.strip()

    @field_validator("platform_account_id")
    @classmethod
    def _account_id(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not value.isdigit():
            raise ValueError("platform_account_id must be the numeric id")
        return value

    @model_validator(mode="after")
    def _check(self) -> SocialSourceConfig:
        if self.platform is SocialPlatform.FACEBOOK:
            if not is_facebook_url(self.account_url) or account_key(self.account_url) is None:
                raise ValueError("account_url must be the address of a Facebook Page, e.g. https://www.facebook.com/<page>")
            self.account_url = canonical_account_url(self.account_url)
        if self.enabled and get_adapter(self.platform.value) is None:
            raise ValueError(
                f"{self.platform.value} collection is not available yet (no verified Actor); keep enabled: false"
            )
        return self


@dataclass
class SyncResult:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_config(path: Path | None = None) -> tuple[list[SocialSourceConfig], list[str]]:
    """Parse the YAML. Invalid entries are reported and skipped, never half-applied."""
    path = path or DEFAULT_CONFIG_PATH
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    entries = (document or {}).get("social_sources") or []
    configs: list[SocialSourceConfig] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        label = (entry or {}).get("name", f"entry #{index}") if isinstance(entry, dict) else f"entry #{index}"
        try:
            config = SocialSourceConfig.model_validate(entry)
        except ValidationError as exc:
            errors.append(f"{label}: " + "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors()))
            continue
        if config.name.lower() in seen:
            errors.append(f"{label}: duplicate name")
            continue
        if len(configs) >= MAX_PAGES:
            errors.append(f"{label}: allowlist is limited to {MAX_PAGES} pages")
            continue
        seen.add(config.name.lower())
        configs.append(config)
    return configs, errors


def sync_social_sources(db: Session, configs: list[SocialSourceConfig]) -> SyncResult:
    """Create or update allow-list rows. The caller commits."""
    result = SyncResult()
    for config in configs:
        source = db.scalar(select(Source).where(Source.name == config.name))
        if source is not None and source.kind != SourceKind.SOCIAL.value:
            result.errors.append(f"{config.name}: a non-social source already uses this name")
            continue
        created = source is None
        if source is None:
            source = Source(name=config.name, kind=SourceKind.SOCIAL.value, rights_notes=RIGHTS_NOTE)
            db.add(source)
        source.enabled = config.enabled
        source.poll_interval_seconds = config.poll_interval_minutes * 60
        source.verification_tier = config.verification_tier.value
        db.flush()

        social = db.scalar(select(SocialSource).where(SocialSource.source_id == source.id))
        if social is None:
            social = SocialSource(source_id=source.id, platform=config.platform.value, account_url=config.account_url, actor_id=config.actor_id)
            db.add(social)
        elif social.account_url != config.account_url or social.platform != config.platform.value:
            # A different account: nothing learned about the old one applies.
            social.platform_account_id = None
            social.last_post_id = social.last_post_at = None
        social.platform = config.platform.value
        social.account_url = config.account_url
        social.actor_id = config.actor_id
        social.max_posts_per_run = config.max_posts_per_run
        if config.platform_account_id:
            social.platform_account_id = config.platform_account_id
        db.flush()
        (result.created if created else result.updated).append(config.name)
    return result
