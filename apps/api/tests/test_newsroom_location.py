"""The one newsroom location filter: regional AI labels plus conservative legacy text matching."""

from datetime import UTC, datetime, timedelta

import pytest

from api_helpers import sign_in
from newsroom_helpers import N, classification, make_article, newsroom_client  # noqa: F401 (fixture)
from test_newsroom_api import ids, named_source

pytestmark = pytest.mark.usefixtures("migrated_engine")
REGION = "bulawayo_matabeleland"


def test_regional_ai_labels_match_without_a_literal_place_name(newsroom_client, session):
    local = [
        make_article(session, reply=classification(geographic_relevance=geo))
        for geo in ("bulawayo", "matabeleland")
    ]
    national = make_article(session)
    sign_in(newsroom_client, session, "analyst")
    before = {str(item.id): dict(item.source_metadata) for item in [*local, national]}

    response = newsroom_client.get(f"{N}/articles", params={"location": REGION})
    assert response.status_code == 200, response.text
    assert ids(response) == {str(item.id) for item in local}
    assert ids(newsroom_client.get(f"{N}/articles")) == set(before)
    for item in [*local, national]:
        session.refresh(item)
        assert item.source_metadata == before[str(item.id)]
        assert item.processing_status == "processed"


def test_fallback_covers_both_provinces_bulawayo_suburbs_and_campus(newsroom_client, session):
    names = [
        "Binga", "Bubi", "Hwange", "Lupane", "Nkayi", "Tsholotsho", "Umguza", "Victoria Falls",
        "Beitbridge", "Bulilima", "Mangwe", "Gwanda", "Insiza", "Matobo", "Umzingwane", "Plumtree",
        "Makokoba", "Cowdray Park", "Mpilo Hospital", "NUST", "National University of Science and Technology",
        "Matebeleland South", "MAT NORTH", "Matabeleland-South",
    ]
    items = [make_article(session, title_redacted=f"New project announced in {name}") for name in names]
    sign_in(newsroom_client, session, "reporter")
    response = newsroom_client.get(f"{N}/articles", params={"location": REGION, "page_size": 100})
    assert response.status_code == 200, response.text
    assert ids(response) == {str(item.id) for item in items}
    assert response.json()["total"] == len(names)


def test_pending_legacy_and_named_entity_matches_work_without_reclassification(newsroom_client, session):
    items = [
        make_article(session, status="pending", title_redacted="NUST announces new semester dates"),
        make_article(session, status="failed", excerpt_redacted="Residents in Pumula will get a new clinic."),
        make_article(session, status="filtered", article_text_redacted="The meeting took place in Bulawayo."),
        make_article(session, metadata={"classification": {"primary_category": "education"}}, title_redacted="School opens in Gwanda"),
        make_article(session, reply=classification(geographic_relevance="unclear", places=["Hwange"])),
        make_article(session, reply=classification(organisations=["NUST"])),
        make_article(session, reply=classification(places=["Cowdray\nPark"])),
        make_article(session, metadata={"classification": {"places": None, "organisations": "not an array"}}, title_redacted="Matobo council meets"),
    ]
    make_article(session, status="pending", title_redacted="New semester dates announced in Harare")
    sign_in(newsroom_client, session, "analyst")
    response = newsroom_client.get(f"{N}/articles", params={"location": REGION})
    assert response.status_code == 200, response.text
    assert ids(response) == {str(item.id) for item in items}


def test_foreign_ambiguous_and_publisher_only_mentions_do_not_match(newsroom_client, session):
    local_publisher = named_source(session, "Bulawayo NUST News")
    rejected = [
        make_article(session, local_publisher),
        make_article(session, title_redacted="NUST partnership abroad", reply=classification(geographic_relevance="international")),
        make_article(session, status="pending", title_redacted="NUST students graduate in Islamabad, Pakistan"),
        make_article(session, status="pending", title_redacted="NUST announces a campus expansion in Namibia"),
        make_article(session, status="pending", title_redacted="The Natural History Museum opens an exhibition"),
        make_article(session, status="pending", title_redacted="Bring your own: BYO picnic this weekend"),
        make_article(session, status="pending", title_redacted="New development in Hillside and Richmond"),
        make_article(session, status="pending", title_redacted="A nustlike acronym and Nkayiland are not regional names"),
        make_article(session, metadata={"classification": {"places": "Bulawayo", "organisations": None}}, title_redacted="National budget presented"),
    ]
    # Foreign collaboration does not exclude an explicitly Zimbabwean campus,
    # and an explicit regional place is stronger than a campus-only ambiguity.
    accepted = [
        make_article(session, status="pending", title_redacted="Zimbabwe's NUST welcomes a South African delegation"),
        make_article(session, status="pending", title_redacted="Bulawayo's NUST welcomes a Namibian delegation"),
        make_article(session, title_redacted="NUST welcomes a delegation from Namibia", reply=classification(geographic_relevance="bulawayo")),
    ]
    sign_in(newsroom_client, session, "analyst")
    response = newsroom_client.get(f"{N}/articles", params={"location": REGION})
    assert response.status_code == 200, response.text
    assert ids(response) == {str(item.id) for item in accepted}
    assert newsroom_client.get(f"{N}/articles").json()["total"] == len(accepted) + len(rejected)


def test_location_combines_with_categories_search_and_pagination(newsroom_client, session):
    now = datetime.now(UTC)
    source = named_source(session, "Test daily")
    first = make_article(
        session, source, title_redacted="Bulawayo football final", received_at=now,
        reply=classification(primary_category="sports"),
    )
    second = make_article(
        session, source, title_redacted="Hwange football final", received_at=now - timedelta(hours=1),
        reply=classification(primary_category="community_local", secondary_category="sports"),
    )
    make_article(session, source, title_redacted="Harare football final", reply=classification(primary_category="sports"))
    make_article(session, source, title_redacted="Gwanda budget meeting")
    sign_in(newsroom_client, session, "analyst")
    params = {"location": REGION, "category": "sports", "q": "football", "publisher_id": str(source.id), "page_size": 1}
    page1 = newsroom_client.get(f"{N}/articles", params=params).json()
    page2 = newsroom_client.get(f"{N}/articles", params={**params, "page": 2}).json()
    assert page1["total"] == page2["total"] == 2
    assert [item["id"] for item in page1["items"]] == [str(first.id)]
    assert [item["id"] for item in page2["items"]] == [str(second.id)]
    assert newsroom_client.get(f"{N}/articles", params={"category": "sports"}).json()["total"] == 3


def test_only_the_combined_location_is_accepted(newsroom_client, session):
    sign_in(newsroom_client, session, "analyst")
    for value in ("bulawayo", "matabeleland_north", "campus", "bogus"):
        assert newsroom_client.get(f"{N}/articles", params={"location": value}).status_code == 422
