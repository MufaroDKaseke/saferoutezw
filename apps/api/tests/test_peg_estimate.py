"""Kilometre-peg estimates and the Geoapify geocoder (no network, no database)."""

import pytest

from app.core.config import Settings
from app.models.enums import LocationStatus
from app.services.geolocation import parse_geoapify_results, resolve_location
from app.services.peg_estimate import PegEstimator, parse_peg_reference, point_along
from app.services.routing.mock import MockRoutingProvider

PLACES = {"rusape": (-18.53, 32.12), "nyanga": (-18.22, 32.75)}
SETTINGS = Settings(_env_file=None)


class NoGeocoder:
    source, method = "test", "test"

    def geocode(self, query):
        raise AssertionError("a peg must never be geocoded as text")


@pytest.mark.parametrize(
    "text, km, a, b",
    [
        ("89-kilometre peg along the Rusape-Nyanga Road", 89, "Rusape", "Nyanga"),
        ("45 km peg on the Harare-Mutare Highway", 45, "Harare", "Mutare"),
        ("the 120km mark of the Masvingo to Beitbridge road", 120, "Masvingo", "Beitbridge"),
    ],
)
def test_peg_references_are_parsed(text, km, a, b):
    ref = parse_peg_reference(text)
    assert (ref.km, ref.start, ref.end) == (km, a, b)


@pytest.mark.parametrize("text", ["peg 85", "the 12 kilometre peg", "near Mbudzi roundabout", "Rusape-Nyanga Road"])
def test_unparseable_pegs_give_no_estimate(text):
    assert parse_peg_reference(text) is None


def test_point_along_interpolates_and_rejects_overlong_distances():
    line = [(-18.0, 31.0), (-18.0, 32.0)]  # ~105 km due east
    mid = point_along(line, 52_000)
    assert mid is not None and -18.0 == pytest.approx(mid[0]) and 31.4 < mid[1] < 31.6
    assert point_along(line, 500_000) is None


def test_estimate_is_ambiguous_coarse_and_labelled_never_resolved():
    estimator = PegEstimator(MockRoutingProvider(PLACES))
    resolution = resolve_location("40-kilometre peg along the Rusape-Nyanga Road", NoGeocoder(), SETTINGS, estimator)
    assert resolution.status == LocationStatus.AMBIGUOUS
    assert resolution.latitude is None and resolution.longitude is None  # no point is placed
    assert len(resolution.candidates) == 2
    for c in resolution.candidates:
        assert c["label"].startswith("ESTIMATE") and c["match_type"] == "estimated_peg"
        assert c["precision_meters"] >= 5000
    assert "Estimate only" in resolution.note


def test_peg_longer_than_the_route_or_unknown_places_stay_unresolved():
    estimator = PegEstimator(MockRoutingProvider(PLACES))
    far = resolve_location("900-kilometre peg along the Rusape-Nyanga Road", NoGeocoder(), SETTINGS, estimator)
    unknown = resolve_location("10-kilometre peg along the Atlantis-Nyanga Road", NoGeocoder(), SETTINGS, estimator)
    for resolution in (far, unknown):
        assert resolution.status == LocationStatus.UNRESOLVED and not resolution.candidates


def test_without_an_estimator_pegs_stay_unresolved():
    r = resolve_location("89-kilometre peg along the Rusape-Nyanga Road", NoGeocoder(), SETTINGS)
    assert r.status == LocationStatus.UNRESOLVED


def test_geoapify_results_are_parsed_conservatively():
    payload = {
        "results": [
            {"lat": -17.83, "lon": 31.05, "formatted": "Harare", "result_type": "city",
             "rank": {"match_type": "full_match"}, "bbox": {"lat1": -17.9, "lon1": 30.9, "lat2": -17.75, "lon2": 31.2}},
            {"lat": 51.5, "lon": -0.12, "formatted": "London"},  # outside Zimbabwe: dropped
            {"lat": "x", "lon": 1},  # malformed: dropped
            {"lat": -17.8, "lon": 31.0, "formatted": "Some building", "result_type": "building",
             "rank": {"match_type": "inner_part"}},
        ]
    }
    results = parse_geoapify_results(payload)
    assert [r.label for r in results] == ["Harare", "Some building"]
    assert results[0].precision_meters > 5000 and results[0].partial is False  # a whole city is not a marker
    assert results[1].precision_meters == 30 and results[1].partial is True
