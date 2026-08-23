"""S21: the quotation's product picture - live while it is a draft, frozen at issue.

Written BEFORE the implementation. Two rules, and each is invisible when it breaks:

1. **A draft resolves LIVE.** 30 of the 535 products with candidate photos carry a choice, so
   almost every line starts with none. When somebody finally chooses one, it has to appear on the
   quotations already open - re-saving 52 lines to pick up a decision made elsewhere is not a
   workflow anybody would perform, so a stale cell would simply stay wrong forever.
2. **Issuing freezes it.** What the customer holds does not move. Re-choosing a product's photo
   next year must not rewrite the picture on a quotation already in their inbox, and re-issuing an
   unchanged scope in R2 must show what R1 showed.

Postgres only, via ``blank_session``. Every row carries the ``zzt-qimg`` marker, because the dev
database this runs against holds a copy of production data.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text

from app.models.numbering import DocumentNumberingRule
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.projects import ProjectQuotationLine
from app.models.resources import Attachment
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-qimg"
SIGNATURE_DATA_URI = "data:image/png;base64,zzt"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _numbering_rule(db, company_id: str) -> None:
    """Seeded, not borrowed: CI's database is empty, so a test that assumed an existing
    `project_quotation` rule would pass only on a developer's machine."""
    scoped = hasattr(DocumentNumberingRule, "company_id")
    query = db.query(DocumentNumberingRule).filter(
        DocumentNumberingRule.doc_type == "project_quotation"
    )
    if scoped:
        query = query.filter(DocumentNumberingRule.company_id == company_id)
    rule = query.first()
    if rule is None:
        rule = DocumentNumberingRule(id=_uid(), doc_type="project_quotation")
        if scoped:
            rule.company_id = company_id
        db.add(rule)
    rule.enabled = True
    rule.prefix_template = f"{MARKER}/Q/"
    rule.number_digits = 4
    rule.next_value = 141
    rule.start_value = 141
    rule.reset_policy = "none"
    rule.last_reset_key = None
    db.flush()


def _attachment(db, company_id: str, name: str) -> Attachment:
    row = Attachment(
        id=_uid(),
        company_id=company_id,
        original_filename=f"{MARKER}-{name}",
        stored_filename=f"{MARKER}-{name}",
        file_path=f"https://cdn.zzt.test/products/{MARKER}/{name}",
        thumbnail_path=f"https://cdn.zzt.test/products/{MARKER}/{name}.thumb.jpg",
        mime_type="image/jpeg",
    )
    db.add(row)
    db.flush()
    return row


def _link(db, product, attachment, *, primary=False, sort_order=None) -> ProductAttachment:
    row = ProductAttachment(
        id=_uid(),
        product_id=product.id,
        attachment_id=attachment.id,
        is_primary=primary,
        sort_order=sort_order,
    )
    db.add(row)
    db.flush()
    return row


def _setup(db):
    from app.services.project_service import register_project

    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    _numbering_rule(db, company_id)
    owner = _user(db, f"{MARKER} Baser Ramli")

    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name=f"{MARKER} each")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} Sanitary Ware"
    )
    db.add_all([uom, category])
    db.flush()

    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Cadangan Membina Pangsapuri {_uid()[:12]}",
    )
    return {
        "company_id": company_id,
        "owner": owner,
        "uom": uom,
        "category": category,
        "project": project,
    }


def _product(db, env) -> Product:
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} WC Suite",
        description=f"{MARKER} close-coupled WC, white",
        category_id=env["category"].id,
        base_uom_id=env["uom"].id,
        list_price=Decimal("300.00"),
    )
    db.add(row)
    db.flush()
    return row


def _issue(db, document, owner):
    from app.services import project_quotation_document_service as qdocs

    qdocs.sign_as_sorento(
        db,
        document=document,
        actor_user_id=owner,
        payload={
            "mode": "draw",
            "signer_name": f"{MARKER} Baser Ramli",
            "image_data_uri": SIGNATURE_DATA_URI,
        },
    )
    return qdocs.issue(db, document=document, actor_user_id=owner)


def _priced_line(db, env, scope, product=None, **payload):
    from app.services import project_quotation_service as quotes

    body = {"unit_price": "250.00", "quantity": 4}
    if product is not None:
        body["product_id"] = product.id
    else:
        body["description_snapshot"] = f"{MARKER} bespoke feature wall"
    body.update(payload)
    return quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=env["owner"],
        payload=body,
    )


def _cell(db, line):
    from app.services import project_quotation_service as quotes

    return quotes.serialize_lines(db, [line])[0]["product_image"]


# ------------------------------------------------------------------------- FRZ-1


