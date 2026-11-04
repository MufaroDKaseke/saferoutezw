"""End-to-end SYNTHETIC demonstration of the public workflow (mock messaging only).

    cd apps/api
    python scripts/demo_acceptance.py

Walks the acceptance scenario against the configured database using the real services:

 1. a synthetic incident exists internally (plus one unverified candidate that must stay hidden)
 2. an editor saves and approves a specific bulletin version
 3. an editor explicitly publishes that exact version
 4. it appears in the public alert list and on the public map
 5. a route is planned (mock routing) and the published hazard is found near it
 6. a visitor subscribes, the mock provider "verifies" the number, preferences are set
 7. the matching alert is queued and a SIMULATED delivery is recorded
 8. the visitor unsubscribes and receives nothing further
 9. the unverified candidate was never visible

Everything it creates is labelled [SYNTHETIC]. No real SMS/WhatsApp message is sent and no
real routing service is called. Run it against a development database, not production.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geoalchemy2 import WKTElement  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.pagination import PageParams  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.models import Incident, SubscriberDelivery, User  # noqa: E402
from app.models.enums import ReviewDecision  # noqa: E402
from app.models.subscription import SubscriberChannel  # noqa: E402
from app.repositories import public as public_repo  # noqa: E402
from app.schemas.public import PlaceInput, RoutePlanRequest  # noqa: E402
from app.services import alert_notifications, editorial, publishing  # noqa: E402
from app.services import subscriptions as subs  # noqa: E402
from app.services.notifications import get_notification_provider, reset_mock_providers  # noqa: E402
from app.services.route_planning import plan_route  # noqa: E402
from app.services.routing.mock import MockRoutingProvider  # noqa: E402

PHONE = "+263771230000"  # synthetic, non-routable example number
TAG = "[SYNTHETIC]"


def step(n: int, text: str) -> None:
    print(f"{n:>2}. {text}")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAILED: {message}")
    print(f"    ok - {message}")


def main() -> int:
    base = get_settings()
    settings = Settings(
        _env_file=None,
        postgres_host=base.postgres_host, postgres_port=base.postgres_port,
        postgres_user=base.postgres_user, postgres_password=base.postgres_password,
        postgres_db=base.postgres_db,
        notification_provider="mock", routing_provider="mock", otp_resend_cooldown_seconds=0,
        subscription_corridors="A3 Harare-Mutare",
    )
    reset_mock_providers()
    run = uuid.uuid4().hex[:6]
    with Session(get_engine()) as session:
        editor = User(email=f"synthetic-editor-{run}@example.test", display_name=f"{TAG} Editor {run}", role="editor")
        session.add(editor)
        session.flush()

        step(1, "Create a synthetic incident and an unverified candidate")
        incident = Incident(
            reference_code=f"SYNTH-{run}", incident_type="collision", severity="serious", status="under_review",
            location_text="Near Marondera, Mashonaland East", location_status="editor_confirmed",
            location_precision_m=50, geom=WKTElement("POINT(31.6 -18.216)", srid=4326),
        )
        candidate = Incident(
            reference_code=f"SYNTH-CAND-{run}", incident_type="collision", status="candidate",
            location_text="Unverified candidate road",
        )
        session.add_all([incident, candidate])
        session.commit()

        step(2, "Editor saves and approves a specific bulletin version")
        version, _ = editorial.save_bulletin(
            session, editor, incident.id, f"{TAG} Crash on the Harare-Mutare road",
            f"{TAG} A collision was reported near Marondera. Drive with care.", None,
        )
        editorial.record_review(session, editor, incident.id, ReviewDecision.APPROVED, version.id, "synthetic approval")
        before = public_repo.list_alerts(session, PageParams(), q=f"{TAG} Crash", province=None, road=None, hazard_type=None)[1]
        check(before == 0, "approved-but-unpublished bulletin is not public")

        step(3, "Editor explicitly publishes the approved version")
        alert = publishing.publish_alert(
            session, editor, incident.id, version.id, province="Mashonaland East", road_name="A3 Harare-Mutare"
        )
        check(alert.status == "published", "alert is published")

        step(4, "Public list and map show it")
        items, total = public_repo.list_alerts(session, PageParams(), q=f"{TAG} Crash", province=None, road=None, hazard_type=None)
        check(total == 1 and items[0].id == alert.id, "alert is in the public list")
        rows, _ = public_repo.map_rows(session, hazard_type=None, severity=None, since=None)
        check(any(r[0].id == alert.id for r in rows), "alert is on the public map (reliable position)")
        check(all(r[0].incident_id != candidate.id for r in rows), "unverified candidate is not on the map")

        step(5, "Plan a route (mock routing) and find the hazard")
        provider = MockRoutingProvider({"Harare": (-17.8292, 31.0522), "Mutare": (-18.9707, 32.6709)})
        plan = plan_route(
            session, provider, settings,
            RoutePlanRequest(origin=PlaceInput(query="Harare"), destination=PlaceInput(query="Mutare")),
        )
        check(any(h.alert_id == alert.id for h in plan.hazards), "published hazard found near the route")

        step(6, "Visitor subscribes; mock provider verifies the number")
        prefs = subs.validate_preferences(settings, False, ["Mashonaland East"], [])
        subs.register(
            session, settings, e164=PHONE, channel=SubscriberChannel.SMS, prefs=prefs,
            consent_accepted=True, consent_version=subs.CONSENT_VERSION, ip_digest=None, user_agent="demo-script",
        )
        sms = get_notification_provider(settings, "sms")
        verified = subs.verify(session, settings, e164=PHONE, code=sms.last_code_for(PHONE) or "")
        check(verified.activated, "subscription active only after verification")

        step(7, "Queue the matching alert and record a SIMULATED delivery")
        summary = alert_notifications.run_once(session, settings)
        check(summary.sent >= 1, f"mock delivery recorded (queued={summary.queued}, sent={summary.sent}) - nothing was sent to a phone")
        delivery = session.scalars(select(SubscriberDelivery).order_by(SubscriberDelivery.created_at.desc())).first()
        check(delivery is not None and delivery.provider_name == "mock", "delivery is labelled mock")

        step(8, "Visitor unsubscribes")
        subscriber = subs.subscriber_for_token(session, verified.token)
        subs.unsubscribe(session, subscriber)
        check(subscriber.status == "unsubscribed", "unsubscribed")

        step(9, "Unverified incident stayed hidden throughout")
        everything = public_repo.list_alerts(session, PageParams(page_size=100), q=None, province=None, road=None, hazard_type=None)[0]
        check(all(candidate.reference_code not in repr(i) for i in everything), "candidate never appeared publicly")
    print("\nAll acceptance steps passed. Synthetic records remain in the database, labelled [SYNTHETIC].")
    return 0


if __name__ == "__main__":
    sys.exit(main())
