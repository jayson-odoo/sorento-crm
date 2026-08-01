"""The PDF worker, end to end, against a real browser and the running stack.

This is the test the slice exists for. Everything else proves the pieces; this
proves that a request actually becomes a file, and - the part that matters -
that a staff export and a consumer export of the SAME page produce DIFFERENT
documents.

These drive headless Chromium at a real print page, so they need a frontend.
An absent one is a FAILURE, not a skip: see `_require_a_reachable_frontend`.
Run with the stack up:

    DEALER_KIT_PRINT_BASE_URL=http://localhost:3020 pytest tests/test_dealer_kit_pdf_render.py
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.services.dealer_kit import collection_service, export_service, page_service
from app.tasks import dealer_kit_export_tasks as task
from tests._pg_fixture import unique_code

PRINT_BASE = os.environ.get("DEALER_KIT_PRINT_BASE_URL", "http://localhost:3020")
_USER = "00000000-0000-4000-8000-00000000e001"

# The one way to say "I know, and I am choosing not to run them".
RENDER_TESTS_ENV = "DEALER_KIT_RENDER_TESTS"


@pytest.fixture()
def committed_db():
    """A session whose writes are REALLY committed, then cleaned up by marker.

    The usual rolled-back fixture cannot work here: a browser and the API read
    through their own connections, and uncommitted rows are invisible to them.
    So this commits for real - and because the local database is a copy of
    production, teardown deletes ONLY the ids this test created, never by
    pattern and never globally.
    """
    from app.database import SessionLocal
    from app.models.base import set_company_scope

    session = SessionLocal()
    set_company_scope(session, frozenset({"00000000-0000-0000-0000-000000000001"}))
    created: dict[str, list] = {"pages": [], "products": [], "categories": [], "uoms": [], "designs": []}
    try:
        yield session, created
    finally:
        try:
            from app.models.dealer_kit import Page, TileTemplate
            from app.models.product import Product, ProductCategory, UnitOfMeasure
            from app.models.download import UserDownload

            # Pages cascade to versions, labels, collections and export
            # requests; downloads cascade to their export request.
            for page_id in created["pages"]:
                session.query(UserDownload).filter(
                    UserDownload.source_entity_id == page_id
                ).delete(synchronize_session=False)
                session.query(Page).filter(Page.id == page_id).delete(
                    synchronize_session=False
                )
            for model, key in (
                (TileTemplate, "designs"),
                (Product, "products"),
                (ProductCategory, "categories"),
                (UnitOfMeasure, "uoms"),
            ):
                for row_id in created[key]:
                    session.query(model).filter(model.id == row_id).delete(
                        synchronize_session=False
                    )
            session.commit()
        finally:
            session.close()


_frontend_probe: dict[str, bool] = {}


def _frontend_up() -> bool:
    """Is something answering at PRINT_BASE?

    Probed lazily and remembered, not at import: collection happens in places
    that never intend to RUN these (the `--collect-only` gate runs inside a
    container with no network), and a per-collection socket timeout there is
    pure cost.
    """
    if "up" not in _frontend_probe:
        import urllib.request

        try:
            with urllib.request.urlopen(PRINT_BASE, timeout=3) as response:
                _frontend_probe["up"] = response.status < 500
        except Exception:
            _frontend_probe["up"] = False
    return _frontend_probe["up"]


_NO_FRONTEND = f"""\
The Dealer Kit PDF render tests need a running frontend, and nothing answered
at {PRINT_BASE}.

These are the ONLY tests that prove an exported PDF matches the brochure, so
they must not disappear quietly. To run them:

    cd sorento_crm_frontend && npm ci --force && npm run build && npm start
    # `npm start` serves on :3000; use `PORT=3020 npm start` to match the
    # DEALER_KIT_PRINT_BASE_URL default below.

    # Chromium is driven from a spawned subprocess, so the browser binary must
    # exist for the backend interpreter:
    python -m playwright install chromium

    DEALER_KIT_PRINT_BASE_URL=http://localhost:3020 pytest tests/test_dealer_kit_pdf_render.py

The print page also fetches the backend directly, so :8000 (or whatever
NEXT_PUBLIC_API_URL was baked into the frontend build) has to be up too, with
the frontend's origin in CORS_ORIGINS.

