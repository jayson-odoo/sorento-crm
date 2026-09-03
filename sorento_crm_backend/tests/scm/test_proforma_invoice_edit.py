"""The proforma invoice edited as a DOCUMENT: one Save, one write.

The detail screen holds a local draft - a line removed is struck through, a line added is a
blank row, and nothing reaches the server until Save - so the write it makes is
`update_invoice`: the number, the container size and the WHOLE line array in one call. Rows
carrying an id update, rows without one are created, and a line the array no longer names is
deleted. Sending them one at a time is what left a half-applied invoice on screen when the
third line was refused.

Also covers the two things that had nowhere to go before: the line's stated weights
(净重 / 毛重, migration 435) and the list screen's search box.

Runs on the REAL Postgres via `pg_session` (rolled back at teardown) like its neighbours,
because the reader resolves its header aliases from the alias table - so this suite also
proves migration 435's seed was applied rather than merely written. Every row is seeded under
the shared `ZZPIV` marker; nothing is borrowed.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.scm import ContainerSize, ProformaInvoice, SupplierProductCodeAlias
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service as svc
from app.services.scm import supplier_code_alias_service
from tests._pg_fixture import pg_session
from tests.scm.fixtures.proforma_shapes import kailu_proforma_workbook
from tests.scm.test_proforma_invoice_adjust import _apply_preloading, _seed_container_sizes
from tests.scm.test_proforma_invoice_import import World, _invoices, _lines


def _draft_from(lines) -> list[dict]:
    """The line array the edit screen would send back untouched - every stored line, with
    exactly the fields the PUT accepts."""
    return [
        {
            "id": str(ln.id),
            "product_id": str(ln.product_id) if ln.product_id else None,
            "item_code": ln.item_code,
            "description": ln.description,
            "qty": float(ln.qty),
            "uom": ln.uom,
            "cartons": None if ln.cartons is None else float(ln.cartons),
            "cbm_per_unit": None if ln.cbm_per_unit is None else float(ln.cbm_per_unit),
            "unit_price": None if ln.unit_price is None else float(ln.unit_price),
            "net_weight": None if ln.net_weight is None else float(ln.net_weight),
            "gross_weight": None if ln.gross_weight is None else float(ln.gross_weight),
        }
        for ln in lines
    ]


# --------------------------------------------------------------------------------- #
# The weights the document states (migration 435)
# --------------------------------------------------------------------------------- #


def test_the_preloading_list_stores_the_weights_it_states():
    with pg_session() as db:
        w = World(db)
        invoice = _apply_preloading(db, w)[0]

        line = _lines(db, invoice.id)[0]
        assert float(line.net_weight) == pytest.approx(40)
        assert float(line.gross_weight) == pytest.approx(50)


def test_a_document_stating_no_weight_stores_null_never_zero():
    """Kailu's proforma prints no weight column at all - and an unstated weight is a
    different answer from a weightless line, the same rule the volume columns follow."""
    with pg_session() as db:
        w = World(db)
        svc.apply(
            db,
            kailu_proforma_workbook({"SRTWT7443": w.code("A")}),
            supplier_id=str(w.supplier.id),
        )

        for line in _lines(db, _invoices(db, w)[0].id):
            assert line.net_weight is None
            assert line.gross_weight is None


def test_the_serialized_line_carries_its_weights():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]

        out = svc.serialize(db, invoice)

        assert out["lines"][0]["net_weight"] == pytest.approx(40)
        assert out["lines"][0]["gross_weight"] == pytest.approx(50)


# --------------------------------------------------------------------------------- #
# AC-B1 / AC-B3 - the edit screen's Product select has an id to show, and Save cannot
# silently unbind a match it never touched (S2, issue #579)
# --------------------------------------------------------------------------------- #


def test_the_serialized_line_carries_product_id_and_product_set_id():
    """AC-B1: alongside `product_code` / `set_code`, so the edit screen's Product select has
    an id to pre-select rather than reading empty on every open."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]

        out = svc.serialize(db, invoice)

        matched = next(ln for ln in out["lines"] if ln["item_code"] == w.code("A"))
        assert matched["product_id"] == str(w.product("A").id)
        assert matched["product_set_id"] is None


