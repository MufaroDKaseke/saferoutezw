"""NUST FM archive API: stories that went to air, and the bulletin revisions that aired them.

Mounted only when ``APP_MODE=nust_newsroom``. Read-only and open to everyone signed in to the newsroom (reporters,
the Executive Producer, analysts). A story is in the archive once a bulletin revision carrying it was marked as
broadcast; what the archive keeps is the script version that was read, even if the story was rewritten afterwards.
Follow-ups are stories whose ``follows_story_id`` points at an earlier archived story.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, NewsroomReader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.repositories import newsroom_archive as repo
from app.schemas.newsroom import NewsCategory
from app.schemas.newsroom_workflow import ArchiveBulletin, ArchiveBulletinDetail, ArchiveStory, ArchiveStoryDetail

router = APIRouter(prefix="/newsroom/archive", tags=["newsroom-archive"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[ArchiveStory])
def search_archive(
    auth: NewsroomReader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200, description="Title, or the headline or text of a script that aired")] = None,
    aired_from: datetime | None = None,
    aired_to: datetime | None = None,
    category: Annotated[NewsCategory | None, Query(description="Primary or secondary category of the source article")] = None,
) -> Page[ArchiveStory]:
    """Stories that went to air, newest first. Unaired drafts are never searched or shown."""
    filters = repo.ArchiveFilters(q=q, aired_from=aired_from, aired_to=aired_to, category=category.value if category else None)
    rows, total = paginate(db, repo.stories_query(filters), pagination)
    return Page(items=repo.build_stories(db, rows), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/stories/{story_id}", response_model=ArchiveStoryDetail)
def get_archived_story(story_id: uuid.UUID, auth: NewsroomReader, db: DbSession) -> ArchiveStoryDetail:
    """An archived story: the script that aired, where and when, the version history, decisions and follow-ups."""
    detail = repo.story_detail(db, story_id)
    if detail is None:
        raise not_found("ARCHIVE_STORY_NOT_FOUND", "That story is not in the archive: it has not gone to air.")
    return detail


@router.get("/bulletins", response_model=Page[ArchiveBulletin])
def search_archived_bulletins(
    auth: NewsroomReader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200, description="Bulletin name, or the title of a story in it")] = None,
    aired_from: datetime | None = None,
    aired_to: datetime | None = None,
) -> Page[ArchiveBulletin]:
    """Bulletin revisions that went to air, newest first. A bulletin that aired twice shows both revisions."""
    rows, total = paginate(db, repo.bulletins_query(q, aired_from, aired_to), pagination)
    return Page(items=repo.build_bulletins(db, rows), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/bulletins/{bulletin_id}/revisions/{number}", response_model=ArchiveBulletinDetail)
def get_archived_bulletin(bulletin_id: uuid.UUID, number: int, auth: NewsroomReader, db: DbSession) -> ArchiveBulletinDetail:
    """Exactly what went to air in one revision, with the script text that was read."""
    detail = repo.bulletin_detail(db, bulletin_id, number)
    if detail is None:
        raise not_found("ARCHIVE_BULLETIN_NOT_FOUND", "That bulletin revision is not in the archive: it has not gone to air.")
    return detail
