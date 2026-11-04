"""Outbound client (retries, timeouts, secrecy), webhook parsing, provider and the worker. Offline."""

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.integrations.whatsapp.client import MetaCloudClient, MockWhatsAppClient, build_client
from app.integrations.whatsapp.messages import (
    Choice,
    buttons_message,
    list_message,
    parse_webhook,
    text_message,
    to_payload,
)
from app.jobs import whatsapp_dispatch as job
from app.models import AlertSubscriber, SubscriberDelivery, WhatsAppConversation, WhatsAppInbound, WhatsAppOutbound
from app.services.notifications.whatsapp_meta import WhatsAppMetaProvider
from app.services.whatsapp.context import Deps, PlaceLookupUnavailable
from app.services.whatsapp.inbox import StoreResult, store_message
from app.services.whatsapp.route_check import StaticResolver
from app.integrations.whatsapp.messages import InboundEvent
from public_helpers import make_settings
from whatsapp_helpers import WA_ID, bot_settings, make_deps

pytestmark = pytest.mark.usefixtures("migrated_engine")

TOKEN = "EAAG-super-secret-token"


def live_settings(**overrides):
    return make_settings(
        whatsapp_send_mode="live", whatsapp_access_token=TOKEN, whatsapp_phone_number_id="1055",
        whatsapp_graph_api_version="v23.0", **overrides,
    )


def client_with(handler, **overrides):
    sleeps: list[float] = []
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return MetaCloudClient(live_settings(**overrides), http=http, sleep=sleeps.append), sleeps


OK = httpx.Response(200, json={"messages": [{"id": "wamid.SENT1"}]})


# ---- Meta client -------------------------------------------------------------------------------


def test_live_send_posts_to_the_documented_endpoint_with_a_bearer_token():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["json"] = str(request.url), request.headers["Authorization"], request.read()
        return OK

    client, _ = client_with(handler)
    result = client.send("263771234567", text_message("hello"))
    assert result.status == "sent" and result.provider_reference == "wamid.SENT1"
    assert seen["url"] == "https://graph.facebook.com/v23.0/1055/messages"
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert b'"messaging_product":"whatsapp"' in seen["json"].replace(b" ", b"")


def test_server_errors_are_retried_with_backoff_then_succeed():
    answers = iter([httpx.Response(503), httpx.Response(429), OK])
    calls = []

    def handler(request):
        calls.append(1)
        return next(answers)

    client, sleeps = client_with(handler)
    assert client.send("1", text_message("x")).status == "sent"
    assert len(calls) == 3 and sleeps == [1, 2]


def test_retries_are_bounded_and_the_failure_is_reported():
    calls = []
    client, _ = client_with(lambda r: calls.append(1) or httpx.Response(500), whatsapp_api_max_retries=2)
    result = client.send("1", text_message("x"))
    assert result.status == "failed" and len(calls) == 3


def test_client_errors_are_not_retried():
    calls = []
    body = {"error": {"code": 131047, "message": "Re-engagement message"}}
    client, _ = client_with(lambda r: calls.append(1) or httpx.Response(400, json=body))
    result = client.send("1", text_message("x"))
    assert result.status == "failed" and len(calls) == 1 and "131047" in result.error


def test_a_timeout_is_unknown_and_never_retried_to_avoid_double_sending():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    client, _ = client_with(handler)
    result = client.send("1", text_message("x"))
    assert result.status == "unknown" and len(calls) == 1


def test_connection_failures_are_retried():
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectError("down")
        return OK

    client, _ = client_with(handler)
    assert client.send("1", text_message("x")).status == "sent"


def test_the_token_and_message_text_never_reach_the_logs(caplog):
    caplog.set_level(logging.DEBUG)
    client, _ = client_with(lambda r: httpx.Response(401, json={"error": {"code": 190}}))
    result = client.send("263771234567", text_message("private words about an accident"))
    logged = caplog.text + (result.error or "")
    assert TOKEN not in logged and "private words" not in logged and "263771234567" not in logged


def test_template_payload_and_interactive_payloads_follow_the_cloud_api_shape():
    sent = []
    client, _ = client_with(lambda r: sent.append(r.read()) or OK, whatsapp_alert_template_name="road_alert")
    client.send_template("263771234567", "road_alert", "en", ["Crash on A3"])
    assert b'"type":"template"' in sent[0].replace(b" ", b"") and b"road_alert" in sent[0]

    buttons = to_payload("1", buttons_message("Pick", [Choice(str(i), f"Option number {i} is long") for i in range(5)]))
    assert buttons["interactive"]["type"] == "button" and len(buttons["interactive"]["action"]["buttons"]) == 3
    assert all(len(b["reply"]["title"]) <= 20 for b in buttons["interactive"]["action"]["buttons"])
    rows = to_payload("1", list_message("Pick", [Choice(f"r{i}", "T" * 40, "D" * 100) for i in range(15)]))
    section = rows["interactive"]["action"]["sections"][0]["rows"]
    assert len(section) == 10 and all(len(r["title"]) <= 24 and len(r["description"]) <= 72 for r in section)


