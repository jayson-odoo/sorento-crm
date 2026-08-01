"""Keeping a flyer reading, and deriving its report on demand (S7.3).

``flyer_extraction`` reads the paper. ``flyer_matching`` says what the paper
means against the master. This module is what sits between them and a designer:
it stores what was read, and rebuilds the report every time somebody asks.

**The reading is stored. The report is not, and must not be.**

A report is only true for the product master and the promotion it was computed
against, and both move every day. A report written at upload time is wrong the
first time somebody creates one of the products it listed as missing, and wrong
in the direction that costs money: it tells marketing to close gaps that are
already closed, and a reviewer has no way to see that the answer is stale.
Recomputing costs 0.4s against the real flyer's 998 codes - three statements,
not 998 - which buys an answer that is true at the moment it is read. If that
ever stops being cheap, the fix is a cache with an explicit invalidation on
product and promotion writes, NOT a column.

**Extraction runs inside the request.** The real 36 page flyer extracts in about
a second, so a queue here would buy nothing and cost a state machine: a pending
row, a polling screen, a failure path, and a worker restart every time this
module changes. It stops being true if extraction reaches roughly ten seconds -
a flyer several times the size of the real one, or artwork rasterisation landing
in S7.5 - at which point this moves onto the ``imports`` queue and the route
returns 202 with a row to watch, exactly as the catalogue PDF export does.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import FlyerReadingRecord
from app.services.dealer_kit.flyer_extraction import (
    EncryptedFlyerError,
    FlyerArtwork,
    FlyerCard,
    FlyerGrid,
    FlyerPage,
    FlyerReading,
    extract_flyer,
)
from app.services.dealer_kit.flyer_matching import MatchReport, match_reading
from app.services.error_handler import AppException

# The ceiling on an uploaded flyer.
#
# The real _SORENTO A3 FLYER 2025-2026_ is 20 MB compressed. A designer
# exporting the same 36 A3 pages without compression can comfortably double
# that, so the limit has to clear 40 MB or it refuses the very document this
# feature exists for. 50 MB also stays inside what one request can hold in
# memory and extract synchronously; past it, the queue argument in the module
# docstring starts winning.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# What the stored JSON is shaped like. Bumped if the extractor's dataclasses
# change shape, so an old row is recognisably old rather than silently misread.
READING_FORMAT_VERSION = 1


def assert_within_limit(byte_size: int) -> None:
    """413 for anything over the ceiling, naming the ceiling.

    Called as the upload is read rather than after it, so an oversized file is
    refused without first being held whole in memory.

    The limit is stated in the message on purpose: "file too large" leaves a
    designer guessing what smaller means, and they will guess by uploading again.
    """
    if byte_size > MAX_UPLOAD_BYTES:
        raise AppException(
            status_code=413,
            message=(
                f"That flyer is larger than the {_megabytes(MAX_UPLOAD_BYTES)} MB limit. "
                "Export it at a lower image quality and upload it again."
            ),
            code="FLYER_TOO_LARGE",
        )


def _megabytes(value: int) -> str:
    return f"{value / (1024 * 1024):.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# Serialising a reading
#
# The WHOLE reading is kept, not just its codes. Matching needs the codes alone,
# but the seeder that follows (S7.4) builds one collection per printed ROW and
# one section per page heading, and S7.5 places the artwork - so a serialiser
# that kept only what today's report reads would seed a catalogue with no layout
# at all, and every test in this slice would still pass.
# --------------------------------------------------------------------------- #
def serialise(reading: FlyerReading) -> dict:
    return {
        "version": READING_FORMAT_VERSION,
        "pages": [_page_json(page) for page in reading.pages],
    }


def _page_json(page: FlyerPage) -> dict:
    return {
        "number": page.number,
        "width": page.width,
        "height": page.height,
        "heading": page.heading,
        "cards": [_card_json(card) for card in page.cards],
        # Rows reference their cards by code rather than repeating them. A code
        # is unique within a page (the extractor dedupes), and one copy of a card
        # cannot drift out of step with another.
        "grids": [
            {"y": grid.y, "codes": [card.code for card in grid.cards]}
            for grid in page.grids
        ],
        "artwork": [
            {
                "x_pct": art.x_pct,
                "y_pct": art.y_pct,
                "width_pct": art.width_pct,
                "height_pct": art.height_pct,
                "xref": art.xref,
            }
            for art in page.artwork
        ],
    }


def _card_json(card: FlyerCard) -> dict:
    return {
        "code": card.code,
        "lines": list(card.lines),
        "x": card.x,
        "y": card.y,
        "list_price": card.list_price,
        "offer_price": card.offer_price,
        "length_mm": card.length_mm,
        "width_mm": card.width_mm,
        "height_mm": card.height_mm,
    }


def deserialise(payload: dict) -> FlyerReading:
    """Rebuild the reading the extractor produced.

    Lossless by construction, and pinned by a round trip test: what is rebuilt
    here is what the seeder will build a catalogue from, so a dropped field is a
    catalogue missing a row rather than a visible error.
    """
    reading = FlyerReading()
    for entry in (payload or {}).get("pages", []):
        cards = [_card_of(raw) for raw in entry.get("cards", [])]
        by_code = {card.code: card for card in cards}

        page = FlyerPage(
            number=entry["number"],
            width=entry["width"],
            height=entry["height"],
            heading=entry.get("heading"),
        )
        page.cards = cards
        page.grids = [
            FlyerGrid(
                cards=[by_code[code] for code in raw.get("codes", []) if code in by_code],
                y=raw["y"],
            )
            for raw in entry.get("grids", [])
        ]
        page.artwork = [
            FlyerArtwork(
                x_pct=raw["x_pct"],
                y_pct=raw["y_pct"],
                width_pct=raw["width_pct"],
                height_pct=raw["height_pct"],
                xref=raw["xref"],
            )
            for raw in entry.get("artwork", [])
        ]
        reading.pages.append(page)
    return reading


def _card_of(raw: dict) -> FlyerCard:
    return FlyerCard(
        code=raw["code"],
        lines=list(raw.get("lines", [])),
        x=raw["x"],
        y=raw["y"],
        list_price=raw.get("list_price"),
        offer_price=raw.get("offer_price"),
        length_mm=raw.get("length_mm"),
        width_mm=raw.get("width_mm"),
        height_mm=raw.get("height_mm"),
    )


def to_reading(record: FlyerReadingRecord) -> FlyerReading:
    return deserialise(record.reading_json or {})


def page_count(record: FlyerReadingRecord) -> int:
    """Read straight off the JSON rather than through ``deserialise``.

    The list screen shows this for every row, and rebuilding a 998 card reading
    per row to count its pages is work nobody asked for.
    """
    return len((record.reading_json or {}).get("pages", []))


def code_count(record: FlyerReadingRecord) -> int:
    codes = {
        card["code"]
        for page in (record.reading_json or {}).get("pages", [])
        for card in page.get("cards", [])
    }
    return len(codes)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def create_reading(
    db: Session,
    *,
    filename: Optional[str],
    data: bytes,
    user_id: Optional[str],
) -> FlyerReadingRecord:
    """Read the uploaded PDF and keep what it says.

    ``extract_flyer`` raises ``ValueError`` for anything that is not a readable
    PDF, and that becomes a 400 in words. The alternatives are both worse: a 500
    tells a designer the system is broken when their file is, and a 201 carrying
    an empty report tells them their flyer has no products on it.

    A LOCKED PDF gets its own message. Print-ready artwork comes back from an
    agency password protected far more often than it comes back corrupt, and it
    is fixable in a minute by the person holding it - but only if they are told
    that is the problem. Handed the generic advice, they re-export the same
    locked file and upload it again.
    """
    try:
        reading = extract_flyer(data)
    except EncryptedFlyerError as exc:
        raise AppException(
            status_code=400,
            message=(
                "That PDF is password protected, so its contents cannot be read. "
                "Save an unprotected copy and upload that."
            ),
            code="FLYER_PASSWORD_PROTECTED",
        ) from exc
    except ValueError as exc:
        raise AppException(
            status_code=400,
            message=(
                f"That file could not be read as a PDF ({exc}). "
                "Upload the flyer as a PDF export rather than a Word or image file."
            ),
            code="FLYER_NOT_A_PDF",
        ) from exc

    record = FlyerReadingRecord(
        filename=(filename or "flyer.pdf")[:255],
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        reading_json=serialise(reading),
        created_by=user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_reading(db: Session, reading_id: str) -> FlyerReadingRecord:
    record = (
        db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).first()
    )
    if record is None:
        # The company scope filter runs before this, so "another company's
        # reading" and "no such reading" are deliberately the same answer. A 403
        # would confirm the id exists, which is the one thing the other company
        # must not learn.
        raise AppException(status_code=404, message="Flyer reading not found")
    return record


def list_readings(db: Session) -> list[FlyerReadingRecord]:
    """Newest first: the flyer somebody is working on is the one they just read.

    ``id`` breaks ties. Postgres ``now()`` is transaction time, so two readings
    written inside one transaction share a timestamp and would otherwise come
    back in whatever order the planner felt like.
    """
    return (
        db.query(FlyerReadingRecord)
        .order_by(FlyerReadingRecord.created_at.desc(), FlyerReadingRecord.id.desc())
        .all()
    )


def delete_reading(db: Session, reading_id: str) -> None:
    """Hard delete. A reading is a working artefact, not a record to retain."""
    record = get_reading(db, reading_id)
    db.delete(record)
    db.commit()


def report_for(
    db: Session,
    record: FlyerReadingRecord,
    promotion_id: Optional[str] = None,
) -> MatchReport:
    """The report, computed NOW against the master as it stands NOW.

    Deliberately not memoised on the row. See the module docstring: the whole
    value of this report is that it is true at the moment it is read.

    ``promotion_id`` is not checked for existence on purpose. A promotion that
    has been deleted reports every matched product as not promoted, which is how
    a reviewer discovers the brochure points at something that is gone - a 404
    here would just look like a broken screen.
    """
    return match_reading(db, to_reading(record), promotion_id=promotion_id)
