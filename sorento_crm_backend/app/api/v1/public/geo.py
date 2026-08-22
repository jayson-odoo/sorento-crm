"""Turn a pair of coordinates into a place name, for a signature pad that is still capturing.

Exists because of a gap the client noticed (S13): the place lookup lived only on the server, so
`near Kajang, Selangor` appeared once a signature was SAVED and the pad showed bare coordinates
while somebody was actually signing. That read as a missing service they had to switch on.

The fix is deliberately NOT to ship the table to the browser. `geo_places` is the single
definition the PDF renders from, and a second copy in JavaScript is how the screen and the printed
document start disagreeing about where a person stood. So the browser asks, and this answers.

PUBLIC because the customer counter-signing has no session and never will. It discloses nothing:
it hands back a place name for coordinates the caller already supplied, reads no database and
writes nothing.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from app.services import geo_places
from app.services.error_handler import AppException

router = APIRouter()


def _position(lat: Any, lng: Any) -> tuple[float, float]:
    """The pair as floats, or a 422 that says which half was wrong.

    Validated here rather than by FastAPI's own float coercion because that accepts `nan` and
    `inf` happily, and a NaN would travel all the way into the distance arithmetic and come back
    as a town chosen by an undefined comparison. A pad with a bad fix has to be told so.
    """
    pair = geo_places.coordinate_pair(lat, lng)
    if pair is None:
        raise AppException(
            status_code=422,
            message="Give a latitude between -90 and 90 and a longitude between -180 and 180.",
            code="invalid_coordinates",
        )
    return pair


@router.get("/nearest-place")
async def nearest_place(
    lat: Optional[str] = Query(None, description="Latitude, -90 to 90."),
    lng: Optional[str] = Query(None, description="Longitude, -180 to 180."),
):
    """The nearest known Malaysian town to a position, or nothing when none is near enough.

    `description` is the string to show: `near Kajang, Selangor (3.03927, 101.80660)` when a town
    is within the threshold, and the bare coordinates when it is not. The numbers are ALWAYS
    present, because they are the evidence and the place name is only the convenience.

    Taken as strings and parsed here so `nan` and `inf` are refused rather than coerced.
    """
    latitude, longitude = _position(lat, lng)

    found = geo_places.nearest_place(latitude, longitude)
    within = found is not None and found[1] <= geo_places.NEAREST_PLACE_MAX_KM

    return {
        "lat": latitude,
        "lng": longitude,
        "coordinates": geo_places.format_coordinates(latitude, longitude),
        # Through the same helpers the PDF calls, never recomputed here. If these ever stop
        # agreeing, the screen and the document are describing different places.
        "description": geo_places.describe_coordinates(latitude, longitude),
        "place": geo_places.place_label(latitude, longitude),
        "place_name": found[0].name if within else None,
        "state": found[0].state if within else None,
        "distance_km": round(found[1], 3) if within else None,
    }
