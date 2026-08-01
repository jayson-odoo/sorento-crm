"""Turning a stored flyer reading into a DRAFT brochure (S7.4, UAC group E).

``flyer_extraction`` reads the paper, ``flyer_matching`` says what the paper
means against the master, and this module turns both into a page document
somebody can open in the builder and correct. It is the payoff of the whole
slice: 36 A3 pages of finished design become an afternoon of corrections
instead of a rebuild nobody starts on a Tuesday.

**A draft is a draft BY CONSTRUCTION (AC-E2).** There is no draft flag anywhere
in this module, and there must never be one. A version with no label pointing at
it is unreachable by every reader - ``published_doc`` deliberately refuses to
fall back to the latest version - so the ABSENCE of a label is the draft, and
approving it is the publish that already exists. A flag would be a second way to
say the same thing, and the two would disagree the first time one of them was
forgotten.

**One page, one section per flyer page (AC-E1, PLAN D2).** A reader scrolls one
catalogue, not 36 URLs, and one page also means one publish, one label and one
rollback. Every section carries ``printMode: breakBefore`` so the PDF export
still comes out with the same number of pages as the flyer.

**A printed row is a pinned collection (AC-E3, PLAN D3).** Never a rule: only
193 of the real flyer's 347 printed rows sit wholly inside one promotion group,
so a rule would quietly add and drop products the flyer never printed together.
The row is the layout unit; the promotion is a pricing binding.

**Re-seeding never reuses a collection (AC-E4, PLAN D10).** Same page,
``max(version) + 1``, published label untouched, and always FRESH page-scoped
collections. Reusing one would mutate what an older version renders, which is
the single thing versioning exists to prevent: a published edition would
silently start showing a product nobody approved. The cost is a few rows nobody
looks at; the alternative is a customer seeing a catalogue that was never signed
off.

**Nothing is invented.** A code the master does not have is left out and named
in the response, because the difference between a gap and a silent loss is
whether the person reviewing the seed can see it (PLAN D8). A heading the
extractor misread is carried through verbatim rather than guessed at: fixture
page 2 reads "Transforming Your" where the paper says "BATHTUB COLLECTION", and
a draft that quietly repaired it would be a draft nobody could check against the
flyer. Two products printed under one photo - a real pattern here - both get a
tile, in printed order, because deciding which one owns the picture would drop a
product from the catalogue on a guess.

**And no price, ever.** The document holds bindings: product ids, a collection
id, a heading string. Which figure a reader sees is resolved per viewer at read
time from the page's promotion (ADR 0008). A price written in here would freeze
one number for every audience and break the one thing the Kit exists to do.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import Collection, Page, PageVersion
from app.services.dealer_kit import collection_service, flyer_reading_service, page_service
from app.services.dealer_kit.flyer_extraction import FlyerPage, FlyerReading
from app.services.dealer_kit.flyer_matching import UnmatchedCode

# Paper this system can name, in millimetres, portrait. Anything else falls back
# to the builder's default profile: a print profile is a promise about how the
# document paginates, and inventing one for paper nobody recognises is worse than
# an A4 default a designer can see and change.
_PAPER_MM = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "Letter": (215.9, 279.4),
}

_MM_PER_PT = 25.4 / 72.0

# How far a measured page may sit from a named size and still be it. The fixture
# reads 297.0 x 420.0 mm on two pages and 297.2 x 420.2 on the third, so the
# tolerance covers the printer's own rounding without letting A4 pass as A3.
_PAPER_TOLERANCE_MM = 3.0

# The desktop grid is 12 columns wide (BREAKPOINT_COLUMNS in the builder), and
# every seeded block is full width: composition INSIDE a block - how many tiles
# across - is the block's own business, which is what lets a 6-across A3 row
# become 2-across on a phone without the layout knowing anything about tiles.
_BREAKPOINT_COLUMNS = {"desktop": 12, "tablet": 8, "mobile": 4}

# How tall each seeded block claims to be, in grid rows. Approximate on purpose:
# the builder measures real heights and reflows on open, so these only have to
# put the blocks in the right ORDER.
_HEADING_ROWS = 1
_COLLECTION_ROWS = 4

# The narrower breakpoints do not come from the paper. Six across on A3 is not
# six across on a phone, so desktop takes the printed row's own width and the
# rest follow the builder's defaults.
_MAX_TABLET_COLUMNS = 3
_MOBILE_COLUMNS = 1


@dataclass
class SeedResult:
    """What the seed made, for the screen that asked for it."""

    page: Page
    version: PageVersion
    section_count: int = 0
    collections: list[Collection] = field(default_factory=list)
    seeded_product_count: int = 0
    #: Printed codes that reached no tile, with the nearest existing code as a
    #: suggestion. The seed is only trustworthy if what it dropped is visible.
    skipped: list[UnmatchedCode] = field(default_factory=list)


def seed(
    db: Session,
    record,
    *,
    page_id: Optional[str] = None,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    promotion_id: Optional[str] = None,
    commit_message: Optional[str] = None,
    user_id: Optional[str] = None,
) -> SeedResult:
    """Build a draft brochure from a stored reading.

    ``page_id`` re-seeds an existing brochure as a NEW version; ``name`` and
    ``slug`` create one. Exactly one of the two, because the ambiguity resolves
    into the wrong answer half the time: silently creating a second page leaves
    a designer hunting for a catalogue they did not name, and silently
    re-seeding the page whose address collides overwrites somebody else's work.

    Nothing links a reading to a page it seeded earlier, deliberately. A reading
    is a working artefact, and one flyer legitimately seeds two brochures - a
    dealer edition and a consumer one - so which page a re-seed lands on is a
    decision the review screen makes, not a column.
    """
    reading = flyer_reading_service.to_reading(record)

    # The report the review screen already showed, recomputed against the master
    # as it stands right now. Reusing it is what keeps the seed and the report
    # from ever disagreeing about what a code resolved to.
    #
    # No promotion is passed: the seed needs only what each code IS, and whether
    # the linked promotion carries it is a question about the report that costs
    # a query the seed has no use for.
    report = flyer_reading_service.report_for(db, record)
    product_by_code = {entry.code: entry.product_id for entry in report.matched}

    page = _target_page(
        db,
        page_id=page_id,
        name=name,
        slug=slug,
        promotion_id=promotion_id,
        user_id=user_id,
        profile=paper_profile(reading),
    )

    doc, collections = _build_document(
        db, reading, page, product_by_code=product_by_code, user_id=user_id
    )

    version = page_service.save_version(
        db,
        page.id,
        doc=doc,
        commit_message=commit_message or f"Seeded from {record.filename}",
        user_id=user_id,
    )

    seeded = {
        product_id
        for collection in collections
        for product_id in (collection.pinned_product_ids or [])
    }
    return SeedResult(
        page=page,
        version=version,
        section_count=len(doc["sections"]),
        collections=collections,
        seeded_product_count=len(seeded),
        skipped=list(report.unmatched),
    )


def _target_page(
    db: Session,
    *,
    page_id: Optional[str],
    name: Optional[str],
    slug: Optional[str],
    promotion_id: Optional[str],
    user_id: Optional[str],
    profile: dict,
) -> Page:
    """The page this seed writes a version onto.

    The promotion is applied HERE, before a single collection exists, so an
    unknown one is a 404 that leaves nothing behind rather than a half-made
    catalogue somebody finds later.

    The measured paper is applied on CREATION only. On a re-seed the page
    already has a profile, and a designer may have changed it deliberately -
    overwriting it would silently re-paginate a brochure that is already
    published, since the profile lives on the page and is shared by every
    version of it.
    """
    if page_id:
        page = page_service.get_page(db, page_id)
        if promotion_id:
            # Only when one is given. An omitted promotion on a re-seed means
            # "leave it alone", never "unlink": silently dropping a live
            # brochure's offer sends it back to list prices with nobody told,
            # and clearing the link is the page's own PUT, which says so out
            # loud.
            page = page_service.set_promotion(db, page.id, promotion_id)
        return page

    page = page_service.create_page(
        db,
        name=(name or "").strip(),
        slug=(slug or "").strip(),
        user_id=user_id,
        promotion_id=promotion_id,
    )
    page.print_profile = profile
    db.commit()
    db.refresh(page)
    return page


# --------------------------------------------------------------------------- #
# The document
# --------------------------------------------------------------------------- #
def _build_document(
    db: Session,
    reading: FlyerReading,
    page: Page,
    *,
    product_by_code: dict[str, str],
    user_id: Optional[str],
) -> tuple[dict, list[Collection]]:
    sections: list[dict] = []
    created: list[Collection] = []

    for flyer_page in reading.pages:
        section, collections = _section(
            db, flyer_page, page, product_by_code=product_by_code, user_id=user_id
        )
        sections.append(section)
        created.extend(collections)

    # On a NEW page the profile was measured off the flyer; on a re-seed the page
    # already has one, and a designer may have changed it. The document mirrors
    # whatever the row holds so the editor and the PDF cannot disagree - the
    # export reads the row, the builder reads the doc.
    return {"sections": sections, "printProfile": page.print_profile or paper_profile(reading)}, created


def _section(
    db: Session,
    flyer_page: FlyerPage,
    page: Page,
    *,
    product_by_code: dict[str, str],
    user_id: Optional[str],
) -> tuple[dict, list[Collection]]:
    blocks: list[dict] = []
    placements: dict[str, dict] = {}
    collections: list[Collection] = []
    row = 1

    if flyer_page.heading:
        # Carried through EXACTLY as read. The detector is a heuristic (largest
        # non-card text in the top band) and is known wrong on at least one page
        # of the real flyer; correcting it is a five second edit on the review
        # screen, and a seed that guessed at a better heading would be a draft
        # nobody could check against the paper.
        block_id = _block_id()
        blocks.append(
            {
                "id": block_id,
                "type": "heading",
                "hideInPrint": False,
                "props": {"kind": "heading", "text": flyer_page.heading, "scale": "2xl"},
            }
        )
        placements[block_id] = _placement(row, _HEADING_ROWS)
        row += _HEADING_ROWS

    for grid in flyer_page.grids:
        # Printed order, de-duplicated. Two codes resolving to one product would
        # otherwise pin it twice and render the same tile beside itself.
        product_ids: list[str] = []
        for card in grid.cards:
            product_id = product_by_code.get(card.code)
            if product_id and product_id not in product_ids:
                product_ids.append(product_id)

        if not product_ids:
            # A row where nothing resolved becomes NO block. An empty pinned
            # collection renders a blank grid a designer can do nothing with,
            # inside a page that otherwise looks complete - and the codes are
            # reported as skipped, which says the same thing where somebody is
            # reading it.
            continue

        # ALWAYS a fresh row, never a reused one (AC-E4, PLAN D10). Recycling
        # the collection an earlier version points at would make that version
        # render something nobody approved - and if it is the published one, a
        # customer sees it with no trace of the change. The stale rows left
        # behind are page-scoped and die with the page.
        collection = collection_service.create_collection(
            db,
            scope=collection_service.PAGE,
            page_id=page.id,
            # Pins and a manual order, never a rule (PLAN D3). manual_order
            # carries the printed left-to-right sequence, which is what the
            # resolver sorts members by.
            pinned_product_ids=product_ids,
            manual_order=product_ids,
            user_id=user_id,
        )
        collections.append(collection)

        block_id = _block_id()
        blocks.append(
            {
                "id": block_id,
                "type": "collection",
                "hideInPrint": False,
                "props": {
                    "kind": "collection",
                    "collectionId": collection.id,
                    # No design is invented: a null template renders the
                    # builder's default field set, and choosing one is an
                    # editorial decision for the review screen.
                    "tileTemplateId": None,
                    "columns": _columns(len(product_ids)),
                },
            }
        )
        placements[block_id] = _placement(row, _COLLECTION_ROWS)
        row += _COLLECTION_ROWS

    return (
        {
            "id": _section_id(),
            # Named after what the flyer page says, so the editor's section list
            # lines up against the paper. A page with no heading is named for its
            # page number rather than left blank: a section a reviewer cannot
            # place is worse than one with a dull name.
            "name": flyer_page.heading or f"Page {flyer_page.number}",
            "style": {"background": "transparent", "paddingY": "lg"},
            "blocks": blocks,
            "layouts": _layouts(placements),
            # Uniformly, including on the first section: the paginator already
            # ignores a break before the very first one, so applying it
            # everywhere removes a special case nobody would remember (AC-E1).
            "printMode": "breakBefore",
        },
        collections,
    )


def _columns(printed: int) -> dict:
    """Tile density per breakpoint. Only desktop comes from the paper."""
    desktop = max(1, printed)
    return {
        "desktop": desktop,
        "tablet": min(desktop, _MAX_TABLET_COLUMNS),
        "mobile": _MOBILE_COLUMNS,
    }


def _placement(row: int, rows: int) -> dict:
    return {
        "colStart": 1,
        "colSpan": _BREAKPOINT_COLUMNS["desktop"],
        "rowStart": row,
        "rowSpan": rows,
    }


def _layouts(desktop: dict[str, dict]) -> dict:
    """Desktop as authored, the narrower breakpoints derived from it.

    Mirrors ``createLayouts`` in the builder: derivation stacks every block full
    width in reading order, which is exactly what these already are, so the
    derived maps differ only in their column span. ``isDerived`` stays true on
    both so a Designer's first edit to either one pins it and it stops following
    desktop.
    """
    return {
        "desktop": {"blocks": desktop, "isDerived": False},
        **{
            breakpoint: {
                "blocks": {
                    block_id: {**placement, "colSpan": _BREAKPOINT_COLUMNS[breakpoint]}
                    for block_id, placement in desktop.items()
                },
                "isDerived": True,
            }
            for breakpoint in ("tablet", "mobile")
        },
    }


def _section_id() -> str:
    return f"sec-{uuid.uuid4().hex[:8]}"


def _block_id() -> str:
    return f"blk-{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- #
# Paper
# --------------------------------------------------------------------------- #
def paper_profile(reading: FlyerReading) -> dict:
    """The print profile the flyer's own paper implies.

    The PDF export renders at the PAGE row's ``pageSize`` and ``orientation``, so
    a seed that left an A3 flyer on the A4 default would print an A3 layout onto
    A4 and overflow every section. Margins are not measurable from a reading -
    the flyer bleeds to the edge - so the builder's defaults stand and a designer
    adjusts them.
    """
    profile = dict(page_service.DEFAULT_PRINT_PROFILE)
    # The flyer's own first page IS its cover. Reserving another one puts a
    # blank leading sheet in front of it and pushes every page number out by one.
    profile["cover"] = False

    if not reading.pages:
        return profile

    first = reading.pages[0]
    width_mm = first.width * _MM_PER_PT
    height_mm = first.height * _MM_PER_PT

    for size, (short_mm, long_mm) in _PAPER_MM.items():
        if _close(width_mm, short_mm) and _close(height_mm, long_mm):
            profile["pageSize"] = size
            profile["orientation"] = "portrait"
            return profile
        if _close(width_mm, long_mm) and _close(height_mm, short_mm):
            profile["pageSize"] = size
            profile["orientation"] = "landscape"
            return profile

    return profile


def _close(measured: float, named: float) -> bool:
    return abs(measured - named) <= _PAPER_TOLERANCE_MM


def assert_target_is_unambiguous(page_id: Optional[str], name: Optional[str], slug: Optional[str]) -> None:
    """A seed says where it is going, and says it once.

    Raised from the schema's own validator so the answer is a 422 at the edge
    rather than a page created in the wrong place. Both branches name the two
    ways out: an error that only says what is wrong leaves the caller guessing.
    """
    named = bool((name or "").strip() and (slug or "").strip())
    if page_id and named:
        raise ValueError(
            "Seed into an existing page, or give a name and address for a new one, not both"
        )
    if not page_id and not named:
        raise ValueError(
            "Say where this seed goes: an existing page, or a name and address for a new one"
        )


__all__ = [
    "SeedResult",
    "seed",
    "paper_profile",
    "assert_target_is_unambiguous",
]
