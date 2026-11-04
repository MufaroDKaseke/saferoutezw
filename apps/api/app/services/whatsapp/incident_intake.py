"""Function 1 - report a road incident.

Flow: where -> what -> when -> confirm -> saved. A report becomes one ``source_items`` row of the
``whatsapp`` source and goes through the *existing* pipeline (keyword relevance is skipped for
public reports, then privacy redaction and OpenAI extraction). It can only ever become a
``candidate`` incident: a human editor must approve it before anything is public.

Rules kept here:
* location and time are the sender's claims, stored as claims; a location pin is stored with its
  origin (``whatsapp_location_pin``) and is never treated as verified;
* the sender's phone number is not stored on the report (only a keyed digest, for abuse control);
* text is redacted before it is stored, so nothing sensitive waits in the table for the pipeline;
* the report id derives from the confirming message's id, so duplicate deliveries cannot duplicate a
  report;
* photos are not accepted in this version (no media pipeline exists): the user is told so.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.normalized import NormalizedReport, make_title, report_row
from app.ingestion.rss import _insert_items
from app.integrations.whatsapp.messages import Choice, buttons_message, text_message
from app.models import Source
from app.models.enums import SourceKind, VerificationTier
from app.services.redaction import redact
from app.services.routing.base import inside_zimbabwe
from app.services.whatsapp.context import Ctx
from app.services.whatsapp.inbox import sender_digest

FLOW = "report"
SOURCE_NAME = "WhatsApp public reports"
USER_REPORT = "user_report"  # source_metadata.content_kind; recognised by the pipeline

MIN_LOCATION, MAX_LOCATION = 3, 200
MIN_WHAT, MAX_WHAT = 8, 1000
MIN_WHEN, MAX_WHEN = 2, 100

WHERE_PROMPT = (
    "Where did it happen?\n\n"
    "Type a road name or a nearby landmark (for example: Harare–Mutare road near Marondera), "
    "or share a WhatsApp location pin.\n\n"
    "⚠️ Please don't use WhatsApp while driving."
)
WHAT_PROMPT = "What happened? Describe it in a sentence or two."
WHEN_PROMPT = (
    "When did it happen?\n\nReply 1 if it is happening now, or tell me when "
    "(for example: this morning around 8)."
)
NO_PHOTOS = "Photos can't be added yet — a written description is enough."
SAFETY = (
    "⚠️ Don't use WhatsApp while driving. For anything urgent, contact the police or emergency "
    "services directly — don't wait for this report."
)


# --------------------------------------------------------------------------- prompts


def prompt(ctx: Ctx) -> None:
    step = ctx.conv.step
    if step == "where":
        ctx.say(text_message(WHERE_PROMPT))
    elif step == "what":
        ctx.say(text_message(WHAT_PROMPT))
    elif step == "when":
        ctx.say(buttons_message(WHEN_PROMPT, [Choice("1", "Happening now")]))
    elif step == "confirm":
        ctx.say(buttons_message(_summary(ctx.data), [Choice("1", "Submit report"), Choice("2", "Cancel")]))
    else:
        start(ctx)


def start(ctx: Ctx) -> None:
    ctx.goto(FLOW, "where")
    ctx.set(location_text=None, pin_lat=None, pin_lon=None, what=None, when_text=None, happening_now=False)
    prompt(ctx)


def back(ctx: Ctx) -> bool:
    """Step back; False means 'already at the first step' (the caller shows the menu)."""
    previous = {"what": "where", "when": "what", "confirm": "when"}.get(ctx.conv.step)
    if previous is None:
        return False
    ctx.goto(FLOW, previous)
    prompt(ctx)
    return True


# --------------------------------------------------------------------------- steps


def handle(ctx: Ctx) -> None:
    event, step = ctx.event, ctx.conv.step
    if event.is_media:
        ctx.say(text_message(NO_PHOTOS))
        return prompt(ctx)

    if step == "where":
        if event.is_location:
            lat, lon = event.latitude, event.longitude
            if lat is None or lon is None or not inside_zimbabwe(lat, lon):
                ctx.say(text_message("That pin is outside Zimbabwe. Please share a location in Zimbabwe, or type the place."))
                return
            ctx.goto(FLOW, "what", pin_lat=round(lat, 5), pin_lon=round(lon, 5), location_text=None)
            return prompt(ctx)
        text = event.free_text
        if event.is_text and MIN_LOCATION <= len(text) <= MAX_LOCATION:
            ctx.goto(FLOW, "what", location_text=text, pin_lat=None, pin_lon=None)
            return prompt(ctx)
        ctx.say(text_message("Please type a road name or landmark (3–200 characters), or share a location pin."))
        return

    if step == "what":
        text = event.free_text
        if event.is_text and MIN_WHAT <= len(text) <= MAX_WHAT:
            ctx.goto(FLOW, "when", what=text)
            return prompt(ctx)
        ctx.say(text_message(f"Please describe what happened ({MIN_WHAT}–{MAX_WHAT} characters)."))
        return

    if step == "when":
        if event.choice in ("1", "NOW", "HAPPENING NOW"):
            ctx.goto(FLOW, "confirm", when_text="happening now", happening_now=True)
            return prompt(ctx)
        text = event.free_text
        if event.is_text and MIN_WHEN <= len(text) <= MAX_WHEN:
            ctx.goto(FLOW, "confirm", when_text=text, happening_now=False)
            return prompt(ctx)
        ctx.say(text_message("Please tell me when it happened, or reply 1 if it is happening now."))
        return

    if step == "confirm":
        if event.choice in ("1", "YES", "SUBMIT", "SUBMIT REPORT", "CONFIRM"):
            return submit(ctx)
        if event.choice in ("2", "NO"):
            ctx.reset()
            ctx.say(text_message("Cancelled. Nothing was saved. Reply MENU for options."))
            return
        return prompt(ctx)

    start(ctx)  # unknown step: begin again rather than fail


# --------------------------------------------------------------------------- summary / text


def _where(data: dict[str, Any]) -> str:
    if data.get("pin_lat") is not None and data.get("pin_lon") is not None:
        return f"location pin ({data['pin_lat']}, {data['pin_lon']})"
    return data.get("location_text") or "not given"


def _summary(data: dict[str, Any]) -> str:
    return (
        "Please check your report:\n\n"
        f"📍 Where: {_where(data)}\n"
        f"📝 What: {data.get('what')}\n"
        f"🕒 When: {data.get('when_text')}\n\n"
        "Submit this report? It will be sent for review — nothing is published automatically."
    )


def compose_text(data: dict[str, Any]) -> str:
    """The text the pipeline reads. Location and time are labelled as the sender's claims."""
    return (
        "Road incident report from a member of the public (unverified).\n"
        f"What happened (as reported): {data.get('what')}\n"
        f"Location (as reported): {_where(data)}\n"
        f"Time (as reported): {data.get('when_text')}"
    )


