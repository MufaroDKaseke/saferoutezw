"""Expanded keyword screening: categories, Zimbabwe relevance and false-positive checks.

Pure unit tests: no database, network or OpenAI key. All headlines are synthetic.
"""

import pytest

from app.services.screening import GEO_FOREIGN, GEO_REGIONAL, GEO_ZIMBABWE, ScreenResult, screen
from app.taxonomy import PrimaryCategory as C


@pytest.mark.parametrize(
    ("title", "category"),
    [
        ("Five killed in Harare road accident", C.ROAD_INCIDENT),
        ("Kombi overturns along Seke Road", C.ROAD_INCIDENT),
        ("Truck crashes near the 120km peg", C.ROAD_INCIDENT),
        ("Traffic delays at Beitbridge border", C.TRAFFIC_DISRUPTION),
        ("ZINARA announces road rehabilitation", C.ROAD_INFRASTRUCTURE),
        ("ZRP releases annual road accident statistics", C.ROAD_SAFETY_DATA),
        ("TSCZ launches road safety campaign", C.ROAD_SAFETY),
        ("Government announces new toll tariffs", C.TRANSPORT_POLICY),
        ("Flooding closes a major Zimbabwean highway", C.ROAD_HAZARD),
        ("New freight restrictions affect Chirundu border", C.FREIGHT_AND_LOGISTICS),
        ("Public transport fares increase in Bulawayo", C.PUBLIC_TRANSPORT),
    ],
)
def test_spec_positive_examples_are_relevant_with_the_expected_candidate(title, category):
    result = screen(title)
    assert result.relevant, result.reason
    assert category.value in result.candidate_categories
    assert result.screening_reason_code == "matched"


@pytest.mark.parametrize(
    "title",
    [
        "Zimbabwe Stock Exchange crashes",
        "Zimbabwe cricket team suffers defeat",
        "Software system crash disrupts company",
        "Aircraft crashes near the airport",
        "New bus lanes open in London",
        "Bus accident kills 20 in South Africa",
        "Politicians trade barbs over the budget",
        "Financial market congestion worries investors",
        "Singer shows off his new car",
        "ZRP",
        "ZINARA",
    ],
)
def test_spec_negative_examples_are_filtered(title):
    result = screen(title)
    assert not result.relevant
    assert result.matched_terms == () or result.screening_reason_code == "false_positive_context"


def test_statistics_are_a_report_not_an_incident():
    result = screen("ZRP releases annual road accident statistics")
    assert result.candidate_categories[0] == C.ROAD_SAFETY_DATA.value


def test_campaign_is_informational_not_an_incident():
    result = screen("Police launch road safety campaign ahead of the holidays in Harare")
    assert result.candidate_categories[0] == C.ROAD_SAFETY.value


def test_foreign_crash_is_filtered_even_for_a_zimbabwean_publisher():
    result = screen("Bus accident kills 20 in South Africa")
    assert not result.relevant
    assert result.geographical_relevance == GEO_FOREIGN
    assert result.screening_reason_code == "no_zimbabwe_connection"
    assert "Zimbabwe connection" in result.reason


def test_cross_border_story_with_a_zimbabwe_link_is_regional():
    result = screen("Zimbabwean passengers killed in South Africa bus crash")
    assert result.relevant
    assert result.geographical_relevance == GEO_REGIONAL


def test_unknown_geography_is_kept_at_low_confidence():
    result = screen("Two die in head-on collision")
    assert result.relevant
    assert result.geographical_relevance == "unknown"


def test_zimbabwe_place_sets_scope():
    assert screen("Five killed in Harare road accident").geographical_relevance == GEO_ZIMBABWE


def test_multiple_categories_are_reported():
    result = screen("Flooding closes the Harare-Mutare road, traffic diversion in place")
    assert {"road_hazard", "traffic_disruption"} <= set(result.candidate_categories)


def test_html_summaries_are_stripped():
    result = screen("Update", "<p>A <b>kombi</b> &amp; truck <a href='/x'>collided</a> near Gweru</p>")
    assert result.relevant


def test_hyphen_and_space_variants_match():
    assert screen("Hit and run on Mutare Road").relevant
    assert screen("Hit-and-run on Mutare Road").relevant
    assert screen("Head on collision near Chivhu").relevant


def test_substring_errors_are_avoided():
    assert not screen("Broadcast ministry opens new studio").relevant


@pytest.mark.parametrize("title", [None, "", "   "])
def test_empty_input_is_not_relevant(title):
    result = screen(title, None)
    assert result == ScreenResult(False, screening_reason_code="empty")


def test_broad_words_without_context_are_not_enough():
    for title in ("Transport costs weigh on retailers", "Traffic to the website doubles",
                  "Minister speaks on the road ahead for the economy"):
        assert not screen(title).relevant, title


def test_shona_accident_term():
    assert screen("Tsaona: vanhu vashanu vafa paHarare").relevant


def test_organisation_name_alone_is_not_proof():
    result = screen("Traffic Safety Council of Zimbabwe appoints new board chair")
    assert not result.relevant


def test_backward_compatible_reason_texts():
    assert "overturned" in screen("Bus overturned").reason
    assert screen("Budget speech").reason.startswith("no road-incident")


def test_score_and_matched_terms_are_bounded():
    result = screen("crash collision accident overturned rollover killed injured dead deaths bus")
    assert len(result.matched_terms) <= 8
    assert result.screening_score > 0
