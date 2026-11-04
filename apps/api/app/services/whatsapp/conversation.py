"""The conversation engine: menu, global commands, expiry, and dispatch to the three flows.

Deterministic - no AI. State lives in ``whatsapp_conversations`` (flow, step, draft data, expiry),
never in memory. Global commands are matched on the whole message:

    MENU   back to the menu           BACK    previous step
    CANCEL discard the draft          HELP    explain, then repeat the question
    STOP   unsubscribe from alerts (also UNSUBSCRIBE)

Numeric replies (1, 2, 3 ...) always work in place of buttons and lists.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.whatsapp.client import WhatsAppClient
from app.integrations.whatsapp.messages import Choice, buttons_message, text_message
from app.models import WhatsAppConversation, WhatsAppInbound
from app.services import subscriptions as core_subscriptions
from app.services.whatsapp import incident_intake, route_check, subscriptions
from app.services.whatsapp.context import CHOOSE, MENU, START, Ctx, Deps, Event
from app.services.whatsapp.outbound import Replier

log = logging.getLogger(__name__)

WELCOME = (
    "Welcome to SafeRouteZW 🇿🇼\n\n"
    "1. Report a road incident\n"
    "2. Road alerts\n"
    "3. Check a route\n\n"
    "Reply with 1, 2 or 3."
)
MENU_CHOICES = [Choice("1", "Report incident"), Choice("2", "Road alerts"), Choice("3", "Check a route")]
HELP = (
    "SafeRouteZW helps you report road incidents, get road alerts, and check a route.\n\n"
    "Commands: MENU (start over), BACK (previous step), CANCEL (discard), STOP (unsubscribe from alerts), HELP.\n"
    "Reports are reviewed before anything is published. For emergencies contact the police or emergency "
    "services directly, and never use WhatsApp while driving."
)
STOP_WORDS = frozenset({"STOP", "UNSUBSCRIBE", "STOP ALERTS", "STOP ALL"})
FLOWS = {
    incident_intake.FLOW: incident_intake,
    subscriptions.FLOW: subscriptions,
    route_check.FLOW: route_check,
}
FLOW_FOR_CHOICE = {"1": incident_intake, "2": subscriptions, "3": route_check}


def show_menu(ctx: Ctx, note: str | None = None) -> None:
    ctx.reset()
    ctx.say(buttons_message((note + "\n\n" if note else "") + WELCOME, MENU_CHOICES))


def _get_conversation(session: Session, settings: Settings, row: WhatsAppInbound, now: datetime) -> WhatsAppConversation:
    """The sender's conversation, created on first contact and locked while we work on it."""
    session.execute(
        insert(WhatsAppConversation)
        .values(
            sender_digest=row.sender_digest,
            sender_ciphertext=row.sender_ciphertext,
            expires_at=now + timedelta(minutes=settings.whatsapp_session_ttl_minutes),
        )
        .on_conflict_do_nothing(index_elements=["sender_digest"])
    )
    conv = session.scalar(
        select(WhatsAppConversation)
        .where(WhatsAppConversation.sender_digest == row.sender_digest)
        .with_for_update()
    )
    assert conv is not None
    return conv


def process(
    session: Session,
    settings: Settings,
    client: WhatsAppClient,
    deps: Deps,
    row: WhatsAppInbound,
    *,
    now: datetime,
) -> None:
    """Handle one stored inbound message. The caller commits (or rolls back) the session."""
    wa_id = core_subscriptions.decrypt_phone(settings, row.sender_ciphertext).lstrip("+")
    conv = _get_conversation(session, settings, row, now)
    event = Event.from_row(row)
    ctx = Ctx(session, settings, conv, wa_id, event, Replier(session, settings, client), deps, now)

    expired = conv.expires_at <= now
    if expired:
        ctx.reset()  # an idle conversation never resumes half-way: the draft is erased
    conv.last_inbound_at = now
    conv.expires_at = now + timedelta(minutes=settings.whatsapp_session_ttl_minutes)

    _dispatch(ctx, expired)


def _dispatch(ctx: Ctx, expired: bool) -> None:
    event, conv = ctx.event, ctx.conv
    command = event.choice if event.is_text else ""

    if command in STOP_WORDS:  # always honoured, in any state
        ended = core_subscriptions.unsubscribe_by_phone(ctx.session, ctx.settings, ctx.e164)
        ctx.reset()
        ctx.say(
            text_message(
                "You've been unsubscribed from SafeRouteZW alerts. Reply MENU for options."
                if ended
                else "You aren't subscribed to alerts. Reply MENU for options."
            )
        )
        return
    if command == "MENU":
        return show_menu(ctx)
    if command == "CANCEL":
        had_draft = conv.flow != MENU
        ctx.reset()
        ctx.say(text_message("Cancelled. Nothing was saved. Reply MENU for options." if had_draft else "Nothing to cancel. Reply MENU for options."))
        return
    if command == "HELP":
        ctx.say(text_message(HELP))
        flow = FLOWS.get(conv.flow)
        return flow.prompt(ctx) if flow else show_menu(ctx)

    if conv.flow == MENU:
        if conv.step == START or expired:
            return show_menu(ctx, "Your earlier session timed out — let's start again." if expired and event.is_text and command not in ("", "HI", "HELLO") else None)
        module = FLOW_FOR_CHOICE.get(event.choice)
        if module is None:
            return show_menu(ctx, "Please reply with 1, 2 or 3." if not event.is_media else "Please reply with text.")
        return module.start(ctx)

    if expired:  # unreachable (expiry resets the flow to the menu) but keeps the invariant explicit
        return show_menu(ctx)

    flow = FLOWS.get(conv.flow)
    if flow is None:
        return show_menu(ctx)
    if command == "BACK":
        if not flow.back(ctx):
            show_menu(ctx)
        return
    flow.handle(ctx)
