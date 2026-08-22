"""The offline nearest-place lookup that turns a signature's coordinates into a readable place.

Written BEFORE the implementation. What is asserted here is what makes the answer usable as
evidence rather than as decoration:

- **The coordinates are never discarded.** The place name is a convenience; the numbers are the
  evidence, so every rendered string still carries them.
- **It says "near", never an address.** A great-circle nearest neighbour over a table of towns
  cannot know a street, and claiming one on a document a customer signs would be a lie.
- **A far-away nearest place is no answer at all.** Beyond the threshold the raw coordinates are
  returned alone, rather than naming a town hundreds of kilometres away.
- **It is offline and deterministic.** No lookup leaves the process, so re-rendering a two-year-old
  issue on a server with no egress prints exactly what it printed the day it was sent.

No database: the table is committed code and the maths is pure, so these are plain unit tests.
The one coordinate that is not a fixture is the real signature sitting in the dev database.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import geo_places

# The signature already recorded in the dev database, and the reason this feature exists.
REAL_SIGNATURE = (3.03927, 101.80660)
REAL_SIGNATURE_TEXT = "3.03927, 101.80660"

# Malaysia's bounding box, generously drawn. A typo in the table (a swapped pair, a dropped
# digit) lands outside it, and a table nobody checks is how a signature ends up "near" Sumatra.
LAT_RANGE = (0.5, 7.6)
LNG_RANGE = (99.4, 119.4)

# The 13 states plus the 3 federal territories. "Main towns of every state" is only true if
# every one of them is actually in the table.
EXPECTED_STATES = {
    "Perlis",
    "Kedah",
    "Penang",
    "Perak",
    "Selangor",
    "Kuala Lumpur",
    "Putrajaya",
    "Negeri Sembilan",
    "Melaka",
    "Johor",
    "Pahang",
    "Terengganu",
    "Kelantan",
    "Sabah",
    "Sarawak",
    "Labuan",
}


# ------------------------------------------------------------------ the table itself


def test_every_state_and_federal_territory_has_a_town():
    states = {place.state for place in geo_places.MALAYSIA_PLACES}
    assert EXPECTED_STATES - states == set()


def test_every_row_sits_inside_malaysia_and_appears_once():
    seen = set()
    for place in geo_places.MALAYSIA_PLACES:
        assert LAT_RANGE[0] <= place.lat <= LAT_RANGE[1], place
        assert LNG_RANGE[0] <= place.lng <= LNG_RANGE[1], place
        key = (place.name, place.state)
        assert key not in seen, f"{key} listed twice"
        seen.add(key)


def test_the_table_covers_the_country_not_just_the_klang_valley():
    """Sabah and Sarawak are more than a third of the country and the client called them out."""
    east = [p for p in geo_places.MALAYSIA_PLACES if p.state in ("Sabah", "Sarawak", "Labuan")]
    assert len(east) >= 25
    assert len(geo_places.MALAYSIA_PLACES) >= 100


@pytest.mark.parametrize(
    "name",
    ["Kuala Lumpur", "George Town", "Johor Bahru", "Kota Kinabalu", "Kuching", "Kota Bharu"],
)
def test_a_town_resolves_to_itself(name):
    """A coordinate taken off the table must come back as that town, at ~0 km. Catches a
    nearest-neighbour that is comparing the wrong axes."""
    place = next(p for p in geo_places.MALAYSIA_PLACES if p.name == name)
    found = geo_places.nearest_place(place.lat, place.lng)
    assert found is not None
    assert found[0].name == name
    assert found[1] < 1.0


# ------------------------------------------------------------------ the real signature


def test_the_signature_in_the_dev_database_resolves_to_the_town_it_is_in():
    """3.03927, 101.80660 is the Sungai Long side of Kajang, about 5 km from the town centre and
    about 17 km from the middle of Kuala Lumpur. The nearer town is the more useful answer, and
    naming the capital instead would be a worse description of the same point."""
    found = geo_places.nearest_place(*REAL_SIGNATURE)
    assert found is not None
    place, distance_km = found
    assert place.name == "Kajang"
    assert place.state == "Selangor"
    assert distance_km < 10.0
    assert geo_places.place_label(*REAL_SIGNATURE) == "Kajang, Selangor"


def test_the_rendered_line_names_the_place_and_drops_the_raw_numbers():
    """Client decision, 2026-08-05: `3.03927, 101.80660` printed beside a signature read as
    noise to the person holding the document, not evidence. The exact figures are not lost -
    they stay on the stored signature row - they are simply not part of this label. "near",
    never an address: the table knows towns, not streets."""
    described = geo_places.describe_coordinates(*REAL_SIGNATURE)
    assert described == "near Kajang, Selangor"
    assert REAL_SIGNATURE_TEXT not in described
    assert described.startswith("near ")


def test_decimal_input_is_accepted_because_the_column_is_numeric():
    """`quotation_signatures.gps_lat` is NUMERIC(10,7), so what reaches this is a Decimal."""
    assert geo_places.place_label(
        Decimal("3.0392700"), Decimal("101.8066000")
    ) == "Kajang, Selangor"


# ------------------------------------------------------------------ the fallback


def test_a_point_far_from_every_known_town_falls_back_to_the_raw_coordinates():
    """Open sea in the South China Sea. Naming a town 300 km away would be a confident lie, and a
    signature record is the last place to put one."""
    far = (4.0, 108.0)
    assert geo_places.nearest_place(*far) is not None  # something is always nearest
    assert geo_places.place_label(*far) is None
    assert geo_places.describe_coordinates(*far) == "4.00000, 108.00000"


def test_another_country_is_never_named_as_a_malaysian_town():
    """Tokyo. The lookup is Malaysian by construction, so anything outside it must fall back."""
    assert geo_places.place_label(35.6762, 139.6503) is None
    assert geo_places.describe_coordinates(35.6762, 139.6503) == "35.67620, 139.65030"


def test_the_threshold_is_what_decides_the_fallback():
    """Stated as a constant so the rule is one number, reviewable, rather than a magic literal
    buried in a comparison.

    Measured from Bario, deep in the Sarawak highlands, because it is the one place in the table
    with nothing else within 100 km: walking away from a Klang Valley town just lands you in the
    next one, which would prove nothing about the threshold.
    """
    bario = next(p for p in geo_places.MALAYSIA_PLACES if p.name == "Bario")
    # Due north, where a degree of latitude is a clean 111.2 km.
    inside = (bario.lat + (geo_places.NEAREST_PLACE_MAX_KM - 5) / 111.2, bario.lng)
    outside = (bario.lat + (geo_places.NEAREST_PLACE_MAX_KM + 5) / 111.2, bario.lng)

    assert geo_places.place_label(*inside) == "Bario, Sarawak"
    # Past the threshold nothing is named, and the numbers stand alone.
    assert geo_places.nearest_place(*outside)[1] > geo_places.NEAREST_PLACE_MAX_KM
    assert geo_places.place_label(*outside) is None
    assert geo_places.describe_coordinates(*outside) == geo_places.format_coordinates(*outside)


# ------------------------------------------------------------------ absent and broken input


@pytest.mark.parametrize("lat,lng", [(None, None), (3.03927, None), (None, 101.80660)])
def test_a_missing_coordinate_produces_nothing_at_all(lat, lng):
    """The browser refusing the location prompt is a normal answer, not an error. Half a fix is
    not a position either, so it is treated the same as none."""
    assert geo_places.describe_coordinates(lat, lng) is None
    assert geo_places.place_label(lat, lng) is None


@pytest.mark.parametrize("lat,lng", [("abc", "def"), (200.0, 400.0), (float("nan"), 101.0)])
def test_unusable_input_is_refused_rather_than_guessed(lat, lng):
    """A corrupt row must not take a PDF render down with it, and must never be rounded into a
    plausible-looking position."""
    assert geo_places.describe_coordinates(lat, lng) is None
    assert geo_places.place_label(lat, lng) is None


# ------------------------------------------------------- what the frontend is handed


def test_every_serialized_signature_carries_the_resolved_place():
    """The backend is the authority and the screen consumes its answer.

    There is no runtime shared code across the FE/BE boundary, so the alternative was a second
    copy of the table in the browser - and two copies drift, at which point the screen and the PDF
    disagree about where somebody signed. Instead the ONE place-lookup answer rides on the one
    serializer every signing surface already goes through.
    """
    from app.schemas.projects import QuotationSignatureResponse

    signed = QuotationSignatureResponse(
        id="sig-1",
        signer_name="Jayson",
        mode="draw",
        gps_lat=Decimal("3.0392672"),
        gps_lng=Decimal("101.8066021"),
    ).model_dump()

    assert signed["gps_place"] == "Kajang, Selangor"
    # The numbers travel untouched beside it. The place is a label, not a replacement.
    assert signed["gps_lat"] == Decimal("3.0392672")
    assert signed["gps_lng"] == Decimal("101.8066021")


def test_a_signature_with_no_location_carries_no_place():
    """The browser refusing the prompt is a normal answer. The screen prints `-` for it, and a
    guessed place would be worse than nothing."""
    from app.schemas.projects import QuotationSignatureResponse

    assert QuotationSignatureResponse(id="sig-2").model_dump()["gps_place"] is None


def test_the_same_coordinate_always_reads_the_same()  :
    """Determinism is the whole reason this is a committed table and not a web service: a
    re-download of a two-year-old issue must say what it said the day it was sent."""
    first = geo_places.describe_coordinates(*REAL_SIGNATURE)
    assert all(geo_places.describe_coordinates(*REAL_SIGNATURE) == first for _ in range(5))
