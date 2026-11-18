"""Regressions for provider/local newsroom array limits drifting apart."""

import pytest
from pydantic import ValidationError

from app.schemas.newsroom import NEWS_JSON_SCHEMA, NewsClassification
from app.services.newsroom_extraction import NewsroomExtractor
from newsroom_helpers import classification
from test_pipeline_units import FakeCompletions, fake_client, sample_input


@pytest.mark.parametrize("field", ["topics", "organisations", "places"])
def test_provider_schema_keeps_the_local_array_limit(field):
    raw = NewsClassification.model_json_schema()
    assert NEWS_JSON_SCHEMA["properties"][field]["maxItems"] == raw["properties"][field]["maxItems"] == 8


@pytest.mark.parametrize("field", ["topics", "organisations", "places"])
def test_eight_entities_are_valid_but_overflow_still_fails_local_validation(field):
    values = [f"Named entity {index}" for index in range(8)]
    assert getattr(NewsClassification.model_validate(classification(**{field: values})), field) == values
    with pytest.raises(ValidationError):
        NewsClassification.model_validate(classification(**{field: values + ["Ninth entity"]}))


def test_classifier_sends_all_three_bounds_to_the_provider():
    client = FakeCompletions(classification())
    NewsroomExtractor(fake_client(client), model="existing-model").extract(sample_input())
    schema = client.calls[0]["response_format"]["json_schema"]["schema"]
    assert {name: schema["properties"][name]["maxItems"] for name in ["topics", "organisations", "places"]} == {
        "topics": 8, "organisations": 8, "places": 8,
    }


def test_unrelated_schema_constraints_stay_strict():
    assert NEWS_JSON_SCHEMA["additionalProperties"] is False
    assert set(NEWS_JSON_SCHEMA["required"]) == set(NewsClassification.model_fields)
    assert NEWS_JSON_SCHEMA["properties"]["summary"] == {
        "description": NewsClassification.model_fields["summary"].description, "type": "string",
    }
