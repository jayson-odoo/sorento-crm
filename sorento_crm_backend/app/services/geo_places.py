"""Turn a signature's coordinates into a place a reader recognises, offline.

`GPS LOCATION 3.03927, 101.80660` tells a person nothing. `near Kajang, Selangor (3.03927,
101.80660)` tells them where somebody stood, and still hands them the numbers.

**Why a committed table and not a geocoding service.** Three reasons, and each one on its own
would be enough:

1. A signature is legal evidence rendered inside a PDF, on a server that may have no egress at
   all. A document that fails to render, or renders differently, because an API was unreachable
   is not a record.
2. Calling a third party would ship a customer's exact position to somebody outside this system.
   Nobody consented to that by signing a quotation.
3. It has to be deterministic. Re-rendering a two-year-old issue must print what it printed the
   day it was sent; a provider that re-tiles its data would silently rewrite history.

**Why the answer says "near".** A nearest-neighbour over a table of towns knows a town, never a
street. Printing anything that reads like an address on a document a customer signs would be a
claim this data cannot support.

**Why the coordinates are always kept.** The numbers are the evidence and the name is the
convenience. Every rendered string carries both, so a dispute is settled on the coordinates and
nobody has to trust this table to have picked well.

This module is the ONE implementation. The PDF (``project_quotation_pdf_service``) calls it
directly; the frontend receives its answer as ``gps_place`` on every serialized signature
(``QuotationSignatureResponse``) rather than owning a second copy of the table. A browser-side
copy would drift from this one, and then the screen and the document would disagree about where
somebody signed.
"""
from __future__ import annotations

import math
from typing import Any, NamedTuple, Optional, Tuple


class Place(NamedTuple):
    name: str
    state: str
    lat: float
    lng: float


# How far "near" is allowed to stretch, in kilometres.
#
# 50 km is roughly an hour on a trunk road, and it is shorter than the typical spacing between
# the towns below, so a match means the point really does sit in that town's orbit rather than
# merely being closer to it than to anything else in the list. Past that the honest answer is the
# raw coordinates: a site 200 km up the Rajang from Kapit is not "near Kapit" to anybody who has
# made that journey. Peninsular signings land well inside it (the dense stretches of the table
# put most points within 15 km); the number exists for the interior of Sabah and Sarawak and for
# anything recorded outside the country.
NEAREST_PLACE_MAX_KM = 50.0

# Mean earth radius, km. A sphere is right to well under a percent at these distances, and the
# comparison being made is "which of these towns is closest", not a survey.
_EARTH_RADIUS_KM = 6371.0088