If you deliberately do not want them in this run, say so and they will skip:

    {RENDER_TESTS_ENV}=skip pytest ...
"""


# A skip has to be a DECISION. `skipif(not _frontend_up())` made it an accident:
# CI never starts a frontend, so all seven skipped and the job reported green -
# a tick standing for nothing over the one requirement the user actually stated.
pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
    ),
]


@pytest.fixture(autouse=True)
def _honour_the_opt_out():
    """The ONLY route to a skip: someone asked for one.

    A skip is a setup-time decision, so it belongs in a fixture. The absent
    frontend deliberately does NOT - see `_require_a_reachable_frontend`.
    """
    if os.environ.get(RENDER_TESTS_ENV, "").strip().lower() == "skip":
        pytest.skip(f"{RENDER_TESTS_ENV}=skip (explicitly opted out)")


def _require_a_reachable_frontend() -> None:
    """Fail - as a FAILURE, not an error - when there is no frontend to drive.

    Called from `_render`, i.e. from the test BODY, rather than from a fixture.
    `pytest.fail` during setup is reported as an *error*, and in this repo a run
    with errors means something else entirely (a contended database, see
    PRINCIPLES); a missing frontend must not be mistaken for that. Every test in
    this file renders a PDF, because a render test that renders nothing is not
    one, so `_render` is the honest choke point.
    """
    if not _frontend_up():
        pytest.fail(_NO_FRONTEND, pytrace=False)


def _product(db, created, list_price=Decimal("1290.00")):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = unique_code("ZZTPDF")
    category = ProductCategory(category_code=code, category_name=f"ZZT cat {code}")
    uom = UnitOfMeasure(uom_code=code[:20], uom_name=f"ZZT uom {code}")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=code,
        product_name=f"ZZT PDF product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=list_price,
        invoice_price=Decimal("777.77"),
        currency="MYR",
        is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    db.flush()
    created["categories"].append(category.id)
    created["uoms"].append(uom.id)
    created["products"].append(product.id)
    return product


def _page_with_products(db, created, *, product_count: int = 1, profile=None):
    """A published page carrying one collection block bound to its products.

    ``product_count`` fills the tile row: a document that overflows the paper
    loses the RIGHTMOST tile first, so a single centred tile can hide a clip
    that three tiles make obvious.

    Every product gets a DIFFERENT list price, so a price string read out of a
    rendered PDF identifies which tile it came from. With every tile priced the
    same, a price that has been carried onto the next page by a fold is
    indistinguishable from the one that belongs there.
    """
    from app.services.dealer_kit import tile_template_service

    products = [
        _product(db, created, list_price=Decimal("1290.00") + index)
        for index in range(product_count)
    ]
    product = products[0]
    page = page_service.create_page(
        db,
        name=f"ZZT PDF {unique_code('page')}",
        slug=unique_code("zzt-pdf").lower(),
        user_id=None,
    )
    collection = collection_service.create_collection(
        db, scope="page", page_id=page.id, pinned_product_ids=[p.id for p in products]
    )
    design = tile_template_service.create_template(
        db, name=f"ZZT design {unique_code('d')}", fields=["name", "code", "price"]
    )
    created["pages"].append(page.id)
    created["designs"].append(design.id)

    doc = {
        "sections": [
            {
                "id": "s1",
                "name": "Products",
                "style": {"paddingY": "md"},
                "printMode": "include",
                "blocks": [
                    {
                        "id": "b1",
                        "type": "collection",
                        "props": {
                            "kind": "collection",
                            "collectionId": collection.id,
                            "tileTemplateId": design.id,
                            "columns": {"desktop": 3, "tablet": 2, "mobile": 1},
                        },
                    }
                ],
                "layouts": {
                    breakpoint: {
                        "blocks": {"b1": {"colStart": 1, "colSpan": 12, "rowStart": 1, "rowSpan": 6}},
                        "isDerived": breakpoint != "desktop",
                    }
                    for breakpoint in ("desktop", "tablet", "mobile")
                },
            }
        ],
        "printProfile": profile or page_service.DEFAULT_PRINT_PROFILE,
    }

    version = page_service.save_version(
        db, page.id, doc=doc, commit_message="pdf test", user_id=None
    )
    page_service.move_label(db, page.id, "published", version_id=version.id, user_id=None)
    return page, product, products


def _render(db, page_id, audience, show_invoice_price, *, landscape=False, paper="A4"):
    _require_a_reachable_frontend()
    download = export_service.request_export(
        db,
        page_id=page_id,
        audience=audience,
        show_invoice_price=show_invoice_price,
        user_id=_USER,
    )
    db.commit()  # the browser and the API read through their OWN connections

    url = task._print_url(download.id)
    return task._render_pdf(url, landscape=landscape, paper=paper), download


def _drawn_extents(pdf_bytes: bytes) -> list[dict]:
    """Per page: the paper box, and the x-extent of everything drawn on it.

    PyMuPDF reports DEVICE coordinates - the transformation Chromium wrote into
    the content stream is already applied - so these are the numbers a reader
    sees. Reading the text matrix raw instead gives figures 4/3 too large and
    an overflow that is not there.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages = []
        for page in doc:
            width = float(page.rect.width)
            # A text block is (x0, y0, x1, y1, text, ...), so the coordinates
            # need pulling out as floats before any arithmetic.
            text_boxes = [
                (float(block[0]), float(block[2])) for block in page.get_text("blocks")
            ]
            boxes = list(text_boxes)
            boxes += [
                (float(d["rect"].x0), float(d["rect"].x1)) for d in page.get_drawings()
            ]
            boxes += [
                (float(i["bbox"][0]), float(i["bbox"][2]))
                for i in page.get_image_info()
            ]
            pages.append(
                {
                    "width": width,
                    "height": float(page.rect.height),
                    "right": max((x1 for _x0, x1 in boxes), default=0.0),
                    # Backgrounds paint the whole sheet whatever the document
                    # does, so they say nothing about how wide the brochure is.
                    # Everything else is content, and content is what has to
                    # follow the paper when the paper turns landscape.
                    "content_right": max(
                        (x1 for x0, x1 in boxes if x1 - x0 < width * 0.99), default=0.0
                    ),
                    # Text only: the document's background legitimately starts
                    # at x=0, so it cannot answer "where does the brochure
                    # begin".
                    "text_left": min((x0 for x0, _x1 in text_boxes), default=0.0),
                }
            )
        return pages
    finally:
        doc.close()


