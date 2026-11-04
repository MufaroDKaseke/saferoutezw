"""AI draft summary for editors: drafting only, redacted sources only, never saved or published."""

import pytest
from sqlalchemy import select

import db_factories as f
from api_helpers import sign_in
from app.api.v1.summaries import get_summariser
from app.models import AuditEvent, BulletinVersion, IncidentEvidence
from app.services import summarise as svc
from app.api.errors import ApiError

pytestmark = pytest.mark.usefixtures("migrated_engine")

URL = "/api/v1/incidents/{}/summary"


class FakeSummariser:
    model_name = "fake-model"

    def __init__(self, text="A collision was reported on the Harare-Mutare road near Marondera. Expect delays.", error=None):
        self.text, self.error, self.seen = text, error, []

    def summarise(self, data):
        self.seen.append(data)
        if self.error:
            raise self.error
        return svc.SummaryOutput(text=self.text, model="fake-model", input_tokens=10, output_tokens=5)


def incident_with_story(session, article="Full redacted article text about the crash. [NAME] was involved."):
    incident = f.make_incident(session, status="under_review", location_text="Marondera")
    source = f.make_source(session)
    item = f.make_source_item(session, source, article_text_redacted=article)
    session.add(IncidentEvidence(incident_id=incident.id, source_item_id=item.id, evidence_role="primary"))
    session.commit()
    return incident


def use(client, fake):
    from app.main import app

    app.dependency_overrides[get_summariser] = lambda: fake


def test_editor_gets_a_draft_built_from_redacted_text_only(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = incident_with_story(session)
    fake = FakeSummariser()
    use(client, fake)
    r = client.post(URL.format(incident.id), headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"].startswith("A collision") and body["sources_used"] == 1
    assert "Nothing has been saved" in body["notice"]
    sent = fake.seen[0]
    assert sent.sources[0].text.startswith("Full redacted article text") and "[NAME]" in sent.sources[0].text
    assert session.scalars(select(BulletinVersion)).all() == []  # nothing was saved
    actions = set(session.scalars(select(AuditEvent.action)).all())
    assert "incident.summary_drafted" in actions


def test_only_editors_can_generate_drafts(client, session):
    incident = incident_with_story(session)
    use(client, FakeSummariser())
    assert client.post(URL.format(incident.id)).status_code == 401
    _, analyst = sign_in(client, session, "analyst")
    assert client.post(URL.format(incident.id), headers=analyst).status_code == 403


def test_drafts_with_personal_details_are_discarded(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = incident_with_story(session)
    use(client, FakeSummariser("Driver can be reached on +263 77 123 4567 or driver@example.com."))
    r = client.post(URL.format(incident.id), headers=headers)
    assert r.status_code == 502 and r.json()["error"]["code"] == "AI_FAILED"
    assert "driver@example.com" not in r.text


def test_provider_failure_and_missing_sources_are_clean_errors(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = incident_with_story(session)
    use(client, FakeSummariser(error=svc.SummaryError("OpenAI call failed (Timeout)")))
    assert client.post(URL.format(incident.id), headers=headers).status_code == 502
    use(client, FakeSummariser(error=svc.SummariserUnavailable()))
    assert client.post(URL.format(incident.id), headers=headers).json()["error"]["code"] == "AI_UNAVAILABLE"
    bare = f.make_incident(session, status="under_review")
    session.commit()
    use(client, FakeSummariser())
    r = client.post(URL.format(bare.id), headers=headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_SOURCE_TEXT"


def test_unknown_incident_is_404(client, session):
    import uuid

    _, headers = sign_in(client, session, "editor")
    use(client, FakeSummariser())
    assert client.post(URL.format(uuid.uuid4()), headers=headers).status_code == 404


def test_not_configured_is_a_503(client, session):
    from app.core.config import Settings, get_settings
    from app.main import app

    _, headers = sign_in(client, session, "editor")
    incident = incident_with_story(session)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    r = client.post(URL.format(incident.id), headers=headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI_UNAVAILABLE"


def test_clean_summary_tidies_and_limits():
    assert svc.clean_summary('  "A crash\n happened."  ') == "A crash happened."
    assert len(svc.clean_summary("word " * 600)) <= svc.MAX_SUMMARY_CHARS + 1
    with pytest.raises(svc.SummaryError):
        svc.clean_summary("Call 0771234567 now")


def test_prompt_forbids_casualty_counts_and_names():
    text = svc.SYSTEM_PROMPT
    assert "Do NOT state how many people died" in text and "untrusted data" in text