# Main towns of every state and federal territory, including Sabah and Sarawak. Coordinates are
# town centres to about 4 decimal places, which is far finer than a 50 km threshold needs.
#
# Ordered by state, north to south down the peninsula and then east, so a missing town is easy
# to spot. Adding a row is safe: the lookup is a scan, and denser coverage only ever moves an
# answer to a nearer, truer town.
MALAYSIA_PLACES: Tuple[Place, ...] = (
    # ---------------------------------------------------------------- Perlis
    Place("Kangar", "Perlis", 6.4414, 100.1986),
    Place("Arau", "Perlis", 6.4290, 100.2700),
    Place("Padang Besar", "Perlis", 6.6580, 100.3200),
    # ---------------------------------------------------------------- Kedah
    Place("Alor Setar", "Kedah", 6.1248, 100.3678),
    Place("Sungai Petani", "Kedah", 5.6470, 100.4877),
    Place("Kulim", "Kedah", 5.3650, 100.5610),
    Place("Jitra", "Kedah", 6.2680, 100.4220),
    Place("Langkawi", "Kedah", 6.3220, 99.8510),
    Place("Baling", "Kedah", 5.6750, 100.9160),
    Place("Yan", "Kedah", 5.8060, 100.3800),
    Place("Sik", "Kedah", 5.8200, 100.7400),
    # ---------------------------------------------------------------- Penang
    Place("George Town", "Penang", 5.4141, 100.3288),
    Place("Butterworth", "Penang", 5.3991, 100.3638),
    Place("Bukit Mertajam", "Penang", 5.3630, 100.4670),
    Place("Bayan Lepas", "Penang", 5.2940, 100.2730),
    Place("Balik Pulau", "Penang", 5.3500, 100.2320),
    Place("Nibong Tebal", "Penang", 5.1660, 100.4780),
    # ---------------------------------------------------------------- Perak
    Place("Ipoh", "Perak", 4.5975, 101.0901),
    Place("Taiping", "Perak", 4.8500, 100.7333),
    Place("Kuala Kangsar", "Perak", 4.7700, 100.9300),
    Place("Batu Gajah", "Perak", 4.4700, 101.0400),
    Place("Kampar", "Perak", 4.3060, 101.1530),
    Place("Sitiawan", "Perak", 4.2160, 100.6960),
    Place("Lumut", "Perak", 4.2300, 100.6300),
    Place("Teluk Intan", "Perak", 4.0230, 101.0210),
    Place("Tapah", "Perak", 4.1970, 101.2600),
    Place("Parit Buntar", "Perak", 5.1230, 100.4930),
    Place("Gerik", "Perak", 5.4270, 101.1300),
    Place("Tanjung Malim", "Perak", 3.6840, 101.5200),
    # ---------------------------------------------------------------- Selangor
    Place("Shah Alam", "Selangor", 3.0733, 101.5185),
    Place("Klang", "Selangor", 3.0449, 101.4455),
    Place("Port Klang", "Selangor", 3.0000, 101.3900),
    Place("Petaling Jaya", "Selangor", 3.1073, 101.6067),
    Place("Subang Jaya", "Selangor", 3.0436, 101.5807),
    Place("Puchong", "Selangor", 3.0000, 101.6167),
    Place("Seri Kembangan", "Selangor", 3.0250, 101.7050),
    Place("Kajang", "Selangor", 2.9931, 101.7876),
    Place("Bandar Baru Bangi", "Selangor", 2.9500, 101.7833),
    Place("Semenyih", "Selangor", 2.9500, 101.8433),
    Place("Ampang", "Selangor", 3.1500, 101.7600),
    Place("Selayang", "Selangor", 3.2600, 101.6500),
    Place("Rawang", "Selangor", 3.3210, 101.5770),
    Place("Sungai Buloh", "Selangor", 3.2100, 101.5800),
    Place("Kuala Selangor", "Selangor", 3.3400, 101.2500),
    Place("Sabak Bernam", "Selangor", 3.7600, 100.9900),
    Place("Kuala Kubu Bharu", "Selangor", 3.5600, 101.6600),
    Place("Banting", "Selangor", 2.8160, 101.5000),
    Place("Sepang", "Selangor", 2.6900, 101.7500),
    # ---------------------------------------------------------------- Federal territories
    Place("Kuala Lumpur", "Kuala Lumpur", 3.1390, 101.6869),
    Place("Putrajaya", "Putrajaya", 2.9264, 101.6964),
    Place("Labuan", "Labuan", 5.2831, 115.2308),
    # ---------------------------------------------------------------- Negeri Sembilan
    Place("Seremban", "Negeri Sembilan", 2.7297, 101.9381),
    Place("Nilai", "Negeri Sembilan", 2.8140, 101.7970),
    Place("Port Dickson", "Negeri Sembilan", 2.5228, 101.7960),
    Place("Kuala Pilah", "Negeri Sembilan", 2.7370, 102.2490),
    Place("Bahau", "Negeri Sembilan", 2.8100, 102.4100),
    Place("Rembau", "Negeri Sembilan", 2.5900, 102.0900),
    Place("Tampin", "Negeri Sembilan", 2.4700, 102.2300),
    # ---------------------------------------------------------------- Melaka
    Place("Melaka", "Melaka", 2.1896, 102.2501),
    Place("Alor Gajah", "Melaka", 2.3800, 102.2080),
    Place("Masjid Tanah", "Melaka", 2.3500, 102.1100),
    Place("Jasin", "Melaka", 2.3080, 102.4310),
    # ---------------------------------------------------------------- Johor
    Place("Johor Bahru", "Johor", 1.4927, 103.7414),
    Place("Iskandar Puteri", "Johor", 1.4200, 103.6300),
    Place("Pasir Gudang", "Johor", 1.4700, 103.8800),
    Place("Kulai", "Johor", 1.6600, 103.6000),
    Place("Kota Tinggi", "Johor", 1.7370, 103.9000),
    Place("Pontian", "Johor", 1.4870, 103.3900),
    Place("Batu Pahat", "Johor", 1.8548, 102.9325),
    Place("Kluang", "Johor", 2.0250, 103.3185),
    Place("Muar", "Johor", 2.0442, 102.5689),
    Place("Tangkak", "Johor", 2.2660, 102.5450),
    Place("Segamat", "Johor", 2.5148, 102.8158),
    Place("Mersing", "Johor", 2.4312, 103.8405),
    # ---------------------------------------------------------------- Pahang
    Place("Kuantan", "Pahang", 3.8077, 103.3260),
    Place("Pekan", "Pahang", 3.4900, 103.3900),
    Place("Temerloh", "Pahang", 3.4500, 102.4167),
    Place("Jerantut", "Pahang", 3.9360, 102.3620),
    Place("Bentong", "Pahang", 3.5200, 101.9100),
    Place("Raub", "Pahang", 3.7900, 101.8600),
    Place("Kuala Lipis", "Pahang", 4.1830, 102.0500),
    Place("Cameron Highlands", "Pahang", 4.4700, 101.3800),
    Place("Genting Highlands", "Pahang", 3.4230, 101.7930),
    Place("Maran", "Pahang", 3.5800, 102.7700),
    Place("Rompin", "Pahang", 2.8100, 103.4700),
    # ---------------------------------------------------------------- Terengganu
    Place("Kuala Terengganu", "Terengganu", 5.3302, 103.1408),
    Place("Marang", "Terengganu", 5.2060, 103.2060),
    Place("Dungun", "Terengganu", 4.7800, 103.4200),
    Place("Kerteh", "Terengganu", 4.5100, 103.4400),
    Place("Kemaman", "Terengganu", 4.2300, 103.4200),
    Place("Kuala Berang", "Terengganu", 5.0600, 102.9600),
    Place("Setiu", "Terengganu", 5.5300, 102.8000),
    Place("Kampung Raja", "Terengganu", 5.7600, 102.5500),
    # ---------------------------------------------------------------- Kelantan
    Place("Kota Bharu", "Kelantan", 6.1254, 102.2381),
    Place("Tumpat", "Kelantan", 6.2000, 102.1700),
    Place("Pasir Mas", "Kelantan", 6.0430, 102.1400),
    Place("Machang", "Kelantan", 5.7660, 102.2160),
    Place("Tanah Merah", "Kelantan", 5.8000, 102.1500),
    Place("Jeli", "Kelantan", 5.7000, 101.8400),
    Place("Kuala Krai", "Kelantan", 5.5300, 102.2000),
    Place("Gua Musang", "Kelantan", 4.8830, 101.9660),
    # ---------------------------------------------------------------- Sabah
    Place("Kota Kinabalu", "Sabah", 5.9804, 116.0735),
    Place("Tuaran", "Sabah", 6.1800, 116.2300),
    Place("Kota Belud", "Sabah", 6.3500, 116.4300),
    Place("Kudat", "Sabah", 6.8830, 116.8330),
    Place("Papar", "Sabah", 5.7350, 115.9330),
    Place("Beaufort", "Sabah", 5.3470, 115.7450),
    Place("Sipitang", "Sabah", 5.0800, 115.5500),
    Place("Tenom", "Sabah", 5.1300, 115.9400),
    Place("Keningau", "Sabah", 5.3390, 116.1600),
    Place("Nabawan", "Sabah", 5.0700, 116.4500),
    Place("Ranau", "Sabah", 5.9500, 116.6700),
    Place("Beluran", "Sabah", 5.7800, 117.5500),
    Place("Sandakan", "Sabah", 5.8402, 118.1179),
    Place("Kota Kinabatangan", "Sabah", 5.5300, 118.0500),
    Place("Lahad Datu", "Sabah", 5.0270, 118.3270),
    Place("Kunak", "Sabah", 4.6900, 118.2400),
    Place("Semporna", "Sabah", 4.4800, 118.6100),
    Place("Tawau", "Sabah", 4.2440, 117.8910),
    # ---------------------------------------------------------------- Sarawak
    Place("Kuching", "Sarawak", 1.5533, 110.3592),
    Place("Bau", "Sarawak", 1.4180, 110.1540),
    Place("Lundu", "Sarawak", 1.6700, 109.8500),
    Place("Serian", "Sarawak", 1.1670, 110.5670),
    Place("Sri Aman", "Sarawak", 1.2370, 111.4630),
    Place("Betong", "Sarawak", 1.4030, 111.5350),
    Place("Sarikei", "Sarawak", 2.1280, 111.5190),
    Place("Sibu", "Sarawak", 2.2870, 111.8300),
    Place("Kanowit", "Sarawak", 2.1000, 112.1500),
    Place("Kapit", "Sarawak", 2.0170, 112.9330),
    Place("Belaga", "Sarawak", 2.7000, 113.7700),
    Place("Mukah", "Sarawak", 2.8960, 112.0900),
    Place("Bintulu", "Sarawak", 3.1710, 113.0420),
    Place("Miri", "Sarawak", 4.3990, 113.9910),
    Place("Marudi", "Sarawak", 4.1830, 114.3170),
    Place("Bario", "Sarawak", 3.7500, 115.4700),
    Place("Limbang", "Sarawak", 4.7500, 115.0000),
    Place("Lawas", "Sarawak", 4.8500, 115.4000),
)