def test_a_line_omitting_the_product_id_key_keeps_its_match():
    """AC-B3(a) - RED without the fix: the edit screen's Save omits `product_id` on every
    line the operator did not touch, which is exactly the shape a bare `model_dump()` cannot
    tell apart from "unbind this". A quantity change on an unrelated line must not sweep
    every other line's match away with it."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        matched_line = next(
            ln for ln in _lines(db, invoice.id) if ln.item_code == w.code("A")
        )
        assert matched_line.product_id is not None

        draft = _draft_from(_lines(db, invoice.id))
        for row in draft:
            row.pop("product_id", None)
            if row["id"] != str(matched_line.id):
                row["qty"] = float(row["qty"]) + 1

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        after = next(ln for ln in out["lines"] if ln["id"] == str(matched_line.id))
        assert after["product_id"] == str(matched_line.product_id)
        assert after["matched"] is True


def test_a_line_with_an_explicit_null_product_id_unbinds_it():
    """AC-B3(b): `product_id: null` sent ON PURPOSE is the operator clearing the select, and
    that has to actually unbind - the fix for (a) must not swing the other way and ignore a
    real clear."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        matched_line = next(
            ln for ln in _lines(db, invoice.id) if ln.item_code == w.code("A")
        )

        draft = _draft_from(_lines(db, invoice.id))
        for row in draft:
            if row["id"] == str(matched_line.id):
                row["product_id"] = None

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        after = next(ln for ln in out["lines"] if ln["id"] == str(matched_line.id))
        assert after["product_id"] is None
        assert after["matched"] is False
        db.refresh(matched_line)
        assert matched_line.product_id is None


