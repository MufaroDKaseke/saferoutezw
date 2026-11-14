"""Every application table the migrations must create."""

EXPECTED_TABLES = frozenset(
    {
        # A. Source ingestion
        "sources",
        "ingestion_runs",
        "source_items",
        "social_sources",
        "social_quarantine",
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
        # I. WhatsApp bot
        "whatsapp_conversations",
        "whatsapp_inbound",
        "whatsapp_outbound",
        # G. Phone alert subscriptions
        "alert_subscribers",
        "subscription_preferences",
        "subscription_challenges",
        "subscription_consents",
        "subscription_tokens",
        "subscriber_deliveries",
        # H. Transport intelligence
        "intelligence_records",
        "statistical_observations",
        "intelligence_versions",
        "intelligence_reviews",
        "publication_outputs",
        # J. NUST FM story-to-air workflow
        "stories",
        "story_scripts",
        "story_reviews",
        "radio_bulletins",
        "radio_bulletin_revisions",
        "radio_bulletin_items",
        "radio_bulletin_decisions",
        # F. Auditing
        "audit_events",
    }
)