def test_a_draft_line_shows_the_photo_chosen_today_not_the_one_chosen_when_it_was_typed():
    """The line was priced before anybody had chosen a photograph, which is the state of almost
    every product in the catalogue. Choosing one has to reach the quotations already open;
    re-saving 52 lines to pick it up is not a thing anybody would ever do."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)

        cell = _cell(db, line)
        assert cell["state"] == "no_photos"
        assert cell["url"] is None

        # Somebody links two photographs. Still nobody has said which one is the product.
        _link(db, product, _attachment(db, env["company_id"], "blank-page.jpg"), sort_order=0)
        chosen_file = _attachment(db, env["company_id"], "the-actual-wc.jpg")
        link = _link(db, product, chosen_file, sort_order=1)

        cell = _cell(db, line)
        assert cell["state"] == "not_chosen"
        assert cell["candidate_count"] == 2
        assert cell["url"] is None

        # And now they do.
        from app.services import product_image_service as images

        images.choose(db, link)

        cell = _cell(db, line)
        assert cell["state"] == "chosen"
        assert cell["filename"] == f"{MARKER}-the-actual-wc.jpg"
        # Nothing was written to the line: the draft is live, not stamped.
        db.refresh(line)
        assert line.image_attachment_id is None


def test_an_off_catalog_line_is_never_invited_to_choose_a_photo():
    """No product, so no `product_attachments` row a flag could point at. This is not "nobody has
    chosen yet" - there is nothing to choose, and offering the choice would be the second place a
    picture gets decided, which is exactly the defect the flag removes."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, None)

        cell = _cell(db, line)
        assert cell["state"] == "off_catalog"
        assert cell["url"] is None
        assert cell["candidate_count"] == 0


# ------------------------------------------------------------------- FRZ-2 / FRZ-3


def test_issuing_freezes_the_photo_and_re_choosing_never_rewrites_what_went_out():
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        first = _attachment(db, env["company_id"], "as-issued.jpg")
        second = _attachment(db, env["company_id"], "re-chosen-later.jpg")
        link_a = _link(db, product, first)
        link_b = _link(db, product, second)
        images.choose(db, link_a)

        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)
        assert line.image_attachment_id is None

        _issue(db, document, env["owner"])

        db.refresh(line)
        assert line.image_attachment_id == first.id

        # The product's photograph is re-chosen afterwards. The issued line does not move.
        images.choose(db, link_b)
        db.refresh(line)
        assert line.image_attachment_id == first.id
        assert images.chosen_attachment_id(db, product.id) == second.id


def test_re_issuing_an_unchanged_scope_leaves_the_frozen_photo_alone():
    """A revision does not force every scope to move: an untouched scope contributes the same
    version it contributed last time. R1 and R2 must not disagree about a picture."""
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        first = _attachment(db, env["company_id"], "r1.jpg")
        second = _attachment(db, env["company_id"], "r2.jpg")
        link_a = _link(db, product, first)
        link_b = _link(db, product, second)
        images.choose(db, link_a)

        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)
        _issue(db, document, env["owner"])

        images.choose(db, link_b)
        _issue(db, document, env["owner"])

        db.refresh(line)
        assert line.image_attachment_id == first.id


def test_a_frozen_line_reads_its_own_photo_not_the_products_current_one():
    """The screen shows the frozen picture on an issued version, for the same reason the PDF
    does: it is the record of what was sent."""
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        first = _attachment(db, env["company_id"], "as-issued.jpg")
        second = _attachment(db, env["company_id"], "re-chosen.jpg")
        images.choose(db, _link(db, product, first))
        link_b = _link(db, product, second)

        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)
        _issue(db, document, env["owner"])
        images.choose(db, link_b)

        cell = _cell(db, line)
        assert cell["state"] == "chosen"
        assert cell["filename"] == f"{MARKER}-as-issued.jpg"


# --------------------------------------------------------------------------- API


def test_the_line_payload_carries_a_signed_thumbnail_and_never_a_raw_object_key(monkeypatch):
    """API-1. A raw `file_path` in the payload is a URL the browser cannot load and a storage key
    leaked to the client at the same time."""
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        photo = _attachment(db, env["company_id"], "wc.jpg")
        images.choose(db, _link(db, product, photo))

        signed: list = []

        def _sign(file_path, *, provider=None, expires_in=3600):
            signed.append(file_path)
            return f"https://signed.zzt.test/x?sig={len(signed)}"

        monkeypatch.setattr(images, "resolve_signed_url", _sign)

        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)

        cell = _cell(db, line)
        assert cell["url"] == "https://signed.zzt.test/x?sig=1"
        # The ~320px thumbnail in the CELL, not the original: a 52-line table of
        # full-resolution photographs is tens of megabytes down the wire for cells about 48px
        # across. The ORIGINAL is signed too but only travels as `preview_url`, for the viewer
        # that opens on click - a thumbnail turns to mush the moment somebody zooms it.
        assert cell["preview_url"] == "https://signed.zzt.test/x?sig=2"
        assert signed == [photo.thumbnail_path, photo.file_path]
        # And the id, so the viewer can download through the authenticated route.
        assert cell["attachment_id"] == str(photo.id)


