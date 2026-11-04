import uuid

from app.services.blackspot_clusters import Point, find_clusters, risk_for_count

# ~0.0009 degrees of latitude is about 100 m.
def _pt(dlat: float = 0.0, dlng: float = 0.0) -> Point:
    return Point(uuid.uuid4(), -17.83 + dlat, 31.05 + dlng)


def test_incidents_within_radius_form_one_blackspot():
    points = [_pt(0), _pt(0.002), _pt(0.004), _pt(0.5)]  # last one is ~55 km away
    clusters = find_clusters(points, radius_m=1000, min_incidents=3)
    assert len(clusters) == 1
    assert clusters[0].count == 3
    assert set(clusters[0].member_ids) == {p.id for p in points[:3]}


def test_fewer_than_minimum_is_not_a_blackspot():
    assert find_clusters([_pt(0), _pt(0.001)], radius_m=1000, min_incidents=3) == []


def test_each_incident_counts_once_and_clusters_are_ordered_by_size():
    near = [_pt(0, i * 0.001) for i in range(3)]
    far = [_pt(1.0, i * 0.001) for i in range(5)]
    clusters = find_clusters(near + far, radius_m=1000, min_incidents=3)
    assert [c.count for c in clusters] == [5, 3]
    assert not set(clusters[0].member_ids) & set(clusters[1].member_ids)


def test_cluster_id_is_stable_for_the_same_members():
    points = [_pt(0), _pt(0.001), _pt(0.002)]
    assert find_clusters(points, 1000, 3)[0].id == find_clusters(list(reversed(points)), 1000, 3)[0].id


def test_risk_rises_with_incident_count():
    assert [risk_for_count(n, 3) for n in (3, 4, 6, 12)] == ["low", "medium", "high", "critical"]
