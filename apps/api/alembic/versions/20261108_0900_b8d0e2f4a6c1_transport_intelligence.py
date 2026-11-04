"""transport intelligence: classified records, statistics, editorial history, outputs

Revision ID: b8d0e2f4a6c1
Revises: a7c9d1e3f5b2
Create Date: 2026-11-08 09:00:00.000000

Additive. New tables: ``intelligence_records`` (one classified reading of a source item),
``statistical_observations`` (queryable figures with period/coverage/source),
``intelligence_versions`` and ``intelligence_reviews`` (append-only editorial history) and
``publication_outputs`` (separate publication of one approved version; never a hazard alert).

Also widens ``incidents.incident_type`` with ``road_closure`` and ``traffic_disruption`` so
actionable closures/disruptions can reuse the incident workflow. Existing rows are untouched:
no historical record is reclassified or backfilled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8d0e2f4a6c1'
down_revision: Union[str, Sequence[str], None] = 'a7c9d1e3f5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_INCIDENT_TYPES = "'collision', 'pedestrian_strike', 'rollover', 'vehicle_fire', 'breakdown', 'road_hazard', 'other'"
NEW_INCIDENT_TYPES = (
    "'collision', 'pedestrian_strike', 'rollover', 'vehicle_fire', 'breakdown', 'road_hazard', "
    "'road_closure', 'traffic_disruption', 'other'"
)

# An approval must cover the latest version of its record.
FN_LATEST_VERSION = """
CREATE FUNCTION saferoutezw_require_latest_intelligence_version() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    latest uuid;
BEGIN
    IF NEW.decision = 'approved' THEN
        SELECT id INTO latest FROM intelligence_versions
        WHERE record_id = NEW.record_id ORDER BY version_number DESC LIMIT 1;
        IF latest IS DISTINCT FROM NEW.version_id AND EXISTS (
            SELECT 1 FROM intelligence_versions WHERE id = NEW.version_id AND record_id = NEW.record_id
        ) THEN
            RAISE EXCEPTION 'an approval must refer to the latest version of the intelligence record'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$
"""

# A record can only become approved/published once an approving review exists.
FN_RECORD_APPROVAL = """
CREATE FUNCTION saferoutezw_require_intelligence_approval() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.status IN ('approved', 'published')
       AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM NEW.status) THEN
        IF NOT EXISTS (
            SELECT 1 FROM intelligence_reviews r WHERE r.record_id = NEW.id AND r.decision = 'approved'
        ) THEN
            RAISE EXCEPTION 'intelligence record % cannot be % without an approved editorial review',
                NEW.id, NEW.status USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$
"""

# A publication output needs an approving review of the same record and version, made by an
# active human editor, on the latest version, and not superseded by a later non-approval.
# Withdrawing an existing output is always allowed.
FN_PUBLICATION_APPROVAL = """
CREATE FUNCTION saferoutezw_require_publication_approval() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    approval intelligence_reviews%ROWTYPE;
    reviewer users%ROWTYPE;
    latest uuid;
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.record_id = OLD.record_id AND NEW.version_id = OLD.version_id
       AND NEW.approval_review_id = OLD.approval_review_id
       AND NOT (NEW.status = 'published' AND OLD.status <> 'published') THEN
        RETURN NEW;
    END IF;

    SELECT * INTO approval FROM intelligence_reviews WHERE id = NEW.approval_review_id;
    IF NOT FOUND OR approval.decision <> 'approved' THEN
        RAISE EXCEPTION 'a publication output requires an approving editorial review'
            USING ERRCODE = 'check_violation';
    END IF;
    IF approval.record_id <> NEW.record_id OR approval.version_id IS DISTINCT FROM NEW.version_id THEN
        RAISE EXCEPTION 'approving review % covers a different record or version', approval.id
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO reviewer FROM users WHERE id = approval.reviewer_id;
    IF NOT FOUND OR NOT reviewer.is_active OR reviewer.role NOT IN ('admin', 'editor') THEN
        RAISE EXCEPTION 'approving review % was not made by an active human editor', approval.id
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT id INTO latest FROM intelligence_versions
    WHERE record_id = NEW.record_id ORDER BY version_number DESC LIMIT 1;
    IF latest IS DISTINCT FROM NEW.version_id THEN
        RAISE EXCEPTION 'only the latest approved version can be published' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM intelligence_reviews r
        WHERE r.record_id = NEW.record_id AND r.decision <> 'approved'
          AND (r.reviewed_at, r.id::text) > (approval.reviewed_at, approval.id::text)
    ) THEN
        RAISE EXCEPTION 'approval % was superseded by a later decision', approval.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$