def _pdf_text(pdf_bytes: bytes) -> str:
    """Every readable string in the document, sheet order.

    PyMuPDF rather than pypdf, which was the only pypdf import in the repo and
    is not in requirements.txt: it happens to be present in one developer venv,
    so these tests would have ERRORED the moment they ran anywhere else. Same
    extraction the rest of this file already relies on, one dependency fewer.
    """
    return "\n".join(_text_per_page(pdf_bytes))


def _text_per_page(pdf_bytes: bytes) -> list[str]:
    """One string per SHEET, so a fold can be seen as a change of page."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()


def _tile_rects(pdf_bytes: bytes) -> list[list[tuple[float, float, float, float]]]:
    """Per page, the drawn border box of each product tile.

    A tile is a bordered card, so it is a stroked path. Backgrounds are the only
    other paths and they paint the full sheet, which is what the width test
    excludes; the height floor drops rules such as a struck-through price.

    A tile that a fold has cut in two is emitted as several overlapping paths
    for the same box, so identical boxes are collapsed - the count is meant to
    read as "how many tiles", not "how many path operations".
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages = []
        for page in doc:
            width = float(page.rect.width)
            seen: dict[tuple, tuple[float, float, float, float]] = {}
            for drawing in page.get_drawings():
                rect = drawing["rect"]
                box = (
                    float(rect.x0),
                    float(rect.y0),
                    float(rect.x1),
                    float(rect.y1),
                )
                if box[2] - box[0] >= width * 0.99:
                    continue
                if box[3] - box[1] < 20:
                    continue
                seen.setdefault(tuple(round(value) for value in box), box)
            pages.append(sorted(seen.values(), key=lambda box: (box[1], box[0])))
        return pages
    finally:
        doc.close()


def _top_row(rects: list[tuple[float, float, float, float]]) -> list:
    """The tiles sharing the topmost row, which is how many are across."""
    if not rects:
        return []
    top = min(box[1] for box in rects)
    return [box for box in rects if abs(box[1] - top) <= 2]


_HEADING = "ZZT BREAKPOINT MARKER"