def test_one_table_of_lines_costs_one_pass_not_one_query_per_line(monkeypatch):
    """RES-6, through the serializer the screen actually calls."""
    from sqlalchemy import event

    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        env = _setup(db)
        monkeypatch.setattr(
            images, "resolve_signed_url", lambda path, **kwargs: "https://signed.zzt.test/x"
        )
        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        for _ in range(10):
            product = _product(db, env)
            images.choose(db, _link(db, product, _attachment(db, env["company_id"], "p.jpg")))
            _priced_line(db, env, scope, product)

        lines = quotes.list_lines(db, quotes.current_version(db, scope.id).id)
        db.flush()

        statements: list[str] = []

        def _count(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _count)
        try:
            payload = quotes.serialize_lines(db, lines)
        finally:
            event.remove(engine, "before_cursor_execute", _count)

        assert len(payload) == 10
        assert all(row["product_image"]["state"] == "chosen" for row in payload)
        # Chosen rows, candidate counts, which products this company can see, and the
        # attachment rows for signing. A fixed handful for the WHOLE table, never one per line -
        # that is the property under test, not the exact number. Ten lines here; the ceiling
        # must not move when that becomes fifty-two.
        assert len(statements) <= 5, statements


def test_freezing_is_only_ever_a_fill_never_an_overwrite():
    """A line that already carries an id keeps it, whatever the product says today. That is what
    makes re-issuing safe, and it is also the guard against a future caller running the freeze on
    something that is not being issued."""
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_image_service as line_images

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        stamped = _attachment(db, env["company_id"], "stamped.jpg")
        current = _attachment(db, env["company_id"], "current.jpg")
        _link(db, product, stamped)
        images.choose(db, _link(db, product, current))

        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        from app.services import project_quotation_service as quotes

        version = quotes.current_version(db, scope.id)
        held = _priced_line(db, env, scope, product)
        held.image_attachment_id = stamped.id
        db.flush()
        untouched = _priced_line(db, env, scope, _product(db, env))

        filled = line_images.freeze_version_images(db, version.id)

        db.refresh(held)
        db.refresh(untouched)
        assert held.image_attachment_id == stamped.id
        assert untouched.image_attachment_id is None  # its product has no chosen photo
        assert filled == 0

        assert (
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == version.id)
            .count()
            == 2
        )


# --------------------------------------------------------------------------- the contract
#
# Every test above asserts on what `serialize_lines` BUILDS. None of them could see that
# FastAPI was deleting the field again on the way out: the route declares
# `response_model=ListResponse[ProjectQuotationLineResponse]`, and a response model drops
# every key no field declares. `product_image` was built from S21 onward and stripped from
# every line route, so the picture column rendered "-" for every product, including ones
# whose photograph had been chosen correctly. Reported from the live screen on 2026-08-09.


def test_the_line_response_schema_declares_every_key_the_serializer_emits():
    """Guards the whole bug class, not just `product_image`.

    A field the serializer adds and the schema does not know about is silently deleted
    between the service and the browser, and nothing fails: the service test passes, the
    route returns 200, and the column is simply empty. So the assertion is set-shaped -
    add a key to `serialize_lines` without declaring it and this fails here, at the seam,
    rather than on somebody's screen.
    """
    from app.schemas.projects import ProjectQuotationLineResponse
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)

        emitted = set(quotes.serialize_lines(db, [line])[0].keys())
        declared = set(ProjectQuotationLineResponse.model_fields)

        dropped = sorted(emitted - declared)
        assert not dropped, (
            f"serialize_lines emits {dropped}, which ProjectQuotationLineResponse does not "
            "declare - FastAPI will delete these before the frontend sees them"
        )


def test_a_chosen_photo_survives_the_response_model_and_reaches_the_frontend():
    """The end-to-end shape, through the schema that had been eating it.

    Not a duplicate of the serializer tests: this one validates the payload THROUGH
    `ProjectQuotationLineResponse`, which is what the route actually returns.
    """
    from app.schemas.projects import ProjectQuotationLineResponse
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)

        chosen_file = _attachment(db, env["company_id"], "the-actual-wc.jpg")
        images.choose(db, _link(db, product, chosen_file, sort_order=0))

        payload = quotes.serialize_lines(db, [line])[0]
        modelled = ProjectQuotationLineResponse.model_validate(payload)

        assert modelled.product_image is not None, (
            "the chosen photograph did not survive the response model"
        )
        assert modelled.product_image.state == "chosen"
        assert modelled.product_image.filename == f"{MARKER}-the-actual-wc.jpg"