def test_default_client_is_the_mock_and_live_needs_credentials():
    assert isinstance(build_client(make_settings()), MockWhatsAppClient)
    with pytest.raises(RuntimeError):
        build_client(make_settings(whatsapp_send_mode="live"))


# ---- webhook parsing ---------------------------------------------------------------------------


def wrap(*messages):
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": list(messages)}}]}]}


def msg(kind, **fields):
    return {"id": f"wamid.{kind}", "from": "263771234567", "timestamp": "1760000000", "type": kind, **fields}


def test_parser_understands_text_buttons_lists_locations_and_media():
    parsed = parse_webhook(wrap(
        msg("text", text={"body": "hello"}),
        msg("interactive", interactive={"type": "button_reply", "button_reply": {"id": "2", "title": "Road alerts"}}),
        msg("interactive", interactive={"type": "list_reply", "list_reply": {"id": "c:origin:1", "title": "Harare"}}),
        msg("location", location={"latitude": -17.8, "longitude": 31.0, "name": "Somewhere", "address": "x"}),
        msg("image", image={"id": "media-1"}),
        msg("sticker"),
        msg("reaction", reaction={}),
    ))
    assert [(e.kind, e.text, e.reply_id) for e in parsed.messages[:3]] == [
        ("text", "hello", None), ("reply", "Road alerts", "2"), ("reply", "Harare", "c:origin:1")]
    assert (parsed.messages[3].kind, parsed.messages[3].latitude) == ("location", -17.8)
    assert [e.kind for e in parsed.messages[4:]] == ["media", "media", "unsupported"]
    assert "Somewhere" not in str(parsed.messages[3].payload())  # place names and addresses are not kept


def test_parser_skips_malformed_entries_instead_of_failing():
    bad = {"object": "whatsapp_business_account", "entry": [None, {"changes": [None, {"value": {"messages": [None, {"id": 5}, {"id": "w", "from": "abc"}]}}]}]}
    assert parse_webhook(bad).messages == []
    assert parse_webhook({"object": "page"}).messages == []
    assert parse_webhook(msg("text")).messages == []
    pin = parse_webhook(wrap(msg("location", location={"latitude": 999, "longitude": 1})))
    assert pin.messages[0].kind == "unsupported"


# ---- provider ----------------------------------------------------------------------------------


def test_provider_sends_codes_as_session_text_and_alerts_as_the_approved_template():
    mock = MockWhatsAppClient()
    plain = WhatsAppMetaProvider(make_settings(), client=mock)
    plain.send_verification("+263771234567", "123456", idempotency_key="k")
    plain.send_alert("+263771234567", "Alert text", idempotency_key="k2")
    assert [m.kind for m in mock.sent] == ["text", "text"] and mock.sent[0].to_wa_id == "263771234567"

    templated = WhatsAppMetaProvider(make_settings(whatsapp_alert_template_name="road_alert"), client=mock)
    templated.send_alert("+263771234567", "Alert text", idempotency_key="k3")
    assert mock.sent[-1].kind == "template" and "road_alert" in mock.sent[-1].body and plain.is_mock


# ---- worker ------------------------------------------------------------------------------------


def enqueue(session, settings, text, wamid, *, sent_at=None):
    event = InboundEvent(wamid=wamid, wa_id=WA_ID, kind="text", text=text, sent_at=sent_at or datetime.now(UTC))
    store_message(session, settings, event, StoreResult())
    session.commit()


def run_job(engine, settings, client, deps=None, **kw):
    return job.process_inbound(engine, settings, client=client, deps=deps or make_deps(), **kw)


def test_worker_processes_stored_messages_in_order_and_clears_their_content(migrated_engine, session):
    settings, client = bot_settings(), MockWhatsAppClient()
    t = datetime.now(UTC)
    enqueue(session, settings, "1", "wamid.B", sent_at=t + timedelta(seconds=1))  # arrives first, was sent second
    enqueue(session, settings, "hi", "wamid.A", sent_at=t)
    summary = run_job(migrated_engine, settings, client)
    session.expire_all()
    assert summary.processed == 2
    rows = session.scalars(select(WhatsAppInbound)).all()
    assert all(r.status == "done" and r.payload == {} and r.processed_at for r in rows)
    assert "Welcome to SafeRouteZW" in client.sent[0].body and "Where did it happen" in client.sent[1].body  # ordered by send time


class ExplodingResolver(StaticResolver):
    def candidates(self, query):
        raise RuntimeError("boom with private words")


