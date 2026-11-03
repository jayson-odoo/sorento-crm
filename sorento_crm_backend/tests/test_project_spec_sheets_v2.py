"""SPEC-SHEET-V2 red tests: saved spec sheets (table `projects.quotation_spec_sheets`).

Written BEFORE the implementation, from `documentation/plans/project-sales/PLAN-spec-sheet-v2-03nov.md`
(Contract + Red test list items 1-14) and the UAC. Numbers in test names follow the red list.

The service module, the model `ProjectQuotationSpecSheet`, the routes and the migration do not
exist yet. Every app import is done INSIDE its test so each test fails on its own, at the first
call into the not-yet-built code, not as one collection error.

Postgres only via ``blank_session``; every chain is seeded here (CI's database is empty).

Names this file pins down for the coder (all from the plan contract):
  model        app.models.projects.ProjectQuotationSpecSheet
  service      app.services.project_spec_sheet_service: snapshot_items, pages(db, sheet), sources,
               create_sheet, update_sheet, save_page_edit, reset_page_edit, build_print_payload,
               request_export(db, sheet, user_id), source_of_download(db, download) -> (document, sheet),
               print_payload_for_download, page_size_for_download
  migration    alembic/versions/ssv2_0001_spec_sheets.py exposing backfill(connection)
  routes       /api/v1/project-sales/projects/{p}/quotation-documents/{d}/spec-sheets[...]
  actions      quotation_spec_sheet.delete, quotation_spec_sheet.reset_page (entity_type
               "quotation_spec_sheet")
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import _attachment, _issue, _product, _setup  # noqa: F401
from .test_project_spec_sheet import (  # noqa: F401  (helpers, not tests)
    H,
    MARKER,
    W,
    _chain,
    _client,
    _codes,
    _document,
    _line,
    _restore,
    _scope,
    _template,
    _templates,
    _wc_set,
)

VIEW_ONLY = ["projects.projects.view"]
EDIT_SLUGS = [
    "projects.projects.view",
    "projects.projects.edit",
    "projects.projects.manage",
    "projects.projects.delete",
]


def _uid() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ seed helpers


def _make(db, c, *, source=None, templates=None, user_id=None, document=None):
    """Create a sheet through the service with the standard three templates."""
    from app.services import project_spec_sheet_service as spec

    t = templates or _templates(db, c)
    return spec.create_sheet(
        db,
        document or c["document"],
        source=source or c["issue"].id,
        cover_template_id=t["cover"].id,
        page_template_id=t["page"].id,
        single_page_template_id=t["single"].id,
        user_id=user_id or c["owner"],
    )


def _draft_chain(db):
    """A document with lines but NO issue yet."""
    env = _setup(db)
    document = _document(db, env)
    scope = _scope(db, env, document)
    basin = _product(db, env["category"].id, env["uom"], description=f"{MARKER} draft basin")
    tap = _product(db, env["category"].id, env["uom"], description=f"{MARKER} draft tap")
    _line(db, env, scope, {"product_id": basin.id})
    _line(db, env, scope, {"product_id": tap.id})
    return {**env, "document": document, "scope": scope, "basin": basin, "tap": tap}


def _issued_doc(db, env, *, kind=None):
    """Another issued document in the same project."""
    document = _document(db, env)
    if kind:
        document.kind = kind
        db.flush()
    scope = _scope(db, env, document)
    product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} other product")
    _line(db, env, scope, {"product_id": product.id})
    issue = _issue(db, document, env["owner"])
    return document, scope, product, issue


def _base(c, suffix="", document=None):
    document = document or c["document"]
    return (
        f"/api/v1/project-sales/projects/{c['project'].id}/quotation-documents/"
        f"{document.id}/spec-sheets{suffix}"
    )


def _layer(text="EDITED"):
    return {
        "id": f"layer-{_uid()[:8]}",
        "type": "text",
        "x_mm": 2,
        "y_mm": 2,
        "width_mm": 40,
        "height_mm": 8,
        "rotation": 0,
        "props": {"kind": "text", "text": text},
    }


def _tags(payload):
    return [s["tags"][0] for s in payload["doc"]["sheets"]]


# ------------------------------------------------------------------ 1 create from an issue


def test_01_create_from_an_issue_snapshots_items_pins_versions_and_numbers_sheets():
    from app.models.projects import ProjectQuotationSpecSheet
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        first = _make(db, c, templates=t)

        assert isinstance(first, ProjectQuotationSpecSheet)
        assert first.sheet_no == 1
        assert first.document_id == c["document"].id
        assert first.issue_id == c["issue"].id
        assert first.company_id == c["company_id"]
        assert first.cover_template_id == t["cover"].id
        assert first.page_template_id == t["page"].id
        assert first.single_page_template_id == t["single"].id
        assert first.cover_version_id == t["cover"].published_version_id
        assert first.page_version_id == t["page"].published_version_id
        assert first.single_version_id == t["single"].published_version_id
        assert first.created_by == c["owner"]
        assert first.items_taken_at is not None
        # Q4: a new sheet starts clean.
        assert first.rows == []
        assert first.page_edits == {}
        # cover + basin + WC set.
        assert first.page_count == 3

        keys = [i["key"] for i in first.items]
        assert keys == [c["basin"].id, f"set:{c['set'].id}"]
        basin, wc = first.items
        assert {
            "key",
            "line_id",
            "product_id",
            "code",
            "description",
            "brand",
            "image_attachment_id",
            "drawing_attachment_id",
            "section",
            "unit_price",
            "set_parts",
        } <= set(basin)
        assert basin["code"] == c["basin"].product_code
        assert basin["unit_price"] == 100.0
        assert wc["code"] == c["pedestal"].product_code
        assert [p["product_code"] for p in wc["set_parts"]] == [
            c["valve"].product_code,
            c["hose"].product_code,
        ]

        second = _make(db, c, templates=t)
        assert second.sheet_no == 2
        assert first.sheet_no == 1
        assert spec.snapshot_items(db, c["document"], c["issue"]) == first.items


def test_01_sheet_numbers_are_never_reused_after_a_delete():
    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        _make(db, c, templates=t)
        second = _make(db, c, templates=t)
        db.delete(second)
        db.flush()
        assert _make(db, c, templates=t).sheet_no == 2  # max + 1 of the survivors
        third = _make(db, c, templates=t)
        assert third.sheet_no == 3


# ------------------------------------------------------------------ 2 create from the draft


def test_02_a_draft_sheet_before_any_issue_is_frozen_and_listed_as_draft():
    from app.models.projects import ProjectQuotationLine
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _draft_chain(db)
        sheet = _make(db, c, source="draft")

        assert sheet.issue_id is None
        assert sheet.based_on_issue_no is None
        assert sheet.page_count == 3  # cover + two products
        before = _codes(spec.pages(db, sheet))
        assert before == [c["basin"].product_code, c["tap"].product_code]

        # A later line edit on the draft does not move the sheet.
        extra = _product(db, c["category"].id, c["uom"], description=f"{MARKER} added later")
        _line(db, c, c["scope"], {"product_id": extra.id})
        db.query(ProjectQuotationLine).filter(
            ProjectQuotationLine.product_id == c["tap"].id
        ).delete(synchronize_session=False)
        db.flush()
        db.expire_all()
        assert _codes(spec.pages(db, sheet)) == before

        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            got = client.get(_base(c))
            assert got.status_code == 200, got.text
            row = got.json()["items"][0]
            assert row["label"] == "SS1"
            assert row["is_draft"] is True
            assert row["source_label"] == "Draft"
        finally:
            _restore(originals)


def test_02_a_draft_sheet_after_an_issue_reads_draft_after_r1_and_keeps_its_own_items():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        from app.services import project_quotation_service as quotes

        quotes.revise(db, quotation=c["scope"], actor_user_id=c["owner"])
        newer = _product(db, c["category"].id, c["uom"], description=f"{MARKER} after r1")
        _line(db, c, c["scope"], {"product_id": newer.id})

        sheet = _make(db, c, source="draft")
        assert sheet.issue_id is None
        assert sheet.based_on_issue_no == c["issue"].issue_no
        assert newer.product_code in _codes(spec.pages(db, sheet))

        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            got = client.get(_base(c, f"/{sheet.id}"))
            assert got.status_code == 200, got.text
            assert got.json()["source_label"] == f"Draft after {c['issue'].revision_label}"
            assert got.json()["is_draft"] is True

            # An issue stored without a label reads as R<n>.
            c["issue"].revision_label = None
            db.flush()
            again = client.get(_base(c, f"/{sheet.id}"))
            assert again.json()["source_label"] == f"Draft after R{c['issue'].issue_no}"
            assert spec.sources(db, c["document"])[0]["hint"] == (
                f"changed after R{c['issue'].issue_no} · not issued"
            )
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 3 sources


def test_03_sources_list_the_draft_first_only_when_lines_changed_after_the_newest_issue():
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sources = spec.sources(db, c["document"])
        assert [s["value"] for s in sources] == [c["issue"].id]
        assert sources[0]["label"] == qdocs.quotation_no(
            c["document"].document_no, c["issue"].issue_no, c["issue"].revision_label
        )
        assert sources[0]["hint"].startswith("issued ")

        quotes.revise(db, quotation=c["scope"], actor_user_id=c["owner"])
        extra = _product(db, c["category"].id, c["uom"], description=f"{MARKER} changed")
        _line(db, c, c["scope"], {"product_id": extra.id})

        sources = spec.sources(db, c["document"])
        assert sources[0]["value"] == "draft"
        assert sources[0]["label"] == "Current draft"
        assert sources[0]["hint"] == f"changed after {c['issue'].revision_label} · not issued"
        assert [s["value"] for s in sources[1:]] == [c["issue"].id]


def test_03_a_document_with_no_issue_offers_only_the_draft():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _draft_chain(db)
        sources = spec.sources(db, c["document"])
        assert [(s["value"], s["label"], s["hint"]) for s in sources] == [
            ("draft", "Current draft", "not issued yet")
        ]


def test_03_a_proposal_labels_its_revisions_a_and_b_newest_first():
    from app.models.projects import ProjectQuotation
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        env = _setup(db)
        document, scope, _product_row, first = _issued_doc(db, env, kind=qdocs.KIND_PROPOSAL)
        quotes.revise(db, quotation=db.get(ProjectQuotation, scope.id), actor_user_id=env["owner"])
        second = _issue(db, document, env["owner"])
        assert (first.revision_label, second.revision_label) == ("A", "B")

        sources = spec.sources(db, document)
        assert [s["value"] for s in sources] == [second.id, first.id]
        assert [s["label"] for s in sources] == [
            f"{document.document_no}-B",
            f"{document.document_no}-A",
        ]


# ------------------------------------------------------------------ 4 create refusals


def _refusal(db, c, **overrides):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    t = overrides.pop("templates", None) or _templates(db, c)
    body = {
        "source": c["issue"].id,
        "cover_template_id": t["cover"].id,
        "page_template_id": t["page"].id,
        "single_page_template_id": t["single"].id,
        "user_id": c["owner"],
    }
    body.update(overrides)
    document = body.pop("document", c["document"])
    with pytest.raises(AppException) as raised:
        spec.create_sheet(db, document, **body)
    assert raised.value.status_code == 422
    return raised.value.code


def test_04_create_refuses_templates_that_cannot_print():
    from app.models.projects import ProjectQuotationSpecSheet

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        unpublished = _template(db, c["company_id"], "spec_page", published=False)
        wrong_family = _template(db, c["company_id"], "wc")
        a4 = _template(db, c["company_id"], "spec_page", width=297, height=210)

        assert _refusal(db, c, templates=t, page_template_id=unpublished.id) == "spec_sheet_template_invalid"
        assert _refusal(db, c, templates=t, page_template_id=wrong_family.id) == "spec_sheet_template_invalid"
        assert _refusal(db, c, templates=t, cover_template_id=t["page"].id) == "spec_sheet_template_invalid"
        assert _refusal(db, c, templates=t, single_page_template_id=a4.id) == "spec_sheet_size_mismatch"
        assert _refusal(db, c, templates=t, page_template_id=a4.id) == "spec_sheet_size_mismatch"
        assert _refusal(db, c, templates=t, cover_template_id=None) == "spec_sheet_templates_missing"
        assert db.query(ProjectQuotationSpecSheet).count() == 0


def test_04_create_refuses_an_issue_of_another_document_and_a_document_without_lines():
    with blank_session() as db:
        c = _chain(db)
        other_doc, _scope_row, _prod, other_issue = _issued_doc(db, c)
        assert _refusal(db, c, source=other_issue.id) == "spec_sheet_issue_invalid"
        assert _refusal(db, c, source=_uid()) == "spec_sheet_issue_invalid"
        assert _refusal(db, c, source="not-a-uuid") == "spec_sheet_issue_invalid"

        empty = _document(db, c)
        _scope(db, c, empty)
        assert _refusal(db, c, document=empty, source="draft") == "spec_sheet_no_lines"


def test_04_the_create_route_answers_422_with_the_code():
    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            bad = client.post(
                _base(c),
                json={
                    "source": c["issue"].id,
                    "cover_template_id": t["page"].id,
                    "page_template_id": t["page"].id,
                },
            )
            assert bad.status_code == 422, bad.text
            assert bad.json().get("code") == "spec_sheet_template_invalid"

            ok = client.post(
                _base(c),
                json={
                    "source": c["issue"].id,
                    "cover_template_id": t["cover"].id,
                    "page_template_id": t["page"].id,
                },
            )
            assert ok.status_code == 201, ok.text
            body = ok.json()
            assert body["label"] == "SS1"
            assert body["pages"][0]["key"] == "cover"
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 5 pages from the snapshot


def test_05_pages_from_the_snapshot_keep_the_2103_rules():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        set_key = f"set:{c['set'].id}"

        pages = spec.pages(db, sheet)
        assert _codes(pages) == [c["basin"].product_code, c["pedestal"].product_code]
        assert pages[0]["key"] == c["basin"].id and pages[1]["key"] == set_key
        assert [a["code"] for a in pages[1]["accessories"]] == [
            c["valve"].product_code,
            c["hose"].product_code,
        ]
        assert pages[0]["area"] == "" and pages[0]["hidden"] is False

        # A picked accessory leaves its own page and prints after the set parts.
        spec.update_sheet(db, sheet, {"rows": [{"key": set_key, "accessories": [c["basin"].id]}]})
        pages = spec.pages(db, sheet)
        assert [p["key"] for p in pages] == [set_key]
        assert [a["code"] for a in pages[0]["accessories"]] == [
            c["valve"].product_code,
            c["hose"].product_code,
            c["basin"].product_code,
        ]

        # Order, hidden and typed area apply; the hidden page stays listed (flagged).
        spec.update_sheet(
            db,
            sheet,
            {
                "rows": [
                    {"key": set_key, "area": "Unit", "accessories": []},
                    {"key": c["basin"].id, "hidden": True},
                ]
            },
        )
        pages = spec.pages(db, sheet)
        assert [p["key"] for p in pages] == [set_key, c["basin"].id]
        assert pages[0]["area"] == "Unit"
        assert pages[1]["hidden"] is True


def test_05_area_defaults_to_the_section_heading_in_the_snapshot():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        first = _scope(db, env, document, "Block A")
        second = _scope(db, env, document, "Block B")
        wc = _product(db, env["category"].id, env["uom"], description=f"{MARKER} wc")
        basin = _product(db, env["category"].id, env["uom"], description=f"{MARKER} basin")
        trap = _product(db, env["category"].id, env["uom"], description=f"{MARKER} trap")
        _line(db, env, first, {"product_id": wc.id, "band_label": "UNIT"})
        _line(db, env, first, {"product_id": basin.id})
        _line(db, env, second, {"product_id": trap.id})
        issue = _issue(db, document, env["owner"])
        c = {**env, "document": document, "issue": issue}
        sheet = _make(db, c)

        pages = {p["key"]: p for p in spec.pages(db, sheet)}
        assert pages[wc.id]["area"] == "UNIT"
        assert pages[basin.id]["area"] == "UNIT" and pages[basin.id]["area_default"] == "UNIT"
        assert pages[trap.id]["area"] == ""
        spec.update_sheet(db, sheet, {"rows": [{"key": basin.id, "area": "Guard house"}]})
        pages = {p["key"]: p for p in spec.pages(db, sheet)}
        assert pages[basin.id]["area"] == "Guard house"
        assert pages[basin.id]["area_default"] == "UNIT"


# ------------------------------------------------------------------ 6 PATCH rows


def test_06_rows_merge_and_refusals_and_sheets_do_not_leak_into_each_other():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        ss1 = _make(db, c, templates=t)
        ss2 = _make(db, c, templates=t)
        set_key = f"set:{c['set'].id}"
        basin = c["basin"].id

        spec.update_sheet(db, ss2, {"rows": [{"key": basin, "area": "Pantry"}]})
        spec.update_sheet(db, ss2, {"rows": [{"key": set_key, "comment": "Soft close", "marker": "*"}]})
        stored = {r["key"]: r for r in ss2.rows}
        assert stored[basin]["area"] == "Pantry"  # merge keeps rows the payload did not mention
        assert stored[set_key] == {
            "key": set_key,
            "area": "",
            "comment": "Soft close",
            "marker": "*",
            "hidden": False,
            "accessories": [],
        }
        assert [r["key"] for r in ss2.rows][0] == set_key  # payload rows come first
        assert ss1.rows == []
        assert ss2.updated_by is None or isinstance(ss2.updated_by, str)

        for rows in (
            [{"key": set_key, "accessories": [set_key]}],
            [{"key": set_key}, {"key": set_key}],
            [{"key": set_key, "accessories": [basin]}, {"key": basin, "accessories": [set_key]}],
        ):
            with pytest.raises(AppException) as raised:
                spec.update_sheet(db, ss2, {"rows": rows})
            assert raised.value.status_code == 422
            assert raised.value.code == "spec_sheet_rows_invalid"


def test_06_the_patch_route_merges_rows_and_refuses_bad_ones():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            url = _base(c, f"/{sheet.id}")
            ok = client.patch(url, json={"rows": [{"key": c["basin"].id, "area": "Pantry"}]})
            assert ok.status_code == 200, ok.text
            page = next(p for p in ok.json()["pages"] if p["key"] == c["basin"].id)
            assert page["area"] == "Pantry"

            bad = client.patch(url, json={"rows": [{"key": "a", "accessories": ["a"]}]})
            assert bad.status_code == 422, bad.text
            assert bad.json().get("code") == "spec_sheet_rows_invalid"
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 7 page edits


def test_07_a_page_edit_changes_only_that_page_and_reset_restores_the_template():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        sheet = _make(db, c, templates=t)
        set_key = f"set:{c['set'].id}"
        template_layers = t["page"].published_version.doc["layers"]

        before = {tag["request_tag_id"]: tag["layers"] for tag in _tags(spec.build_print_payload(db, sheet))}
        edited = [_layer("EDITED")]
        spec.save_page_edit(db, sheet, set_key, edited)
        db.refresh(sheet)
        assert sheet.page_edits[set_key]["layers"] == edited

        after = {tag["request_tag_id"]: tag["layers"] for tag in _tags(spec.build_print_payload(db, sheet))}
        assert after[set_key] == edited
        assert after[c["basin"].id] == before[c["basin"].id]
        assert after["cover"] == before["cover"]
        # The template and its version are untouched.
        assert t["page"].published_version.doc["layers"] == template_layers
        assert next(p for p in spec.pages(db, sheet) if p["key"] == set_key)["edited"] is True

        # The cover is editable the same way; an unknown key is a 404; too many layers refused.
        spec.save_page_edit(db, sheet, "cover", [_layer("COVER")])
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, "set:not-a-page", edited)
        assert raised.value.status_code == 404
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, set_key, [_layer(str(i)) for i in range(301)])
        assert raised.value.status_code == 422

        spec.reset_page_edit(db, sheet, set_key)
        db.refresh(sheet)
        assert set_key not in sheet.page_edits
        reset = {tag["request_tag_id"]: tag["layers"] for tag in _tags(spec.build_print_payload(db, sheet))}
        assert reset[set_key] == before[set_key]


def test_07_the_edit_and_design_routes_use_the_override():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            key = c["basin"].id
            design = client.get(_base(c, f"/{sheet.id}/pages/{key}/design"))
            assert design.status_code == 200, design.text
            body = design.json()
            assert {"layers", "bound", "images", "assets", "fonts", "width_mm", "height_mm", "template_name"} <= set(body)
            assert body["bound"]["code"] == c["basin"].product_code
            assert (body["width_mm"], body["height_mm"]) == (W, H)

            layers = [_layer("ROUTE")]
            put = client.put(_base(c, f"/{sheet.id}/pages/{key}/edit"), json={"layers": layers})
            assert put.status_code == 200, put.text
            page = next(p for p in put.json()["pages"] if p["key"] == key)
            assert page["edited"] is True

            again = client.get(_base(c, f"/{sheet.id}/pages/{key}/design"))
            assert again.json()["layers"] == layers

            missing = client.put(
                _base(c, f"/{sheet.id}/pages/set:nope/edit"), json={"layers": layers}
            )
            assert missing.status_code == 404
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 8 re-published template


def test_08_a_republished_template_keeps_the_old_version_until_use_latest_templates():
    from app.models.dealer_kit import TagTemplateVersion
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        sheet = _make(db, c, templates=t)
        set_key = f"set:{c['set'].id}"
        v1 = t["page"].published_version
        old_layers = v1.doc["layers"]
        spec.save_page_edit(db, sheet, set_key, [_layer("KEEP ME")])

        new_doc = {**v1.doc, "layers": [_layer("TEMPLATE V2")]}
        v2 = TagTemplateVersion(
            id=_uid(), template_id=t["page"].id, version_no=2, doc=new_doc, print_size=t["page"].print_size
        )
        db.add(v2)
        db.flush()
        t["page"].published_version_id = v2.id
        db.flush()

        # Re-publish the single-item template (the basin page, no override) and the cover too.
        single_v1 = t["single"].published_version
        cover_v1 = t["cover"].published_version
        for template, v1_version in ((t["single"], single_v1), (t["cover"], cover_v1)):
            fresh = TagTemplateVersion(
                id=_uid(),
                template_id=template.id,
                version_no=2,
                doc={**v1_version.doc, "layers": [_layer("REPUBLISHED")]},
                print_size=template.print_size,
            )
            db.add(fresh)
            db.flush()
            template.published_version_id = fresh.id
            db.flush()

        # The sheet still draws the VERSIONS it pinned, in the window and in the export.
        for payload in (
            spec.build_print_payload(db, sheet, keys=[c["basin"].id, "cover"]),
            spec.build_print_payload(db, sheet, full=True),
        ):
            tags = {tag["request_tag_id"]: tag for tag in _tags(payload)}
            assert tags[c["basin"].id]["layers"] == single_v1.doc["layers"]
            assert tags["cover"]["layers"] == cover_v1.doc["layers"]
        assert sheet.page_version_id == v1.id

        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            detail = client.get(_base(c, f"/{sheet.id}")).json()
            assert detail["newer_templates"]
            assert detail["templates"]["page"]["version_no"] == 1
        finally:
            _restore(originals)

        spec.update_sheet(db, sheet, {"use_latest_templates": True})
        assert sheet.page_version_id == v2.id
        assert sheet.cover_version_id == t["cover"].published_version_id
        assert sheet.page_edits[set_key]["layers"][0]["props"]["text"] == "KEEP ME"
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            detail = client.get(_base(c, f"/{sheet.id}")).json()
            assert not detail["newer_templates"]
            assert detail["templates"]["page"]["version_no"] == 2
        finally:
            _restore(originals)


def test_08_use_latest_templates_refuses_a_template_that_was_unpublished():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        sheet = _make(db, c, templates=t)
        t["page"].published_version_id = None
        db.flush()
        with pytest.raises(AppException) as raised:
            spec.update_sheet(db, sheet, {"use_latest_templates": True})
        assert raised.value.status_code == 422


# ------------------------------------------------------------------ 9 preview window + export


def _with_photos(db, c, sheet):
    """Give both items a frozen photo so signing is observable."""
    photo_a = _attachment(db, c["company_id"], "a.png")
    photo_b = _attachment(db, c["company_id"], "b.png")
    items = [dict(i) for i in sheet.items]
    items[0]["image_attachment_id"] = photo_a.id
    items[1]["image_attachment_id"] = photo_b.id
    sheet.items = items
    db.flush()
    return photo_a, photo_b


def test_09_the_keys_window_returns_only_those_sheets_and_signs_thumbnails(monkeypatch):
    from app.services import product_image_service as images
    from app.services import project_spec_sheet_service as spec

    calls = []

    def fake_preview_urls(db, ids, *, full=False, **kwargs):
        calls.append((list(ids), full))
        return {i: f"https://signed.zzt.test/{i}" for i in ids if i}

    monkeypatch.setattr(images, "preview_urls", fake_preview_urls)

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        photo_a, photo_b = _with_photos(db, c, sheet)
        basin = c["basin"].id

        payload = spec.build_print_payload(db, sheet, keys=[basin])
        assert [t["request_tag_id"] for t in _tags(payload)] == [basin]
        assert basin in payload["resolvedData"]
        assert photo_a.id in payload["images"] and photo_b.id not in payload["images"]
        assert calls and all(full is False for _ids, full in calls)

        calls.clear()
        full = spec.build_print_payload(db, sheet, full=True)
        assert [t["request_tag_id"] for t in _tags(full)] == ["cover", basin, f"set:{c['set'].id}"]
        assert calls and all(full_flag is True for _ids, full_flag in calls)


def test_09_export_payload_prints_the_visible_pages_only_the_preview_route_flags_hidden():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        basin = c["basin"].id
        spec.update_sheet(db, sheet, {"rows": [{"key": basin, "hidden": True}]})

        exported = spec.build_print_payload(db, sheet, full=True)
        assert basin not in [t["request_tag_id"] for t in _tags(exported)]

        client, originals = _client(db, c["owner"], slugs=VIEW_ONLY)
        try:
            ok = client.get(_base(c, f"/{sheet.id}/preview"), params=[("key", "cover"), ("key", basin)])
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert [t["request_tag_id"] for t in _tags(body)] == ["cover", basin]
            assert body["hidden"] == [basin]
            assert body["page_size"] == {"width_mm": W, "height_mm": H}

            many = ",".join(["cover"] + [_uid() for _ in range(12)])
            assert client.get(_base(c, f"/{sheet.id}/preview"), params=[("key", k) for k in many.split(",")]).status_code == 422
            unknown = client.get(_base(c, f"/{sheet.id}/preview"), params={"key": "set:nope"})
            assert unknown.status_code == 422
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 10 export


def test_10_request_export_points_the_download_at_the_sheet(monkeypatch):
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_spec_sheet_service as spec

    calls = []
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: calls.append((a, k)))
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        assert sheet.last_exported_at is None
        download = spec.request_export(db, sheet, user_id=c["owner"])

        assert download.kind == spec.KIND == "quotation_spec_sheet_pdf"
        assert download.source_entity_type == "quotation_spec_sheet"
        assert download.source_entity_id == sheet.id
        number = qdocs.quotation_no(c["document"].document_no, c["issue"].issue_no, c["issue"].revision_label)
        assert download.filename == f"spec-sheet-{number}-SS1.pdf"
        assert sheet.last_exported_at is not None
        assert len(calls) == 1
        assert calls[0][0][1] == str(download.id)
        assert calls[0][1]["queue_name"] == "catalogue_render"


def test_10_a_draft_sheet_export_is_named_draft(monkeypatch):
    from app.services import project_spec_sheet_service as spec

    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: None)
    with blank_session() as db:
        c = _draft_chain(db)
        sheet = _make(db, c, source="draft")
        download = spec.request_export(db, sheet, user_id=c["owner"])
        assert download.filename == f"spec-sheet-{c['document'].document_no}-draft-SS1.pdf"


def _download(db, c, sheet, *, source_type="quotation_spec_sheet", source_id=None):
    from app.models.download import UserDownload
    from app.services import project_spec_sheet_service as spec

    row = UserDownload(
        user_id=c["owner"],
        kind=spec.KIND,
        source_entity_type=source_type,
        source_entity_id=source_id or sheet.id,
        status="pending",
        filename="spec-sheet-x.pdf",
    )
    db.add(row)
    db.flush()
    return row


def test_10_the_public_print_payload_answers_a_sheet_download_pinned_to_its_company():
    from app.services import project_spec_sheet_service as spec
    from app.services.dealer_kit.tag_sheet_export_service import resolve_tag_sheet_print_payload

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        download = _download(db, c, sheet)

        payload = resolve_tag_sheet_print_payload(db, str(download.id))
        assert len(payload["doc"]["sheets"]) == 3
        assert "cover" in payload["resolvedData"]
        assert spec.page_size_for_download(db, download) == (W, H)


def test_10_a_sheet_download_on_a_document_without_a_company_fails_closed(monkeypatch):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        download = _download(db, c, sheet)

        class _NoCompany:
            company_id = None

        # source_of_download(db, download) -> (document, sheet), as #2103's answered (document, issue).
        monkeypatch.setattr(spec, "source_of_download", lambda db, dl: (_NoCompany(), sheet))
        for call in (spec.print_payload_for_download, spec.page_size_for_download):
            with pytest.raises(AppException) as raised:
                call(db, download)
            assert raised.value.status_code == 404


def test_10_a_legacy_quotation_issue_download_and_a_deleted_sheet_answer_404():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        legacy = _download(db, c, sheet, source_type="quotation_issue", source_id=c["issue"].id)
        for call in (spec.print_payload_for_download, spec.page_size_for_download):
            with pytest.raises(AppException) as raised:
                call(db, legacy)
            assert raised.value.status_code == 404

        live = _download(db, c, sheet)
        db.delete(sheet)
        db.flush()
        with pytest.raises(AppException) as raised:
            spec.print_payload_for_download(db, live)
        assert raised.value.status_code == 404


def test_10_the_export_route_queues_the_download(monkeypatch):
    queued = []
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: queued.append((a, k)))
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=VIEW_ONLY)
        try:
            got = client.post(_base(c, f"/{sheet.id}/export"))
            assert got.status_code == 200, got.text
            assert got.json()["kind"] == "quotation_spec_sheet_pdf"
            assert len(queued) == 1
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 11 deferred actions + ownership


def test_11_the_two_deferred_actions_are_registered():
    import app.services.record_actions  # noqa: F401  (registers on import)
    from app.services.form_action_registry import get_action

    for key in ("quotation_spec_sheet.delete", "quotation_spec_sheet.reset_page"):
        action = get_action(key)
        assert action is not None, key
        assert "quotation_spec_sheet" in action.entity_types


PENDING = "/api/v1/pending-actions"


def _park(client, key, sheet_id, payload=None):
    return client.post(
        PENDING,
        json={
            "action_key": key,
            "entity_type": "quotation_spec_sheet",
            "entity_id": sheet_id,
            "payload": payload or {},
        },
    )


def _lapse(db, parked_id):
    from datetime import datetime, timedelta

    from app.models.sla import SlaFormAction

    db.query(SlaFormAction).filter(SlaFormAction.id == parked_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
    )
    db.commit()


def _sheet_exists(db, sheet_id):
    from app.models.projects import ProjectQuotationSpecSheet

    db.expire_all()
    return db.get(ProjectQuotationSpecSheet, sheet_id) is not None


def test_11_parking_a_delete_needs_the_edit_right_and_the_commit_hard_deletes():
    from app.models.base import company_scope

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        sheet_id = sheet.id
        db.commit()
        with company_scope(db, frozenset({c["company_id"]})):
            client, originals = _client(db, c["owner"], slugs=VIEW_ONLY)
            try:
                refused = _park(client, "quotation_spec_sheet.delete", sheet_id)
                assert refused.status_code == 403, refused.text
                assert _sheet_exists(db, sheet_id)
            finally:
                _restore(originals)

            client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
            try:
                parked = _park(client, "quotation_spec_sheet.delete", sheet_id)
                assert parked.status_code == 202, parked.text
                assert _sheet_exists(db, sheet_id), "nothing applies until the window lapses"
                _lapse(db, parked.json()["id"])
                current = client.get(
                    f"{PENDING}/current",
                    params={"entity_type": "quotation_spec_sheet", "entity_id": sheet_id},
                )
                assert current.status_code == 200, current.text
                assert (current.json().get("last_outcome") or {}).get("status") == "committed", current.text
                assert not _sheet_exists(db, sheet_id)
            finally:
                _restore(originals)


def test_11_the_reset_page_action_removes_only_that_override():
    from app.models.base import company_scope
    from app.models.projects import ProjectQuotationSpecSheet
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        set_key = f"set:{c['set'].id}"
        spec.save_page_edit(db, sheet, set_key, [_layer("ONE")])
        spec.save_page_edit(db, sheet, c["basin"].id, [_layer("TWO")])
        sheet_id = sheet.id
        db.commit()
        with company_scope(db, frozenset({c["company_id"]})):
            client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
            try:
                parked = _park(client, "quotation_spec_sheet.reset_page", sheet_id, {"page_key": set_key})
                assert parked.status_code == 202, parked.text
                _lapse(db, parked.json()["id"])
                client.get(
                    f"{PENDING}/current",
                    params={"entity_type": "quotation_spec_sheet", "entity_id": sheet_id},
                )
                db.expire_all()
                edits = db.get(ProjectQuotationSpecSheet, sheet_id).page_edits
                assert set_key not in edits
                assert c["basin"].id in edits
            finally:
                _restore(originals)


def test_11_a_sheet_of_another_document_is_404_on_every_route():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        other = _document(db, c)
        key = c["basin"].id
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            sid = sheet.id
            calls = [
                client.get(_base(c, f"/{sid}", other)),
                client.patch(_base(c, f"/{sid}", other), json={"rows": []}),
                client.get(_base(c, f"/{sid}/preview", other), params={"key": "cover"}),
                client.get(_base(c, f"/{sid}/pages/{key}/design", other)),
                client.put(_base(c, f"/{sid}/pages/{key}/edit", other), json={"layers": []}),
                client.post(_base(c, f"/{sid}/export", other)),
            ]
            assert [r.status_code for r in calls] == [404] * 6, [r.text for r in calls]
            # And the owning document still answers.
            assert client.get(_base(c, f"/{sid}")).status_code == 200
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 12 rights


def test_12_a_read_only_user_reads_and_exports_but_cannot_write(monkeypatch):
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: None)
    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        sheet = _make(db, c, templates=t)
        key = c["basin"].id
        client, originals = _client(db, c["owner"], slugs=VIEW_ONLY)
        try:
            assert client.get(_base(c)).status_code == 200
            detail = client.get(_base(c, f"/{sheet.id}"))
            assert detail.status_code == 200
            assert detail.json()["can_edit"] is False
            assert client.get(_base(c, f"/{sheet.id}/preview"), params={"key": "cover"}).status_code == 200
            assert client.post(_base(c, f"/{sheet.id}/export")).status_code == 200

            create = client.post(
                _base(c),
                json={"source": c["issue"].id, "cover_template_id": t["cover"].id, "page_template_id": t["page"].id},
            )
            assert create.status_code == 403
            assert client.patch(_base(c, f"/{sheet.id}"), json={"rows": []}).status_code == 403
            assert client.get(_base(c, f"/{sheet.id}/pages/{key}/design")).status_code == 403
            assert client.put(_base(c, f"/{sheet.id}/pages/{key}/edit"), json={"layers": []}).status_code == 403
        finally:
            _restore(originals)


def test_12_the_detail_carries_the_contract_fields_and_neighbours():
    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        ss1 = _make(db, c, templates=t)
        ss2 = _make(db, c, templates=t)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            body = client.get(_base(c, f"/{ss1.id}")).json()
            assert body["label"] == "SS1" and body["can_edit"] is True
            assert body["is_draft"] is False
            assert body["page_size"] == {"width_mm": W, "height_mm": H}
            assert body["templates"]["cover"]["id"] == t["cover"].id
            assert body["templates"]["cover"]["version_no"] == 1
            assert body["templates"]["page"]["name"]
            assert [p["key"] for p in body["pages"]] == ["cover", c["basin"].id, f"set:{c['set'].id}"]
            assert all("images" not in p for p in body["pages"])  # no per-page images in the detail
            assert body["pages"][0]["template"] == "cover"
            assert {body["prev_id"], body["next_id"]} == {None, ss2.id}
        finally:
            _restore(originals)


# ------------------------------------------------------------------ 13 migration backfill


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "ssv2_0001_spec_sheets.py"
    spec = importlib.util.spec_from_file_location("ssv2_0001_spec_sheets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_13_backfill_turns_a_set_up_document_into_ss1_and_is_idempotent():
    from app.models.projects import ProjectQuotationSpecSheet

    migration = _migration()
    with blank_session() as db:
        env = _setup(db)
        t = _templates(db, env)
        settings_rows = [
            {"key": "k", "area": "Pantry", "comment": "", "marker": "", "hidden": False, "accessories": []}
        ]

        def setup_doc(doc, issue_id):
            doc.spec_sheet = {
                "cover_template_id": t["cover"].id,
                "page_template_id": t["page"].id,
                "single_page_template_id": None,
                "issue_id": issue_id,
                "rows": settings_rows,
            }
            db.flush()

        # A: templates + saved issue (an older one, though a newer exists).
        doc_a, scope_a, _p, issue_a1 = _issued_doc(db, env)
        from app.models.projects import ProjectQuotation
        from app.services import project_quotation_service as quotes

        quotes.revise(db, quotation=db.get(ProjectQuotation, scope_a.id), actor_user_id=env["owner"])
        issue_a2 = _issue(db, doc_a, env["owner"])
        setup_doc(doc_a, issue_a1.id)
        # D: templates, no saved issue, two issues -> the newest.
        doc_d, scope_d, _p2, issue_d1 = _issued_doc(db, env)
        quotes.revise(db, quotation=db.get(ProjectQuotation, scope_d.id), actor_user_id=env["owner"])
        issue_d2 = _issue(db, doc_d, env["owner"])
        setup_doc(doc_d, None)
        # B: templates but no issue at all -> none.
        doc_b = _document(db, env)
        _scope(db, env, doc_b)
        setup_doc(doc_b, None)
        # C: an issue but no templates -> none.
        doc_c, _s, _p3, _i = _issued_doc(db, env)

        migration.backfill(db.connection())
        db.expire_all()

        def sheets(doc):
            return db.query(ProjectQuotationSpecSheet).filter(ProjectQuotationSpecSheet.document_id == doc.id).all()

        (a,) = sheets(doc_a)
        assert a.sheet_no == 1
        assert a.issue_id == issue_a1.id and a.issue_id != issue_a2.id
        assert a.company_id == doc_a.company_id
        assert a.rows == settings_rows
        assert a.cover_template_id == t["cover"].id and a.page_template_id == t["page"].id
        assert a.single_page_template_id is None
        assert a.cover_version_id == t["cover"].published_version_id
        assert a.page_version_id == t["page"].published_version_id
        assert [i["key"] for i in a.items]
        assert a.page_count >= 2
        (d,) = sheets(doc_d)
        assert d.issue_id == issue_d2.id and d.issue_id != issue_d1.id
        assert sheets(doc_b) == [] and sheets(doc_c) == []

        migration.backfill(db.connection())
        db.expire_all()
        assert len(sheets(doc_a)) == 1 and len(sheets(doc_d)) == 1


# ------------------------------------------------------------------ 14 list defaults


def test_14_list_defaults_take_the_users_newest_sheet_templates():
    with blank_session() as db:
        c = _chain(db)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            first = client.get(_base(c))
            assert first.status_code == 200, first.text
            body = first.json()
            assert body["items"] == []
            assert body["defaults"] == {
                "source": c["issue"].id,
                "cover_template_id": None,
                "page_template_id": None,
                "single_page_template_id": None,
            }
            assert body["create_disabled_reason"] is None
            assert [s["value"] for s in body["sources"]] == [c["issue"].id]
            assert {"cover", "page"} <= set(body["templates"])

            t = _templates(db, c)
            sheet = _make(db, c, templates=t)
            body = client.get(_base(c)).json()
            assert body["defaults"]["cover_template_id"] == t["cover"].id
            assert body["defaults"]["page_template_id"] == t["page"].id
            assert body["defaults"]["single_page_template_id"] == t["single"].id
            row = body["items"][0]
            assert row["id"] == sheet.id and row["label"] == "SS1"
            assert row["is_draft"] is False
            assert row["page_count"] == 3 and row["edited_count"] == 0
            assert row["cover_name"] == t["cover"].name and row["single_name"] == t["single"].name
            assert row["last_exported_at"] is None
            assert not row["newer_templates"]
            assert row["created_by_name"]
            assert "created_at" in row and "updated_at" in row

            # The defaults follow the newest sheet this user created.
            other = _make(db, c, templates=_templates(db, c))
            body = client.get(_base(c)).json()
            assert [r["label"] for r in body["items"]] == ["SS2", "SS1"]  # newest first
            assert body["defaults"]["cover_template_id"] == other.cover_template_id
        finally:
            _restore(originals)


def test_14_create_is_disabled_when_the_quotation_has_no_line():
    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        _scope(db, env, document)
        c = {**env, "document": document, "project": env["project"]}
        client, originals = _client(db, env["owner"], slugs=EDIT_SLUGS)
        try:
            body = client.get(_base(c)).json()
            assert body["items"] == []
            assert body["create_disabled_reason"] == "Add a line to the quotation first."
        finally:
            _restore(originals)


# ------------------------------------------------------------------ security review round (fix round 2)


def _big_layers(count, size=4900):
    out = []
    for i in range(count):
        layer = _layer("x")
        layer["props"]["text"] = "a" * size
        layer["id"] = f"big-{i}"
        out.append(layer)
    return out


def _other_company_template(db, family="spec_page"):
    from app.models.company import Company

    from ._pg_fixture import unique_code

    other = Company(id=_uid(), name="ZZT Other", code=unique_code("OTH")[:20])
    db.add(other)
    db.flush()
    return _template(db, other.id, family)


def test_s1_a_page_edit_is_bounded_per_page_and_per_sheet(monkeypatch):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        set_key = f"set:{c['set'].id}"
        # ~1.4 MB serialized: over the 512 000 page cap.
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, set_key, _big_layers(300))
        assert (raised.value.status_code, raised.value.code) == (422, "spec_sheet_page_edit_too_large")

        # Each page fits, the sheet's whole set of edits does not.
        monkeypatch.setattr(spec, "PAGE_EDITS_TOTAL_MAX", 300_000)
        spec.save_page_edit(db, sheet, set_key, _big_layers(40))  # ~200 KB
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, c["basin"].id, _big_layers(40))
        assert (raised.value.status_code, raised.value.code) == (422, "spec_sheet_page_edit_too_large")
        # Replacing the page that already holds an edit is measured without its old copy.
        spec.save_page_edit(db, sheet, set_key, _big_layers(41))


def _nested(depth):
    node = {"k": "v"}
    for _ in range(depth):
        node = {"child": node}
    return node


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-dict",
        {"id": "l1"},
        {"id": "l1", "type": "nonsense"},
        {"id": "l1", "type": "text", "props": {"kind": "text", "text": "a" * 5001}},
        {"id": "l1", "type": "text", "props": _nested(9)},
    ],
)
def test_s1_a_page_edit_layer_must_look_like_a_designer_layer(bad):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, c["basin"].id, [bad])
        assert (raised.value.status_code, raised.value.code) == (422, "spec_sheet_page_edit_invalid")


def test_s1_every_layer_type_the_designer_produces_is_accepted():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        layers = [
            {
                "id": f"l-{kind}",
                "type": kind,
                "x_mm": 1,
                "y_mm": 1,
                "width_mm": 10,
                "height_mm": 10,
                "rotation_deg": 0,
                "z_index": 0,
                "locked": False,
                "visible": True,
                "slot_binding": None,
                "text_override": None,
                "props": {"kind": kind, "subjectPart": 1, "children": []},
                "show_when": {"spec": "is_rimless", "part": 1},
            }
            for kind in ("image", "text", "shape", "product_slot", "price_badge", "badge", "barcode", "group")
        ]
        spec.save_page_edit(db, sheet, c["basin"].id, layers)
        assert len(sheet.page_edits[c["basin"].id]["layers"]) == 8


def test_s2_a_template_of_another_company_is_refused_on_create_and_use_latest():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        foreign = _other_company_template(db, "spec_page")
        for field in ("page_template_id", "single_page_template_id"):
            with pytest.raises(AppException) as raised:
                spec.create_sheet(
                    db,
                    c["document"],
                    source=c["issue"].id,
                    cover_template_id=t["cover"].id,
                    **{"page_template_id": t["page"].id, field: foreign.id},
                    user_id=c["owner"],
                )
            assert (raised.value.status_code, raised.value.code) == (422, "spec_sheet_template_invalid")

        sheet = _make(db, c, templates=t)
        sheet.page_template_id = foreign.id  # e.g. a template reassigned after the sheet was made
        db.flush()
        with pytest.raises(AppException) as raised:
            spec.update_sheet(db, sheet, {"use_latest_templates": True})
        assert raised.value.code == "spec_sheet_template_invalid"


def test_s2_backfill_skips_a_cross_company_or_wrong_family_template():
    from app.models.projects import ProjectQuotationSpecSheet

    migration = _migration()
    with blank_session() as db:
        env = _setup(db)
        t = _templates(db, env)
        foreign = _other_company_template(db, "spec_page")
        doc_a, _s, _p, issue_a = _issued_doc(db, env)
        doc_a.spec_sheet = {"cover_template_id": t["cover"].id, "page_template_id": foreign.id, "rows": []}
        doc_b, _s2, _p2, issue_b = _issued_doc(db, env)
        # Right company, wrong family (a page template used as the cover).
        doc_b.spec_sheet = {"cover_template_id": t["page"].id, "page_template_id": t["page"].id, "rows": []}
        db.flush()
        migration.backfill(db.connection())
        db.expire_all()
        for doc in (doc_a, doc_b):
            assert (
                db.query(ProjectQuotationSpecSheet).filter(ProjectQuotationSpecSheet.document_id == doc.id).count()
                == 0
            )


def _asset(db, company_id):
    from app.models.dealer_kit import Asset
    from ._pg_fixture import unique_code

    from .test_project_quotation_pdf import _attachment

    att = _attachment(db, company_id, "logo.png")
    row = Asset(id=_uid(), company_id=company_id, name=unique_code("LOGO"), kind="logo", attachment_id=att.id)
    db.add(row)
    db.flush()
    return row


def _asset_layer(asset_id):
    return {
        "id": f"a-{asset_id[:6]}",
        "type": "image",
        "props": {"kind": "image", "source": {"type": "asset", "assetId": asset_id}},
    }


def test_sf8_a_page_edit_may_name_a_template_or_same_company_asset_and_it_is_signed(monkeypatch):
    from app.services import project_spec_sheet_service as spec
    from app.services.dealer_kit import asset_service

    asked = []
    monkeypatch.setattr(
        asset_service, "urls_for", lambda db, ids: asked.append(set(ids)) or {i: f"https://x/{i}" for i in ids}
    )
    with blank_session() as db:
        c = _chain(db)
        own = _template(db, c["company_id"], "spec_page", layers=[_asset_layer("asset-in-template")])
        t = _templates(db, c)
        t["page"], t["single"] = own, own
        sheet = _make(db, c, templates=t)
        logo = _asset(db, c["company_id"])
        spec.save_page_edit(db, sheet, c["basin"].id, [_asset_layer(logo.id), _asset_layer("asset-in-template")])
        spec.build_print_payload(db, sheet)
        assert asked[-1] == {"asset-in-template", logo.id}


def test_sf8_another_companys_asset_is_refused_at_save():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException
    from app.models.company import Company
    from ._pg_fixture import unique_code

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        other = Company(id=_uid(), name="ZZT Other", code=unique_code("OTH")[:20])
        db.add(other)
        db.flush()
        foreign = _asset(db, other.id)
        for asset_id in (foreign.id, "asset-nobody-has"):
            with pytest.raises(AppException) as raised:
                spec.save_page_edit(db, sheet, c["basin"].id, [_asset_layer(asset_id)])
            assert (raised.value.status_code, raised.value.code) == (422, "spec_sheet_page_edit_invalid")


def test_n2_n3_the_page_routes_use_page_key_and_the_design_route_needs_a_writable_project():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert any("/spec-sheets/{sheet_id}/pages/{page_key" in p and p.endswith("/design") for p in paths)
    assert any("/spec-sheets/{sheet_id}/pages/{page_key" in p and p.endswith("/edit") for p in paths)
    assert not any("/pages/{key" in p for p in paths)

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        stranger = _uid()
        client, originals = _client(db, stranger, slugs=EDIT_SLUGS[:2])  # view + edit, no manage, not the owner
        try:
            got = client.get(_base(c, f"/{sheet.id}/pages/{c['basin'].id}/design"))
            assert got.status_code == 403, got.text
        finally:
            _restore(originals)


def test_n4_reset_page_refuses_a_page_key_the_sheet_does_not_have():
    from app.models.base import company_scope

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        sheet_id = sheet.id
        db.commit()
        with company_scope(db, frozenset({c["company_id"]})):
            client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
            try:
                for bad in ("set:not-a-page", "x" * 121):
                    refused = _park(client, "quotation_spec_sheet.reset_page", sheet_id, {"page_key": bad})
                    assert refused.status_code == 422, refused.text
                ok = _park(client, "quotation_spec_sheet.reset_page", sheet_id, {"page_key": "cover"})
                assert ok.status_code == 202, ok.text
            finally:
                _restore(originals)


# ------------------------------------------------------------------ code review round (fix round 3)


def test_b2_a_main_page_without_a_frozen_photo_prints_the_products_chosen_files(monkeypatch):
    from app.services import project_spec_sheet_service as spec

    from .test_project_quotation_pdf import _attachment

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        photo = _attachment(db, c["company_id"], "chosen.png")
        drawing = _attachment(db, c["company_id"], "first-drawing.png")
        # A backfilled sheet froze no media on its items.
        sheet.items = [{**i, "image_attachment_id": None, "drawing_attachment_id": None} for i in sheet.items]
        db.flush()
        monkeypatch.setattr(
            spec, "_files", lambda db, ids: {str(i): {"photo": photo.id, "drawing": drawing.id} for i in ids}
        )
        monkeypatch.setattr(
            spec, "_sign", lambda db, ids, full=False: {i: f"https://signed.zzt.test/{i}" for i in ids if i}
        )
        row = spec.build_print_payload(db, sheet)["resolvedData"][c["basin"].id]
        assert row["images"][0]["attachment_id"] == photo.id
        assert row["drawing"]["attachment_id"] == drawing.id


def test_b3_backfill_drops_an_unusable_single_template_and_keeps_the_sheet():
    from app.models.projects import ProjectQuotationSpecSheet

    migration = _migration()
    with blank_session() as db:
        env = _setup(db)
        t = _templates(db, env)
        foreign = _other_company_template(db, "spec_page")
        unpublished = _template(db, env["company_id"], "spec_page", published=False)
        wrong_family = _template(db, env["company_id"], "wc")
        docs = []
        for single_id in (foreign.id, unpublished.id, wrong_family.id, _uid()):
            doc, _s, _p, _i = _issued_doc(db, env)
            doc.spec_sheet = {
                "cover_template_id": t["cover"].id,
                "page_template_id": t["page"].id,
                "single_page_template_id": single_id,
                "rows": [],
            }
            docs.append(doc)
        db.flush()
        migration.backfill(db.connection())
        db.expire_all()
        for doc in docs:
            (sheet,) = (
                db.query(ProjectQuotationSpecSheet).filter(ProjectQuotationSpecSheet.document_id == doc.id).all()
            )
            assert sheet.single_page_template_id is None and sheet.single_version_id is None
            assert sheet.cover_version_id == t["cover"].published_version_id


def test_sf1_a_create_that_collides_on_the_sheet_number_retries_with_a_fresh_number(monkeypatch):
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        _make(db, c, templates=t)  # SS1
        real = spec._next_sheet_no
        calls = []

        def stale_first(db_, document):
            calls.append(1)
            return 1 if len(calls) == 1 else real(db_, document)

        monkeypatch.setattr(spec, "_next_sheet_no", stale_first)
        second = _make(db, c, templates=t)
        assert second.sheet_no == 2 and len(calls) == 2


def test_sf2_an_editor_without_write_access_to_the_project_is_refused_everywhere():
    from app.models.base import company_scope

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        sheet = _make(db, c, templates=t)
        key = c["basin"].id
        sheet_id = sheet.id
        db.commit()
        with company_scope(db, frozenset({c["company_id"]})):
            client, originals = _client(db, _uid(), slugs=EDIT_SLUGS[:2])  # edit right, not owner/collaborator
            try:
                body = {"source": c["issue"].id, "cover_template_id": t["cover"].id, "page_template_id": t["page"].id}
                assert client.post(_base(c), json=body).status_code == 403
                assert client.patch(_base(c, f"/{sheet_id}"), json={"rows": []}).status_code == 403
                assert client.put(_base(c, f"/{sheet_id}/pages/{key}/edit"), json={"layers": []}).status_code == 403
                parked = _park(client, "quotation_spec_sheet.delete", sheet_id)
                assert parked.status_code == 403, parked.text
            finally:
                _restore(originals)


def test_sf3_hints_show_malaysia_time():
    from datetime import datetime

    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        # 17:00 UTC on 2 Nov is 01:00 on 3 Nov in Malaysia.
        c["issue"].issued_at = datetime(2026, 11, 2, 17, 0)
        sheet = _make(db, c, source="draft")
        sheet.items_taken_at = datetime(2026, 11, 2, 17, 0)
        db.flush()
        assert spec.sources(db, c["document"])[-1]["hint"] == "issued 03 Nov 2026"
        label, hint = spec.source_text(db, c["document"], sheet)
        assert hint == "lines taken 03 Nov 2026 01:00"


def test_sf7_the_list_costs_the_same_number_of_queries_for_one_sheet_and_for_many_issues():
    from sqlalchemy import event

    from app.models.projects import ProjectQuotation
    from app.services import project_quotation_service as quotes
    from app.services import project_spec_sheet_service as spec

    def count(db, c):
        seen = []
        bind = db.get_bind()

        def hook(conn, cursor, statement, *a):
            seen.append(statement)

        event.listen(bind, "before_cursor_execute", hook)
        try:
            db.expire_all()
            spec.list_view(db, c["document"], c["owner"])
        finally:
            event.remove(bind, "before_cursor_execute", hook)
        return len(seen)

    with blank_session() as db:
        c = _chain(db)
        t = _templates(db, c)
        _make(db, c, templates=t)  # SS1 on issue 1
        one = count(db, c)

        def next_issue():
            quotes.revise(db, quotation=db.get(ProjectQuotation, c["scope"].id), actor_user_id=c["owner"])
            return _issue(db, c["document"], c["owner"])

        _make(db, c, templates=t)  # SS2, issue 1
        _make(db, c, templates=t, source="draft")  # draft based on issue 1
        issue2 = next_issue()
        _make(db, c, templates=t, source=issue2.id)  # issue 2
        _make(db, c, templates=t, source=issue2.id)
        _make(db, c, templates=t, source="draft")  # draft based on issue 2
        issue3 = next_issue()
        _make(db, c, templates=t, source=issue3.id)  # issue 3
        many = count(db, c)
        assert many == one, (one, many)


def test_nit_a_quotation_with_only_heading_lines_cannot_create():
    from app.models.projects import ProjectQuotationLine

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        scope = _scope(db, env, document)
        product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} to blank")
        line = _line(db, env, scope, {"product_id": product.id})
        row = db.get(ProjectQuotationLine, line.id)
        row.product_id = None
        row.product_code_snapshot = None
        row.band_label = "UNIT"
        db.flush()
        client, originals = _client(db, env["owner"], slugs=EDIT_SLUGS)
        try:
            c = {**env, "document": document}
            body = client.get(_base(c)).json()
            assert body["create_disabled_reason"] == "Add a line to the quotation first."
        finally:
            _restore(originals)


def test_nit_the_draft_is_offered_when_a_scope_of_the_newest_issue_is_gone(monkeypatch):
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        assert spec.sources(db, c["document"])[0]["value"] == c["issue"].id
        monkeypatch.setattr(qdocs, "list_scopes", lambda db_, document: [])
        assert spec.sources(db, c["document"])[0]["value"] == "draft"


def test_nit_page_keys_with_a_slash_or_comma_work_through_the_routes():
    from app.models.projects import ProjectQuotationLine

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        scope = _scope(db, env, document)
        product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} odd code")
        line = _line(db, env, scope, {"product_id": product.id})
        row = db.get(ProjectQuotationLine, line.id)
        row.product_id = None
        row.product_code_snapshot = "AB/12,X"
        row.description_snapshot = "Odd code"
        db.flush()
        issue = _issue(db, document, env["owner"])
        c = {**env, "document": document, "issue": issue}
        sheet = _make(db, c)
        key = "code:AB/12,X"
        assert [i["key"] for i in sheet.items] == [key]
        client, originals = _client(db, env["owner"], slugs=EDIT_SLUGS)
        try:
            ok = client.get(_base(c, f"/{sheet.id}/preview"), params=[("key", "cover"), ("key", key)])
            assert ok.status_code == 200, ok.text
            assert [t["request_tag_id"] for t in _tags(ok.json())] == ["cover", key]
            from urllib.parse import quote

            quoted = quote(key, safe="")
            design = client.get(_base(c, f"/{sheet.id}/pages/{quoted}/design"))
            assert design.status_code == 200, design.text
            put = client.put(_base(c, f"/{sheet.id}/pages/{quoted}/edit"), json={"layers": []})
            assert put.status_code == 200, put.text
        finally:
            _restore(originals)


@pytest.mark.parametrize(
    "props",
    [
        "a string",
        ["a", "list"],
        {"kind": "image", "assetId": ["x"]},
        {"kind": "image", "assetId": {"id": "x"}},
        {"kind": "image", "source": {"type": "asset", "assetId": ["x"]}},
        {"kind": "image", "source": {"type": "asset", "assetId": {"id": "x"}}},
        {"kind": "image", "source": "a string"},
    ],
)
def test_malformed_props_or_asset_ids_answer_422_and_store_nothing(props):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, c["basin"].id, [{"id": "l1", "type": "image", "props": props}])
        assert (raised.value.status_code, raised.value.code) == (422, "spec_sheet_page_edit_invalid")
        assert sheet.page_edits == {}