"""


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('intelligence_records',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('source_item_id', sa.Uuid(), nullable=False),
    sa.Column('extraction_run_id', sa.Uuid(), nullable=True),
    sa.Column('incident_id', sa.Uuid(), nullable=True, comment='Only actionable events link to an incident.'),
    sa.Column('extraction_version', sa.String(length=48), nullable=False),
    sa.Column('taxonomy_version', sa.String(length=24), nullable=False),
    sa.Column('primary_category', sa.String(length=32), nullable=False),
    sa.Column('primary_subtype', sa.String(length=40), nullable=True),
    sa.Column('secondary_categories', postgresql.ARRAY(sa.String(length=32)), server_default=sa.text("'{}'::varchar[]"), nullable=False),
    sa.Column('record_kind', sa.String(length=32), nullable=False),
    sa.Column('temporal_status', sa.String(length=16), nullable=False),
    sa.Column('geographic_scope', sa.String(length=24), nullable=False),
    sa.Column('classification_confidence', sa.Float(), nullable=False),
    sa.Column('headline', sa.Text(), nullable=False),
    sa.Column('neutral_summary', sa.Text(), nullable=False),
    sa.Column('event_date', sa.Date(), nullable=True),
    sa.Column('location_description', sa.Text(), nullable=True),
    sa.Column('country', sa.Text(), nullable=True),
    sa.Column('province', sa.Text(), nullable=True),
    sa.Column('district_or_town', sa.Text(), nullable=True),
    sa.Column('road_name', sa.Text(), nullable=True),
    sa.Column('source_attribution', sa.Text(), nullable=True),
    sa.Column('topic_key', sa.Text(), nullable=True, comment='Groups follow-up items about one project, policy or report; not a dedup key.'),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='Category-specific payload, validated against app.schemas.intelligence.'),
    sa.Column('quality', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='Data-quality flags, missing information, evidence quotes, review hints.'),
    sa.Column('needs_editorial_review', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'candidate'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("geographic_scope IN ('precise_point', 'approximate_point', 'road_segment', 'corridor', 'town', 'district', 'province', 'national', 'regional', 'unknown')", name=op.f('ck_intelligence_records_geographic_scope_valid')),
    sa.CheckConstraint("incident_id IS NULL OR (record_kind = 'actionable_event' AND primary_category IN ('road_hazard', 'road_incident', 'traffic_disruption'))", name=op.f('ck_intelligence_records_only_actionable_events_link_incidents')),
    sa.CheckConstraint("primary_category IN ('road_incident', 'traffic_disruption', 'road_hazard', 'road_infrastructure', 'public_transport', 'freight_and_logistics', 'road_safety', 'road_safety_data', 'transport_policy', 'other_transport_intelligence')", name=op.f('ck_intelligence_records_primary_category_valid')),
    sa.CheckConstraint("primary_subtype IS NULL OR (primary_category = 'road_incident' AND primary_subtype IN ('collision', 'head_on_collision', 'rear_end_collision', 'multi_vehicle_collision', 'vehicle_rollover', 'pedestrian_collision', 'cyclist_collision', 'hit_and_run', 'vehicle_fire', 'vehicle_off_road', 'other_road_accident')) OR (primary_category = 'traffic_disruption' AND primary_subtype IN ('traffic_congestion', 'road_closure', 'lane_closure', 'traffic_diversion', 'road_blockage', 'vehicle_breakdown', 'abnormal_delay', 'border_queue', 'tollgate_congestion', 'other_traffic_disruption')) OR (primary_category = 'road_hazard' AND primary_subtype IN ('pothole', 'road_surface_damage', 'flooded_road', 'washed_away_road', 'bridge_damage', 'landslide_or_rockfall', 'fallen_tree', 'debris_on_road', 'unsafe_roadworks', 'poor_visibility', 'other_road_hazard')) OR (primary_category = 'road_infrastructure' AND primary_subtype IN ('road_rehabilitation', 'road_construction', 'bridge_construction', 'bridge_rehabilitation', 'scheduled_roadworks', 'infrastructure_project', 'tollgate_infrastructure', 'road_network_upgrade', 'infrastructure_funding', 'other_road_infrastructure')) OR (primary_category = 'public_transport' AND primary_subtype IN ('bus_service_change', 'kombi_service_change', 'route_change', 'fare_change', 'service_disruption', 'operator_announcement', 'passenger_safety', 'fleet_development', 'public_transport_regulation', 'other_public_transport')) OR (primary_category = 'freight_and_logistics' AND primary_subtype IN ('border_post_delay', 'freight_restriction', 'haulage_disruption', 'truck_queue', 'logistics_policy', 'freight_route_change', 'cross_border_transport', 'other_freight_logistics')) OR (primary_category = 'road_safety' AND primary_subtype IN ('road_safety_campaign', 'traffic_enforcement', 'speed_enforcement', 'drunk_driving_enforcement', 'vehicle_roadworthiness', 'driver_licensing', 'safety_training', 'safety_recommendations', 'other_road_safety')) OR (primary_category = 'road_safety_data' AND primary_subtype IN ('accident_statistics', 'fatality_statistics', 'injury_statistics', 'blackspot_analysis', 'traffic_volume_statistics', 'transport_research', 'annual_report', 'safety_trend_analysis', 'other_road_safety_data')) OR (primary_category = 'transport_policy' AND primary_subtype IN ('policy_announcement', 'transport_legislation', 'toll_fee_change', 'licensing_regulation', 'vehicle_regulation', 'enforcement_policy', 'transport_budget', 'institutional_announcement', 'other_transport_policy')) OR (primary_category = 'other_transport_intelligence' AND primary_subtype IN ('other'))", name=op.f('ck_intelligence_records_subtype_matches_category')),
    sa.CheckConstraint("primary_subtype IS NULL OR primary_subtype IN ('collision', 'head_on_collision', 'rear_end_collision', 'multi_vehicle_collision', 'vehicle_rollover', 'pedestrian_collision', 'cyclist_collision', 'hit_and_run', 'vehicle_fire', 'vehicle_off_road', 'other_road_accident', 'traffic_congestion', 'road_closure', 'lane_closure', 'traffic_diversion', 'road_blockage', 'vehicle_breakdown', 'abnormal_delay', 'border_queue', 'tollgate_congestion', 'other_traffic_disruption', 'pothole', 'road_surface_damage', 'flooded_road', 'washed_away_road', 'bridge_damage', 'landslide_or_rockfall', 'fallen_tree', 'debris_on_road', 'unsafe_roadworks', 'poor_visibility', 'other_road_hazard', 'road_rehabilitation', 'road_construction', 'bridge_construction', 'bridge_rehabilitation', 'scheduled_roadworks', 'infrastructure_project', 'tollgate_infrastructure', 'road_network_upgrade', 'infrastructure_funding', 'other_road_infrastructure', 'bus_service_change', 'kombi_service_change', 'route_change', 'fare_change', 'service_disruption', 'operator_announcement', 'passenger_safety', 'fleet_development', 'public_transport_regulation', 'other_public_transport', 'border_post_delay', 'freight_restriction', 'haulage_disruption', 'truck_queue', 'logistics_policy', 'freight_route_change', 'cross_border_transport', 'other_freight_logistics', 'road_safety_campaign', 'traffic_enforcement', 'speed_enforcement', 'drunk_driving_enforcement', 'vehicle_roadworthiness', 'driver_licensing', 'safety_training', 'safety_recommendations', 'other_road_safety', 'accident_statistics', 'fatality_statistics', 'injury_statistics', 'blackspot_analysis', 'traffic_volume_statistics', 'transport_research', 'annual_report', 'safety_trend_analysis', 'other_road_safety_data', 'policy_announcement', 'transport_legislation', 'toll_fee_change', 'licensing_regulation', 'vehicle_regulation', 'enforcement_policy', 'transport_budget', 'institutional_announcement', 'other_transport_policy', 'other')", name=op.f('ck_intelligence_records_primary_subtype_valid')),
    sa.CheckConstraint("record_kind IN ('actionable_event', 'informational_development', 'statistical_report', 'research_or_analysis', 'advisory', 'unknown')", name=op.f('ck_intelligence_records_record_kind_valid')),
    sa.CheckConstraint("status IN ('candidate', 'under_review', 'approved', 'rejected', 'published', 'archived')", name=op.f('ck_intelligence_records_status_valid')),
    sa.CheckConstraint("temporal_status IN ('planned', 'ongoing', 'resolved', 'historical', 'unknown')", name=op.f('ck_intelligence_records_temporal_status_valid')),
    sa.CheckConstraint('classification_confidence BETWEEN 0 AND 1', name=op.f('ck_intelligence_records_confidence_range')),
    sa.CheckConstraint('length(btrim(headline)) > 0 AND length(btrim(neutral_summary)) > 0', name=op.f('ck_intelligence_records_content_not_blank')),
    sa.ForeignKeyConstraint(['extraction_run_id'], ['extraction_runs.id'], name=op.f('fk_intelligence_records_extraction_run_id_extraction_runs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], name=op.f('fk_intelligence_records_incident_id_incidents'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_item_id'], ['source_items.id'], name=op.f('fk_intelligence_records_source_item_id_source_items'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intelligence_records')),
    sa.UniqueConstraint('source_item_id', 'extraction_version', name='uq_intelligence_records_source_item_id_extraction_version')
    )
    op.create_index('ix_intelligence_records_category_status_created', 'intelligence_records', ['primary_category', 'status', 'created_at'], unique=False)
    op.create_index('ix_intelligence_records_event_date', 'intelligence_records', ['event_date'], unique=False)
    op.create_index('ix_intelligence_records_extraction_run_id', 'intelligence_records', ['extraction_run_id'], unique=False)
    op.create_index('ix_intelligence_records_incident_id', 'intelligence_records', ['incident_id'], unique=False)
    op.create_index('ix_intelligence_records_province', 'intelligence_records', ['province'], unique=False)
    op.create_index('ix_intelligence_records_record_kind', 'intelligence_records', ['record_kind'], unique=False)
    op.create_index('ix_intelligence_records_topic_key', 'intelligence_records', ['topic_key'], unique=False)
    op.create_table('intelligence_versions',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('record_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('headline', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('primary_category', sa.String(length=32), nullable=False),
    sa.Column('primary_subtype', sa.String(length=40), nullable=True),
    sa.Column('geographic_scope', sa.String(length=24), nullable=False),
    sa.Column('event_date', sa.Date(), nullable=True),
    sa.Column('figures', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False, comment='Snapshot of the confirmed statistical observations.'),
    sa.Column('source_attribution', sa.Text(), nullable=True),
    sa.Column('change_note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("geographic_scope IN ('precise_point', 'approximate_point', 'road_segment', 'corridor', 'town', 'district', 'province', 'national', 'regional', 'unknown')", name=op.f('ck_intelligence_versions_geographic_scope_valid')),
    sa.CheckConstraint("primary_category IN ('road_incident', 'traffic_disruption', 'road_hazard', 'road_infrastructure', 'public_transport', 'freight_and_logistics', 'road_safety', 'road_safety_data', 'transport_policy', 'other_transport_intelligence')", name=op.f('ck_intelligence_versions_primary_category_valid')),
    sa.CheckConstraint("primary_subtype IS NULL OR (primary_category = 'road_incident' AND primary_subtype IN ('collision', 'head_on_collision', 'rear_end_collision', 'multi_vehicle_collision', 'vehicle_rollover', 'pedestrian_collision', 'cyclist_collision', 'hit_and_run', 'vehicle_fire', 'vehicle_off_road', 'other_road_accident')) OR (primary_category = 'traffic_disruption' AND primary_subtype IN ('traffic_congestion', 'road_closure', 'lane_closure', 'traffic_diversion', 'road_blockage', 'vehicle_breakdown', 'abnormal_delay', 'border_queue', 'tollgate_congestion', 'other_traffic_disruption')) OR (primary_category = 'road_hazard' AND primary_subtype IN ('pothole', 'road_surface_damage', 'flooded_road', 'washed_away_road', 'bridge_damage', 'landslide_or_rockfall', 'fallen_tree', 'debris_on_road', 'unsafe_roadworks', 'poor_visibility', 'other_road_hazard')) OR (primary_category = 'road_infrastructure' AND primary_subtype IN ('road_rehabilitation', 'road_construction', 'bridge_construction', 'bridge_rehabilitation', 'scheduled_roadworks', 'infrastructure_project', 'tollgate_infrastructure', 'road_network_upgrade', 'infrastructure_funding', 'other_road_infrastructure')) OR (primary_category = 'public_transport' AND primary_subtype IN ('bus_service_change', 'kombi_service_change', 'route_change', 'fare_change', 'service_disruption', 'operator_announcement', 'passenger_safety', 'fleet_development', 'public_transport_regulation', 'other_public_transport')) OR (primary_category = 'freight_and_logistics' AND primary_subtype IN ('border_post_delay', 'freight_restriction', 'haulage_disruption', 'truck_queue', 'logistics_policy', 'freight_route_change', 'cross_border_transport', 'other_freight_logistics')) OR (primary_category = 'road_safety' AND primary_subtype IN ('road_safety_campaign', 'traffic_enforcement', 'speed_enforcement', 'drunk_driving_enforcement', 'vehicle_roadworthiness', 'driver_licensing', 'safety_training', 'safety_recommendations', 'other_road_safety')) OR (primary_category = 'road_safety_data' AND primary_subtype IN ('accident_statistics', 'fatality_statistics', 'injury_statistics', 'blackspot_analysis', 'traffic_volume_statistics', 'transport_research', 'annual_report', 'safety_trend_analysis', 'other_road_safety_data')) OR (primary_category = 'transport_policy' AND primary_subtype IN ('policy_announcement', 'transport_legislation', 'toll_fee_change', 'licensing_regulation', 'vehicle_regulation', 'enforcement_policy', 'transport_budget', 'institutional_announcement', 'other_transport_policy')) OR (primary_category = 'other_transport_intelligence' AND primary_subtype IN ('other'))", name=op.f('ck_intelligence_versions_subtype_matches_category')),
    sa.CheckConstraint('length(btrim(headline)) > 0 AND length(btrim(summary)) > 0', name=op.f('ck_intelligence_versions_content_not_blank')),
    sa.CheckConstraint('version_number >= 1', name=op.f('ck_intelligence_versions_version_number_positive')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_intelligence_versions_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['record_id'], ['intelligence_records.id'], name=op.f('fk_intelligence_versions_record_id_intelligence_records'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intelligence_versions')),
    sa.UniqueConstraint('id', 'record_id', name='uq_intelligence_versions_id_record_id'),
    sa.UniqueConstraint('record_id', 'version_number', name='uq_intelligence_versions_record_id_version_number')
    )
    op.create_index('ix_intelligence_versions_created_by', 'intelligence_versions', ['created_by'], unique=False)
    op.create_table('statistical_observations',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('record_id', sa.Uuid(), nullable=False),
    sa.Column('metric', sa.Text(), nullable=False),
    sa.Column('value', sa.Numeric(precision=20, scale=4), nullable=False),
    sa.Column('unit', sa.Text(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('geographic_coverage', sa.Text(), nullable=True),
    sa.Column('source_reference', sa.Text(), nullable=True),
    sa.Column('methodology', sa.Text(), nullable=True),
    sa.Column('comparison_period', sa.Text(), nullable=True),
    sa.Column('is_preliminary', sa.Boolean(), nullable=True),
    sa.Column('verification_status', sa.String(length=16), server_default=sa.text("'unverified'"), nullable=False),
    sa.Column('verified_by', sa.Uuid(), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("verification_status = 'unverified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)", name=op.f('ck_statistical_observations_verification_has_actor')),
    sa.CheckConstraint("verification_status IN ('unverified', 'verified', 'rejected')", name=op.f('ck_statistical_observations_verification_status_valid')),
    sa.CheckConstraint('period_start IS NULL OR period_end IS NULL OR period_end >= period_start', name=op.f('ck_statistical_observations_period_order')),
    sa.ForeignKeyConstraint(['record_id'], ['intelligence_records.id'], name=op.f('fk_statistical_observations_record_id_intelligence_records'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['verified_by'], ['users.id'], name=op.f('fk_statistical_observations_verified_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_statistical_observations'))
    )
    op.create_index('ix_statistical_observations_metric_period', 'statistical_observations', ['metric', 'period_start', 'period_end'], unique=False)
    op.create_index('ix_statistical_observations_record_id', 'statistical_observations', ['record_id'], unique=False)
    op.create_index('ix_statistical_observations_verified_by', 'statistical_observations', ['verified_by'], unique=False)
    op.create_table('intelligence_reviews',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('record_id', sa.Uuid(), nullable=False),
    sa.Column('version_id', sa.Uuid(), nullable=True),
    sa.Column('reviewer_id', sa.Uuid(), nullable=False),
    sa.Column('decision', sa.String(length=16), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("decision <> 'approved' OR version_id IS NOT NULL", name=op.f('ck_intelligence_reviews_approval_requires_version')),
    sa.CheckConstraint("decision IN ('approved', 'rejected', 'needs_changes')", name=op.f('ck_intelligence_reviews_decision_valid')),
    sa.ForeignKeyConstraint(['record_id'], ['intelligence_records.id'], name=op.f('fk_intelligence_reviews_record_id_intelligence_records'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_intelligence_reviews_reviewer_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['version_id', 'record_id'], ['intelligence_versions.id', 'intelligence_versions.record_id'], name='fk_intelligence_reviews_version_id_intelligence_versions', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intelligence_reviews')),
    sa.UniqueConstraint('id', 'record_id', 'version_id', name='uq_intelligence_reviews_id_record_id_version_id')
    )
    op.create_index('ix_intelligence_reviews_record_id_reviewed_at', 'intelligence_reviews', ['record_id', 'reviewed_at'], unique=False)
    op.create_index('ix_intelligence_reviews_reviewer_id', 'intelligence_reviews', ['reviewer_id'], unique=False)
    op.create_index('ix_intelligence_reviews_version_id', 'intelligence_reviews', ['version_id'], unique=False)
    op.create_table('publication_outputs',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('record_id', sa.Uuid(), nullable=False),
    sa.Column('version_id', sa.Uuid(), nullable=False),
    sa.Column('approval_review_id', sa.Uuid(), nullable=False),
    sa.Column('output_type', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=16), server_default=sa.text("'published'"), nullable=False),
    sa.Column('published_by', sa.Uuid(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("output_type IN ('transport_news', 'statistical_insight', 'analytical_report', 'journalism_briefing', 'dashboard_source')", name=op.f('ck_publication_outputs_output_type_valid')),
    sa.CheckConstraint("status <> 'withdrawn' OR withdrawn_at IS NOT NULL", name=op.f('ck_publication_outputs_withdrawn_has_timestamp')),
    sa.CheckConstraint("status IN ('published', 'withdrawn')", name=op.f('ck_publication_outputs_status_valid')),
    sa.ForeignKeyConstraint(['approval_review_id', 'record_id', 'version_id'], ['intelligence_reviews.id', 'intelligence_reviews.record_id', 'intelligence_reviews.version_id'], name='fk_publication_outputs_approval_review_id_intelligence_reviews', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['published_by'], ['users.id'], name=op.f('fk_publication_outputs_published_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['record_id'], ['intelligence_records.id'], name=op.f('fk_publication_outputs_record_id_intelligence_records'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_publication_outputs')),
    sa.UniqueConstraint('version_id', 'output_type', name='uq_publication_outputs_version_id_output_type')
    )
    op.create_index('ix_publication_outputs_published_by', 'publication_outputs', ['published_by'], unique=False)
    op.create_index('ix_publication_outputs_record_id', 'publication_outputs', ['record_id'], unique=False)
    op.create_index('ix_publication_outputs_type_status_published', 'publication_outputs', ['output_type', 'status', 'published_at'], unique=False)
    # ### end Alembic commands ###

    # ---- triggers (this revision stays self-contained) ----------------------------------
    for table in ("intelligence_records", "statistical_observations"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION saferoutezw_set_updated_at()"
        )
    for table in ("intelligence_versions", "intelligence_reviews"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION saferoutezw_forbid_modification()"
        )
    op.execute(
        "CREATE TRIGGER trg_intelligence_reviews_require_human_reviewer BEFORE INSERT ON intelligence_reviews "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_human_reviewer()"
    )
    op.execute(FN_LATEST_VERSION)
    op.execute(
        "CREATE TRIGGER trg_intelligence_reviews_latest_version BEFORE INSERT ON intelligence_reviews "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_latest_intelligence_version()"
    )
    op.execute(FN_RECORD_APPROVAL)
    op.execute(
        "CREATE TRIGGER trg_intelligence_records_require_approval "
        "BEFORE INSERT OR UPDATE OF status ON intelligence_records "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_intelligence_approval()"
    )
    op.execute(FN_PUBLICATION_APPROVAL)
    op.execute(
        "CREATE TRIGGER trg_publication_outputs_require_approval BEFORE INSERT OR UPDATE ON publication_outputs "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_publication_approval()"
    )

    # ---- incident types for closures and disruptions ------------------------------------
    op.drop_constraint(op.f("ck_incidents_incident_type_valid"), "incidents", type_="check")
    op.create_check_constraint(
        op.f("ck_incidents_incident_type_valid"), "incidents", f"incident_type IN ({NEW_INCIDENT_TYPES})"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Closures/disruptions have no equivalent in the old vocabulary; fold them into 'other'
    # (the information stays in the incident's text) before the narrower constraint returns.
    op.drop_constraint(op.f("ck_incidents_incident_type_valid"), "incidents", type_="check")
    op.execute("UPDATE incidents SET incident_type = 'other' WHERE incident_type IN ('road_closure', 'traffic_disruption')")
    op.create_check_constraint(
        op.f("ck_incidents_incident_type_valid"), "incidents", f"incident_type IN ({OLD_INCIDENT_TYPES})"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_publication_outputs_require_approval ON publication_outputs")
    op.execute("DROP TRIGGER IF EXISTS trg_intelligence_records_require_approval ON intelligence_records")
    op.execute("DROP TRIGGER IF EXISTS trg_intelligence_reviews_latest_version ON intelligence_reviews")
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_publication_outputs_type_status_published', table_name='publication_outputs')
    op.drop_index('ix_publication_outputs_record_id', table_name='publication_outputs')
    op.drop_index('ix_publication_outputs_published_by', table_name='publication_outputs')
    op.drop_table('publication_outputs')
    op.drop_index('ix_intelligence_reviews_version_id', table_name='intelligence_reviews')
    op.drop_index('ix_intelligence_reviews_reviewer_id', table_name='intelligence_reviews')
    op.drop_index('ix_intelligence_reviews_record_id_reviewed_at', table_name='intelligence_reviews')
    op.drop_table('intelligence_reviews')
    op.drop_index('ix_statistical_observations_verified_by', table_name='statistical_observations')
    op.drop_index('ix_statistical_observations_record_id', table_name='statistical_observations')
    op.drop_index('ix_statistical_observations_metric_period', table_name='statistical_observations')
    op.drop_table('statistical_observations')
    op.drop_index('ix_intelligence_versions_created_by', table_name='intelligence_versions')
    op.drop_table('intelligence_versions')
    op.drop_index('ix_intelligence_records_topic_key', table_name='intelligence_records')
    op.drop_index('ix_intelligence_records_record_kind', table_name='intelligence_records')
    op.drop_index('ix_intelligence_records_province', table_name='intelligence_records')
    op.drop_index('ix_intelligence_records_incident_id', table_name='intelligence_records')
    op.drop_index('ix_intelligence_records_extraction_run_id', table_name='intelligence_records')
    op.drop_index('ix_intelligence_records_event_date', table_name='intelligence_records')
    op.drop_index('ix_intelligence_records_category_status_created', table_name='intelligence_records')
    op.drop_table('intelligence_records')
    # ### end Alembic commands ###
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_require_publication_approval()")
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_require_intelligence_approval()")
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_require_latest_intelligence_version()")
