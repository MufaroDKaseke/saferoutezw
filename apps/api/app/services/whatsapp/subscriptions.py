"""Function 2 - road alert subscriptions, on top of the existing subscriber domain.

Nothing parallel is created: sign-up is ``services.subscriptions.register`` (consent row + one-time
code sent over WhatsApp) and activation is ``services.subscriptions.verify``. A number becomes
``active`` only after the sender typed the code AND consented explicitly, exactly as for the web
sign-up. Messaging the bot, or submitting a report, never subscribes anyone.

Steps: menu -> areas -> consent -> otp.  Manage: manage_areas.  STOP is handled globally.
"""

from __future__ import annotations

import re

from app.api.errors import ApiError
from app.integrations.whatsapp.messages import Choice, buttons_message, text_message
from app.models.subscription import SubscriberChannel, SubscriberStatus
from app.services import subscriptions as core
from app.services.whatsapp.context import Ctx
from app.services.zimbabwe import normalise_province

FLOW = "alerts"
ALL_WORDS = ("ALL", "ALL ZIMBABWE", "ZIMBABWE", "EVERYWHERE")
CODE_RE = re.compile(r"^\d{6}$")

ALERTS_MENU = (
    "Road alerts\n\n1. Subscribe\n2. Manage preferences\n3. Unsubscribe\n\n"
    "Alerts are only sent for incidents our team has reviewed and published. Reply 1, 2 or 3."
)


def areas_prompt(ctx: Ctx, *, managing: bool = False) -> str:
    corridors = core.configured_corridors(ctx.settings)
    lines = [
        "Which areas should alerts cover?" if not managing else "Which areas should alerts cover from now on?",
        "",
        "Reply with ALL for All Zimbabwe, or one or more provinces (for example: Harare, Mashonaland East)",
    ]
    if corridors:
        lines[-1] += " or road corridors: " + ", ".join(corridors)
    lines[-1] += ". Separate several with commas."
    return "\n".join(lines)


def _consent_prompt(ctx: Ctx) -> str:
    data = ctx.data
    return (
        f"You chose: {_describe(data)}.\n\n"
        "You will receive short WhatsApp messages about road incidents that our team has reviewed "
        "and published in those areas, with a link for details. Alerts may be incomplete or late.\n\n"
        + core.CONSENT_TEXT.format(channel="WhatsApp")
        + "\n\nDo you agree?"
    )


def _describe(data: dict) -> str:
    if data.get("all_zimbabwe"):
        return "All Zimbabwe"
    return ", ".join([*data.get("provinces", []), *data.get("corridors", [])]) or "no area"


def _parse_areas(ctx: Ctx, text: str) -> tuple[core.PreferenceInput | None, list[str]]:
    """Split the reply into provinces / corridors / 'all'. Returns (prefs, unrecognised tokens)."""
    corridors = {c.lower(): c for c in core.configured_corridors(ctx.settings)}
    all_zw, provinces, chosen, unknown = False, [], [], []
    for token in re.split(r"[,\n;]+|\band\b", text, flags=re.IGNORECASE):
        token = " ".join(token.split())
        if not token:
            continue
        if token.upper() in ALL_WORDS:
            all_zw = True
        elif normalise_province(token) is not None:
            provinces.append(token)
        elif token.lower() in corridors:
            chosen.append(corridors[token.lower()])
        else:
            unknown.append(token)
    if unknown:
        return None, unknown
    try:
        return core.validate_preferences(ctx.settings, all_zw, provinces, chosen), []
    except ApiError:
        return None, []


# --------------------------------------------------------------------------- entry


def prompt(ctx: Ctx) -> None:
    step = ctx.conv.step
    if step == "menu":
        ctx.say(buttons_message(ALERTS_MENU, [Choice("1", "Subscribe"), Choice("2", "Manage"), Choice("3", "Unsubscribe")]))
    elif step in ("areas", "manage_areas"):
        ctx.say(text_message(areas_prompt(ctx, managing=step == "manage_areas")))
    elif step == "consent":
        ctx.say(buttons_message(_consent_prompt(ctx), [Choice("1", "I agree"), Choice("2", "No thanks")]))
    elif step == "otp":
        ctx.say(text_message("Reply with the 6-digit code I sent you on WhatsApp. Reply RESEND for a new code."))
    else:
        start(ctx)


def start(ctx: Ctx) -> None:
    ctx.goto(FLOW, "menu")
    prompt(ctx)


def back(ctx: Ctx) -> bool:
    previous = {"areas": "menu", "manage_areas": "menu", "consent": "areas", "otp": "consent"}.get(ctx.conv.step)
    if previous is None:
        return False
    ctx.goto(FLOW, previous)
    prompt(ctx)
    return True


