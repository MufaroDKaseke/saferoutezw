"""The application tables: the 16 specified for SafeRouteZW plus the 2 auth tables."""

EXPECTED_TABLES = frozenset(
    {
        # A. Source ingestion
        "sources",
        "ingestion_runs",
        "source_items",
        # B. Incident intelligence
        "incidents",
        "incident_evidence",
        "extraction_runs",
        # C. Geospatial intelligence
        "blackspots",
        "incident_blackspot_matches",
        # D. Editorial workflow
        "users",
        "user_sessions",
        "login_attempts",
        "bulletin_versions",
        "editorial_reviews",
        # E. Public alerts
        "public_alerts",
        "delivery_channels",
        "notification_outbox",
        "delivery_attempts",
        # F. Auditing
        "audit_events",
    }
)
