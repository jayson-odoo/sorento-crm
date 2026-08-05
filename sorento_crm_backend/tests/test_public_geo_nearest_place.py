"""S13: the place name while the customer is still signing.

The pad already has a fix from the browser, but the place name lived only on the server, so
during capture it could show nothing but coordinates and the client read that as a missing
service. This endpoint answers the same string the PDF prints, from the same table.

The tests below exist to hold two things: that the answer is `geo_places`' answer and not a
second copy of the table, and that a stranger with no session can ask.
"""
from __future__ import annotations

import pytest

from app.services import geo_places

PATH = "/api/v1/public/geo/nearest-place"

# The coordinates on a real signature in the development database. The same pair the PDF
# tests use, so a change to the table shows up in both places at once.
REAL_SIGNATURE = (3.03927, 101.80660)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    # No dependency overrides on purpose: no session, no API key, no database. Exactly what
    # a customer's browser sends from the signature pad.
    return TestClient(app)


def test_a_real_signature_gets_the_town_it_was_signed_in(client):
    lat, lng = REAL_SIGNATURE
    response = client.get(PATH, params={"lat": lat, "lng": lng})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["description"] == "near Kajang, Selangor (3.03927, 101.80660)"
    assert body["place"] == "Kajang, Selangor"
    assert body["place_name"] == "Kajang"
    assert body["state"] == "Selangor"
    assert body["coordinates"] == "3.03927, 101.80660"
    assert body["lat"] == pytest.approx(lat)
    assert body["lng"] == pytest.approx(lng)
    assert 0 < body["distance_km"] < geo_places.NEAREST_PLACE_MAX_KM


def test_the_answer_is_the_one_the_pdf_prints(client):
    """One definition. If this ever diverges, the screen and the document start disagreeing
    about where somebody stood, which is the whole reason the table is not in the browser."""
    lat, lng = REAL_SIGNATURE
    body = client.get(PATH, params={"lat": lat, "lng": lng}).json()

    assert body["description"] == geo_places.describe_coordinates(lat, lng)
    assert body["place"] == geo_places.place_label(lat, lng)
    assert body["coordinates"] == geo_places.format_coordinates(lat, lng)


def test_a_point_with_nothing_near_it_falls_back_to_the_coordinates(client):
    """Out in the South China Sea. Nothing known is within the threshold, so the honest
    answer is the numbers, and no town is named."""
    response = client.get(PATH, params={"lat": 4.0, "lng": 108.0})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["place"] is None
    assert body["place_name"] is None
    assert body["state"] is None
    assert body["distance_km"] is None
    assert body["coordinates"] == "4.00000, 108.00000"
    assert body["description"] == "4.00000, 108.00000"


def test_a_point_abroad_is_answered_without_guessing(client):
    """Tokyo. The nearest row in the table is 5000 km away, and naming it would be a lie."""
    body = client.get(PATH, params={"lat": 35.6762, "lng": 139.6503}).json()

    assert body["place"] is None
    assert body["description"] == "35.67620, 139.65030"


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({}, id="nothing at all"),
        pytest.param({"lat": 3.03927}, id="half a fix"),
        pytest.param({"lng": 101.80660}, id="the other half"),
        pytest.param({"lat": "here", "lng": "there"}, id="not numbers"),
        pytest.param({"lat": "", "lng": ""}, id="empty"),
        pytest.param({"lat": 91.0, "lng": 101.0}, id="off the top of the globe"),
        pytest.param({"lat": -91.0, "lng": 101.0}, id="off the bottom"),
        pytest.param({"lat": 3.0, "lng": 181.0}, id="past the date line"),
        pytest.param({"lat": 3.0, "lng": -181.0}, id="past it the other way"),
        pytest.param({"lat": "nan", "lng": "nan"}, id="not a number"),
        pytest.param({"lat": "inf", "lng": "inf"}, id="infinite"),
    ],
)
def test_input_that_is_not_a_position_is_refused_cleanly(client, params):
    """422, never a 500 and never a guessed town. A pad with a bad fix must be told so."""
    response = client.get(PATH, params=params)
    assert response.status_code == 422, f"{params} -> {response.status_code} {response.text}"


def test_it_needs_no_credential(client):
    """The customer counter-signing has no session. It discloses nothing either: it answers
    a place for coordinates the caller already supplied."""
    lat, lng = REAL_SIGNATURE
    anonymous = client.get(PATH, params={"lat": lat, "lng": lng})
    assert anonymous.status_code == 200, anonymous.text

    # A junk bearer token is not treated as an attempted login and rejected.
    with_junk = client.get(
        PATH,
        params={"lat": lat, "lng": lng},
        headers={"Authorization": "Bearer zzt-not-a-real-token"},
    )
    assert with_junk.status_code == 200, with_junk.text


def test_the_route_is_mounted_where_the_pad_will_call_it():
    """A public route that exists only in a router nobody included answers 404 while every
    service test passes."""
    from app.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert PATH in paths
