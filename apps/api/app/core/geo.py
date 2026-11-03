"""Geographic helpers.

PostGIS (and WKT) order coordinates as ``POINT(longitude latitude)`` - the
reverse of the usual "lat, lon" speech order. Build points only through
``point_from_lat_lon`` so that ordering mistakes cannot creep in.
"""

from geoalchemy2 import WKTElement

WGS84_SRID = 4326


def point_from_lat_lon(latitude: float, longitude: float) -> WKTElement:
    """Return a WGS84 point suitable for ``Geography(POINT, 4326)`` columns."""
    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"latitude must be within [-90, 90], got {latitude}")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError(f"longitude must be within [-180, 180], got {longitude}")
    return WKTElement(f"POINT({longitude} {latitude})", srid=WGS84_SRID)