def test_a_photos_url_is_reused_between_reads_so_the_browser_can_cache_it(monkeypatch):
    """The bucket-traffic guard. This has taken the system down before.

    Signing is a local HMAC and costs nothing, but it produces a DIFFERENT string every time
    because the signature covers a timestamp - and a URL that changes on every render is a URL
    the browser can never serve from its own cache. Every paint of a 52-line table re-fetched
    all 52 photographs from the bucket. Handing back the SAME string inside a window turns
    those into cache hits.

    So the assertion is deliberately about STRING IDENTITY across two independent reads, not
    about how many times `resolve_signed_url` was called: the call is not the expensive part,
    the download it provokes is.
    """
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        photo = _attachment(db, env["company_id"], "wc.jpg")
        images.choose(db, _link(db, product, photo))

        images._url_cache.clear()
        calls: list = []

        def _sign(file_path, *, provider=None, expires_in=3600):
            calls.append(file_path)
            # A fresh signature every time, exactly like the real signer.
            return f"https://signed.zzt.test/x?sig={len(calls)}"

        monkeypatch.setattr(images, "resolve_signed_url", _sign)

        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)

        first = _cell(db, line)
        second = _cell(db, line)

        assert second["url"] == first["url"], "the thumbnail URL changed between two reads"
        assert second["preview_url"] == first["preview_url"], "the preview URL changed"
        # Twice for the first read (thumbnail + original), and nothing at all for the second.
        assert len(calls) == 2, f"re-signed on the second read: {calls}"

        # And the window is not forever: once it lapses, a fresh signature is issued rather
        # than handing out a URL that has expired.
        images._url_cache.clear()
        third = _cell(db, line)
        assert third["url"] != first["url"]


def test_a_product_this_company_cannot_see_is_off_catalog_not_an_invitation():
    """Reported from the screen on 2026-08-09: clicking "No photo on file" opened
    /master-data-management/products/<id>/edit and said "Product not found."

    The line was a Sorento line whose product_id pointed at MOCHA's SRTWC8608-SC - 233 quotation
    lines in live data are in that state, same codes, different company. Everything this resolver
    answered from (`product_attachments`) is a link table and is NOT company-scoped, while
    `Product` is, so the product came back as NO_PHOTOS carrying a product_id and the cell
    rendered a LINK to a page that 404s.

    A product this company cannot see is not a product here, which is exactly OFF_CATALOG, and
    off-catalog cells offer nothing to click.

    The line keeps a REAL product row - `project_quotation_lines_product_id_fkey` means a
    dangling product_id cannot exist, so cross-company invisibility is the only way a line can
    name a product the reader cannot reach. The test has to reproduce that, not a deleted row.
    """
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        product = _product(db, env)
        document = qdocs.create_document(
            db, project=env["project"], actor_user_id=env["owner"]
        )
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=env["owner"]
        )
        line = _priced_line(db, env, scope, product)

        # A second company, and a product that belongs to IT rather than to us.
        other_company = _uid()
        db.execute(
            text(
                "INSERT INTO companies (id, code, name, is_active) "
                "VALUES (:id, :code, :name, true)"
            ),
            {"id": other_company, "code": f"ZZT{_uid()[:5]}", "name": f"{MARKER} Mocha"},
        )
        their_product = _uid()
        db.execute(
            text(
                "INSERT INTO products (id, product_code, product_name, category_id, "
                "base_uom_id, list_price, company_id) "
                "VALUES (:id, :code, :name, :cat, :uom, 300.00, :company)"
            ),
            {
                "id": their_product,
                "code": product.product_code,  # the SAME code, which is the whole trap
                "name": f"{MARKER} their WC Suite",
                "cat": env["category"].id,
                "uom": env["uom"].id,
                "company": other_company,
            },
        )
        # Their product HAS a chosen photograph, so a resolver that ignores company scope would
        # cheerfully hand our reader their picture.
        theirs = _attachment(db, other_company, "their-wc.jpg")
        db.execute(
            text(
                "INSERT INTO product_attachments (id, product_id, attachment_id, is_primary) "
                "VALUES (:id, :pid, :aid, true)"
            ),
            {"id": _uid(), "pid": their_product, "aid": str(theirs.id)},
        )
        # Through the ORM, not raw SQL: `quotation_lines` exists in `public` as well as in
        # `projects` (ADR-0011), so an unqualified UPDATE would hit the wrong table.
        db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == line.id).update(
            {ProjectQuotationLine.product_id: their_product}, synchronize_session=False
        )
        db.flush()
        db.expire_all()
        line = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == line.id).one()

        cell = _cell(db, line)
        assert cell["state"] == "off_catalog", (
            f"got {cell['state']!r}: an unreachable product must not be offered as a link"
        )
        # And emphatically not their photograph.
        assert cell["url"] is None
        assert cell["preview_url"] is None
        assert cell["attachment_id"] is None
        assert cell["candidate_count"] == 0
