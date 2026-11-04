"""Derive blackspots from reported incidents: many incidents within a radius make a blackspot.

Pure geometry, no database. A cluster is the incidents within ``radius_m`` of a centre incident;
the centre is the incident with the most neighbours, and its members are removed before the next
cluster is built, so a cluster is never wider than twice the radius and no incident is counted twice.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_008.8
_NAMESPACE = uuid.UUID("5e0f3a52-6f0e-4a6b-9a53-3b1d5c2f9e11")


@dataclass(frozen=True)
class Point:
    id: uuid.UUID
    lat: float
    lng: float


@dataclass(frozen=True)
class Cluster:
    id: uuid.UUID
    lat: float
    lng: float
    count: int
    member_ids: tuple[uuid.UUID, ...]


def haversine_m(a: Point, b: Point) -> float:
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def find_clusters(points: list[Point], radius_m: float, min_incidents: int) -> list[Cluster]:
    """Clusters of at least ``min_incidents`` points, biggest first."""
    remaining = sorted(points, key=lambda p: str(p.id))
    clusters: list[Cluster] = []
    while len(remaining) >= min_incidents:
        best: list[Point] = []
        for centre in remaining:
            near = [p for p in remaining if haversine_m(centre, p) <= radius_m]
            if len(near) > len(best):
                best = near
        if len(best) < min_incidents:
            break
        members = tuple(sorted(p.id for p in best))
        clusters.append(
            Cluster(
                id=uuid.uuid5(_NAMESPACE, ",".join(str(m) for m in members)),
                lat=sum(p.lat for p in best) / len(best),
                lng=sum(p.lng for p in best) / len(best),
                count=len(best),
                member_ids=members,
            )
        )
        taken = set(members)
        remaining = [p for p in remaining if p.id not in taken]
    clusters.sort(key=lambda c: (-c.count, str(c.id)))
    return clusters


def risk_for_count(count: int, min_incidents: int) -> str:
    """low at the threshold, rising with the number of incidents."""
    if count >= min_incidents * 4:
        return "critical"
    if count >= min_incidents * 2:
        return "high"
    if count > min_incidents:
        return "medium"
    return "low"