# --------------------------------------------------------------------------- saving


def reference_for(wamid: str) -> str:
    """Deterministic from the confirming message, so a re-processed message yields the same id."""
    return "WA-" + hashlib.sha256(wamid.encode()).hexdigest()[:8].upper()


def ensure_source(session: Session) -> Source:
    """The single ``whatsapp`` source that owns public reports (created on first use)."""
    source = session.scalar(select(Source).where(Source.name == SOURCE_NAME))
    if source is None:
        session.execute(
            insert(Source)
            .values(
                name=SOURCE_NAME,
                kind=SourceKind.WHATSAPP.value,
                enabled=True,
                poll_interval_seconds=3600,
                verification_tier=VerificationTier.UNVERIFIED.value,
                rights_notes="Reports submitted by members of the public via WhatsApp. Unverified; private until reviewed.",
            )
            .on_conflict_do_nothing(index_elements=["name"])
        )
        source = session.scalar(select(Source).where(Source.name == SOURCE_NAME))
    assert source is not None
    return source


def save_report(session: Session, settings, data: dict[str, Any], *, wamid: str, wa_id: str, received_at: datetime) -> str:
    """Store the report idempotently and return its reference. Raises nothing on a duplicate."""
    reference = reference_for(wamid)
    source = ensure_source(session)
    text = redact(compose_text(data)).text
    has_pin = data.get("pin_lat") is not None and data.get("pin_lon") is not None
    extra: dict[str, Any] = {
        "channel": "whatsapp",
        "submission": "public_report",
        "reference": reference,
        "redaction": "applied",
        "claims_unverified": True,
        "happening_now_claim": bool(data.get("happening_now")),
        "sender_digest": sender_digest(settings, wa_id),
        "location_pin": (
            {"latitude": data["pin_lat"], "longitude": data["pin_lon"], "origin": "whatsapp_location_pin", "claimed": True}
            if has_pin
            else None
        ),
    }
    report = NormalizedReport(
        external_id=f"whatsapp:{wamid}",
        url=f"https://reports.saferoutezw.invalid/whatsapp/{reference}",  # synthetic; never fetched
        text=text,
        title=make_title(redact(str(data.get("what") or "")).text),
        published_at=received_at,
        content_kind=USER_REPORT,
        extra=extra,
    )
    _insert_items(session, [report_row(report, source.id, None)])  # type: ignore[arg-type]
    return reference


def submit(ctx: Ctx) -> None:
    reference = save_report(
        ctx.session, ctx.settings, ctx.data, wamid=ctx.event.wamid, wa_id=ctx.wa_id, received_at=ctx.now
    )
    ctx.say(
        text_message(
            "✅ Your report has been received for review.\n\n"
            f"Reference: {reference}\n\n"
            "Our team checks reports before anything is published, and some reports cannot be confirmed. "
            "We may not be able to reply individually.\n\n"
            f"{SAFETY}\n\nReply MENU for options."
        )
    )
    ctx.reset()
