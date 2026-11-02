"""PS-SPEC-SHEET red tests: the project spec sheet built from an issued quotation revision.

Written BEFORE the implementation, from the behaviour card
(`documentation/plans/project-sales/CARD-ps-spec-sheet-02nov.md` v2) and the UAC. The new module is
imported inside each test so every test fails on its own, not as one collection error.

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


# ------------------------------------------------------------------ pages (rules 3-5)


def test_one_page_per_item_in_quotation_order_and_a_set_prints_its_driver_with_parts():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        pages = spec.pages(db, c["document"], c["issue"])

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

        pages = spec.pages(db, c["document"], c["issue"])
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
        _line(db, env, first, {"product_id": basin.id})
        _line(db, env, second, {"product_id": tap.id})
        _line(db, env, second, {"product_id": basin.id})
        issue = _issue(db, document, env["owner"])

        assert _codes(spec.pages(db, document, issue)) == [basin.product_code, tap.product_code]


def test_latest_issue_is_the_default_and_no_issue_means_no_pages():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        assert spec.issue_for(db, document) is None

        c = _chain(db)
        assert spec.issue_for(db, c["document"]).id == c["issue"].id


# ------------------------------------------------------------------ settings (rules 4a, 12, 13)


def test_saved_order_area_comment_marker_and_hide_apply_and_new_items_append():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        set_key = f"set:{c['set'].id}"
        spec.save_settings(
            db,
            c["document"],
            {
                "rows": [
                    {"key": set_key, "area": "Unit & podium", "comment": "Soft close", "marker": "**"},
                    {"key": "set:not-on-this-revision", "area": "ignored"},
                ]
            },
        )
        pages = spec.pages(db, c["document"], c["issue"])

        assert [p["key"] for p in pages] == [set_key, c["basin"].id]
        assert pages[0]["area"] == "Unit & podium"
        assert pages[0]["comment"] == "Soft close"
        assert pages[0]["marker"] == "**"
        assert pages[1]["area"] == "" and pages[1]["hidden"] is False

        spec.save_settings(db, c["document"], {"rows": [{"key": c["basin"].id, "hidden": True}]})
        pages = spec.pages(db, c["document"], c["issue"])
        assert next(p for p in pages if p["key"] == c["basin"].id)["hidden"] is True


def test_a_hand_picked_accessory_leaves_its_own_page_and_prints_after_the_set_parts():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        set_key = f"set:{c['set'].id}"
        spec.save_settings(
            db, c["document"], {"rows": [{"key": set_key, "accessories": [c["basin"].id]}]}
        )
        pages = spec.pages(db, c["document"], c["issue"])

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
            spec.save_settings(db, c["document"], {"rows": rows})
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

        saved = spec.save_settings(
            db,
            c["document"],
            {
                "cover_template_id": t["cover"].id,
                "page_template_id": t["page"].id,
                "single_page_template_id": t["single"].id,
            },
        )
        assert saved["cover_template_id"] == t["cover"].id

        for bad in (
            {"cover_template_id": t["page"].id},
            {"page_template_id": t["cover"].id},
            {"page_template_id": price_tag.id},
            {"cover_template_id": draft.id},
        ):
            with pytest.raises(AppException) as raised:
                spec.save_settings(db, c["document"], bad)
            assert raised.value.status_code == 422
            assert raised.value.code == "spec_sheet_template_invalid"


def test_settings_persist_on_the_document():
    from app.models.projects import ProjectQuotationDocument
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        spec.save_settings(db, c["document"], {"rows": [{"key": c["basin"].id, "area": "Pantry"}]})
        db.expire_all()
        stored = db.get(ProjectQuotationDocument, c["document"].id).spec_sheet
        assert stored["rows"][0] == {
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
        spec.save_settings(
            db,
            c["document"],
            {
                "cover_template_id": t["cover"].id,
                "page_template_id": t["page"].id,
                "single_page_template_id": t["single"].id,
            },
        )
        payload = spec.build_print_payload(db, c["document"], c["issue"])
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
        spec.save_settings(
            db,
            c["document"],
            {
                "cover_template_id": t["cover"].id,
                "page_template_id": t["page"].id,
                "rows": [{"key": c["basin"].id, "hidden": True}],
            },
        )
        sheets = spec.build_print_payload(db, c["document"], c["issue"])["doc"]["sheets"]
        assert [s["tags"][0]["template_id"] for s in sheets] == [t["cover"].id, t["page"].id]


def test_resolved_rows_carry_product_parts_document_and_line_fields_and_no_price():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db, your_ref=f"{MARKER}/QS/2026/7")
        brand = _brand(db, "SORENTO")
        c["pedestal"].brand_id = brand.id
        c["pedestal"].product_name = f"{MARKER} Wall hung WC"
        db.flush()
        t = _templates(db, c)
        set_key = f"set:{c['set'].id}"
        spec.save_settings(
            db,
            c["document"],
            {
                "cover_template_id": t["cover"].id,
                "page_template_id": t["page"].id,
                "rows": [{"key": set_key, "area": "unit & podium", "comment": "c1", "marker": "*"}],
            },
        )
        data = spec.build_print_payload(db, c["document"], c["issue"])["resolvedData"]
        row = data[set_key]

        assert row["tag_id"] == set_key
        assert row["code"] == c["pedestal"].product_code
        assert row["name"] == f"{MARKER} Wall hung WC"
        assert row["brand"] == "SORENTO"
        assert [p["code"] for p in row["parts"]] == [c["valve"].product_code, c["hose"].product_code]
        assert row["own_parts"] == row["parts"]
        assert row["strict_parts"] is True
        assert row["list_price"] is None and row["sell_price"] is None
        assert row["show_promo_price"] is False
        assert row["area"] == "UNIT & PODIUM"
        assert row["comment"] == "c1"
        assert row["marker"] == "*"

        doc = row["doc"]
        assert doc == data["cover"]["doc"]
        assert doc["project_title"] == c["project"].title
        assert doc["your_ref"] == f"{MARKER}/QS/2026/7"
        assert doc["ref"] == f"{MARKER}/QS/2026/7"
        from app.services.project_quotation_document_service import quotation_no

        assert doc["quotation_no"] == quotation_no(c["document"].document_no, c["issue"].issue_no)
        assert doc["prepared_by"] == f"{MARKER} Signer"
        assert doc["prepared_by_phone"] == "012-000 0000"
        assert doc["date"] == c["issue"].issued_at.strftime("%d %b %Y").upper()


def test_ref_falls_back_to_the_quotation_number_when_your_ref_is_blank():
    from app.services import project_spec_sheet_service as spec
    from app.services.project_quotation_document_service import quotation_no

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        spec.save_settings(
            db, c["document"], {"cover_template_id": t["cover"].id, "page_template_id": t["page"].id}
        )
        doc = spec.build_print_payload(db, c["document"], c["issue"])["resolvedData"]["cover"]["doc"]
        assert doc["your_ref"] == ""
        assert doc["ref"] == quotation_no(c["document"].document_no, c["issue"].issue_no)


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
            spec, "_sign", lambda db, ids: {i: f"https://signed.zzt.test/{i}" for i in ids if i}
        )
        t = _templates(db, c)
        spec.save_settings(
            db, c["document"], {"cover_template_id": t["cover"].id, "page_template_id": t["page"].id}
        )
        payload = spec.build_print_payload(db, c["document"], c["issue"])
        row = payload["resolvedData"][c["basin"].id]

        assert row["images"][0]["attachment_id"] == photo.id
        assert row["drawing"]["attachment_id"] == drawing.id
        assert payload["images"][photo.id] == f"https://signed.zzt.test/{photo.id}"
        assert payload["images"][drawing.id] == f"https://signed.zzt.test/{drawing.id}"


def test_export_refuses_without_templates_and_with_a_page_template_of_another_size():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        with pytest.raises(AppException) as raised:
            spec.build_print_payload(db, c["document"], c["issue"])
        assert raised.value.status_code == 422
        assert raised.value.code == "spec_sheet_templates_missing"

        cover = _template(db, c["company_id"], "spec_cover")
        a4 = _template(db, c["company_id"], "spec_page", width=297, height=210)
        spec.save_settings(
            db, c["document"], {"cover_template_id": cover.id, "page_template_id": a4.id}
        )
        with pytest.raises(AppException) as raised:
            spec.build_print_payload(db, c["document"], c["issue"])
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
        t = _templates(db, c)
        spec.save_settings(
            db, c["document"], {"cover_template_id": t["cover"].id, "page_template_id": t["page"].id}
        )
        download = spec.request_export(db, c["document"], c["issue"], user_id=c["owner"])

        assert download.kind == spec.KIND == "quotation_spec_sheet_pdf"
        assert download.source_entity_type == "quotation_issue"
        assert download.source_entity_id == c["issue"].id
        assert download.status == DownloadStatus.PENDING.value
        assert download.filename.startswith("spec-sheet-") and download.filename.endswith(".pdf")
        assert "/" not in download.filename
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[1] == str(download.id)
        assert kwargs["queue_name"] == "catalogue_render"


def test_the_public_print_payload_answers_a_spec_sheet_download():
    from app.services import project_spec_sheet_service as spec
    from app.services.dealer_kit.tag_sheet_export_service import resolve_tag_sheet_print_payload

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        spec.save_settings(
            db, c["document"], {"cover_template_id": t["cover"].id, "page_template_id": t["page"].id}
        )
        from app.models.download import UserDownload

        download = UserDownload(
            user_id=c["owner"],
            kind=spec.KIND,
            source_entity_type="quotation_issue",
            source_entity_id=c["issue"].id,
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
