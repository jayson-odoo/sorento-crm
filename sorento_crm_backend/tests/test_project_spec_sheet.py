"""PS-SPEC-SHEET tests: the page rules and the print payload of a project spec sheet.

Written from the behaviour card (`documentation/plans/project-sales/CARD-ps-spec-sheet-02nov.md` v2)
and the UAC. SPEC-SHEET-V2 turned the document-level settings into saved sheets
(`projects.quotation_spec_sheets`), so these tests drive the same #2103 rules through a sheet:
`create_sheet` / `update_sheet` / `pages(db, sheet)` / `build_print_payload(db, sheet)`. The
saved-sheet behaviour itself (snapshots, pinned versions, page edits, routes, rights) is in
`test_project_spec_sheets_v2.py`, which imports the seed helpers from this file.

Postgres only via ``blank_session``; every row carries the ``zzt-spec`` marker and the chain is
seeded here (CI's database is empty).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.product import Brand
from app.models.product_set import ProductSet, ProductSetMember

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import (  # noqa: F401  (helpers, not tests)
    _issue,
    _product,
    _setup,
)

MARKER = "zzt-spec"

W, H = 338.7, 190.5


def _uid() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ seed


def _template(db, company_id, family, *, name=None, width=W, height=H, published=True, layers=None):
    """A tag template with a published version, the shape the spec sheet reads."""
    from app.models.dealer_kit import TagTemplate, TagTemplateVersion

    doc = {
        "width_mm": width,
        "height_mm": height,
        "layers": layers
        if layers is not None
        else [
            {
                "id": f"layer-{_uid()[:8]}",
                "type": "text",
                "x_mm": 1,
                "y_mm": 1,
                "width_mm": 50,
                "height_mm": 10,
                "rotation": 0,
                "props": {"kind": "text", "text": "{{product.code}}"},
            }
        ],
    }
    row = TagTemplate(
        id=_uid(),
        company_id=company_id,
        name=name or f"{MARKER} {family}",
        family=family,
        doc=doc,
        print_size={"width_mm": width, "height_mm": height},
    )
    db.add(row)
    db.flush()
    if published:
        version = TagTemplateVersion(
            id=_uid(), template_id=row.id, version_no=1, doc=doc, print_size=row.print_size
        )
        db.add(version)
        db.flush()
        row.published_version_id = version.id
        db.flush()
    return row


def _templates(db, env):
    return {
        "cover": _template(db, env["company_id"], "spec_cover"),
        "page": _template(db, env["company_id"], "spec_page", name=f"{MARKER} with accessories"),
        "single": _template(db, env["company_id"], "spec_page", name=f"{MARKER} single"),
    }


def _brand(db, name):
    row = Brand(id=_uid(), brand_code=f"ZZT{_uid()[:6]}", brand_name=name)
    db.add(row)
    db.flush()
    return row


def _wc_set(db, env):
    """Pedestal (driver: first, one set only), angle valve, flexible hose."""
    token = _uid()[:6].upper()
    pedestal = _product(db, env["category"].id, env["uom"], description=f"{MARKER} pedestal", code=f"ZZTWC{token}")
    valve = _product(db, env["category"].id, env["uom"], description=f"{MARKER} angle valve", code=f"ZZTAV{token}")
    hose = _product(db, env["category"].id, env["uom"], description=f"{MARKER} hose", code=f"ZZTFH{token}")
    row = ProductSet(
        id=_uid(),
        company_id=env["company_id"],
        set_code=f"ZZTSET{token}",
        name=f"{MARKER} WC set {token}",
        is_active=True,
    )
    db.add(row)
    db.flush()
    for order, product in enumerate([pedestal, valve, hose]):
        db.add(
            ProductSetMember(
                id=_uid(),
                product_set_id=row.id,
                product_id=product.id,
                quantity=Decimal("1"),
                contributes_to_price=order == 0,
                sort_order=order,
            )
        )
    db.flush()
    db.refresh(row)
    return row, pedestal, valve, hose


def _line(db, env, scope, payload):
    from app.services import project_quotation_service as quotes

    body = {"unit_price": "100.00", "quantity": 1}
    body.update(payload)
    return quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=env["owner"],
        payload=body,
    )


def _document(db, env, *, your_ref=None):
    from app.services import project_quotation_document_service as qdocs

    document = qdocs.create_document(db, project=env["project"], actor_user_id=env["owner"])
    document.your_ref = your_ref
    document.signatory_name = f"{MARKER} Signer"
    document.signatory_phone = "012-000 0000"
    db.flush()
    return document


def _scope(db, env, document, label="Block A"):
    from app.services import project_quotation_document_service as qdocs

    return qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} {label}", actor_user_id=env["owner"]
    )


def _chain(db, *, your_ref=None):
    """Project, document, one scope with a basin (product line) then a WC set line, issued."""
    env = _setup(db)
    document = _document(db, env, your_ref=your_ref)
    scope = _scope(db, env, document)
    basin = _product(db, env["category"].id, env["uom"], description=f"{MARKER} basin")
    wc_set, pedestal, valve, hose = _wc_set(db, env)
    _line(db, env, scope, {"product_id": basin.id})
    _line(db, env, scope, {"product_set_id": wc_set.id})
    issue = _issue(db, document, env["owner"])
    return {
        **env,
        "document": document,
        "scope": scope,
        "basin": basin,
        "set": wc_set,
        "pedestal": pedestal,
        "valve": valve,
        "hose": hose,
        "issue": issue,
    }


def _codes(pages):
    return [p["code"] for p in pages]


def _sheet(db, c, *, templates=None, rows=None, source=None, single=True, issue=None):
    """A saved spec sheet through the service, optionally with page rows applied."""
    from app.services import project_spec_sheet_service as spec

    t = templates or _templates(db, c)
    sheet = spec.create_sheet(
        db,
        c["document"],
        source=source or (issue or c["issue"]).id,
        cover_template_id=t["cover"].id,
        page_template_id=t["page"].id,
        single_page_template_id=t["single"].id if single else None,
        user_id=c["owner"],
    )
    if rows is not None:
        spec.update_sheet(db, sheet, {"rows": rows})
    return sheet


# ------------------------------------------------------------------ pages (rules 3-5)


def test_one_page_per_item_in_quotation_order_and_a_set_prints_its_driver_with_parts():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        pages = spec.pages(db, _sheet(db, c))

        assert _codes(pages) == [c["basin"].product_code, c["pedestal"].product_code]
        assert pages[0]["key"] == c["basin"].id
        assert pages[1]["key"] == f"set:{c['set'].id}"
        # Set parts other than the driver, in set order, are the accessory rows.
        assert [a["code"] for a in pages[1]["accessories"]] == [
            c["valve"].product_code,
            c["hose"].product_code,
        ]
        assert pages[0]["accessories"] == []


def test_the_spec_sheet_prints_the_issued_revision_not_the_draft():
    from app.services import project_quotation_service as quotes
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        quotes.revise(db, quotation=c["scope"], actor_user_id=c["owner"])
        later = _product(db, c["category"].id, c["uom"], description=f"{MARKER} added later")
        _line(db, c, c["scope"], {"product_id": later.id})

        pages = spec.pages(db, _sheet(db, c))
        assert later.product_code not in _codes(pages)


def test_the_same_product_in_two_scopes_prints_once_at_its_first_position():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        first = _scope(db, env, document, "Block A")
        second = _scope(db, env, document, "Block B")
        basin = _product(db, env["category"].id, env["uom"], description=f"{MARKER} basin")
        tap = _product(db, env["category"].id, env["uom"], description=f"{MARKER} tap")
        first_basin = _line(db, env, first, {"product_id": basin.id})
        _line(db, env, second, {"product_id": tap.id})
        later_basin = _line(db, env, second, {"product_id": basin.id})
        issue = _issue(db, document, env["owner"])
        c = {**env, "document": document, "issue": issue}

        pages = spec.pages(db, _sheet(db, c))
        assert _codes(pages) == [basin.product_code, tap.product_code]
        # The page is the FIRST line's, frozen media and all, not the repeat's.
        assert pages[0]["line_id"] != later_basin.id
        from app.models.projects import ProjectQuotationIssueScope, ProjectQuotationLine

        first_scope_version = (
            db.query(ProjectQuotationIssueScope)
            .filter(
                ProjectQuotationIssueScope.issue_id == issue.id,
                ProjectQuotationIssueScope.quotation_id == first.id,
            )
            .one()
            .version_id
        )
        assert (
            db.get(ProjectQuotationLine, pages[0]["line_id"]).version_id == first_scope_version
        )
        assert first_basin is not None


def test_the_newest_issue_leads_the_sources_and_a_document_without_lines_refuses_a_sheet():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        assert spec.sources(db, c["document"])[0]["value"] == c["issue"].id

        unissued = _document(db, c)
        _scope(db, c, unissued)
        t = _templates(db, c)
        with pytest.raises(AppException) as raised:
            spec.create_sheet(
                db,
                unissued,
                source="draft",
                cover_template_id=t["cover"].id,
                page_template_id=t["page"].id,
                user_id=c["owner"],
            )
        assert raised.value.code == "spec_sheet_no_lines"


# ------------------------------------------------------------------ rows (rules 4a, 12, 13)


def test_saved_order_area_comment_marker_and_hide_apply_and_new_items_append():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        set_key = f"set:{c['set'].id}"
        spec.update_sheet(
            db,
            sheet,
            {
                "rows": [
                    {"key": set_key, "area": "Unit & podium", "comment": "Soft close", "marker": "**"},
                    {"key": "set:not-on-this-revision", "area": "ignored"},
                ]
            },
        )
        pages = spec.pages(db, sheet)

        assert [p["key"] for p in pages] == [set_key, c["basin"].id]
        assert pages[0]["area"] == "Unit & podium"
        assert pages[0]["comment"] == "Soft close"
        assert pages[0]["marker"] == "**"
        assert pages[1]["area"] == "" and pages[1]["hidden"] is False

        spec.update_sheet(db, sheet, {"rows": [{"key": c["basin"].id, "hidden": True}]})
        pages = spec.pages(db, sheet)
        assert next(p for p in pages if p["key"] == c["basin"].id)["hidden"] is True


def test_a_hand_picked_accessory_leaves_its_own_page_and_prints_after_the_set_parts():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        set_key = f"set:{c['set'].id}"
        sheet = _sheet(db, c, rows=[{"key": set_key, "accessories": [c["basin"].id]}])
        pages = spec.pages(db, sheet)

        assert [p["key"] for p in pages] == [set_key]
        assert [a["code"] for a in pages[0]["accessories"]] == [
            c["valve"].product_code,
            c["hose"].product_code,
            c["basin"].product_code,
        ]


@pytest.mark.parametrize("case", ["self", "nested", "duplicate"])
def test_accessory_picks_that_cannot_print_are_refused(case):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        set_key = f"set:{c['set'].id}"
        basin = c["basin"].id
        rows = {
            "self": [{"key": set_key, "accessories": [set_key]}],
            # The picked basin cannot itself host accessories: one level only.
            "nested": [
                {"key": set_key, "accessories": [basin]},
                {"key": basin, "accessories": [set_key]},
            ],
            "duplicate": [{"key": set_key}, {"key": set_key}],
        }[case]
        with pytest.raises(AppException) as raised:
            spec.update_sheet(db, sheet, {"rows": rows})
        assert raised.value.status_code == 422
        assert raised.value.code == "spec_sheet_rows_invalid"


def test_templates_must_be_published_spec_templates_of_the_right_family():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        price_tag = _template(db, c["company_id"], "wc")
        draft = _template(db, c["company_id"], "spec_cover", published=False)

        saved = _sheet(db, c, templates=t)
        assert saved.cover_template_id == t["cover"].id

        good = {
            "cover_template_id": t["cover"].id,
            "page_template_id": t["page"].id,
            "single_page_template_id": t["single"].id,
        }
        for bad in (
            {"cover_template_id": t["page"].id},
            {"page_template_id": t["cover"].id},
            {"page_template_id": price_tag.id},
            {"cover_template_id": draft.id},
        ):
            with pytest.raises(AppException) as raised:
                spec.create_sheet(
                    db, c["document"], source=c["issue"].id, user_id=c["owner"], **{**good, **bad}
                )
            assert raised.value.status_code == 422
            assert raised.value.code == "spec_sheet_template_invalid"


def test_rows_persist_on_the_sheet():
    from app.models.projects import ProjectQuotationSpecSheet
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        spec.update_sheet(db, sheet, {"rows": [{"key": c["basin"].id, "area": "Pantry"}]})
        db.expire_all()
        stored = db.get(ProjectQuotationSpecSheet, sheet.id).rows
        assert stored[0] == {
            "key": c["basin"].id,
            "area": "Pantry",
            "comment": "",
            "marker": "",
            "hidden": False,
            "accessories": [],
        }


# ------------------------------------------------------------------ print payload (rules 6-11)


def test_the_payload_is_a_cover_sheet_then_one_full_page_sheet_per_visible_item():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        payload = spec.build_print_payload(db, _sheet(db, c, templates=t))
        doc = payload["doc"]

        assert doc["kind"] == "tag_sheet"
        assert doc["imposition"]["page_width_mm"] == W
        assert doc["imposition"]["page_height_mm"] == H
        assert doc["imposition"]["bleed_mm"] == 0
        assert payload["page_size"] == {"width_mm": W, "height_mm": H}

        sheets = doc["sheets"]
        assert len(sheets) == 3
        placed = [s["tags"][0] for s in sheets]
        assert all(len(s["tags"]) == 1 for s in sheets)
        assert all((p["x_mm"], p["y_mm"], p["width_mm"], p["height_mm"]) == (0, 0, W, H) for p in placed)
        # Cover, then the basin (no accessories -> single item), then the set (accessories -> page).
        assert [p["template_id"] for p in placed] == [t["cover"].id, t["single"].id, t["page"].id]
        assert placed[0]["layers"] == t["cover"].published_version.doc["layers"]
        assert [p["request_tag_id"] for p in placed] == [
            "cover",
            c["basin"].id,
            f"set:{c['set'].id}",
        ]
        assert set(payload["resolvedData"]) == {"cover", c["basin"].id, f"set:{c['set'].id}"}


def test_without_a_single_item_template_every_page_uses_the_page_template_and_hidden_pages_drop():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        sheet = _sheet(db, c, templates=t, single=False, rows=[{"key": c["basin"].id, "hidden": True}])
        sheets = spec.build_print_payload(db, sheet)["doc"]["sheets"]
        assert [s["tags"][0]["template_id"] for s in sheets] == [t["cover"].id, t["page"].id]


def test_resolved_rows_carry_product_parts_document_and_line_fields_and_the_quoted_price():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db, your_ref=f"{MARKER}/QS/2026/7")
        brand = _brand(db, "SORENTO")
        c["pedestal"].brand_id = brand.id
        c["pedestal"].product_name = f"{MARKER} Wall hung WC"
        db.flush()
        set_key = f"set:{c['set'].id}"
        sheet = _sheet(
            db,
            c,
            rows=[{"key": set_key, "area": "unit & podium", "comment": "c1", "marker": "*"}],
        )
        data = spec.build_print_payload(db, sheet)["resolvedData"]
        row = data[set_key]

        assert row["tag_id"] == set_key
        assert row["code"] == c["pedestal"].product_code
        assert row["name"] == f"{MARKER} Wall hung WC"
        assert row["brand"] == "SORENTO"
        assert [p["code"] for p in row["parts"]] == [c["valve"].product_code, c["hose"].product_code]
        assert row["own_parts"] == row["parts"]
        assert row["strict_parts"] is True
        # Owner Q-B: the quoted unit price, in the field a price tag's List Price slot reads;
        # set parts carry none (the set line carries it); no promotion; the cover has none.
        assert row["list_price"] == 100.0 and row["parent_list_price"] == 100.0
        assert row["sell_price"] is None and row["show_promo_price"] is False
        assert all(p["list_price"] is None for p in row["parts"])
        assert data["cover"]["list_price"] is None
        assert row["area"] == "UNIT & PODIUM"
        assert row["comment"] == "c1"
        assert row["marker"] == "*"

        doc = row["doc"]
        assert doc == data["cover"]["doc"]
        assert doc["project_title"] == c["project"].title
        assert doc["your_ref"] == f"{MARKER}/QS/2026/7"
        assert doc["ref"] == f"{MARKER}/QS/2026/7"
        from app.services.project_quotation_document_service import quotation_no

        assert doc["quotation_no"] == quotation_no(
            c["document"].document_no, c["issue"].issue_no, c["issue"].revision_label
        )
        assert doc["prepared_by"] == f"{MARKER} Signer"
        assert doc["prepared_by_phone"] == "012-000 0000"
        # No doc date on this quotation: the issue date.
        assert doc["date"] == c["issue"].issued_at.strftime("%d %b %Y").upper()

        import datetime

        # A date that cannot be the issue date, so the two sources are told apart.
        c["document"].doc_date = datetime.date(2020, 1, 15)
        db.flush()
        dated = spec.build_print_payload(db, sheet)["resolvedData"]["cover"]
        # The quotation's own date wins, as on its PDF and cover page.
        assert dated["doc"]["date"] == "15 JAN 2020"


def test_ref_falls_back_to_the_quotation_number_when_your_ref_is_blank():
    from app.services import project_spec_sheet_service as spec
    from app.services.project_quotation_document_service import quotation_no

    with blank_session() as db:
        c = _chain(db)
        doc = spec.build_print_payload(db, _sheet(db, c))["resolvedData"]["cover"]["doc"]
        assert doc["your_ref"] == ""
        assert doc["ref"] == quotation_no(
            c["document"].document_no, c["issue"].issue_no, c["issue"].revision_label
        )


def test_the_line_frozen_drawing_and_photo_reach_the_row_and_the_signed_image_map(monkeypatch):
    from app.models.projects import ProjectQuotationLine
    from app.services import project_spec_sheet_service as spec

    from .test_project_quotation_pdf import _attachment

    with blank_session() as db:
        c = _chain(db)
        photo = _attachment(db, c["company_id"], "basin.png")
        drawing = _attachment(db, c["company_id"], "basin-drawing.png")
        line = (
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.product_id == c["basin"].id)
            .one()
        )
        line.image_attachment_id = photo.id
        line.drawing_attachment_id = drawing.id
        db.flush()
        monkeypatch.setattr(
            spec,
            "_sign",
            lambda db, ids, full=False: {i: f"https://signed.zzt.test/{i}" for i in ids if i},
        )
        payload = spec.build_print_payload(db, _sheet(db, c))
        row = payload["resolvedData"][c["basin"].id]

        assert row["images"][0]["attachment_id"] == photo.id
        assert row["drawing"]["attachment_id"] == drawing.id
        assert payload["images"][photo.id] == f"https://signed.zzt.test/{photo.id}"
        assert payload["images"][drawing.id] == f"https://signed.zzt.test/{drawing.id}"


def test_create_refuses_without_templates_and_with_a_page_template_of_another_size():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        with pytest.raises(AppException) as raised:
            spec.create_sheet(
                db, c["document"], source=c["issue"].id, cover_template_id=None, page_template_id=None
            )
        assert raised.value.status_code == 422
        assert raised.value.code == "spec_sheet_templates_missing"

        cover = _template(db, c["company_id"], "spec_cover")
        a4 = _template(db, c["company_id"], "spec_page", width=297, height=210)
        with pytest.raises(AppException) as raised:
            spec.create_sheet(
                db,
                c["document"],
                source=c["issue"].id,
                cover_template_id=cover.id,
                page_template_id=a4.id,
            )
        assert raised.value.status_code == 422
        assert raised.value.code == "spec_sheet_size_mismatch"


# ------------------------------------------------------------------ export + print route (rule 14)


def test_request_export_creates_a_download_and_queues_the_render(monkeypatch):
    from app.models.download import DownloadStatus
    from app.services import project_spec_sheet_service as spec

    calls = []
    monkeypatch.setattr(
        "app.services.queue_service.enqueue_job",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        download = spec.request_export(db, sheet, user_id=c["owner"])

        assert download.kind == spec.KIND == "quotation_spec_sheet_pdf"
        assert download.source_entity_type == "quotation_spec_sheet"
        assert download.source_entity_id == sheet.id
        assert download.status == DownloadStatus.PENDING.value
        assert download.filename.startswith("spec-sheet-") and download.filename.endswith("-SS1.pdf")
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[1] == str(download.id)
        assert kwargs["queue_name"] == "catalogue_render"


def test_the_public_print_payload_answers_a_spec_sheet_download():
    from app.models.download import UserDownload
    from app.services import project_spec_sheet_service as spec
    from app.services.dealer_kit.tag_sheet_export_service import resolve_tag_sheet_print_payload

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        download = UserDownload(
            user_id=c["owner"],
            kind=spec.KIND,
            source_entity_type="quotation_spec_sheet",
            source_entity_id=sheet.id,
            status="pending",
            filename="spec-sheet-x.pdf",
        )
        db.add(download)
        db.flush()

        payload = resolve_tag_sheet_print_payload(db, str(download.id))
        assert len(payload["doc"]["sheets"]) == 3
        assert "cover" in payload["resolvedData"]



def test_the_render_cli_takes_a_custom_page_size_and_tag_sheets_stay_a4(monkeypatch):
    """Kill test for the price tag path: its command must not gain a size."""
    from app.tasks import dealer_kit_export_tasks as tasks

    commands = []

    class _Done:
        returncode = 0
        stderr = ""

    def fake_run(command, **kwargs):
        commands.append(command)
        out = command[command.index("app.tasks.catalogue_render_cli") + 2]
        with open(out, "wb") as handle:
            handle.write(b"%PDF-zzt")
        return _Done()

    monkeypatch.setattr("subprocess.run", fake_run)
    tasks._render_pdf("http://x/a", landscape=False, paper="A4")
    tasks._render_pdf("http://x/b", landscape=False, paper="A4", size_mm=(W, H))

    a4, custom = commands
    assert "--width-mm" not in a4 and "--paper" in a4
    assert custom[custom.index("--width-mm") + 1] == str(W)
    assert custom[custom.index("--height-mm") + 1] == str(H)


def test_the_render_cli_passes_width_and_height_to_chromium():
    from app.tasks import catalogue_render_cli as cli

    assert cli.pdf_options(paper="A4", landscape=False, size_mm=None)["format"] == "A4"
    custom = cli.pdf_options(paper="A4", landscape=False, size_mm=(W, H))
    assert "format" not in custom
    assert custom["width"] == f"{W}mm" and custom["height"] == f"{H}mm"


# ------------------------------------------------------------------ spec registry (Q5)


def test_accessible_is_a_yes_no_spec_beside_rimless():
    """Q5 (a): the accessible badge reads a spec key, like Rimless, filled in master data."""
    from app.services.product_spec_registry import SPEC_REGISTRY_SEED

    keys = [entry["spec_key"] for entry in SPEC_REGISTRY_SEED]
    entry = next(e for e in SPEC_REGISTRY_SEED if e["spec_key"] == "is_accessible")
    assert entry["data_type"] == "boolean"
    assert entry["label"] == "Accessible (OKU)"
    assert keys.index("is_accessible") == keys.index("is_rimless") + 1


# ------------------------------------------------------------------ routes (rule 15)

ROUTE_SLUGS = ["projects.projects.view", "projects.projects.edit", "projects.projects.manage"]


def _client(db, user_id, slugs=ROUTE_SLUGS):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in slugs
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(slugs)
    return TestClient(app), originals


def _restore(originals):
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _url(c, suffix=""):
    return (
        f"/api/v1/project-sales/projects/{c['project'].id}/quotation-documents/"
        f"{c['document'].id}/spec-sheets{suffix}"
    )



# ------------------------------------------------------------------ routes (rule 15)


def test_routes_list_create_patch_preview_and_export(monkeypatch):
    queued = []
    monkeypatch.setattr(
        "app.services.queue_service.enqueue_job", lambda *a, **k: queued.append((a, k))
    )
    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        client, originals = _client(db, c["owner"])
        try:
            got = client.get(_url(c))
            assert got.status_code == 200, got.text
            body = got.json()
            assert body["items"] == []
            assert [s["value"] for s in body["sources"]] == [c["issue"].id]
            assert {t["cover"].id} <= {row["id"] for row in body["templates"]["cover"]}
            assert {t["page"].id, t["single"].id} <= {row["id"] for row in body["templates"]["page"]}

            made = client.post(
                _url(c),
                json={
                    "source": c["issue"].id,
                    "cover_template_id": t["cover"].id,
                    "page_template_id": t["page"].id,
                },
            )
            assert made.status_code == 201, made.text
            sheet_id = made.json()["id"]
            assert [p["code"] for p in made.json()["pages"][1:]] == [
                c["basin"].product_code,
                c["pedestal"].product_code,
            ]

            patched = client.patch(
                _url(c, f"/{sheet_id}"), json={"rows": [{"key": c["basin"].id, "area": "Pantry"}]}
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["pages"][1]["area"] == "Pantry"

            preview = client.get(_url(c, f"/{sheet_id}/preview"), params={"key": "cover"})
            assert preview.status_code == 200, preview.text
            assert len(preview.json()["doc"]["sheets"]) == 1

            exported = client.post(_url(c, f"/{sheet_id}/export"))
            assert exported.status_code == 200, exported.text
            assert exported.json()["kind"] == "quotation_spec_sheet_pdf"
            assert len(queued) == 1

            bad = client.post(
                _url(c),
                json={
                    "source": c["issue"].id,
                    "cover_template_id": t["page"].id,
                    "page_template_id": t["page"].id,
                },
            )
            assert bad.status_code == 422
            assert bad.json().get("code") == "spec_sheet_template_invalid"
        finally:
            _restore(originals)


def test_saving_needs_the_edit_right_and_reading_does_not():
    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        client, originals = _client(db, c["owner"], slugs=["projects.projects.view"])
        try:
            assert client.get(_url(c)).status_code == 200
            assert client.get(_url(c, f"/{sheet.id}")).status_code == 200
            assert client.patch(_url(c, f"/{sheet.id}"), json={"rows": []}).status_code == 403
        finally:
            _restore(originals)


def test_a_revision_of_another_document_is_refused():
    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        client, originals = _client(db, c["owner"])
        try:
            other = client.post(
                _url(c),
                json={
                    "source": str(uuid.uuid4()),
                    "cover_template_id": t["cover"].id,
                    "page_template_id": t["page"].id,
                },
            )
            assert other.status_code == 422
            assert other.json().get("code") == "spec_sheet_issue_invalid"
        finally:
            _restore(originals)


# ------------------------------------------------------------------ review round 1


def test_saving_rows_keeps_stored_rows_the_tab_does_not_show():
    """An absorbed item's (or another revision's item's) stored Area must survive a save of the
    rows the tab shows."""
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        set_key = f"set:{c['set'].id}"
        basin = c["basin"].id
        spec.update_sheet(
            db,
            sheet,
            {"rows": [{"key": basin, "area": "Pantry"}, {"key": "set:from-r2", "area": "Guard house"}]},
        )
        # The basin goes under the WC; the tab then shows (and saves) the WC row only.
        spec.update_sheet(db, sheet, {"rows": [{"key": set_key, "accessories": [basin]}]})
        spec.update_sheet(db, sheet, {"rows": [{"key": set_key, "area": "Unit"}]})

        stored = {r["key"]: r for r in sheet.rows}
        assert stored[basin]["area"] == "Pantry"
        assert stored["set:from-r2"]["area"] == "Guard house"
        assert stored[set_key]["area"] == "Unit"
        # Unpicked again: the basin's page comes back with its Area.
        pages = {p["key"]: p for p in spec.pages(db, sheet)}
        assert pages[basin]["area"] == "Pantry"


@pytest.mark.parametrize(
    "body,code",
    [
        ({"cover_template_id": "not-a-uuid"}, "spec_sheet_template_invalid"),
        ({"page_template_id": "1; drop"}, "spec_sheet_template_invalid"),
        ({"source": "nope"}, "spec_sheet_issue_invalid"),
    ],
)
def test_malformed_ids_are_a_422_not_a_500(body, code):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        args = {
            "source": c["issue"].id,
            "cover_template_id": t["cover"].id,
            "page_template_id": t["page"].id,
            "user_id": c["owner"],
        }
        with pytest.raises(AppException) as raised:
            spec.create_sheet(db, c["document"], **{**args, **body})
        assert raised.value.status_code == 422
        assert raised.value.code == code


@pytest.mark.parametrize("size", [(0, 190.5), (338.7, -5), (1e9, 190.5)])
def test_a_template_page_size_chromium_cannot_print_is_refused(size):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        cover = _template(db, c["company_id"], "spec_cover", width=size[0], height=size[1])
        page = _template(db, c["company_id"], "spec_page", width=size[0], height=size[1])
        with pytest.raises(AppException) as raised:
            spec.create_sheet(
                db,
                c["document"],
                source=c["issue"].id,
                cover_template_id=cover.id,
                page_template_id=page.id,
            )
        assert raised.value.status_code == 422
        assert raised.value.code == "spec_sheet_size_invalid"


def test_the_layer_schema_accepts_the_drawing_slot_and_show_when():
    from app.schemas.price_tag import TagLayerDoc

    layer = TagLayerDoc.model_validate(
        {
            "id": "l1",
            "type": "image",
            "x_mm": 0,
            "y_mm": 0,
            "width_mm": 10,
            "height_mm": 10,
            "z_index": 0,
            "slot_binding": "drawing",
            "props": {"kind": "image", "source": None, "fit": "contain", "maskShape": "none"},
            "show_when": {"part": 1, "spec": "is_rimless"},
        }
    )
    assert layer.slot_binding == "drawing"
    assert layer.show_when.part == 1 and layer.show_when.spec == "is_rimless"



def test_a_spec_sheet_download_on_a_document_without_a_company_fails_closed(monkeypatch):
    """The public print route must never read a payload with no company filter."""
    from app.models.download import UserDownload
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _sheet(db, c)
        download = UserDownload(
            user_id=c["owner"],
            kind=spec.KIND,
            source_entity_type="quotation_spec_sheet",
            source_entity_id=sheet.id,
            status="pending",
            filename="spec-sheet-x.pdf",
        )
        db.add(download)
        db.flush()

        class _NoCompany:
            company_id = None

        monkeypatch.setattr(spec, "source_of_download", lambda db, dl: (_NoCompany(), sheet))
        for call in (spec.print_payload_for_download, spec.page_size_for_download):
            with pytest.raises(AppException) as raised:
                call(db, download)
            assert raised.value.status_code == 404


def test_a_hand_picked_accessory_carries_its_own_quoted_price_and_the_page_view_shows_none():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        set_key = f"set:{c['set'].id}"
        sheet = _sheet(db, c, rows=[{"key": set_key, "accessories": [c["basin"].id]}])
        row = spec.build_print_payload(db, sheet)["resolvedData"][set_key]
        assert [p["list_price"] for p in row["parts"]] == [None, None, 100.0]

        for page in spec.pages(db, sheet):
            shown = spec._public(page)
            assert not any(k.startswith("_") for k in shown)
            assert all(not any(k.startswith("_") for k in a) for a in shown["accessories"])


def test_a_zero_priced_line_carries_no_price_and_the_detail_route_never_returns_one():
    """B3: zero = no separate charge, printed blank (as the quotation PDF). B4: the GET route's
    page list carries no price at any depth."""
    import json

    from app.services import project_quotation_service as quotes
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        # A component quoted at zero after its parent, picked under the WC.
        hose = _product(db, c["category"].id, c["uom"], description=f"{MARKER} spare hose")
        quotes.revise(db, quotation=c["scope"], actor_user_id=c["owner"])
        _line(db, c, c["scope"], {"product_id": hose.id, "unit_price": "0"})
        issue = _issue(db, c["document"], c["owner"])
        set_key = f"set:{c['set'].id}"
        sheet = _sheet(
            db, c, issue=issue, rows=[{"key": set_key, "accessories": [hose.id, c["basin"].id]}]
        )
        row = spec.build_print_payload(db, sheet)["resolvedData"][set_key]
        assert [p["list_price"] for p in row["parts"]] == [None, None, None, 100.0]

        client, originals = _client(db, c["owner"])
        try:
            got = client.get(_url(c, f"/{sheet.id}"))
            assert got.status_code == 200, got.text
            pages = got.json()["pages"]
            assert pages, "the page list is not empty"

            def keys(value):
                if isinstance(value, dict):
                    for k, v in value.items():
                        yield k
                        yield from keys(v)
                elif isinstance(value, list):
                    for v in value:
                        yield from keys(v)

            assert not [k for k in keys(pages) if k.startswith("_")]
            assert "_price" not in json.dumps(got.json())
        finally:
            _restore(originals)


def test_area_defaults_to_the_section_heading_the_line_sits_under_and_a_typed_area_wins():
    """Owner, mock v5: one rule. The page's AREA is the quotation's Section heading over the line
    (it does not run into the next scope); typing on the page overrides it."""
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        first = _scope(db, env, document, "Block A")
        second = _scope(db, env, document, "Block B")
        wc = _product(db, env["category"].id, env["uom"], description=f"{MARKER} wc")
        basin = _product(db, env["category"].id, env["uom"], description=f"{MARKER} basin")
        tap = _product(db, env["category"].id, env["uom"], description=f"{MARKER} tap")
        trap = _product(db, env["category"].id, env["uom"], description=f"{MARKER} trap")
        _line(db, env, first, {"product_id": wc.id, "band_label": "UNIT"})
        _line(db, env, first, {"product_id": basin.id})
        _line(db, env, first, {"product_id": tap.id, "band_label": "PANTRY (TYPE A)"})
        _line(db, env, second, {"product_id": trap.id})
        issue = _issue(db, document, env["owner"])
        sheet = _sheet(db, {**env, "document": document, "issue": issue})

        pages = {p["key"]: p for p in spec.pages(db, sheet)}
        assert pages[wc.id]["area"] == "UNIT"
        assert pages[basin.id]["area"] == "UNIT"
        assert pages[tap.id]["area"] == "PANTRY (TYPE A)"
        assert pages[trap.id]["area"] == ""  # a new scope starts with no heading
        assert pages[basin.id]["area_default"] == "UNIT"

        spec.update_sheet(db, sheet, {"rows": [{"key": basin.id, "area": "Guard house"}]})
        pages = {p["key"]: p for p in spec.pages(db, sheet)}
        assert pages[basin.id]["area"] == "Guard house"
        assert pages[basin.id]["area_default"] == "UNIT"