def test_a_line_given_a_new_product_id_rebinds_it():
    """AC-B3(c): picking a different product in edit mode is a real rebind, not just a
    survive-the-save no-op."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        matched_line = next(
            ln for ln in _lines(db, invoice.id) if ln.item_code == w.code("A")
        )
        other = w.product("ZZ-OTHER")
        assert str(matched_line.product_id) != str(other.id)

        draft = _draft_from(_lines(db, invoice.id))
        for row in draft:
            if row["id"] == str(matched_line.id):
                row["product_id"] = str(other.id)

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        after = next(ln for ln in out["lines"] if ln["id"] == str(matched_line.id))
        assert after["product_id"] == str(other.id)
        assert after["product_code"] == other.product_code


# --------------------------------------------------------------------------------- #
# AC-C1 / AC-C2 - a product picked (or cleared) in edit mode is remembered as the
# supplier's own code alias, the same memory the in-row Match/Change/Forget writes (S3,
# issue #582, ruling 2 of PLAN-scm-pi-packing-list-feedback-3sep.md)
# --------------------------------------------------------------------------------- #


def _alias(db, supplier_id: str, code: str) -> SupplierProductCodeAlias | None:
    return (
        db.query(SupplierProductCodeAlias)
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.supplier_code.ilike(code),
        )
        .first()
    )


def _upload_kailu(db, w: World, item_code_map: dict | None = None):
    """The Kailu file. `item_code_map` substitutes a real Sorento code (Kailu writes OUR
    codes directly, unlike Jinbaichuan's own spelling) with a `w`-scoped one, so the line
    lands genuinely unmatched rather than exact-matching whatever the shared dev database
    already holds under that code."""
    svc.apply(
        db,
        kailu_proforma_workbook(item_code_map),
        supplier_id=str(w.supplier.id),
        actor="Ms Tee",
    )
    return _invoices(db, w)[0]


def test_a_changed_product_upserts_a_manual_alias_and_rebinds_every_sibling_line():
    """AC-C1: the picked product is remembered as a `manual` alias for the supplier's own
    code, and every OTHER current line of that supplier carrying the same code re-binds -
    the sibling on the SAME invoice (Kailu states its `SRTWT7443` line twice) and one on a
    second, unrelated invoice of the same supplier."""
    with pg_session() as db:
        w = World(db)
        code = f"ZZPI-DUP-{w.tag}"
        invoice_one = _upload_kailu(db, w, {"SRTWT7443": code})
        # Free the derived number so a second Kailu upload lands as a NEW invoice rather
        # than a revision of this one - two current invoices of the same supplier, both
        # carrying a line under `code`.
        svc.update_invoice(db, str(invoice_one.id), pi_number="ZZPI-ONE")
        invoice_two = _upload_kailu(db, w, {"SRTWT7443": code})
        assert str(invoice_two.id) != str(invoice_one.id)

        lines_one = [ln for ln in _lines(db, invoice_one.id) if ln.item_code == code]
        lines_two = [ln for ln in _lines(db, invoice_two.id) if ln.item_code == code]
        assert len(lines_one) == 2  # the sibling on the SAME invoice
        assert len(lines_two) >= 1  # the sibling on the OTHER invoice
        assert all(ln.product_id is None for ln in lines_one + lines_two)
        picked_line, sibling_line = lines_one
        product_a = w.product("A")

        # The real edit screen sends `product_id` ONLY for the line the operator actually
        # touched (S2, `saveEdit`) - every other row's key is ABSENT, "leave alone", not a
        # redundant echo of what it already held.
        draft = _draft_from(_lines(db, invoice_one.id))
        for row in draft:
            if row["id"] == str(picked_line.id):
                row["product_id"] = str(product_a.id)
            else:
                row.pop("product_id", None)

        out = svc.update_invoice(db, str(invoice_one.id), lines=draft, actor="Ms Tee")

        after = next(ln for ln in out["lines"] if ln["id"] == str(picked_line.id))
        assert after["product_id"] == str(product_a.id)
        assert after["matched"] is True

        alias = _alias(db, w.supplier.id, code)
        assert alias is not None
        assert alias.source == "manual"
        assert str(alias.product_id) == str(product_a.id)

        db.refresh(sibling_line)
        assert str(sibling_line.product_id) == str(product_a.id)
        for ln in lines_two:
            db.refresh(ln)
            assert str(ln.product_id) == str(product_a.id)


def test_clearing_a_line_deletes_its_manual_alias():
    """AC-C2(a): a `null` sent on purpose unbinds the line, and the manual alias behind it
    is deleted - the inverse of picking a product in edit mode."""
    with pg_session() as db:
        w = World(db)
        code = f"ZZPI-DUP-{w.tag}"
        invoice = _upload_kailu(db, w, {"SRTWT7443": code})
        product_a = w.product("A")
        supplier_code_alias_service.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=code,
            product_id=str(product_a.id),
            actor="setup",
        )
        line = next(ln for ln in _lines(db, invoice.id) if ln.item_code == code)
        assert str(line.product_id) == str(product_a.id)

        draft = _draft_from(_lines(db, invoice.id))
        for row in draft:
            if row["id"] == str(line.id):
                row["product_id"] = None
            else:
                row.pop("product_id", None)

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        after = next(ln for ln in out["lines"] if ln["id"] == str(line.id))
        assert after["product_id"] is None
        assert after["matched"] is False
        assert _alias(db, w.supplier.id, code) is None


def test_clearing_a_line_leaves_an_auto_alias_on_file():
    """AC-C2(b): a bind the LADDER worked out (source `auto`) is not what the operator's
    clear is undoing - only a `manual` alias is that operator's own decision to take back."""
    with pg_session() as db:
        w = World(db)
        code = f"ZZPI-DUP2-{w.tag}"
        invoice = _upload_kailu(db, w, {"SRTWT8203": code})
        product_b = w.product("B")
        auto_alias = SupplierProductCodeAlias(
            id=str(uuid.uuid4()),
            supplier_id=str(w.supplier.id),
            supplier_code=code,
            product_id=str(product_b.id),
            source="auto",
            matched_by="separator",
        )
        db.add(auto_alias)
        line = next(ln for ln in _lines(db, invoice.id) if ln.item_code == code)
        line.product_id = str(product_b.id)
        db.flush()

        draft = _draft_from(_lines(db, invoice.id))
        for row in draft:
            if row["id"] == str(line.id):
                row["product_id"] = None
            else:
                row.pop("product_id", None)

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        after = next(ln for ln in out["lines"] if ln["id"] == str(line.id))
        assert after["product_id"] is None

        still_there = _alias(db, w.supplier.id, code)
        assert still_there is not None
        assert still_there.source == "auto"
        assert str(still_there.product_id) == str(product_b.id)


# --------------------------------------------------------------------------------- #
# One PUT: create, update and delete in the same call
# --------------------------------------------------------------------------------- #


def test_one_call_updates_creates_and_deletes_lines_together():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[2]
        before = _lines(db, invoice.id)
        assert len(before) >= 2

        draft = _draft_from(before)
        # Kept and changed.
        draft[0]["qty"] = 100
        # Struck through in the draft, so it simply is not in the array.
        removed_code = draft[1]["item_code"]
        del draft[1]
        # Added by hand, with no id at all.
        draft.append(
            {
                "product_id": str(w.product("A").id),
                "item_code": w.code("A"),
                "description": "Added by hand",
                "qty": 7,
                "uom": "PCS",
                "cartons": 2,
                "cbm_per_unit": 0.5,
                "unit_price": 11,
                "net_weight": 3.5,
                "gross_weight": 4.25,
            }
        )

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        codes = [ln["item_code"] for ln in out["lines"]]
        assert removed_code not in codes
        assert w.code("A") in codes
        assert out["line_count"] == len(before)  # one out, one in
        changed = next(ln for ln in out["lines"] if ln["id"] == draft[0]["id"])
        assert changed["qty"] == 100


def test_an_added_line_keeps_every_figure_it_was_given():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]

        draft = _draft_from(_lines(db, invoice.id))
        draft.append(
            {
                "product_id": str(w.product("B").id),
                "item_code": w.code("B"),
                "description": "Hand-added",
                "qty": 4,
                "uom": "SET",
                "cartons": 2,
                "cbm_per_unit": 0.25,
                "unit_price": 30,
                "net_weight": 9,
                "gross_weight": 11,
            }
        )

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        added = next(ln for ln in out["lines"] if ln["item_code"] == w.code("B"))
        assert added["qty"] == 4
        assert added["uom"] == "SET"
        assert added["cartons"] == 2
        assert added["unit_price"] == 30
        assert added["net_weight"] == 9
        assert added["gross_weight"] == 11
        assert added["matched"] is True
        # Derived from the per-unit figures, never taken on trust from the browser.
        assert added["amount"] == pytest.approx(120)
        assert added["cbm_total"] == pytest.approx(1)


