"""Integration tests against the disposable test database (see conftest.py)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, inspect, select, text

import db_factories as f
from app.core.config import Settings
from app.core.database import Base
from app.core.geo import point_from_lat_lon
from app.models import (
    AuditEvent,
    Blackspot,
    DeliveryChannel,
    ExtractionRun,
    Incident,
    IncidentBlackspotMatch,
    NotificationOutbox,
    Source,
    SourceItem,
)
from schema_constants import EXPECTED_TABLES

UNIQUE, FOREIGN_KEY, CHECK = "23505", "23503", "23514"

pytestmark = pytest.mark.usefixtures("migrated_engine")


# --- connection, PostGIS, tables ------------------------------------------------


def test_connection_works_and_reports_server_version(session):
    version = session.execute(text("SHOW server_version_num")).scalar_one()
    assert int(version) >= 130000  # gen_random_uuid() is built in from PostgreSQL 13


def test_postgis_extension_is_enabled(session):
    assert session.execute(text("SELECT PostGIS_Version()")).scalar_one()
    assert session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")).scalar() == 1


def test_all_sixteen_application_tables_exist_and_nothing_else(migrated_engine):
    present = set(inspect(migrated_engine).get_table_names())
    application = present - {"alembic_version", "spatial_ref_sys"}
    assert application == EXPECTED_TABLES


def test_spatial_indexes_are_gist(session):
    rows = session.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE indexname IN ('ix_incidents_geom','ix_blackspots_geom')")
    ).all()
    assert {r[0] for r in rows} == {"ix_incidents_geom", "ix_blackspots_geom"}
    assert all("USING gist" in r[1] for r in rows)


# --- UUID keys, foreign keys, check constraints ---------------------------------


def test_uuid_primary_keys_are_generated_by_postgres(session):
    source = f.make_source(session)
    assert isinstance(source.id, uuid.UUID)
    assert source.created_at is not None and source.updated_at is not None
    raw = session.execute(
        text("INSERT INTO delivery_channels (name, kind) VALUES ('raw', 'web') RETURNING id")
    ).scalar_one()
    assert isinstance(raw, uuid.UUID)


def test_every_foreign_key_rejects_dangling_references(session, db_error):
    ghost = uuid.uuid4()
    with db_error(session, FOREIGN_KEY):
        session.add(SourceItem(source_id=ghost, external_id="x", title_redacted="t"))
    incident = f.make_incident(session)
    with db_error(session, FOREIGN_KEY):
        session.add(ExtractionRun(source_item_id=ghost, model_name="m"))
    with db_error(session, FOREIGN_KEY):
        session.add(IncidentBlackspotMatch(incident_id=incident.id, blackspot_id=ghost, distance_meters=1))


def test_invalid_status_values_are_rejected(session, db_error):
    with db_error(session, CHECK):
        f.make_incident(session, status="published-ish")
    with db_error(session, CHECK):
        f.make_incident(session, severity="catastrophic")
    with db_error(session, CHECK):
        session.add(Source(name="bad kind", kind="telegram"))
    with db_error(session, CHECK):
        session.add(DeliveryChannel(name="bad", kind="pigeon"))


@pytest.mark.parametrize("field", ["credibility_score", "geographic_risk_score"])
@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_incident_scores_outside_0_to_1_are_rejected(session, db_error, field, value):
    with db_error(session, CHECK):
        f.make_incident(session, **{field: value})


def test_extraction_confidence_outside_0_to_1_is_rejected(session, db_error):
    item = f.make_source_item(session, f.make_source(session))
    with db_error(session, CHECK):
        session.add(ExtractionRun(source_item_id=item.id, model_name="m", extraction_confidence=1.5))


def test_extraction_output_is_stored_as_jsonb(session):
    item = f.make_source_item(session, f.make_source(session))
    run = ExtractionRun(
        source_item_id=item.id, model_name="test-model",
        extraction_output={"incident_type": "collision", "locations": ["Test Road"]},
        extraction_confidence=0.4,
    )
    session.add(run)
    session.flush()
    stored = session.execute(
        text("SELECT extraction_output ->> 'incident_type', jsonb_typeof(extraction_output) "
             "FROM extraction_runs WHERE id = :id"), {"id": run.id}
    ).one()
    assert tuple(stored) == ("collision", "object")


# --- RSS de-duplication ---------------------------------------------------------


def test_duplicate_rss_entries_are_prevented(session, db_error):
    source = f.make_source(session)
    other = f.make_source(session)
    f.make_source_item(session, source, external_id="guid-1", canonical_url="https://example.test/a")

    with db_error(session, UNIQUE):  # same GUID, same source
        f.make_source_item(session, source, external_id="guid-1", canonical_url="https://example.test/b")
    with db_error(session, UNIQUE):  # same canonical URL, same source
        f.make_source_item(session, source, external_id="guid-2", canonical_url="https://example.test/a")

    # The same entry from a *different* source is a different item.
    f.make_source_item(session, other, external_id="guid-1", canonical_url="https://example.test/a")


def test_source_item_needs_a_deduplication_key(session, db_error):
    source = f.make_source(session)
    with db_error(session, CHECK):
        session.add(SourceItem(source_id=source.id, title_redacted="no key"))


def test_rss_source_requires_a_feed_url(session, db_error):
    with db_error(session, CHECK):
        session.add(Source(name="feedless", kind="rss"))


# --- spatial --------------------------------------------------------------------

# Synthetic coordinates used only to exercise the maths. Not a real incident or blackspot.
BASE_LAT, BASE_LON = -17.8292, 31.0522


def _blackspot(session) -> Blackspot:
    spot = Blackspot(
        name="TEST ONLY blackspot (synthetic)",
        geom=point_from_lat_lon(BASE_LAT, BASE_LON),
        source_name="pytest fixture",
        risk_level="high",
    )
    session.add(spot)
    session.flush()
    return spot


def test_stored_points_keep_longitude_latitude_order(session):
    incident = f.make_incident(session, geom=point_from_lat_lon(BASE_LAT, BASE_LON))
    x, y = session.execute(
        text("SELECT ST_X(geom::geometry), ST_Y(geom::geometry) FROM incidents WHERE id = :id"),
        {"id": incident.id},
    ).one()
    assert (x, y) == (pytest.approx(BASE_LON), pytest.approx(BASE_LAT))


def test_st_dwithin_selects_incidents_inside_the_metre_radius(session):
    spot = _blackspot(session)
    near = f.make_incident(session, geom=point_from_lat_lon(BASE_LAT + 0.002, BASE_LON))  # ~222 m
    far = f.make_incident(session, geom=point_from_lat_lon(BASE_LAT + 0.05, BASE_LON))  # ~5.6 km
    f.make_incident(session)  # no location at all

    def incidents_within(metres: float) -> set[uuid.UUID]:
        query = (
            select(Incident.id)
            .join(Blackspot, func.ST_DWithin(Incident.geom, Blackspot.geom, metres))
            .where(Blackspot.id == spot.id)
        )
        return set(session.scalars(query))

    assert incidents_within(500) == {near.id}
    assert incidents_within(10_000) == {near.id, far.id}


def test_geography_distance_is_in_metres(session):
    spot = _blackspot(session)
    near = f.make_incident(session, geom=point_from_lat_lon(BASE_LAT + 0.002, BASE_LON))
    metres = session.scalar(
        select(func.ST_Distance(Incident.geom, Blackspot.geom))
        .select_from(Incident)
        .join(Blackspot, Blackspot.id == spot.id)
        .where(Incident.id == near.id)
    )
    assert 215 < metres < 230  # 0.002 degrees of latitude is about 222 m

    session.add(IncidentBlackspotMatch(incident_id=near.id, blackspot_id=spot.id, distance_meters=metres))
    session.flush()


def test_match_distance_cannot_be_negative_and_pairs_are_unique(session, db_error):
    spot = _blackspot(session)
    incident = f.make_incident(session, geom=point_from_lat_lon(BASE_LAT, BASE_LON))
    with db_error(session, CHECK):
        session.add(IncidentBlackspotMatch(incident_id=incident.id, blackspot_id=spot.id, distance_meters=-1))
    session.add(IncidentBlackspotMatch(incident_id=incident.id, blackspot_id=spot.id, distance_meters=0))
    session.flush()
    with db_error(session, UNIQUE):
        session.add(IncidentBlackspotMatch(incident_id=incident.id, blackspot_id=spot.id, distance_meters=0))


def test_blackspot_requires_provenance_and_a_location(session, db_error):
    with db_error(session, CHECK):
        session.add(Blackspot(name="x", geom=point_from_lat_lon(0, 0), source_name="  ", risk_level="low"))
    with db_error(session, "23502"):  # NOT NULL violation: geom
        session.execute(text("INSERT INTO blackspots (name, source_name, risk_level) VALUES ('x', 'src', 'low')"))


# --- editorial workflow and the public-alert safeguard --------------------------


@pytest.fixture
def workflow(session):
    """An incident with a bulletin drafted by an AI service account, and a human editor."""
    editor = f.make_user(session, "editor")
    ai = f.make_user(session, "service")
    incident = f.make_incident(session)
    bulletin = f.make_bulletin(session, incident, ai)
    return type("Workflow", (), dict(editor=editor, ai=ai, incident=incident, bulletin=bulletin))


def test_human_editor_approval_allows_a_public_alert(session, workflow):
    w = workflow
    approval = f.make_review(session, w.incident, w.bulletin, w.editor, "approved")
    alert = f.make_alert(session, w.incident, w.bulletin, approval)
    alert.status, alert.published_at = "published", datetime.now(UTC)
    session.flush()
    assert alert.status == "published"


def test_public_alert_without_any_review_is_rejected(session, workflow, db_error):
    w = workflow
    with db_error(session, CHECK):
        session.execute(
            text("INSERT INTO public_alerts (incident_id, bulletin_version_id, approval_review_id) "
                 "VALUES (:i, :b, gen_random_uuid())"),
            {"i": w.incident.id, "b": w.bulletin.id},
        )


@pytest.mark.parametrize("decision", ["rejected", "needs_changes"])
def test_public_alert_cannot_rest_on_a_non_approving_review(session, workflow, db_error, decision):
    w = workflow
    review = f.make_review(session, w.incident, w.bulletin, w.editor, decision)
    with db_error(session, CHECK):
        f.make_alert(session, w.incident, w.bulletin, review)


def test_ai_service_account_can_never_review_or_approve(session, workflow, db_error):
    w = workflow
    for decision in ("approved", "rejected", "needs_changes"):
        with db_error(session, CHECK):
            f.make_review(session, w.incident, w.bulletin, w.ai, decision)


def test_inactive_or_non_editor_users_cannot_review(session, workflow, db_error):
    w = workflow
    with db_error(session, CHECK):
        f.make_review(session, w.incident, w.bulletin, f.make_user(session, "editor", is_active=False))
    with db_error(session, CHECK):
        f.make_review(session, w.incident, w.bulletin, f.make_user(session, "contributor"))


def test_approval_must_cover_the_same_incident_and_bulletin(session, workflow, db_error):
    w = workflow
    other_incident = f.make_incident(session)
    other_bulletin = f.make_bulletin(session, other_incident, w.ai)
    with db_error(session, FOREIGN_KEY):  # review cannot cite a bulletin from another incident
        f.make_review(session, w.incident, other_bulletin, w.editor)

    # The approval trigger rejects mismatches first (a CHECK error); the composite
    # foreign keys remain as a second, structural line of defence.
    approval = f.make_review(session, w.incident, w.bulletin, w.editor)
    with db_error(session, CHECK):  # alert cannot pair a different bulletin with this approval
        f.make_alert(session, w.incident, other_bulletin, approval)
    with db_error(session, CHECK):  # ... or a different incident
        f.make_alert(session, other_incident, w.bulletin, approval)


def test_approval_superseded_by_a_later_rejection_cannot_be_published(session, workflow, db_error):
    w = workflow
    now = datetime.now(UTC)
    approval = f.make_review(session, w.incident, w.bulletin, w.editor, "approved", now - timedelta(hours=2))
    f.make_review(session, w.incident, w.bulletin, w.editor, "needs_changes", now - timedelta(hours=1))
    with db_error(session, CHECK):
        f.make_alert(session, w.incident, w.bulletin, approval)


def test_one_public_alert_per_bulletin_version(session, workflow, db_error):
    w = workflow
    first = f.make_review(session, w.incident, w.bulletin, w.editor)
    second = f.make_review(session, w.incident, w.bulletin, w.editor)
    f.make_alert(session, w.incident, w.bulletin, first)
    with db_error(session, UNIQUE):
        f.make_alert(session, w.incident, w.bulletin, second)


def test_published_alert_needs_a_timestamp_and_can_always_be_withdrawn(session, workflow, db_error):
    w = workflow
    approval = f.make_review(session, w.incident, w.bulletin, w.editor)
    with db_error(session, CHECK):
        f.make_alert(session, w.incident, w.bulletin, approval, status="published")
    alert = f.make_alert(session, w.incident, w.bulletin, approval, status="published", published_at=datetime.now(UTC))

    w.editor.is_active = False  # the approving editor leaves; withdrawal must still work
    session.flush()
    alert.status = "withdrawn"
    session.flush()


def test_incident_cannot_be_approved_without_a_human_approval(session, workflow, db_error):
    w = workflow
    with db_error(session, CHECK):
        f.make_incident(session, status="approved")
    with db_error(session, CHECK):
        w.incident.status = "published"
    f.make_review(session, w.incident, w.bulletin, w.editor, "approved")
    w.incident.status = "approved"
    session.flush()


def test_editorial_history_and_bulletin_text_are_append_only(session, workflow, db_error):
    w = workflow
    review = f.make_review(session, w.incident, w.bulletin, w.editor)
    restrict = "23001"
    with db_error(session, restrict):
        review.notes = "rewritten history"
    with db_error(session, restrict):
        session.delete(review)
    with db_error(session, restrict):
        w.bulletin.body = "text changed after approval"


def test_audit_events_are_append_only(session, workflow, db_error):
    w = workflow
    event = AuditEvent(actor_user_id=w.editor.id, action="incident.approved", entity_type="incident",
                       entity_id=w.incident.id, details={"from": "candidate", "to": "approved"})
    session.add(event)
    session.flush()
    with db_error(session, "23001"):
        event.action = "something.else"
    with db_error(session, "23001"):
        session.delete(event)
    with db_error(session, CHECK):
        session.add(AuditEvent(action=" ", entity_type="incident"))


def test_editorial_records_cannot_be_deleted_through_their_parents(session, workflow, db_error):
    w = workflow
    f.make_review(session, w.incident, w.bulletin, w.editor)
    # ON DELETE RESTRICT prevents silent cascades through editorial history.
    # PostgreSQL 18 changed this SQLSTATE from foreign_key_violation (23503)
    # to restrict_violation (23001). CI also runs against PostgreSQL 16.
    version = int(session.execute(text("SHOW server_version_num")).scalar_one())
    restrict = "23001" if version >= 180000 else FOREIGN_KEY
    for obj in (w.incident, w.editor):
        with db_error(session, restrict):
            session.execute(text(f"DELETE FROM {obj.__table__.name} WHERE id = :id"), {"id": obj.id})


# --- outbox idempotency ---------------------------------------------------------


def test_notification_outbox_is_idempotent_per_alert_and_channel(session, workflow, db_error):
    w = workflow
    approval = f.make_review(session, w.incident, w.bulletin, w.editor)
    alert = f.make_alert(session, w.incident, w.bulletin, approval)
    channel = DeliveryChannel(name="web", kind="web")
    session.add(channel)
    session.flush()

    session.add(NotificationOutbox(public_alert_id=alert.id, channel_id=channel.id))
    session.flush()
    with db_error(session, UNIQUE):
        session.add(NotificationOutbox(public_alert_id=alert.id, channel_id=channel.id))
    with db_error(session, CHECK):
        session.add(NotificationOutbox(public_alert_id=alert.id, channel_id=uuid.uuid4(), attempts=-1))


# --- misc -----------------------------------------------------------------------


def test_updated_at_is_maintained_by_the_database(session):
    source = f.make_source(session)
    session.execute(
        text("UPDATE sources SET name = 'renamed', updated_at = '2000-01-01' WHERE id = :id"), {"id": source.id}
    )
    stamp = session.execute(text("SELECT updated_at FROM sources WHERE id = :id"), {"id": source.id}).scalar_one()
    assert stamp.year >= 2026


def test_get_db_yields_a_session_and_closes_it(migrated_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    import app.core.database as database

    monkeypatch.setattr(database, "get_session_factory", lambda: sessionmaker(bind=migrated_engine))
    generator = database.get_db()
    db = next(generator)
    assert db.execute(text("SELECT 1")).scalar_one() == 1
    assert db.in_transaction()
    generator.close()
    assert not db.in_transaction()  # closed: connection returned, uncommitted work rolled back


def test_every_modelled_table_is_truncatable_between_tests(session):
    assert session.scalar(select(func.count()).select_from(Source)) == 0
    assert len(Base.metadata.sorted_tables) == len(EXPECTED_TABLES)


def test_settings_point_tests_away_from_the_development_database(settings: Settings):
    assert settings.postgres_test_db != settings.postgres_db
    assert settings.postgres_test_db.endswith("_test")