def _coordinate(value: Any) -> Optional[float]:
    """A usable float, or nothing.

    Decimal (the column type), float and str all arrive here. Anything unparseable, infinite,
    NaN or outside the globe is refused rather than clamped: a corrupt row must not be rounded
    into a plausible-looking position on a document somebody signed.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _pair(lat: Any, lng: Any) -> Optional[Tuple[float, float]]:
    """Both halves, in range, or nothing. Half a fix is not a position."""
    latitude = _coordinate(lat)
    longitude = _coordinate(lng)
    if latitude is None or longitude is None:
        return None
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None
    return latitude, longitude


def coordinate_pair(lat: Any, lng: Any) -> Optional[Tuple[float, float]]:
    """The public form of the pair parser.

    Callers that must REFUSE a bad position before answering (the public endpoint) need the same
    validation the rendering helpers apply silently, and reaching into a private name to get it
    is how two definitions of "is this a position" appear.
    """
    return _pair(lat, lng)


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance, haversine on a sphere.

    Haversine rather than the flat-earth shortcut because the table spans 2000 km of longitude
    from Perlis to Tawau, where ignoring the cosine of the latitude is a real error.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def nearest_place(lat: Any, lng: Any) -> Optional[Tuple[Place, float]]:
    """The closest town in the table and how far away it is, with no threshold applied.

    Returns None only when the input is not a position. Callers that want "is this close enough
    to name" want ``place_label``; this one is the raw measurement, kept separate so the
    threshold is applied in exactly one place and can be asserted on its own.
    """
    pair = _pair(lat, lng)
    if pair is None:
        return None
    latitude, longitude = pair
    # A linear scan over ~135 rows. An index would be a spatial structure to maintain and to get
    # wrong, for a loop that costs microseconds once per rendered signature.
    best: Optional[Tuple[Place, float]] = None
    for place in MALAYSIA_PLACES:
        away = distance_km(latitude, longitude, place.lat, place.lng)
        if best is None or away < best[1]:
            best = (place, away)
    return best


def place_label(lat: Any, lng: Any) -> Optional[str]:
    """`"Kajang, Selangor"`, or None when nothing known is close enough to name.

    The state is included because a town name alone is ambiguous to a reader outside the state,
    and because several Malaysian town names repeat. It is dropped for the federal territories,
    where "Kuala Lumpur, Kuala Lumpur" reads as a bug.
    """
    found = nearest_place(lat, lng)
    if found is None:
        return None
    place, away = found
    if away > NEAREST_PLACE_MAX_KM:
        return None
    if place.name == place.state:
        return place.name
    return f"{place.name}, {place.state}"


def format_coordinates(lat: Any, lng: Any) -> Optional[str]:
    """`"3.03927, 101.80660"`. Five decimals is about a metre, and it matches what the screen
    prints, so a reader comparing the PDF against the CRM sees the same string."""
    pair = _pair(lat, lng)
    if pair is None:
        return None
    return f"{pair[0]:.5f}, {pair[1]:.5f}"


def describe_coordinates(lat: Any, lng: Any) -> Optional[str]:
    """What a person reads: `"near Kajang, Selangor"`, or the bare coordinates when nothing is
    close enough to name.

    Client decision, 2026-08-05, overruling this function's earlier "never drop the coordinates"
    behaviour: `3.03927, 101.80660` printed on a customer-facing quotation reads as noise, not
    evidence, to the person holding it. The exact figures are not lost - they stay on the
    signature row (`gps_lat`/`gps_lng`) for whoever needs them - they are simply not part of the
    label everybody else reads. Falls back to the coordinates only because that is the only thing
    left to say once no place is known.
    """
    label = place_label(lat, lng)
    if label:
        return f"near {label}"
    return format_coordinates(lat, lng)