def test_an_added_line_is_appended_never_renumbered_over_a_gap():
    """`line_no` is where the line sat on the paper the supplier sent, so a removed line
    leaves its gap and the new one lands after the highest number in use."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[2]
        before = _lines(db, invoice.id)
        highest = max(int(ln.line_no) for ln in before)

        draft = _draft_from(before)
        del draft[0]
        draft.append({"item_code": "HAND-1", "qty": 1})

        svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        after = _lines(db, invoice.id)
        assert [int(ln.line_no) for ln in after][-1] == highest + 1


def test_saving_the_lines_restates_the_total_and_stamps_who():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        draft = _draft_from(_lines(db, invoice.id))
        draft[0]["qty"] = 380

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        assert out["total_amount"] == pytest.approx(250 * 380)
        assert out["total_cbm"] == pytest.approx(0.17 * 380)
        assert out["adjusted_by"] == "Ms Tee"
        assert out["is_adjusted"] is True


def test_the_suppliers_own_figures_survive_a_save():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        draft = _draft_from(_lines(db, invoice.id))
        draft[0]["qty"] = 380
        draft[0]["unit_price"] = 240

        out = svc.update_invoice(db, str(invoice.id), lines=draft, actor="Ms Tee")

        assert out["lines"][0]["supplier_qty"] == 408
        assert out["lines"][0]["supplier_unit_price"] == 250


def test_a_line_belonging_to_another_invoice_is_a_404_not_a_silent_write():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)
        stranger = _draft_from(_lines(db, invoices[1].id))

        with pytest.raises(AppException) as exc:
            svc.update_invoice(db, str(invoices[0].id), lines=stranger, actor="x")
        assert exc.value.status_code == 404


def test_a_negative_quantity_is_refused_and_nothing_lands():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        draft = _draft_from(_lines(db, invoice.id))
        draft[0]["qty"] = -1

        with pytest.raises(AppException) as exc:
            svc.update_invoice(db, str(invoice.id), lines=draft, actor="x")
        assert exc.value.status_code == 422


def test_the_container_size_travels_in_the_same_save():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        small = db.query(ContainerSize).filter(ContainerSize.code == "20GP").one()

        out = svc.update_invoice(
            db,
            str(invoice.id),
            container_size_id=str(small.id),
            lines=_draft_from(_lines(db, invoice.id)),
            actor="Ms Tee",
        )

        assert out["container_size_code"] == "20GP"


def test_a_field_the_caller_never_mentions_is_left_alone():
    """`container_size_id: null` means the tenant default; saying nothing means keep what
    this invoice already chose. The two must not collapse into one instruction."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        small = db.query(ContainerSize).filter(ContainerSize.code == "20GP").one()
        svc.set_container_size(db, str(invoice.id), str(small.id))

        out = svc.update_invoice(db, str(invoice.id), pi_number=invoice.pi_number)

        assert out["container_size_code"] == "20GP"


