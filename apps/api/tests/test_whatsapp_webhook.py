"""WhatsApp webhook: verification handshake, signatures, storage, duplicates, statuses."""

import json

import pytest
from sqlalchemy import func, select

from app.integrations.whatsapp.security import compute_signature, verify_challenge, verify_signature
from app.models import WhatsAppInbound, WhatsAppOutbound
from public_helpers import configure  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("migrated_engine")

URL = "/api/v1/webhooks/whatsapp"
SECRET = "test-app-secret"
VERIFY = "test-verify-token"


def body(messages=None, statuses=None) -> dict:
    value: dict = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "1"}}
    if messages:
        value["messages"] = messages
    if statuses:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [{"id": "x", "changes": [{"field": "messages", "value": value}]}]}


def text_message(wamid="wamid.A1", text="hi", sender="263771234567") -> dict:
    return {"id": wamid, "from": sender, "timestamp": "1760000000", "type": "text", "text": {"body": text}}


def post(client, payload: dict, *, secret: str | None = SECRET, header: str | None = None):
    raw = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if header is not None:
        headers["X-Hub-Signature-256"] = header
    elif secret is not None:
        headers["X-Hub-Signature-256"] = compute_signature(raw, secret)
    return client.post(URL, content=raw, headers=headers)


@pytest.fixture
def enabled(configure):  # noqa: F811
    return configure(whatsapp_enabled=True, whatsapp_app_secret=SECRET, whatsapp_verify_token=VERIFY)


# ---- pure signature / handshake checks ----------------------------------------------------------


def test_signature_is_checked_against_the_raw_body():
    raw = b'{"a": 1}'
    good = compute_signature(raw, SECRET)
    assert verify_signature(raw, good, SECRET)
    assert not verify_signature(raw + b" ", good, SECRET)  # body changed after signing
    assert not verify_signature(raw, good, "other-secret")
    assert not verify_signature(raw, None, SECRET)
    assert not verify_signature(raw, "sha256=", SECRET)
    assert not verify_signature(raw, good.replace("sha256=", "md5="), SECRET)
    assert not verify_signature(raw, good, None)  # no secret configured: nothing is trusted


def test_challenge_requires_subscribe_mode_and_matching_token():
    assert verify_challenge("subscribe", "t", "t")
    assert not verify_challenge("subscribe", "x", "t")
    assert not verify_challenge("unsubscribe", "t", "t")
    assert not verify_challenge("subscribe", "t", None)


# ---- GET handshake ------------------------------------------------------------------------------


def test_get_handshake_echoes_the_challenge(client, enabled):
    response = client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345"})
    assert response.status_code == 200
    assert response.text == "12345"


def test_get_handshake_rejects_a_wrong_token(client, enabled):
    response = client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"})
    assert response.status_code == 403


def test_endpoint_is_hidden_while_the_bot_is_disabled(client, configure):
    configure(whatsapp_enabled=False, whatsapp_app_secret=SECRET, whatsapp_verify_token=VERIFY)
    assert client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"}).status_code == 404
    assert post(client, body([text_message()])).status_code == 404


# ---- POST ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("header", [None, "sha256=deadbeef", "garbage"])
def test_invalid_or_missing_signature_is_rejected_and_nothing_stored(client, enabled, session, header):
    payload = body([text_message()])
    response = post(client, payload, secret=None, header=header)
    assert response.status_code == 401
    assert session.scalar(select(func.count()).select_from(WhatsAppInbound)) == 0


def test_valid_message_is_stored_without_processing(client, enabled, session):
    response = post(client, body([text_message(text="1")]))
    assert response.status_code == 200
    row = session.scalar(select(WhatsAppInbound))
    assert row.status == "pending" and row.kind == "text" and row.payload == {"text": "1"}
    assert row.sender_digest and "263771234567" not in row.sender_digest + row.sender_ciphertext
    assert session.scalar(select(func.count()).select_from(WhatsAppOutbound)) == 0  # nothing was answered inline


def test_duplicate_delivery_is_stored_once(client, enabled, session):
    payload = body([text_message(wamid="wamid.DUP")])
    assert post(client, payload).status_code == 200
    assert post(client, payload).status_code == 200  # Meta retries; we still acknowledge
    assert session.scalar(select(func.count()).select_from(WhatsAppInbound)) == 1


def test_malformed_json_is_a_400(client, enabled):
    raw = b"{not json"
    response = client.post(URL, content=raw, headers={"X-Hub-Signature-256": compute_signature(raw, SECRET)})
    assert response.status_code == 400


def test_unknown_event_types_are_acknowledged_and_ignored(client, enabled, session):
    odd = {"id": "wamid.ODD", "from": "263771234567", "timestamp": "1", "type": "reaction", "reaction": {}}
    assert post(client, body([odd])).status_code == 200
    row = session.scalar(select(WhatsAppInbound))
    assert row.kind == "unsupported"


def test_sender_over_the_rate_limit_is_dropped_but_acknowledged(client, configure, session):
    configure(whatsapp_enabled=True, whatsapp_app_secret=SECRET, whatsapp_verify_token=VERIFY, whatsapp_user_msgs_per_minute=2)
    for i in range(5):
        assert post(client, body([text_message(wamid=f"wamid.R{i}")])).status_code == 200
    assert session.scalar(select(func.count()).select_from(WhatsAppInbound)) == 2


def test_delivery_status_callbacks_update_the_outbound_log_and_never_go_backwards(client, enabled, session):
    session.add(WhatsAppOutbound(idempotency_key="k1", sender_digest="d", kind="reply", provider_message_id="wamid.OUT1", status="sent"))
    session.commit()
    ts = {"id": "wamid.OUT1", "recipient_id": "1"}
    assert post(client, body(statuses=[{**ts, "status": "delivered"}])).status_code == 200
    session.expire_all()
    assert session.scalar(select(WhatsAppOutbound.status)) == "delivered"
    post(client, body(statuses=[{**ts, "status": "sent"}]))  # arrives late
    session.expire_all()
    assert session.scalar(select(WhatsAppOutbound.status)) == "delivered"
    post(client, body(statuses=[{**ts, "status": "read"}]))
    session.expire_all()
    assert session.scalar(select(WhatsAppOutbound.status)) == "read"


def test_failed_status_is_recorded_without_leaking_details(client, enabled, session):
    session.add(WhatsAppOutbound(idempotency_key="k2", sender_digest="d", kind="reply", provider_message_id="wamid.OUT2", status="sent"))
    session.commit()
    status = {"id": "wamid.OUT2", "status": "failed", "errors": [{"code": 131047, "title": "Re-engagement message"}]}
    assert post(client, body(statuses=[status])).status_code == 200
    session.expire_all()
    row = session.scalar(select(WhatsAppOutbound))
    assert row.status == "failed" and "131047" in row.last_error