# Tile density per breakpoint, as `_heading_and_tiles_page` declares it.
_TILES_ACROSS = {"desktop": 3, "tablet": 2, "mobile": 1}
# Only the desktop layout puts the heading beside the tiles.
_HEADING_BESIDE_TILES = {"desktop": True, "tablet": False, "mobile": False}


def _heading_and_tiles_page(db, created, *, profile):
    """A page whose DESKTOP layout differs visibly from its tablet one.

    A heading beside a collection on desktop, and above it on tablet and
    mobile. Which of those a rendered sheet shows says, in the geometry, which
    breakpoint's PLACEMENTS it used - and the tiles across say which one's
    DENSITY it used. They have to be the same breakpoint, and the paper's own
    width is what decides which.
    """
    from app.services.dealer_kit import tile_template_service

    products = [
        _product(db, created, list_price=Decimal("1290.00") + index) for index in range(3)
    ]
    page = page_service.create_page(
        db,
        name=f"ZZT PDF {unique_code('page')}",
        slug=unique_code("zzt-bp").lower(),
        user_id=None,
    )
    collection = collection_service.create_collection(
        db, scope="page", page_id=page.id, pinned_product_ids=[p.id for p in products]
    )
    design = tile_template_service.create_template(
        db, name=f"ZZT design {unique_code('d')}", fields=["name", "code", "price"]
    )
    created["pages"].append(page.id)
    created["designs"].append(design.id)

    doc = {
        "sections": [
            {
                "id": "s1",
                "name": "Products",
                "style": {"paddingY": "md"},
                "printMode": "include",
                "blocks": [
                    {
                        "id": "bh",
                        "type": "heading",
                        "props": {"kind": "heading", "text": _HEADING, "scale": "lg"},
                    },
                    {
                        "id": "bc",
                        "type": "collection",
                        "props": {
                            "kind": "collection",
                            "collectionId": collection.id,
                            "tileTemplateId": design.id,
                            "columns": {"desktop": 3, "tablet": 2, "mobile": 1},
                        },
                    },
                ],
                "layouts": {
                    # Side by side. Both blocks start on row 1, so the heading
                    # sits level with the first tile row.
                    "desktop": {
                        "blocks": {
                            "bh": {"colStart": 1, "colSpan": 4, "rowStart": 1, "rowSpan": 6},
                            "bc": {"colStart": 5, "colSpan": 8, "rowStart": 1, "rowSpan": 6},
                        },
                        "isDerived": False,
                    },
                    # Stacked, which puts the heading wholly above every tile.
                    "tablet": {
                        "blocks": {
                            "bh": {"colStart": 1, "colSpan": 8, "rowStart": 1, "rowSpan": 2},
                            "bc": {"colStart": 1, "colSpan": 8, "rowStart": 3, "rowSpan": 6},
                        },
                        "isDerived": False,
                    },
                    "mobile": {
                        "blocks": {
                            "bh": {"colStart": 1, "colSpan": 4, "rowStart": 1, "rowSpan": 2},
                            "bc": {"colStart": 1, "colSpan": 4, "rowStart": 3, "rowSpan": 6},
                        },
                        "isDerived": False,
                    },
                },
            }
        ],
        "printProfile": profile,
    }

    version = page_service.save_version(
        db, page.id, doc=doc, commit_message="breakpoint test", user_id=None
    )
    page_service.move_label(db, page.id, "published", version_id=version.id, user_id=None)
    return page


def _profile(page_size: str, orientation: str) -> dict:
    return {**page_service.DEFAULT_PRINT_PROFILE, "pageSize": page_size, "orientation": orientation}