def handle(ctx: Ctx) -> None:
    step, event = ctx.conv.step, ctx.event
    if event.is_media or event.is_location:
        ctx.say(text_message("Please reply with text for this step."))
        return prompt(ctx)

    if step == "menu":
        if event.choice == "1":
            return begin_subscribe(ctx)
        if event.choice == "2":
            return begin_manage(ctx)
        if event.choice == "3":
            return unsubscribe(ctx)
        return prompt(ctx)

    if step in ("areas", "manage_areas"):
        prefs, unknown = _parse_areas(ctx, event.free_text)
        if prefs is None:
            if unknown:
                ctx.say(text_message("I didn't recognise: " + ", ".join(unknown[:5]) + ". Please check the spelling."))
            return prompt(ctx)
        data = {"all_zimbabwe": prefs.all_zimbabwe, "provinces": prefs.provinces, "corridors": prefs.corridors}
        if step == "manage_areas":
            return save_areas(ctx, prefs)
        ctx.goto(FLOW, "consent", **data)
        return prompt(ctx)

    if step == "consent":
        if event.choice in ("1", "YES", "I AGREE", "AGREE"):
            return register(ctx)
        if event.choice in ("2", "NO", "NO THANKS"):
            ctx.reset()
            ctx.say(text_message("No problem — you have not been subscribed. Reply MENU for options."))
            return
        return prompt(ctx)

    if step == "otp":
        if event.choice == "RESEND":
            core.resend(ctx.session, ctx.settings, e164=ctx.e164)
            ctx.say(text_message("If a code can be sent, it is on its way. Reply with the 6-digit code."))
            return
        if CODE_RE.match(event.free_text):
            return verify(ctx, event.free_text)
        ctx.say(text_message("Please reply with the 6-digit code, or RESEND."))
        return

    start(ctx)


# --------------------------------------------------------------------------- actions


def begin_subscribe(ctx: Ctx) -> None:
    existing = core.get_by_phone(ctx.session, ctx.settings, ctx.e164)
    if existing is not None and existing.status == SubscriberStatus.ACTIVE.value:
        ctx.reset()
        ctx.say(text_message("You're already subscribed. Choose Road alerts > Manage to change your areas, or reply STOP to unsubscribe."))
        return
    ctx.goto(FLOW, "areas")
    prompt(ctx)


def begin_manage(ctx: Ctx) -> None:
    subscriber = core.get_by_phone(ctx.session, ctx.settings, ctx.e164)
    if subscriber is None or subscriber.status != SubscriberStatus.ACTIVE.value:
        ctx.reset()
        ctx.say(text_message("You're not subscribed to road alerts yet. Choose Road alerts > Subscribe to start."))
        return
    prefs = core.get_preferences(ctx.session, subscriber)
    current = _describe(
        {"all_zimbabwe": prefs.all_zimbabwe, "provinces": prefs.provinces or [], "corridors": prefs.corridors or []}
    )
    ctx.goto(FLOW, "manage_areas")
    ctx.say(text_message(f"You currently get alerts for: {current}."))
    prompt(ctx)


def save_areas(ctx: Ctx, prefs: core.PreferenceInput) -> None:
    subscriber = core.get_by_phone(ctx.session, ctx.settings, ctx.e164)
    if subscriber is None or subscriber.status != SubscriberStatus.ACTIVE.value:
        ctx.reset()
        ctx.say(text_message("You're not subscribed. Choose Road alerts > Subscribe."))
        return
    core.update_preferences(ctx.session, subscriber, prefs)
    ctx.reset()
    ctx.say(text_message(f"Updated. You'll get alerts for: {_describe({'all_zimbabwe': prefs.all_zimbabwe, 'provinces': prefs.provinces, 'corridors': prefs.corridors})}. Reply MENU for options."))


def register(ctx: Ctx) -> None:
    data = ctx.data
    try:
        prefs = core.validate_preferences(
            ctx.settings, bool(data.get("all_zimbabwe")), data.get("provinces", []), data.get("corridors", [])
        )
        core.register(
            ctx.session,
            ctx.settings,
            e164=core.normalise_phone(ctx.e164),
            channel=SubscriberChannel.WHATSAPP,
            prefs=prefs,
            consent_accepted=True,  # the "I agree" reply the sender just gave
            consent_version=core.CONSENT_VERSION,
            ip_digest=None,
            user_agent="whatsapp-bot",
        )
    except ApiError as error:
        ctx.reset()
        ctx.say(text_message(f"Sorry, I couldn't start your subscription ({error.message}). Reply MENU to try again."))
        return
    ctx.goto(FLOW, "otp")
    ctx.say(
        text_message(
            "Thanks. To confirm this number, I've sent you a 6-digit code on WhatsApp. "
            "Reply with the code to activate alerts. You are not subscribed until you do."
        )
    )


def verify(ctx: Ctx, code: str) -> None:
    try:
        result = core.verify(ctx.session, ctx.settings, e164=core.normalise_phone(ctx.e164), code=code)
    except ApiError:
        ctx.say(text_message("That code isn't right or has expired. Try again, or reply RESEND for a new code."))
        return
    subscriber = core.get_by_phone(ctx.session, ctx.settings, ctx.e164)
    prefs = core.get_preferences(ctx.session, subscriber) if subscriber else None
    areas = (
        _describe({"all_zimbabwe": prefs.all_zimbabwe, "provinces": prefs.provinces or [], "corridors": prefs.corridors or []})
        if prefs
        else "your chosen areas"
    )
    ctx.reset()
    if result.activated:
        ctx.say(text_message(f"✅ You're subscribed to road alerts for: {areas}. Reply STOP at any time to unsubscribe. Reply MENU for options."))
    else:
        ctx.say(text_message("Verified. Reply MENU for options."))


def unsubscribe(ctx: Ctx) -> None:
    ended = core.unsubscribe_by_phone(ctx.session, ctx.settings, ctx.e164)
    ctx.reset()
    ctx.say(
        text_message(
            "You've been unsubscribed. You won't receive road alerts. Reply MENU for options."
            if ended
            else "You aren't subscribed to road alerts. Reply MENU for options."
        )
    )