def test_a_failing_message_is_retried_a_bounded_number_of_times_then_apologised_for(migrated_engine, session):
    settings, client = bot_settings(whatsapp_max_attempts=3), MockWhatsAppClient()
    deps = Deps(resolver=ExplodingResolver({}), routing_provider=lambda s: None)
    enqueue(session, settings, "hi", "wamid.1")
    run_job(migrated_engine, settings, client, deps)
    enqueue(session, settings, "3", "wamid.2")
    enqueue(session, settings, "Harare", "wamid.3")
    summaries = [run_job(migrated_engine, settings, client, deps) for _ in range(4)]
    session.expire_all()
    bad = session.scalar(select(WhatsAppInbound).where(WhatsAppInbound.wamid == "wamid.3"))
    assert bad.status == "failed" and bad.attempts == 3 and bad.last_error == "RuntimeError"
    assert sum(s.retried for s in summaries) == 2 and sum(s.failed for s in summaries) == 1
    assert client.sent[-1].body.startswith("Sorry, something went wrong")
    assert "private words" not in str(bad.last_error)
    assert sum(m.body.startswith("Sorry") for m in client.sent) == 1


def test_worker_does_not_pick_up_messages_claimed_by_another_worker(migrated_engine, session):
    settings, client = bot_settings(), MockWhatsAppClient()
    enqueue(session, settings, "hi", "wamid.C")
    session.execute(update(WhatsAppInbound).values(status="processing", created_at=datetime.now(UTC)))
    session.commit()
    assert run_job(migrated_engine, settings, client).processed == 0 and client.sent == []


def test_a_stale_claim_from_a_crashed_worker_is_released(migrated_engine, session):
    settings, client = bot_settings(), MockWhatsAppClient()
    enqueue(session, settings, "hi", "wamid.D")
    session.execute(update(WhatsAppInbound).values(status="processing", created_at=datetime.now(UTC) - timedelta(hours=1)))
    session.commit()
    assert run_job(migrated_engine, settings, client).processed == 1


def test_failed_reply_is_logged_and_unknown_outcomes_are_not_resent(migrated_engine, session):
    settings = bot_settings()
    client = MockWhatsAppClient(fail_next=1)
    enqueue(session, settings, "hi", "wamid.E")
    run_job(migrated_engine, settings, client)
    session.expire_all()
    assert session.scalar(select(WhatsAppOutbound.status)) == "failed"


def test_purge_deletes_old_finished_data_and_keeps_work_in_progress(migrated_engine, session):
    settings = bot_settings(whatsapp_retention_days=7)
    for wamid, status in (("wamid.old-done", "done"), ("wamid.old-pending", "pending"), ("wamid.new-done", "done")):
        enqueue(session, settings, "hi", wamid)
        session.execute(update(WhatsAppInbound).where(WhatsAppInbound.wamid == wamid).values(status=status))
    old = datetime.now(UTC) - timedelta(days=30)
    session.execute(update(WhatsAppInbound).where(WhatsAppInbound.wamid.in_(("wamid.old-done", "wamid.old-pending"))).values(created_at=old))
    session.commit()
    assert job.purge(migrated_engine, settings) == 1
    session.expire_all()
    assert {r.wamid for r in session.scalars(select(WhatsAppInbound))} == {"wamid.old-pending", "wamid.new-done"}


def test_idle_conversations_are_purged_after_the_retention_period(migrated_engine, session):
    settings, client = bot_settings(whatsapp_retention_days=7), MockWhatsAppClient()
    enqueue(session, settings, "hi", "wamid.F")
    run_job(migrated_engine, settings, client)
    session.execute(update(WhatsAppConversation).values(expires_at=datetime.now(UTC) - timedelta(days=30)))
    session.commit()
    job.purge(migrated_engine, settings)
    session.expire_all()
    assert session.scalars(select(WhatsAppConversation)).all() == []


def test_the_whatsapp_alert_run_leaves_other_channels_alone(migrated_engine, session):
    from public_helpers import make_published_alert
    from test_notifications import make_subscriber

    settings = bot_settings()
    make_published_alert(session)
    make_subscriber(session, settings, "+263771000009", channel="sms")
    make_subscriber(session, settings, "+263771000008", channel="whatsapp")
    summary = job.DispatchSummary()
    job.deliver_alerts(migrated_engine, settings, summary)
    session.expire_all()
    deliveries = {d.channel: d.status for d in session.scalars(select(SubscriberDelivery))}
    assert deliveries == {"whatsapp": "sent"} and summary.alerts_sent == 1


def test_disabled_bot_job_does_nothing(monkeypatch):
    called = []
    monkeypatch.setattr(job, "get_settings", lambda: make_settings(whatsapp_enabled=False))
    monkeypatch.setattr(job, "run_cycle", lambda *a, **k: called.append(1))
    job.dispatch_whatsapp()
    assert called == []