@pytest.mark.parametrize(
    ("page_size", "orientation", "expected"),
    [
        # 210mm at the 96dpi CSS reckons in is 794px: past the 768px tablet
        # minimum, short of desktop's 1280.
        ("A4", "portrait", "tablet"),
        # 420mm is 1587px. A sheet that wide IS a desktop, and a brochure
        # printed on it should look like the brochure on a desktop screen.
        # Two rows apart in the table, so a hardcoded answer cannot pass both.
        ("A3", "landscape", "desktop"),
    ],
)
def test_the_paper_is_one_breakpoint_for_both_placement_and_density(
    committed_db, page_size, orientation, expected
):
    """One sheet, one layout. It used to carry half of two.

    Tile density fell back to desktop because the print page named no
    breakpoint, while the renderer's media queries went on resolving against
    the width of the paper and returned tablet placements. So an A4 export
    stacked the blocks the way the tablet layout says and then filled them at
    the desktop tile count - a document that exists at no width at all.
    """
    db, created = committed_db
    page = _heading_and_tiles_page(db, created, profile=_profile(page_size, orientation))
    pdf_bytes, _download = _render(
        db, page.id, "staff", False, landscape=(orientation == "landscape"), paper=page_size
    )

    rects = _tile_rects(pdf_bytes)[0]
    across = len(_top_row(rects))

    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        heading = next(
            block for block in doc[0].get_text("blocks") if _HEADING in block[4]
        )
    finally:
        doc.close()
    heading_bottom = float(heading[3])
    first_tile_top = min(box[1] for box in rects)
    beside = heading_bottom > first_tile_top

    placement = "desktop" if beside else "tablet"
    density = next(
        (name for name, count in _TILES_ACROSS.items() if count == across), f"{across} across"
    )

    assert placement == density, (
        f"one sheet, two layouts: the blocks are placed the {placement} way but "
        f"carry {across} tiles across, which is the {density} density"
    )
    assert beside is _HEADING_BESIDE_TILES[expected], (
        f"{page_size} {orientation} is a {expected} sheet, but the blocks are "
        f"placed the {placement} way"
    )
    assert across == _TILES_ACROSS[expected], (
        f"{page_size} {orientation} is a {expected} sheet, so it should carry "
        f"{_TILES_ACROSS[expected]} tiles across, not {across}"
    )


def test_a_fold_never_cuts_a_product_in_half(committed_db):
    """The break the preview cannot place must still not land inside a tile.

    Print Preview's paginator says sections are atomic, and the print
    stylesheet said the same with `break-inside: avoid`. Neither can hold for a
    section taller than one page: Chromium fragments it and the fold falls
    wherever it falls. Measured on a 40-product A4 export, it fell through the
    middle of a tile row - 47.6pt of a 57pt tile printed on the first sheet,
    the product names with it, and their prices alone at the top of the second.

    Each product carries its own list price here, so a price found on a sheet
    names the tile it belongs to.
    """
    db, created = committed_db
    page, _product, products = _page_with_products(db, created, product_count=40)
    pdf_bytes, _download = _render(db, page.id, "staff", False)

    pages = _text_per_page(pdf_bytes)
    assert len(pages) > 1, "fixture no longer overflows a page, so it proves nothing"

    def sheet_of(needle: str) -> int | None:
        return next((n for n, text in enumerate(pages, start=1) if needle in text), None)

    for product in products:
        price = f"MYR {product.list_price:,.2f}"
        code_sheet = sheet_of(product.product_code)
        price_sheet = sheet_of(price)
        assert code_sheet is not None, f"{product.product_code} did not print at all"
        assert code_sheet == price_sheet, (
            f"the fold cut a tile in half: {product.product_code} printed on "
            f"sheet {code_sheet} and its price {price} on sheet {price_sheet}"
        )

    # And geometrically, from the other side: a tile the fold has clipped is
    # SHORTER than a whole one, which is visible without reading a word of it.
    heights = [box[3] - box[1] for rects in _tile_rects(pdf_bytes) for box in rects]
    assert heights, "no tiles were drawn"
    # A whole tile is a fixed height here; 2pt covers Chromium's rounding and is
    # an order of magnitude under the 9.4pt a clipped tile loses.
    assert max(heights) - min(heights) <= 2.0, (
        f"tiles were drawn between {min(heights):.1f}pt and {max(heights):.1f}pt "
        "tall, so at least one was cut short by a page boundary"
    )


def test_a_request_becomes_a_real_pdf_containing_the_products(committed_db):
    db, created = committed_db
    page, product, _products = _page_with_products(db, created)
    pdf_bytes, _download = _render(db, page.id, "staff", False)

    assert pdf_bytes.startswith(b"%PDF"), "not a PDF"
    assert len(pdf_bytes) > 1000

    text = _pdf_text(pdf_bytes)
    assert product.product_code in text
    # List price is public, so it renders for every audience.
    assert "1,290.00" in text