# --------------------------------------------------------------------------------- #
# The PI number, corrected by hand
# --------------------------------------------------------------------------------- #


def test_the_pi_number_can_be_corrected():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]

        out = svc.update_invoice(db, str(invoice.id), pi_number="  PI-REAL-001  ")

        assert out["pi_number"] == "PI-REAL-001"
        db.refresh(invoice)
        assert invoice.pi_number == "PI-REAL-001"


def test_renaming_onto_another_invoice_of_the_same_supplier_is_refused():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)
        taken = invoices[1].pi_number

        with pytest.raises(AppException) as exc:
            svc.update_invoice(db, str(invoices[0].id), pi_number=taken)

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "duplicate_pi_number"
        db.refresh(invoices[0])
        assert invoices[0].pi_number != taken


def test_a_blank_pi_number_is_refused():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]

        with pytest.raises(AppException) as exc:
            svc.update_invoice(db, str(invoice.id), pi_number="   ")
        assert exc.value.status_code == 422


def test_saving_the_same_number_back_is_not_a_clash_with_itself():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]

        out = svc.update_invoice(db, str(invoice.id), pi_number=invoice.pi_number)

        assert out["pi_number"] == invoice.pi_number


# --------------------------------------------------------------------------------- #
# The two documents that are read-only refuse the whole save
# --------------------------------------------------------------------------------- #


def test_a_converted_invoice_refuses_the_save():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]
        svc.convert_to_draft_shipment(db, [str(invoice.id)])

        with pytest.raises(AppException) as exc:
            svc.update_invoice(db, str(invoice.id), pi_number="PI-NEW-1")

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "already_converted"


def test_a_superseded_revision_refuses_the_save():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        invoice.status = "superseded"
        db.flush()

        with pytest.raises(AppException) as exc:
            svc.update_invoice(
                db, str(invoice.id), lines=_draft_from(_lines(db, invoice.id))
            )

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "superseded"


# --------------------------------------------------------------------------------- #
# The list screen's search box
# --------------------------------------------------------------------------------- #


def _searched(db, w: World, needle: str) -> list[str]:
    out = svc.list_for_supplier(
        db, supplier_id=str(w.supplier.id), query=needle, limit=100
    )
    return [row["pi_number"] for row in out["data"]]


def test_the_search_finds_an_invoice_by_its_number():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        svc.update_invoice(db, str(invoice.id), pi_number="PI-FINDME-77")

        assert _searched(db, w, "findme") == ["PI-FINDME-77"]


def test_the_search_finds_an_invoice_by_its_container_and_bl():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        invoice.container_ref = "FSCU8103365"
        invoice.bl_ref = "BL-ZZ-4412"
        db.flush()

        assert invoice.pi_number in _searched(db, w, "fscu810")
        assert invoice.pi_number in _searched(db, w, "zz-4412")


