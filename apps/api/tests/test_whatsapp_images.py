"""Map images in WhatsApp messages: rendering, upload, and the text fallback. No database, no network."""

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.maps import static_map
from app.integrations.whatsapp.client import MetaCloudClient
from app.integrations.whatsapp.messages import image_message, text_message

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def settings(**over) -> Settings:
    base = {
        "whatsapp_access_token": SecretStr("tok"), "whatsapp_phone_number_id": "123",
        "geoapify_api_key": SecretStr("secret-geo-key"), "routing_provider": "mock",
    }
    base.update(over)
    return Settings(_env_file=None, **base)


def meta_client(handler):
    return MetaCloudClient(settings(), http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _s: None)


def test_image_is_uploaded_then_sent_with_its_caption():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "MEDIA1"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    result = meta_client(handler).send("263771234567", image_message("hello caption", JPEG))
    assert result.status == "sent"
    assert seen[0].url.path.endswith("/123/media") and seen[1].url.path.endswith("/123/messages")
    assert b'"type":"image"' in seen[1].content.replace(b" ", b"")
    assert b"MEDIA1" in seen[1].content and b"hello caption" in seen[1].content


def test_failed_upload_falls_back_to_the_caption_as_text():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media"):
            return httpx.Response(400, json={"error": {"code": 100}})
        sent.append(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    result = meta_client(handler).send("263771234567", image_message("the alert text", JPEG))
    assert result.status == "sent"
    assert b'"type":"text"' in sent[0].replace(b" ", b"") and b"the alert text" in sent[0]


def test_text_messages_do_not_touch_media():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    meta_client(handler).send("263771234567", text_message("hi"))
    assert paths == ["/v23.0/123/messages"]


def test_no_geoapify_key_means_no_map():
    assert static_map.incident_map(settings(geoapify_api_key=None), -17.8, 31.0) is None


def test_map_request_carries_markers_and_a_thinned_route(monkeypatch):
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    monkeypatch.setattr(static_map.httpx, "get", fake_get)
    line = {"type": "LineString", "coordinates": [[31.0 + i * 0.001, -17.8 - i * 0.001] for i in range(2000)]}
    image = static_map.route_map(settings(), line, (-17.8, 31.0), (-19.8, 33.0), [(-18.5, 32.0, False), (-18.9, 32.5, True)])
    assert image == JPEG
    url = urls[0]
    assert url.count("polyline:") == 1
    assert len(url.split("polyline:")[1].split(";")[0].split(",")) == static_map.MAX_ROUTE_POINTS * 2
    assert url.count("lonlat:") == 4  # start, end, two alerts
    assert len(url) < 6000


def test_a_failing_map_provider_returns_none_without_leaking_the_key(monkeypatch, caplog):
    def boom(url, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(static_map.httpx, "get", boom)
    assert static_map.incident_map(settings(), -17.8, 31.0) is None
    assert "secret-geo-key" not in caplog.text


def test_non_image_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(
        static_map.httpx, "get", lambda url, timeout: httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})
    )
    assert static_map.incident_map(settings(), -17.8, 31.0) is None