# Chromium rounds the paper to whole device pixels, so the box is never exact
# to the point. One point of slack is far below the 64pt clip these catch.
_TOLERANCE_PT = 1.0

_MM_PT = 72 / 25.4
_MARGIN_PT = page_service.DEFAULT_PRINT_PROFILE["margins"]["left"] * _MM_PT

# Inside its own margin the renderer adds a section gutter and a tile border,
# so the first and last tile stop short of the margin by a few points. 30pt of
# slack absorbs that while still being an order of magnitude smaller than the
# 65pt frame and the 145pt shortfall these assertions exist to catch.
_INSIDE_MARGIN_SLACK_PT = 30.0


def test_nothing_the_reader_can_see_falls_off_the_paper(committed_db):
    """The user's requirement, measured: the PDF looks like the brochure.

    It did not. The document was rendered inside the `(auth)` group's sign-in
    Card, so it started 65pt in from the left edge and its last 64pt - the
    right-hand tile - hung off the paper and was clipped. Nothing in the
    document said so; only the rendered file does.
    """
    db, created = committed_db
    page, _product, _products = _page_with_products(db, created, product_count=3)
    pdf_bytes, _download = _render(db, page.id, "staff", False)

    for index, extent in enumerate(_drawn_extents(pdf_bytes), start=1):
        assert extent["right"] <= extent["width"] + _TOLERANCE_PT, (
            f"page {index}: content reaches {extent['right']:.1f}pt on a "
            f"{extent['width']:.1f}pt page, so "
            f"{extent['right'] - extent['width']:.1f}pt of it is clipped"
        )
        # And from the other side: a document squeezed into a centred card fits
        # the paper trivially while looking nothing like the brochure. The
        # brochure begins and ends at ITS OWN margins, not somewhere inside a
        # frame that belongs to another screen.
        assert extent["text_left"] <= _MARGIN_PT + _INSIDE_MARGIN_SLACK_PT, (
            f"page {index}: the brochure starts {extent['text_left']:.1f}pt in "
            f"on a page whose own margin is {_MARGIN_PT:.1f}pt, so something is "
            "framing it"
        )
        assert (
            extent["content_right"]
            >= extent["width"] - _MARGIN_PT - _INSIDE_MARGIN_SLACK_PT
        ), (
            f"page {index}: the brochure only reaches "
            f"{extent['content_right']:.1f}pt of a {extent['width']:.1f}pt page"
        )


def test_a_landscape_export_fills_the_landscape_paper(committed_db):
    """One owner of the page geometry, proved on the orientation that breaks it.

    Chromium's `landscape=True` rotates the paper. The print page used to state
    the width in millimetres as well, swapping it for landscape itself, so the
    rotation lived in two places and only ever agreed by luck. The page now
    takes the page box as it finds it.
    """
    db, created = committed_db
    page, _product, _products = _page_with_products(db, created, product_count=3)
    pdf_bytes, _download = _render(db, page.id, "staff", False, landscape=True)

    extents = _drawn_extents(pdf_bytes)
    assert extents[0]["width"] > extents[0]["height"], "not a landscape page box"
    for index, extent in enumerate(extents, start=1):
        assert extent["right"] <= extent["width"] + _TOLERANCE_PT, (
            f"page {index}: {extent['right'] - extent['width']:.1f}pt clipped"
        )
        assert (
            extent["content_right"]
            >= extent["width"] - _MARGIN_PT - _INSIDE_MARGIN_SLACK_PT
        ), (
            f"page {index}: the document did not follow the paper round to "
            f"landscape - {extent['content_right']:.1f}pt of "
            f"{extent['width']:.1f}pt"
        )


def test_a_staff_export_and_a_consumer_export_of_one_page_differ(committed_db):
    """The gate item: the audience recorded at enqueue changes the FILE."""
    db, created = committed_db
    page, _product, _products = _page_with_products(db, created)

    staff_pdf, _ = _render(db, page.id, "staff", True)
    consumer_pdf, _ = _render(db, page.id, "consumer", True)

    staff_text = _pdf_text(staff_pdf)
    consumer_text = _pdf_text(consumer_pdf)

    # Same document, same toggle - only the audience differs.
    assert "777.77" in staff_text, "staff copy should carry the invoice price"
    assert "777.77" not in consumer_text, "consumer copy must NOT carry it"