def test_the_search_finds_every_invoice_of_a_supplier_by_name():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)

        found = svc.list_for_supplier(db, query=w.supplier.supplier_name, limit=100)

        assert found["total"] == len(invoices)


def test_a_needle_nothing_matches_returns_nothing_rather_than_everything():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        _apply_preloading(db, w)

        out = svc.list_for_supplier(
            db, supplier_id=str(w.supplier.id), query="zzzz-no-such-thing", limit=100
        )

        assert out["total"] == 0
        assert out["data"] == []


def test_the_total_counts_the_matches_not_the_page():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)

        out = svc.list_for_supplier(
            db, supplier_id=str(w.supplier.id), query=w.supplier.supplier_code, limit=2
        )

        assert out["total"] == len(invoices)
        assert len(out["data"]) == 2


def test_the_search_and_the_placement_filter_narrow_together():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)
        svc.convert_to_draft_shipment(db, [str(invoices[4].id)])

        out = svc.list_for_supplier(
            db,
            supplier_id=str(w.supplier.id),
            placement="converted",
            query=w.supplier.supplier_code,
            limit=100,
        )

        assert [row["pi_number"] for row in out["data"]] == [invoices[4].pi_number]


def test_an_invoice_of_another_supplier_is_not_swept_in_by_the_needle():
    with pg_session() as db:
        _seed_container_sizes(db)
        mine = World(db)
        theirs = World(db)
        _apply_preloading(db, mine)
        _apply_preloading(db, theirs)

        out = svc.list_for_supplier(db, query=theirs.supplier.supplier_code, limit=100)

        ids = {row["supplier_id"] for row in out["data"]}
        assert ids == {str(theirs.supplier.id)}


def test_the_unfiltered_list_is_unchanged_by_an_empty_needle():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)

        out = svc.list_for_supplier(db, supplier_id=str(w.supplier.id), query="  ", limit=100)

        assert out["total"] == len(invoices)


def test_a_supplier_with_no_invoice_at_all_reads_as_none_found():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)

        out = svc.list_for_supplier(db, supplier_id=str(w.supplier.id), query="anything")

        assert out["total"] == 0


def test_the_invoice_row_still_carries_its_supplier_name_under_a_search():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        _apply_preloading(db, w)

        out = svc.list_for_supplier(db, query=w.supplier.supplier_name, limit=1)

        assert out["data"][0]["supplier_name"] == w.supplier.supplier_name


def test_the_search_is_case_insensitive():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]
        svc.update_invoice(db, str(invoice.id), pi_number="PI-Mixed-Case-9")

        assert _searched(db, w, "mixed-CASE") == ["PI-Mixed-Case-9"]


def test_nothing_but_the_named_invoices_survive_the_marker_scope():
    """Guard for the shared dev database: every row this file writes is one of the
    `World`'s own, so a query with no supplier filter still only counts what we seeded."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        _apply_preloading(db, w)

        out = svc.list_for_supplier(db, query=w.tag, limit=100)

        assert all(row["supplier_id"] == str(w.supplier.id) for row in out["data"])


def test_the_preloading_file_still_applies_after_the_weight_columns_land():
    """A blunt regression pin: the reader gained two fields, and the five-block file has to
    keep landing as five invoices with the lines it always had."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoices = _apply_preloading(db, w)

        assert len(invoices) == 5
        assert all(inv.line_count > 0 for inv in invoices)
        assert db.query(ProformaInvoice).filter(
            ProformaInvoice.supplier_id == w.supplier.id
        ).count() == 5


def test_a_workbook_re_read_twice_stores_the_same_weights():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        _apply_preloading(db, w)
        first = [
            (float(ln.net_weight or 0), float(ln.gross_weight or 0))
            for ln in _lines(db, _invoices(db, w)[0].id)
        ]

        _apply_preloading(db, w)
        second = [
            (float(ln.net_weight or 0), float(ln.gross_weight or 0))
            for ln in _lines(db, _invoices(db, w)[0].id)
        ]

        assert first == second
