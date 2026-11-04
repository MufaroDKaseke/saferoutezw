"""Function 1: reporting an incident. Reports are private claims that feed the existing pipeline."""

import pytest
from sqlalchemy import func, select

from app.models import Incident, IncidentEvidence, PublicAlert, Source, SourceItem
from app.models.enums import ProcessingStatus
from app.services.pipeline import PipelineRunner
from test_article_pipeline import FakeExtractor, FakeFetch, result
from whatsapp_helpers import Chat

pytestmark = pytest.mark.usefixtures("migrated_engine")

WHAT = "A kombi overturned and people are injured. Driver is Tendai Moyo, call 0772 123 456."


def report(chat: Chat, *, where="Harare-Mutare road near Marondera", when="1") -> list[str]:
    chat.say("hi"), chat.say("1"), chat.say(where), chat.say(WHAT)
    return chat.say(when)  # the summary


def items(session):
    return session.scalars(select(SourceItem)).all()


def test_full_report_flow_saves_one_pending_item_and_returns_a_reference(session):
    chat = Chat(session)
    summary = report(chat)[0]
    assert "Please check your report" in summary and "Harare-Mutare road near Marondera" in summary
    assert "happening now" in summary and "nothing is published automatically" in summary

    confirmation = chat.say("1")[0]
    assert "Your report has been received for review." in confirmation
    assert "verified" not in confirmation.lower().replace("unverified", "")
    assert "while driving" in confirmation and "emergency services" in confirmation

    [item] = items(session)
    assert item.processing_status == ProcessingStatus.PENDING.value
    assert item.source_metadata["reference"] in confirmation
    assert item.source_metadata["content_kind"] == "user_report"
    source = session.get(Source, item.source_id)
    assert (source.kind, source.verification_tier) == ("whatsapp", "unverified")


def test_report_text_is_redacted_before_it_is_stored(session):
    chat = Chat(session)
    report(chat), chat.say("1")
    [item] = items(session)
    stored = item.excerpt_redacted + item.title_redacted
    assert "0772" not in stored and "123 456" not in stored
    assert item.source_metadata["redaction"] == "applied"


def test_the_senders_number_is_not_stored_on_the_report(session):
    chat = Chat(session)
    report(chat), chat.say("1")
    [item] = items(session)
    blob = str(item.source_metadata) + (item.excerpt_redacted or "") + item.title_redacted + (item.canonical_url or "")
    assert chat.wa_id not in blob and chat.wa_id[3:] not in blob
    assert item.source_metadata["sender_digest"]  # only a keyed hash, for abuse control


def test_duplicate_delivery_of_the_confirmation_creates_one_report(session):
    chat = Chat(session)
    report(chat)
    first = chat.say("1", wamid="wamid.CONFIRM")
    again = chat.say("1", wamid="wamid.CONFIRM")  # Meta re-delivers the same message
    assert first and again == []
    assert len(items(session)) == 1


def test_resubmitting_the_same_message_in_the_worker_cannot_duplicate(session):
    """Even if the worker re-ran the confirming message, the report id derives from its message id."""
    from app.services.whatsapp.incident_intake import reference_for, save_report

    chat = Chat(session)
    data = {"location_text": "Harare", "what": "Crash on the road", "when_text": "now"}
    ref1 = save_report(session, chat.settings, data, wamid="wamid.X", wa_id=chat.wa_id, received_at=chat.now)
    ref2 = save_report(session, chat.settings, data, wamid="wamid.X", wa_id=chat.wa_id, received_at=chat.now)
    session.commit()
    assert ref1 == ref2 == reference_for("wamid.X") and len(items(session)) == 1


def test_a_location_pin_is_recorded_with_its_origin_as_a_claim(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1")
    assert "What happened" in chat.pin(-18.1853, 31.5519)[0]
    chat.say(WHAT), chat.say("this morning around 8")
    summary = chat.last
    assert "location pin (-18.1853, 31.5519)" in summary and "this morning around 8" in summary
    chat.say("yes")
    [item] = items(session)
    pin = item.source_metadata["location_pin"]
    assert pin == {"latitude": -18.1853, "longitude": 31.5519, "origin": "whatsapp_location_pin", "claimed": True}
    assert item.source_metadata["claims_unverified"] is True
    assert "(as reported)" in item.excerpt_redacted  # location and time are labelled as claims


def test_a_pin_outside_zimbabwe_is_refused(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1")
    assert "outside Zimbabwe" in chat.pin(51.5, -0.12)[0]
    assert session.scalar(select(func.count()).select_from(SourceItem)) == 0


def test_photos_are_declined_and_do_not_block_the_report(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1")
    assert "Photos can't be added" in chat.photo()[0]
    chat.say("Harare road"), chat.say(WHAT), chat.say("1"), chat.say("1")
    assert len(items(session)) == 1


def test_declining_the_summary_saves_nothing(session):
    chat = Chat(session)
    report(chat)
    assert "Cancelled" in chat.say("2")[0]
    assert items(session) == []


def test_reply_never_claims_verification(session):
    chat = Chat(session)
    report(chat), chat.say("1")
    everything = " ".join(m.body for m in chat.client.sent).lower()
    assert "has been verified" not in everything and "confirmed accident" not in everything


# ---- hand-off to the existing pipeline ---------------------------------------------------------


def pipeline(engine, extractor):
    return PipelineRunner(engine, fetch_article=FakeFetch(), extractor=extractor, batch_size=10)


def test_a_short_report_is_not_dropped_by_the_keyword_screen(migrated_engine, session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1"), chat.say("Mbare rank"), chat.say("Bad accident, someone is hurt"), chat.say("1"), chat.say("1")
    extractor = FakeExtractor(result())
    summary = pipeline(migrated_engine, extractor).run()
    assert summary.filtered == 0 and summary.screened == 1
    assert "public report" in items(session)[0].screen_reason


def test_report_reaches_a_candidate_incident_after_redaction_and_is_never_published(migrated_engine, session):
    chat = Chat(session)
    report(chat), chat.say("1")
    extractor = FakeExtractor(result())

    summary = pipeline(migrated_engine, extractor).run()

    assert (summary.fetched, summary.incidents_created) == (1, 1)
    assert "0772" not in extractor.calls[0].text  # redacted before it reaches OpenAI
    assert "unverified" in extractor.calls[0].text.lower()
    incident = session.scalars(select(Incident)).one()
    assert incident.status == "candidate"  # a human editor must still approve it
    assert session.scalar(select(func.count()).select_from(PublicAlert)) == 0
    assert session.scalars(select(IncidentEvidence)).one().source_item_id == items(session)[0].id
