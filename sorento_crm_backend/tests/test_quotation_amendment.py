"""QUOTE-CUSTOMER-AMEND: the customer suggests quantities and prices on the quotation link,
the salesperson decides each suggestion, and Apply drafts the next revision.

Written BEFORE the implementation (Phase 2, test-first) from
``documentation/plans/project-sales/quote-customer-amend-29oct-acceptance-criteria.md``
(AC-QCA-01..25) and the plan's "API contract". Every test is red until the module
``app.services.quotation_amendment_service``, the two models, the migration, the public and the
staff routes exist. The ids in the test names are the UAC ids.

Imports of the new module and models are LAZY (inside helpers) so that each test fails on its own
for its own reason instead of the whole file dying at collection.

Fixture world, all values invented:

    Scope "Block A": WC  ZZT-WC-1001   list 600.00  issued 120 x 400.00  floor 390.00
                     CON ZZT-CON-0001  list   0.00  issued 120 x   0.00  (zero-priced companion)
                     BSN ZZT-BSN-4004  list 200.00  issued 120 x 160.00  floor 130.00
                     SHW ZZT-SHW-5005  list  30.00  issued  10 x  25.00  floor  19.50
    Scope "Block B": TAP ZZT-TAP-7007  list 100.00  issued   5 x  90.00  floor  65.00

The floor is one company rule, 65 percent of list. Postgres only, via ``blank_session``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.models.numbering import DocumentNumberingRule
from app.models.notification import Notification
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import (
    PriceFloorRule,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationVersion,
)
from app.models.status import Status
from app.models.user import User
from app.services import project_quotation_document_service as qdocs
from app.services import project_quotation_service as quotes
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-qamend"
A_SIGNATURE = "data:image/png;base64,zzt-strokes"
NOTE = "Please match the project rate agreed on site."
CUSTOMER = f"{MARKER} Kelly"
CUSTOMER_IP = "203.0.113.7"

BASE = "/api/v1/project-sales"
PUBLIC = "/api/v1/public/quotation-sign"

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
APPROVE = "projects.quotations.approve"
EVERYTHING = {
    VIEW,
    EDIT,
    "projects.projects.delete",
    "projects.projects.manage",
    APPROVE,
}

# code, list price, issued unit price, issued quantity
SPECS = {
    "WC": ("ZZT-WC-1001", "600.00", "400.00", "120"),
    "CON": ("ZZT-CON-0001", "0.00", "0.00", "120"),
    "BSN": ("ZZT-BSN-4004", "200.00", "160.00", "120"),
    "SHW": ("ZZT-SHW-5005", "30.00", "25.00", "10"),
    "TAP": ("ZZT-TAP-7007", "100.00", "90.00", "5"),
}


# ------------------------------------------------------------------ lazy contract imports


def _svc():
    from app.services import quotation_amendment_service as amend

    return amend


def _models():
    from app.models import projects as m

    return m.QuotationAmendmentRequest, m.QuotationAmendmentRequestRow


# ------------------------------------------------------------------ world


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
    rule = (
        db.query(DocumentNumberingRule)
        .filter(DocumentNumberingRule.doc_type == "project_quotation")
        .first()
    )
    if rule is None:
        rule = DocumentNumberingRule(id=_uid(), doc_type="project_quotation")
        if hasattr(DocumentNumberingRule, "company_id"):
            rule.company_id = company_id
        db.add(rule)
    if rule.prefix_template == f"{MARKER}/Q/" and rule.enabled:
        return  # a second world in the same session keeps counting, never restarts at 0001
    rule.enabled = True
    rule.prefix_template = f"{MARKER}/Q/"
    rule.number_digits = 4
    rule.next_value = 1
    rule.start_value = 1
    rule.reset_policy = "none"
    rule.last_reset_key = None
    db.flush()


def _product(db, code: str, list_price: str) -> Product:
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} Sanitary"
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{uuid.uuid4().hex}", uom_name="Piece")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal(list_price),
    )
    db.add(product)
    db.flush()
    return product


def _floor_rule(db, company_id: str) -> None:
    exists = (
        db.query(PriceFloorRule)
        .filter(PriceFloorRule.mode == "percent", PriceFloorRule.value == Decimal("65.00"))
        .first()
    )
    if exists is None:
        db.add(
            PriceFloorRule(
                id=_uid(), company_id=company_id, mode="percent", value=Decimal("65.00")
            )
        )
        db.flush()


def _price_line(db, scope, owner: str, key: str, tag: str):
    code, list_price, price, qty = SPECS[key]
    product = _product(db, f"{code}{tag}", list_price)
    return quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={"product_id": product.id, "unit_price": price, "quantity": qty},
    )


def _world(db, tag: str = "") -> SimpleNamespace:
    """A project, one document, two priced scopes, signed by Sorento and issued as R1."""
    from app.services.project_service import register_project

    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    _numbering_rule(db, company_id)
    _floor_rule(db, company_id)
    owner = _user(db, f"{MARKER} Baser")
    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Cabana Elmina {_uid()[:12]}",
        owner_user_id=owner,
    )
    project.owner_user_id = owner
    document = qdocs.create_document(db, project=project, actor_user_id=owner)
    scope_a = qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} Block A", actor_user_id=owner
    )
    scope_b = qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} Block B", actor_user_id=owner
    )
    lines = {
        "WC": _price_line(db, scope_a, owner, "WC", tag),
        "CON": _price_line(db, scope_a, owner, "CON", tag),
        "BSN": _price_line(db, scope_a, owner, "BSN", tag),
        "SHW": _price_line(db, scope_a, owner, "SHW", tag),
        "TAP": _price_line(db, scope_b, owner, "TAP", tag),
    }
    _sign(db, document, owner)
    record = qdocs.issue(db, document=document, actor_user_id=owner)
    db.flush()
    return SimpleNamespace(
        company_id=company_id,
        owner=owner,
        project=project,
        document=document,
        record=record,
        scope_a=scope_a,
        scope_b=scope_b,
        lines=lines,
        tag=tag,
    )


def _sign(db, document, owner) -> None:
    qdocs.sign_as_sorento(
        db,
        document=document,
        actor_user_id=owner,
        payload={
            "signer_name": f"{MARKER} Baser",
            "mode": "draw",
            "image_data_uri": A_SIGNATURE,
        },
    )


def _status(db, key: str) -> Status:
    row = (
        db.query(Status)
        .filter(
            Status.entity_type == "quotation",
            Status.scope_id.is_(None),
            Status.key == key,
        )
        .first()
    )
    assert row is not None, f"the quotation graph has no '{key}' rung"
    return row


def _change(line, quantity=None, unit_price=None, remove=False) -> dict:
    return {
        "line_id": str(line.id),
        "quantity": quantity,
        "unit_price": unit_price,
        "remove": remove,
    }


def _submit(db, w, lines, *, note=None, name=CUSTOMER):
    return _svc().submit_request(
        db,
        record=w.record,
        lines=lines,
        note=note,
        requester_name=name,
        ip_address=CUSTOMER_IP,
    )


def _rows(db, request) -> dict:
    _req, row_model = _models()
    rows = db.query(row_model).filter(row_model.request_id == request.id).all()
    return {(str(r.line_id), r.field): r for r in rows}


def _all_requests(db) -> int:
    request_model, _row = _models()
    return db.query(request_model).count()


def _refused(call, status: int, code: str):
    with pytest.raises(AppException) as refused:
        call()
    assert refused.value.status_code == status, refused.value.detail
    assert refused.value.detail["code"] == code
    return refused.value


def _decide(db, w, request, wanted: dict, *, reason=None):
    """Decide rows by (line key, field) -> decision. Every other row is accepted."""
    by_id = {str(line.id): key for key, line in w.lines.items()}
    for (line_id, field), row in _rows(db, request).items():
        decision = wanted.get((by_id[line_id], field), "accepted")
        _svc().decide_row(
            db,
            request=request,
            row_id=str(row.id),
            decision=decision,
            reason=(reason if decision == "rejected" else None),
            actor_user_id=w.owner,
        )
    db.flush()


def _a_suggestion(db, w):
    """The worked example: WC 120 -> 110 and 400 -> 380, CON 120 -> 110, BSN 160 -> 150,
    SHW staged for removal, TAP (other scope) 90 -> 80."""
    return _submit(
        db,
        w,
        [
            _change(w.lines["WC"], quantity="110.00", unit_price="380.00"),
            _change(w.lines["CON"], quantity="110.00"),
            _change(w.lines["BSN"], unit_price="150.00"),
            _change(w.lines["SHW"], remove=True),
            _change(w.lines["TAP"], unit_price="80.00"),
        ],
        note=NOTE,
    )


def _versions(db, scope):
    return (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == scope.id)
        .order_by(ProjectQuotationVersion.version_no)
        .all()
    )


def _issue_count(db, document) -> int:
    return (
        db.query(ProjectQuotationIssue)
        .filter(ProjectQuotationIssue.document_id == document.id)
        .count()
    )


# ================================================================== AC-QCA-01 / 07: the request


def test_ac01_one_submit_stores_a_row_per_line_and_field_with_issued_and_suggested_values():
    with blank_session() as db:
        w = _world(db)
        request = _submit(
            db,
            w,
            [
                _change(w.lines["WC"], quantity="110.00", unit_price="380.00"),
                _change(w.lines["BSN"], unit_price="150.00"),
            ],
            note=NOTE,
        )

        assert request.status == "open"
        assert request.requester_name == CUSTOMER
        assert request.note == NOTE
        assert request.ip_address == CUSTOMER_IP
        assert request.submitted_at is not None
        assert str(request.issue_id) == str(w.record.id)

        rows = _rows(db, request)
        assert set(rows) == {
            (str(w.lines["WC"].id), "quantity"),
            (str(w.lines["WC"].id), "unit_price"),
            (str(w.lines["BSN"].id), "unit_price"),
        }
        wc_qty = rows[(str(w.lines["WC"].id), "quantity")]
        assert (wc_qty.value_from, wc_qty.value_to) == (Decimal("120.00"), Decimal("110.00"))
        wc_price = rows[(str(w.lines["WC"].id), "unit_price")]
        assert (wc_price.value_from, wc_price.value_to) == (
            Decimal("400.00"),
            Decimal("380.00"),
        )
        assert all(r.decision == "pending" for r in rows.values())

        found = _svc().open_request(db, w.record.id)
        assert found is not None and str(found.id) == str(request.id)


def test_ac01_the_requester_name_and_note_are_optional():
    with blank_session() as db:
        w = _world(db)
        request = _svc().submit_request(
            db,
            record=w.record,
            lines=[_change(w.lines["BSN"], unit_price="150.00")],
            note=None,
            requester_name=None,
            ip_address=None,
        )
        assert request.status == "open"
        assert request.requester_name in (None, "")
        assert request.note in (None, "")


def test_ac07_the_issued_lines_and_totals_are_never_touched_by_a_request():
    with blank_session() as db:
        w = _world(db)
        before_total = Decimal(
            quotes.current_version(db, w.scope_a.id).total_amount or 0
        )
        _a_suggestion(db, w)
        db.flush()
        db.expire_all()

        wc = w.lines["WC"]
        assert (wc.unit_price, wc.quantity) == (Decimal("400.00"), Decimal("120.00"))
        assert w.lines["SHW"] in quotes.list_lines(db, wc.version_id)
        assert Decimal(quotes.current_version(db, w.scope_a.id).total_amount) == before_total
        assert len(_versions(db, w.scope_a)) == 1


def test_ac07_fields_other_than_quantity_price_and_remove_are_ignored():
    """The payload has no field for a description or code: a client that sends one is ignored,
    and only request rows are written."""
    with blank_session() as db:
        w = _world(db)
        description = w.lines["WC"].description_snapshot
        code = w.lines["WC"].product_code_snapshot
        sneaky = _change(w.lines["WC"], quantity="110.00")
        sneaky.update(
            {
                "description": "Gold plated",
                "product_code": "ZZT-FAKE",
                "brand": "Nope",
                "technical_spec": "Nope",
                "unit_type": "lot",
            }
        )
        request = _submit(db, w, [sneaky])
        db.expire_all()

        assert set(f for (_l, f) in _rows(db, request)) == {"quantity"}
        wc = w.lines["WC"]
        assert wc.description_snapshot == description
        assert wc.product_code_snapshot == code
        assert wc.brand_snapshot != "Nope"
        assert wc.technical_spec != "Nope"


# ================================================================== AC-QCA-02: quantity


@pytest.mark.parametrize(
    "bad", ["0", "0.00", "-1", "-0.5", "0.99", "1.005", "10000000.00", "abc", "1e3", ""]
)
def test_ac02_an_invalid_quantity_is_refused_and_nothing_is_stored(bad):
    with blank_session() as db:
        w = _world(db)
        _refused(
            lambda: _submit(db, w, [_change(w.lines["WC"], quantity=bad)], note=NOTE),
            422,
            "quotation_amendment_qty_invalid",
        )
        assert _all_requests(db) == 0


def test_ac02_the_quantity_bounds_are_inclusive():
    with blank_session() as db:
        w = _world(db)
        request = _submit(
            db,
            w,
            [
                _change(w.lines["WC"], quantity="9999999.99"),
                _change(w.lines["BSN"], quantity="1"),
            ],
        )
        rows = _rows(db, request)
        assert rows[(str(w.lines["WC"].id), "quantity")].value_to == Decimal("9999999.99")
        assert rows[(str(w.lines["BSN"].id), "quantity")].value_to == Decimal("1.00")


def test_ac02_a_quantity_error_stores_nothing_even_for_the_valid_lines_beside_it():
    with blank_session() as db:
        w = _world(db)
        _refused(
            lambda: _submit(
                db,
                w,
                [
                    _change(w.lines["BSN"], unit_price="150.00"),
                    _change(w.lines["WC"], quantity="0"),
                ],
            ),
            422,
            "quotation_amendment_qty_invalid",
        )
        assert _all_requests(db) == 0
        assert _svc().open_request(db, w.record.id) is None


# ================================================================== AC-QCA-03: unit price


@pytest.mark.parametrize(
    "bad", ["0", "0.00", "-5", "380.001", "10000000000.00", "abc", "1e3"]
)
def test_ac03_an_invalid_unit_price_is_refused_and_nothing_is_stored(bad):
    with blank_session() as db:
        w = _world(db)
        _refused(
            lambda: _submit(db, w, [_change(w.lines["WC"], unit_price=bad)]),
            422,
            "quotation_amendment_price_invalid",
        )
        assert _all_requests(db) == 0


def test_ac03_the_price_ceiling_is_inclusive():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], unit_price="9999999999.99")])
        row = _rows(db, request)[(str(w.lines["WC"].id), "unit_price")]
        assert row.value_to == Decimal("9999999999.99")


def test_ac03_a_price_on_a_zero_priced_companion_line_is_refused():
    """The money sits on the parent: a set companion's price is read-only."""
    with blank_session() as db:
        w = _world(db)
        _refused(
            lambda: _submit(db, w, [_change(w.lines["CON"], unit_price="5.00")]),
            422,
            "quotation_amendment_price_invalid",
        )
        assert _all_requests(db) == 0


def test_ac03_a_companion_line_may_still_change_quantity():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["CON"], quantity="110.00")])
        assert (str(w.lines["CON"].id), "quantity") in _rows(db, request)


# ================================================================== AC-QCA-04: removal


def test_ac04_a_removal_is_one_remove_row():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["SHW"], remove=True)])
        rows = _rows(db, request)
        assert set(rows) == {(str(w.lines["SHW"].id), "remove")}
        remove = rows[(str(w.lines["SHW"].id), "remove")]
        assert remove.value_to is None
        assert remove.decision == "pending"


@pytest.mark.parametrize(
    "extra", [{"quantity": "110.00"}, {"unit_price": "380.00"}], ids=["with_qty", "with_price"]
)
def test_ac04_remove_together_with_a_qty_or_price_on_the_same_line_is_refused(extra):
    with blank_session() as db:
        w = _world(db)
        change = _change(w.lines["WC"], remove=True)
        change.update(extra)
        _refused(
            lambda: _submit(db, w, [change]), 422, "quotation_amendment_remove_conflict"
        )
        assert _all_requests(db) == 0


# ================================================================== AC-QCA-05: no change


def test_ac05_a_value_equal_to_the_issued_one_is_not_stored():
    with blank_session() as db:
        w = _world(db)
        request = _submit(
            db,
            w,
            [
                _change(w.lines["WC"], quantity="120", unit_price="380.00"),
                _change(w.lines["BSN"], quantity="120.00", unit_price="160"),
            ],
        )
        rows = _rows(db, request)
        assert set(rows) == {(str(w.lines["WC"].id), "unit_price")}


@pytest.mark.parametrize("note", [None, "", "   \n "])
def test_ac05_no_change_and_no_note_is_refused(note):
    with blank_session() as db:
        w = _world(db)
        _refused(
            lambda: _submit(
                db, w, [_change(w.lines["WC"], quantity="120.00")], note=note
            ),
            422,
            "quotation_amendment_empty",
        )
        _refused(
            lambda: _submit(db, w, [], note=note), 422, "quotation_amendment_empty"
        )
        assert _all_requests(db) == 0


def test_ac05_a_note_alone_is_a_valid_request():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [], note=NOTE)
        assert request.status == "open"
        assert request.note == NOTE
        assert _rows(db, request) == {}


# ================================================================== AC-QCA-06: unknown lines


def test_ac06_a_line_of_another_issue_project_or_a_made_up_id_is_refused():
    with blank_session() as db:
        w = _world(db)
        other = _world(db, tag="-b")
        newer = quotes.revise(db, quotation=w.scope_a, actor_user_id=w.owner)
        revised_line = quotes.list_lines(db, newer.id)[0]
        real_ids = {str(line.id) for line in w.lines.values()}

        foreign = [
            SimpleNamespace(id=other.lines["WC"].id),  # another project
            SimpleNamespace(id=revised_line.id),  # a later version, not carried by R1
            SimpleNamespace(id=_uid()),  # made up
        ]
        for line in foreign:
            error = _refused(
                lambda line=line: _submit(
                    db,
                    w,
                    [
                        _change(w.lines["BSN"], unit_price="150.00"),
                        _change(line, quantity="110.00"),
                    ],
                ),
                422,
                "quotation_amendment_line_unknown",
            )
            # It must not teach the caller which ids DO exist.
            assert not any(real in str(error.detail) for real in real_ids)
        assert _all_requests(db) == 0


# ================================================================== AC-QCA-08: one open request


def test_ac08_a_second_submit_while_one_is_open_is_refused():
    with blank_session() as db:
        w = _world(db)
        first = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        _refused(
            lambda: _submit(db, w, [_change(w.lines["BSN"], unit_price="150.00")]),
            409,
            "quotation_amendment_open",
        )
        assert _all_requests(db) == 1
        open_now = _svc().open_request(db, w.record.id)
        assert str(open_now.id) == str(first.id)
        assert set(f for (_l, f) in _rows(db, first)) == {"quantity"}


def test_ac08_the_database_allows_one_open_request_per_issue_and_no_more():
    """The guarantee under a true race: the partial unique index, not the application check."""
    from sqlalchemy.exc import IntegrityError

    with blank_session() as db:
        w = _world(db)
        request_model, _row = _models()
        first = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])

        def another_open():
            return request_model(
                id=_uid(),
                company_id=w.company_id,
                issue_id=w.record.id,
                status="open",
                submitted_at=datetime.utcnow(),
            )

        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(another_open())
                db.flush()

        # Once answered, the issue may hold another one (only OPEN is unique).
        first.status = "applied"
        db.flush()
        db.add(another_open())
        db.flush()


# ================================================================== AC-QCA-10 / 11: state of the issue


def test_ac10_an_accepted_issue_refuses_a_request():
    with blank_session() as db:
        w = _world(db)
        qdocs.accept_issue(
            db,
            record=w.record,
            signer_name=CUSTOMER,
            mode="draw",
            image_data_uri=A_SIGNATURE,
        )
        _refused(
            lambda: _submit(db, w, [_change(w.lines["WC"], quantity="110.00")]),
            409,
            "quotation_already_accepted",
        )
        assert _all_requests(db) == 0


def test_ac11_a_superseded_issue_refuses_a_request_and_names_its_replacement():
    with blank_session() as db:
        w = _world(db)
        r2 = qdocs.issue(db, document=w.document, actor_user_id=w.owner)
        db.flush()

        _refused(
            lambda: _submit(db, w, [_change(w.lines["WC"], quantity="110.00")]),
            409,
            "quotation_superseded",
        )
        assert _all_requests(db) == 0

        page = qdocs.serialize_sign_page(db, w.record)
        assert page["superseded_by_ref"] == r2.our_ref_text
        assert qdocs.serialize_sign_page(db, r2)["superseded_by_ref"] is None


# ================================================================== AC-QCA-13 / 14 / 15: the page


def test_ac13_the_page_blocks_signing_while_a_request_is_open():
    with blank_session() as db:
        w = _world(db)
        clean = qdocs.serialize_sign_page(db, w.record)
        assert clean["can_sign"] is True
        assert clean["sign_blocked_reason"] is None

        _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        db.flush()
        page = qdocs.serialize_sign_page(db, w.record)
        assert page["can_sign"] is False
        assert page["sign_blocked_reason"] == "amendment_open"


def test_ac13_an_accepted_issue_reports_why_it_cannot_be_signed_again():
    with blank_session() as db:
        w = _world(db)
        qdocs.accept_issue(
            db, record=w.record, signer_name=CUSTOMER, mode="draw", image_data_uri=A_SIGNATURE
        )
        page = qdocs.serialize_sign_page(db, w.record)
        assert page["can_sign"] is False
        assert page["sign_blocked_reason"] == "accepted"


def test_ac14_the_page_carries_every_line_id_and_the_amendment_request_block():
    with blank_session() as db:
        w = _world(db)
        before = qdocs.serialize_sign_page(db, w.record)
        assert before["amendment_request"] is None

        ids = {line["id"] for scope in before["scopes"] for line in scope["lines"]}
        assert ids == {str(line.id) for line in w.lines.values()}

        request = _submit(
            db,
            w,
            [
                _change(w.lines["WC"], quantity="110.00"),
                _change(w.lines["SHW"], remove=True),
            ],
            note=NOTE,
        )
        db.flush()
        block = qdocs.serialize_sign_page(db, w.record)["amendment_request"]

        assert block["id"] == str(request.id)
        assert block["status"] == "open"
        assert block["submitted_at"] is not None
        assert block["requester_name"] == CUSTOMER
        assert block["note"] == NOTE
        assert len(block["rows"]) == 2
        for row in block["rows"]:
            assert set(row) >= {
                "id",
                "line_id",
                "field",
                "value_from",
                "value_to",
                "decision",
                "decision_reason",
            }
        by_field = {row["field"]: row for row in block["rows"]}
        assert by_field["quantity"]["line_id"] == str(w.lines["WC"].id)
        assert Decimal(str(by_field["quantity"]["value_from"])) == Decimal("120.00")
        assert Decimal(str(by_field["quantity"]["value_to"])) == Decimal("110.00")
        assert by_field["remove"]["value_to"] is None
        assert by_field["quantity"]["decision"] == "pending"


def test_ac15_an_applied_request_shows_decisions_and_reasons_and_locks_the_issue():
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        _decide(
            db,
            w,
            request,
            {("BSN", "unit_price"): "rejected"},
            reason="Already at project price",
        )
        _svc().apply_request(db, request=request, actor_user_id=w.owner)
        db.flush()

        page = qdocs.serialize_sign_page(db, w.record)
        assert page["can_sign"] is False
        assert page["sign_blocked_reason"] == "amendment_applied"
        block = page["amendment_request"]
        assert block["status"] == "applied"
        rows = {(r["line_id"], r["field"]): r for r in block["rows"]}
        bsn = rows[(str(w.lines["BSN"].id), "unit_price")]
        assert bsn["decision"] == "rejected"
        assert bsn["decision_reason"] == "Already at project price"
        wc = rows[(str(w.lines["WC"].id), "quantity")]
        assert wc["decision"] == "accepted"
        assert wc["decision_reason"] in (None, "")


# ================================================================== AC-QCA-16 / 17: told and recorded


def _capture_send(monkeypatch):
    from app.services import project_notify_service as notify

    sent = []

    def fake(db, **kwargs):
        sent.append(kwargs)
        return 1

    monkeypatch.setattr(notify, "_send", fake)
    return sent


def test_ac16_one_whatsapp_enabled_notice_goes_to_the_project_owner(monkeypatch):
    sent = _capture_send(monkeypatch)
    with blank_session() as db:
        w = _world(db)
        sent.clear()  # the issue itself may notify; only the request is under test
        _submit(
            db,
            w,
            [
                _change(w.lines["WC"], quantity="110.00", unit_price="380.00"),
                _change(w.lines["BSN"], unit_price="150.00"),
            ],
        )

        assert len(sent) == 1
        call = sent[0]
        assert call["notif_type"] == "project_quotation_amendment_requested"
        assert [str(u) for u in call["user_ids"]] == [str(w.owner)]
        assert call["send_whatsapp"] is True
        assert call.get("send_email", True) is True
        words = f"{call['title']} {call['body']}"
        assert w.record.our_ref_text in words
        # Two LINES changed (three rows): the notice counts lines, not rows.
        assert "2 line" in words


def test_ac16_a_project_with_no_owner_falls_back_to_management(monkeypatch):
    from app.services import project_notify_service as notify

    sent = _capture_send(monkeypatch)
    with blank_session() as db:
        w = _world(db)
        manager = _user(db, f"{MARKER} Manager")
        monkeypatch.setattr(notify, "management_user_ids", lambda *a, **k: [manager])
        w.project.owner_user_id = None
        db.flush()
        sent.clear()

        _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])

        assert len(sent) == 1
        assert [str(u) for u in sent[0]["user_ids"]] == [manager]
        assert sent[0]["send_whatsapp"] is True


def test_ac16_the_owner_gets_an_in_app_notification_row_of_the_new_type():
    with blank_session() as db:
        w = _world(db)
        _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        db.flush()
        rows = (
            db.query(Notification)
            .filter(
                Notification.user_id == w.owner,
                Notification.type == "project_quotation_amendment_requested",
            )
            .all()
        )
        assert len(rows) == 1


def test_ac17_the_request_is_written_to_the_project_activity_feed():
    from app.models.activities import ActivityEvent

    with blank_session() as db:
        w = _world(db)
        _submit(db, w, [_change(w.lines["WC"], quantity="110.00")], note=NOTE)
        db.flush()
        rows = (
            db.query(ActivityEvent)
            .filter(
                ActivityEvent.entity_type == "project",
                ActivityEvent.entity_id == str(w.project.id),
                ActivityEvent.system_template == "quotation_amendment_requested",
            )
            .all()
        )
        assert len(rows) == 1


def test_ac17_a_failing_notifier_does_not_fail_the_customers_request(monkeypatch):
    from app.services import project_notify_service as notify

    def boom(*args, **kwargs):
        raise RuntimeError("zzt notifier down")

    with blank_session() as db:
        w = _world(db)
        monkeypatch.setattr(notify, "_send", boom)
        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        assert request.status == "open"
        assert _svc().open_request(db, w.record.id) is not None


def test_ac17_a_failing_activity_feed_does_not_fail_the_customers_request(monkeypatch):
    from app.services import project_activity_service as activity

    def boom(*args, **kwargs):
        raise RuntimeError("zzt feed down")

    with blank_session() as db:
        w = _world(db)
        monkeypatch.setattr(activity, "record_project_event", boom)
        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        assert request.status == "open"


# ================================================================== AC-QCA-18: deciding


def test_ac18_a_row_can_be_accepted_rejected_with_a_reason_and_put_back_to_pending():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], unit_price="380.00")])
        row_id = str(next(iter(_rows(db, request).values())).id)
        amend = _svc()

        row = amend.decide_row(
            db, request=request, row_id=row_id, decision="accepted", reason=None,
            actor_user_id=w.owner,
        )
        assert row.decision == "accepted"
        assert str(row.decided_by) == str(w.owner)
        assert row.decided_at is not None

        row = amend.decide_row(
            db, request=request, row_id=row_id, decision="rejected",
            reason="Below our project price", actor_user_id=w.owner,
        )
        assert row.decision == "rejected"
        assert row.decision_reason == "Below our project price"

        row = amend.decide_row(
            db, request=request, row_id=row_id, decision="pending", reason=None,
            actor_user_id=w.owner,
        )
        assert row.decision == "pending"


def test_ac18_the_reason_is_capped_at_500_characters_and_the_decision_must_be_known():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], unit_price="380.00")])
        row_id = str(next(iter(_rows(db, request).values())).id)
        amend = _svc()

        ok = amend.decide_row(
            db, request=request, row_id=row_id, decision="rejected", reason="x" * 500,
            actor_user_id=w.owner,
        )
        assert len(ok.decision_reason) == 500

        with pytest.raises(AppException) as too_long:
            amend.decide_row(
                db, request=request, row_id=row_id, decision="rejected", reason="x" * 501,
                actor_user_id=w.owner,
            )
        assert too_long.value.status_code == 422

        with pytest.raises(AppException) as unknown:
            amend.decide_row(
                db, request=request, row_id=row_id, decision="maybe", reason=None,
                actor_user_id=w.owner,
            )
        assert unknown.value.status_code == 422


def test_ac18_a_row_of_another_request_is_not_found():
    with blank_session() as db:
        w = _world(db)
        other = _world(db, tag="-b")
        mine = _submit(db, w, [_change(w.lines["WC"], unit_price="380.00")])
        theirs = _submit(db, other, [_change(other.lines["WC"], unit_price="380.00")])
        foreign_row = str(next(iter(_rows(db, theirs).values())).id)

        with pytest.raises(AppException) as missing:
            _svc().decide_row(
                db, request=mine, row_id=foreign_row, decision="accepted", reason=None,
                actor_user_id=w.owner,
            )
        assert missing.value.status_code == 404


def test_ac18_latest_request_for_document_is_the_open_one_then_the_answered_one():
    with blank_session() as db:
        w = _world(db)
        amend = _svc()
        assert amend.latest_request_for_document(db, w.document) is None

        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        assert str(amend.latest_request_for_document(db, w.document).id) == str(request.id)

        _decide(db, w, request, {})
        amend.apply_request(db, request=request, actor_user_id=w.owner)
        latest = amend.latest_request_for_document(db, w.document)
        assert str(latest.id) == str(request.id) and latest.status == "applied"


# ================================================================== AC-QCA-19: floors on the rows


def test_ac19_a_price_below_the_floor_is_reported_on_its_row_with_the_floor_value():
    with blank_session() as db:
        w = _world(db)
        request = _submit(
            db,
            w,
            [
                _change(w.lines["WC"], quantity="110.00", unit_price="380.00"),  # floor 390.00
                _change(w.lines["BSN"], unit_price="150.00"),  # floor 130.00
                _change(w.lines["TAP"], unit_price="65.00"),  # exactly the floor 65.00
            ],
        )
        payload = _svc().serialize_request(db, request)
        rows = {(r["line_id"], r["field"]): r for r in payload["rows"]}

        wc = rows[(str(w.lines["WC"].id), "unit_price")]
        assert wc["below_floor"] is True
        assert Decimal(str(wc["floor_value"])) == Decimal("390.00")

        bsn = rows[(str(w.lines["BSN"].id), "unit_price")]
        assert bsn["below_floor"] is False
        assert Decimal(str(bsn["floor_value"])) == Decimal("130.00")

        tap = rows[(str(w.lines["TAP"].id), "unit_price")]
        assert tap["below_floor"] is False  # equal to the floor is not below it

        qty = rows[(str(w.lines["WC"].id), "quantity")]
        assert not qty.get("below_floor")


# ================================================================== AC-QCA-20 .. 24: apply


def test_ac20_apply_is_refused_while_any_row_is_pending_and_writes_nothing():
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        first = next(iter(_rows(db, request).values()))
        _svc().decide_row(
            db, request=request, row_id=str(first.id), decision="accepted", reason=None,
            actor_user_id=w.owner,
        )
        _refused(
            lambda: _svc().apply_request(db, request=request, actor_user_id=w.owner),
            422,
            "quotation_amendment_undecided",
        )
        assert len(_versions(db, w.scope_a)) == 1
        assert len(_versions(db, w.scope_b)) == 1
        assert request.status == "open"


def test_ac21_apply_revises_only_touched_scopes_and_writes_accepted_values():
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        _decide(
            db,
            w,
            request,
            {
                ("BSN", "unit_price"): "rejected",
                ("TAP", "unit_price"): "rejected",
            },
            reason="Already at project price",
        )

        versions = _svc().apply_request(db, request=request, actor_user_id=w.owner)
        db.flush()

        # Scope B only had a rejected row, so only scope A moved.
        assert len(versions) == 1
        new_a = versions[0]
        assert str(new_a.quotation_id) == str(w.scope_a.id)
        assert new_a.version_no == 2
        assert len(_versions(db, w.scope_b)) == 1

        lines = {l.product_code_snapshot: l for l in quotes.list_lines(db, new_a.id)}
        suffix = w.tag
        assert set(lines) == {
            f"ZZT-WC-1001{suffix}",
            f"ZZT-CON-0001{suffix}",
            f"ZZT-BSN-4004{suffix}",
        }  # the accepted removal is gone

        wc = lines[f"ZZT-WC-1001{suffix}"]
        assert (wc.quantity, wc.unit_price) == (Decimal("110.00"), Decimal("380.00"))
        assert wc.line_total == Decimal("41800.00")
        con = lines[f"ZZT-CON-0001{suffix}"]
        assert (con.quantity, con.unit_price) == (Decimal("110.00"), Decimal("0.00"))
        bsn = lines[f"ZZT-BSN-4004{suffix}"]
        assert (bsn.quantity, bsn.unit_price) == (Decimal("120.00"), Decimal("160.00"))

        # The floor flags recompute exactly as for a hand edit.
        assert wc.is_below_floor is True
        assert wc.floor_value_applied == Decimal("390.00")
        assert bsn.is_below_floor is False

        # 41,800.00 + 0.00 + 19,200.00
        assert Decimal(new_a.total_amount) == Decimal("61000.00")

        # What the customer holds is exactly as issued.
        db.expire_all()
        assert (w.lines["WC"].unit_price, w.lines["WC"].quantity) == (
            Decimal("400.00"),
            Decimal("120.00"),
        )
        issued_codes = {
            l.product_code_snapshot for l in quotes.list_lines(db, w.lines["WC"].version_id)
        }
        assert f"ZZT-SHW-5005{w.tag}" in issued_codes  # R1 still holds the removed line


def test_ac21_a_rejected_removal_keeps_the_line_as_issued():
    with blank_session() as db:
        w = _world(db)
        request = _submit(
            db,
            w,
            [_change(w.lines["SHW"], remove=True), _change(w.lines["WC"], quantity="110.00")],
        )
        _decide(db, w, request, {("SHW", "remove"): "rejected"}, reason="Needed on site")

        (new_a,) = _svc().apply_request(db, request=request, actor_user_id=w.owner)
        codes = {l.product_code_snapshot for l in quotes.list_lines(db, new_a.id)}
        assert f"ZZT-SHW-5005{w.tag}" in codes


def test_ac21_a_price_rejected_and_a_quantity_accepted_on_the_same_line_are_applied_separately():
    with blank_session() as db:
        w = _world(db)
        request = _submit(
            db, w, [_change(w.lines["WC"], quantity="110.00", unit_price="380.00")]
        )
        _decide(db, w, request, {("WC", "unit_price"): "rejected"}, reason="No")

        (new_a,) = _svc().apply_request(db, request=request, actor_user_id=w.owner)
        wc = next(
            l for l in quotes.list_lines(db, new_a.id) if l.product_code_snapshot.startswith("ZZT-WC")
        )
        assert (wc.quantity, wc.unit_price) == (Decimal("110.00"), Decimal("400.00"))
        assert wc.is_below_floor is False


def test_ac21_removing_every_line_of_a_scope_leaves_an_empty_zero_total_draft():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["TAP"], remove=True)])
        _decide(db, w, request, {})
        (new_b,) = _svc().apply_request(db, request=request, actor_user_id=w.owner)
        assert quotes.list_lines(db, new_b.id) == []
        assert Decimal(new_b.total_amount) == Decimal("0.00")


def test_ac22_apply_makes_a_draft_and_issuing_an_accepted_below_floor_price_is_gated():
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], unit_price="380.00")])
        _decide(db, w, request, {})

        _svc().apply_request(db, request=request, actor_user_id=w.owner)
        db.flush()

        # A draft: no issue was created by Apply.
        assert _issue_count(db, w.document) == 1

        _sign(db, w.document, w.owner)
        _refused(
            lambda: qdocs.issue(db, document=w.document, actor_user_id=w.owner),
            422,
            "quotation_below_floor_pending_approval",
        )
        assert _issue_count(db, w.document) == 1

        manager = _user(db, f"{MARKER} Manager")
        approval.move(
            db,
            document=w.document,
            to_status_id=_status(db, "pending_approval").id,
            actor_user_id=w.owner,
        )
        approval.approve(
            db, document=w.document, actor_user_id=manager, permissions=EVERYTHING
        )
        assert qdocs.issue(db, document=w.document, actor_user_id=w.owner).issue_no == 2


def test_ac23_a_later_draft_on_a_touched_scope_refuses_apply_and_writes_nothing():
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        _decide(db, w, request, {})

        # Somebody opened a revision on scope A by hand in the meantime.
        quotes.revise(db, quotation=w.scope_a, actor_user_id=w.owner)
        db.flush()

        _refused(
            lambda: _svc().apply_request(db, request=request, actor_user_id=w.owner),
            409,
            "quotation_amendment_draft_open",
        )
        assert len(_versions(db, w.scope_a)) == 2
        assert len(_versions(db, w.scope_b)) == 1  # not even the clean scope moved
        assert request.status == "open"


def test_ac23_a_draft_on_a_scope_with_no_accepted_row_does_not_block_apply():
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        _decide(db, w, request, {("TAP", "unit_price"): "rejected"}, reason="No")
        quotes.revise(db, quotation=w.scope_b, actor_user_id=w.owner)

        versions = _svc().apply_request(db, request=request, actor_user_id=w.owner)
        assert [str(v.quotation_id) for v in versions] == [str(w.scope_a.id)]


@pytest.mark.parametrize("rung", ["pending_approval", "approved"])
def test_ac23_apply_is_refused_with_the_approval_lock_and_writes_nothing(rung):
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        _decide(db, w, request, {})
        w.document.approval_status_id = _status(db, rung).id
        db.flush()

        _refused(
            lambda: _svc().apply_request(db, request=request, actor_user_id=w.owner),
            422,
            "quotation_locked_for_approval",
        )
        assert len(_versions(db, w.scope_a)) == 1
        assert len(_versions(db, w.scope_b)) == 1
        assert request.status == "open"


def test_ac24_apply_marks_the_request_applied_with_who_and_when_and_a_second_apply_is_refused():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        _decide(db, w, request, {})

        _svc().apply_request(db, request=request, actor_user_id=w.owner)
        db.flush()
        assert request.status == "applied"
        assert str(request.applied_by) == str(w.owner)
        assert request.applied_at is not None
        assert _svc().open_request(db, w.record.id) is None

        _refused(
            lambda: _svc().apply_request(db, request=request, actor_user_id=w.owner),
            409,
            "quotation_amendment_not_open",
        )
        assert len(_versions(db, w.scope_a)) == 2


def test_ac24_a_request_with_only_rejected_rows_applies_without_revising_anything():
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        wanted = {
            (key, field): "rejected"
            for key, field in [
                ("WC", "quantity"),
                ("WC", "unit_price"),
                ("CON", "quantity"),
                ("BSN", "unit_price"),
                ("SHW", "remove"),
                ("TAP", "unit_price"),
            ]
        }
        _decide(db, w, request, wanted, reason="Not this time")

        versions = _svc().apply_request(db, request=request, actor_user_id=w.owner)
        assert versions == []
        assert len(_versions(db, w.scope_a)) == 1
        assert len(_versions(db, w.scope_b)) == 1
        assert request.status == "applied"


# ================================================================== AC-QCA-25: superseded


def test_ac25_issuing_a_newer_revision_closes_an_open_request_as_superseded():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])

        qdocs.issue(db, document=w.document, actor_user_id=w.owner)
        db.flush()
        db.refresh(request)

        assert request.status == "superseded"
        assert _svc().open_request(db, w.record.id) is None
        # R2 is the latest issue and nobody has asked about it.
        assert _svc().latest_request_for_document(db, w.document) is None


def test_ac25_issuing_a_newer_revision_leaves_an_applied_request_as_it_was():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        _decide(db, w, request, {})
        _svc().apply_request(db, request=request, actor_user_id=w.owner)

        qdocs.issue(db, document=w.document, actor_user_id=w.owner)
        db.flush()
        db.refresh(request)
        assert request.status == "applied"


# ================================================================== the public wire


@pytest.fixture()
def public(monkeypatch):
    """A TestClient with no credential but the link, a world already issued, rate limit spied."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.services import rate_limit

    hits = []

    def allowed(bucket, ident, *, limit, window_seconds):
        hits.append((bucket, ident))
        return rate_limit.RateResult(allowed=True)

    monkeypatch.setattr(rate_limit, "hit", allowed)

    with blank_session() as db:
        w = _world(db)
        token = qdocs.issue_sign_link(db, record=w.record)
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        try:
            yield TestClient(app), db, w, token, hits
        finally:
            app.dependency_overrides.clear()


def _body(w, **over) -> dict:
    body = {
        "requester_name": CUSTOMER,
        "note": NOTE,
        "lines": [
            {
                "line_id": str(w.lines["WC"].id),
                "quantity": "110.00",
                "unit_price": "380.00",
                "remove": False,
            },
            {"line_id": str(w.lines["SHW"].id), "remove": True},
        ],
    }
    body.update(over)
    return body


def test_wire_the_public_route_stores_the_request_and_answers_the_page(public):
    client, db, w, token, _hits = public
    response = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert response.status_code == 200, response.text
    page = response.json()

    assert page["can_sign"] is False
    assert page["sign_blocked_reason"] == "amendment_open"
    assert "superseded_by_ref" in page and page["superseded_by_ref"] is None
    block = page["amendment_request"]
    assert block["status"] == "open"
    assert block["note"] == NOTE
    assert block["requester_name"] == CUSTOMER
    assert {(r["field"]) for r in block["rows"]} == {"quantity", "unit_price", "remove"}
    ids = {line["id"] for scope in page["scopes"] for line in scope["lines"]}
    assert str(w.lines["WC"].id) in ids

    # And the page a plain GET returns says the same (response_model drops undeclared keys).
    again = client.get(f"{PUBLIC}/{token}").json()
    assert again["amendment_request"]["id"] == block["id"]
    assert again["can_sign"] is False


def test_wire_unknown_keys_are_ignored_and_the_issued_lines_are_untouched(public):
    client, db, w, token, _hits = public
    body = _body(w, unexpected="x")
    body["lines"][0]["description"] = "Gold plated"
    response = client.post(f"{PUBLIC}/{token}/amendment-request", json=body)
    assert response.status_code == 200, response.text
    db.expire_all()
    assert w.lines["WC"].description_snapshot != "Gold plated"
    assert w.lines["WC"].unit_price == Decimal("400.00")


@pytest.mark.parametrize(
    "line, code",
    [
        ({"quantity": "0"}, "quotation_amendment_qty_invalid"),
        ({"quantity": "abc"}, "quotation_amendment_qty_invalid"),
        ({"unit_price": "0"}, "quotation_amendment_price_invalid"),
        ({"remove": True, "quantity": "5"}, "quotation_amendment_remove_conflict"),
    ],
)
def test_wire_validation_errors_are_422_with_the_contract_code(public, line, code):
    client, db, w, token, _hits = public
    body = _body(w, lines=[{"line_id": str(w.lines["WC"].id), **line}])
    response = client.post(f"{PUBLIC}/{token}/amendment-request", json=body)
    assert response.status_code == 422, response.text
    assert response.json().get("code") == code
    assert _all_requests(db) == 0


def test_wire_an_empty_request_is_422(public):
    client, db, w, token, _hits = public
    response = client.post(
        f"{PUBLIC}/{token}/amendment-request",
        json={"requester_name": None, "note": None, "lines": []},
    )
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_amendment_empty"


def test_ac09_an_unknown_or_expired_link_is_the_same_404_for_the_request_route(public):
    client, db, w, token, _hits = public

    unknown = client.post(f"{PUBLIC}/zzt-not-a-real-token/amendment-request", json=_body(w))
    assert unknown.status_code == 404
    assert unknown.json().get("code") == "quotation_sign_link_invalid"

    w.record.sign_token_expires_at = datetime.utcnow() - timedelta(days=1)
    db.commit()
    expired = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert expired.status_code == 404
    assert expired.json().get("code") == "quotation_sign_link_invalid"
    assert _all_requests(db) == 0


def test_ac10_wire_an_accepted_issue_answers_409(public):
    client, db, w, token, _hits = public
    signed = client.post(
        f"{PUBLIC}/{token}/accept",
        json={"signer_name": CUSTOMER, "mode": "draw", "image_data_uri": A_SIGNATURE},
    )
    assert signed.status_code == 200, signed.text
    late = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert late.status_code == 409
    assert late.json().get("code") == "quotation_already_accepted"


def test_ac11_wire_a_superseded_issue_refuses_a_request_and_a_signature(public):
    client, db, w, token, _hits = public
    r2 = qdocs.issue(db, document=w.document, actor_user_id=w.owner)
    db.commit()

    asked = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert asked.status_code == 409
    assert asked.json().get("code") == "quotation_superseded"

    signed = client.post(
        f"{PUBLIC}/{token}/accept",
        json={"signer_name": CUSTOMER, "mode": "draw", "image_data_uri": A_SIGNATURE},
    )
    assert signed.status_code == 409
    assert signed.json().get("code") == "quotation_superseded"
    db.expire_all()
    assert w.record.accepted_at is None
    assert w.record.customer_signature_id is None

    page = client.get(f"{PUBLIC}/{token}").json()
    assert page["superseded_by_ref"] == r2.our_ref_text
    assert page["can_sign"] is False
    assert page["sign_blocked_reason"] == "superseded"


def test_ac12_the_public_route_is_rate_limited_per_ip_and_per_token(public, monkeypatch):
    from app.services import rate_limit

    client, db, w, token, hits = public
    ok = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert ok.status_code == 200, ok.text
    assert hits, "the route never asked the rate limiter"
    assert all("quotation_amendment" in bucket for bucket, _ident in hits)
    idents = {ident for _bucket, ident in hits}
    assert token in idents
    assert any(ident != token for ident in idents), "no per-IP hit"


def test_ac12_over_the_limit_answers_429_and_stores_nothing(public, monkeypatch):
    from app.services import rate_limit

    client, db, w, token, hits = public
    monkeypatch.setattr(
        rate_limit,
        "hit",
        lambda *a, **k: rate_limit.RateResult(allowed=False, retry_after_seconds=60),
    )
    response = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert response.status_code == 429, response.text
    assert _all_requests(db) == 0


def test_ac13_wire_signing_while_a_request_is_open_is_409_and_writes_no_signature(public):
    client, db, w, token, _hits = public
    asked = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert asked.status_code == 200, asked.text

    signed = client.post(
        f"{PUBLIC}/{token}/accept",
        json={"signer_name": CUSTOMER, "mode": "draw", "image_data_uri": A_SIGNATURE},
    )
    assert signed.status_code == 409, signed.text
    assert signed.json().get("code") == "quotation_amendment_open"
    db.expire_all()
    assert w.record.accepted_at is None
    assert w.record.customer_signature_id is None


def test_ac08_wire_a_second_submit_is_409_and_leaves_one_request(public):
    client, db, w, token, _hits = public
    assert client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w)).status_code == 200
    second = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert second.status_code == 409
    assert second.json().get("code") == "quotation_amendment_open"
    assert _all_requests(db) == 1


def test_ac15_wire_an_applied_issue_can_no_longer_be_signed(public):
    client, db, w, token, _hits = public
    assert client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w)).status_code == 200
    request = _svc().open_request(db, w.record.id)
    _decide(db, w, request, {})
    _svc().apply_request(db, request=request, actor_user_id=w.owner)
    db.commit()

    signed = client.post(
        f"{PUBLIC}/{token}/accept",
        json={"signer_name": CUSTOMER, "mode": "draw", "image_data_uri": A_SIGNATURE},
    )
    assert signed.status_code == 409, signed.text
    page = client.get(f"{PUBLIC}/{token}").json()
    assert page["sign_blocked_reason"] == "amendment_applied"


# ================================================================== the staff wire


@pytest.fixture()
def staff():
    from app.models.base import company_scope

    from .test_project_quotation_approval_routes import _client, _restore

    with blank_session() as db:
        w = _world(db)
        db.commit()
        client, originals = _client(db, w.owner)
        try:
            with company_scope(db, frozenset({w.company_id})):
                yield client, db, w
        finally:
            _restore(originals)


def _root(w, document=None) -> str:
    document = document or w.document
    return f"{BASE}/projects/{w.project.id}/quotation-documents/{document.id}"


def test_staff_get_returns_null_when_nobody_has_asked(staff):
    client, db, w = staff
    response = client.get(f"{_root(w)}/amendment-request")
    assert response.status_code == 200, response.text
    assert response.json() is None


def test_staff_get_returns_the_open_request_with_floor_flags(staff):
    client, db, w = staff
    request = _submit(
        db, w, [_change(w.lines["WC"], unit_price="380.00")], note=NOTE
    )
    db.commit()

    response = client.get(f"{_root(w)}/amendment-request")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(request.id)
    assert body["status"] == "open"
    assert body["note"] == NOTE
    (row,) = body["rows"]
    assert row["field"] == "unit_price" and row["decision"] == "pending"
    assert row["below_floor"] is True
    assert Decimal(str(row["floor_value"])) == Decimal("390.00")


def test_staff_put_decides_a_row_and_answers_the_request(staff):
    client, db, w = staff
    request = _submit(db, w, [_change(w.lines["WC"], unit_price="380.00")])
    row = next(iter(_rows(db, request).values()))
    db.commit()

    url = f"{_root(w)}/amendment-requests/{request.id}/rows/{row.id}"
    accepted = client.put(url, json={"decision": "accepted", "reason": None})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["rows"][0]["decision"] == "accepted"

    rejected = client.put(url, json={"decision": "rejected", "reason": "No"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["rows"][0]["decision_reason"] == "No"

    bad = client.put(url, json={"decision": "maybe"})
    assert bad.status_code == 422


def test_staff_put_on_another_documents_request_is_404(staff):
    client, db, w = staff
    request = _submit(db, w, [_change(w.lines["WC"], unit_price="380.00")])
    row = next(iter(_rows(db, request).values()))
    other = qdocs.create_document(db, project=w.project, actor_user_id=w.owner)
    db.commit()

    url = f"{_root(w, other)}/amendment-requests/{request.id}/rows/{row.id}"
    response = client.put(url, json={"decision": "accepted", "reason": None})
    assert response.status_code == 404, response.text
    assert client.get(f"{_root(w, other)}/amendment-request").json() is None


def test_staff_apply_returns_the_request_and_the_new_version_ids(staff):
    client, db, w = staff
    request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
    _decide(db, w, request, {})
    db.commit()

    undecided_url = f"{_root(w)}/amendment-requests/{request.id}/apply"
    response = client.post(undecided_url)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request"]["status"] == "applied"
    assert len(body["version_ids"]) == 1
    db.expire_all()
    versions = _versions(db, w.scope_a)
    assert body["version_ids"] == [str(versions[-1].id)]

    again = client.post(undecided_url)
    assert again.status_code == 409
    assert again.json().get("code") == "quotation_amendment_not_open"


def test_staff_apply_with_a_pending_row_is_422(staff):
    client, db, w = staff
    request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
    db.commit()
    response = client.post(f"{_root(w)}/amendment-requests/{request.id}/apply")
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_amendment_undecided"


def test_staff_routes_need_the_right_permissions(staff):
    from .test_project_quotation_approval_routes import _without_permission

    client, db, w = staff
    request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
    row = next(iter(_rows(db, request).values()))
    db.commit()

    with _without_permission(VIEW):
        assert client.get(f"{_root(w)}/amendment-request").status_code == 403

    with _without_permission(EDIT):
        put = client.put(
            f"{_root(w)}/amendment-requests/{request.id}/rows/{row.id}",
            json={"decision": "accepted", "reason": None},
        )
        assert put.status_code == 403
        apply = client.post(f"{_root(w)}/amendment-requests/{request.id}/apply")
        assert apply.status_code == 403
    db.expire_all()
    assert _rows(db, request)[(str(w.lines["WC"].id), "quantity")].decision == "pending"


def test_staff_apply_alerts_a_below_floor_accepted_price_like_a_hand_edit(staff, monkeypatch):
    """Apply sends the management breach alert a hand edit sends, for the accepted price under
    its floor (WC 380.00 < 390.00) and not for the one above it (BSN 150.00 > 130.00)."""
    from app.services import project_notify_service as notify

    client, db, w = staff
    alerts = []
    monkeypatch.setattr(
        notify,
        "notify_floor_breach",
        lambda db, *, project, event, actor_user_id=None: alerts.append(event) or 1,
    )
    request = _submit(
        db,
        w,
        [
            _change(w.lines["WC"], unit_price="380.00"),
            _change(w.lines["BSN"], unit_price="150.00"),
        ],
    )
    _decide(db, w, request, {})
    db.commit()

    response = client.post(f"{_root(w)}/amendment-requests/{request.id}/apply")
    assert response.status_code == 200, response.text

    assert len(alerts) == 1
    (event,) = alerts
    assert event["product_code"] == f"ZZT-WC-1001{w.tag}"
    assert Decimal(str(event["unit_price"])) == Decimal("380.00")
    assert Decimal(str(event["floor_value"])) == Decimal("390.00")


# ================================================================== fix round 1 (review + security)


def _statements(db):
    """Every SQL statement the session sends while the block runs."""
    from contextlib import contextmanager

    from sqlalchemy import event

    @contextmanager
    def capture():
        seen: list = []
        engine = db.get_bind()

        def listen(conn, cursor, statement, params, context, executemany):
            seen.append(statement)

        event.listen(engine, "before_cursor_execute", listen)
        try:
            yield seen
        finally:
            event.remove(engine, "before_cursor_execute", listen)

    return capture()


def test_s1_accept_reads_the_issue_for_update_before_its_checks():
    """Two tabs, one signing and one sending suggestions, serialise on the issue row."""
    with blank_session() as db:
        w = _world(db)
        with _statements(db) as seen:
            qdocs.accept_issue(
                db, record=w.record, signer_name=CUSTOMER, mode="draw", image_data_uri=A_SIGNATURE
            )
        assert any(
            "FOR UPDATE" in s and "quotation_issues" in s for s in seen
        ), "accept_issue never locked the issue row"


def test_s2_the_request_is_locked_when_read_for_a_decision_or_apply():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        with _statements(db) as seen:
            found = _svc().get_request_for_document_or_404(db, w.document, str(request.id))
        assert str(found.id) == str(request.id)
        assert any(
            "FOR UPDATE" in s and "quotation_amendment_requests" in s for s in seen
        ), "the request was read without a row lock"


def test_s2_wire_a_decision_after_apply_is_409_not_open(staff):
    client, db, w = staff
    request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
    row = next(iter(_rows(db, request).values()))
    _decide(db, w, request, {})
    db.commit()

    assert client.post(f"{_root(w)}/amendment-requests/{request.id}/apply").status_code == 200
    late = client.put(
        f"{_root(w)}/amendment-requests/{request.id}/rows/{row.id}",
        json={"decision": "rejected", "reason": "Changed my mind"},
    )
    assert late.status_code == 409, late.text
    assert late.json().get("code") == "quotation_amendment_not_open"


def test_s3_the_staff_payload_names_a_scope_with_a_hand_made_draft():
    with blank_session() as db:
        w = _world(db)
        request = _a_suggestion(db, w)
        clean = _svc().serialize_request(db, request)
        assert clean["blocked_scopes"] == []

        quotes.revise(db, quotation=w.scope_a, actor_user_id=w.owner)
        db.flush()
        blocked = _svc().serialize_request(db, request)["blocked_scopes"]
        assert blocked == [
            {"quotation_id": str(w.scope_a.id), "scope_label": w.scope_a.scope_label}
        ]


def _apply_note_only(db, w):
    request = _submit(db, w, [], note=NOTE)
    _svc().apply_request(db, request=request, actor_user_id=w.owner)
    db.flush()
    return request


def _apply_with_a_revision(db, w):
    request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
    _decide(db, w, request, {})
    _svc().apply_request(db, request=request, actor_user_id=w.owner)
    db.flush()
    return request


def test_s4_a_note_only_applied_request_leaves_the_issue_signable():
    with blank_session() as db:
        w = _world(db)
        _apply_note_only(db, w)
        page = qdocs.serialize_sign_page(db, w.record)
        assert page["can_sign"] is True and page["sign_blocked_reason"] is None
        qdocs.accept_issue(
            db, record=w.record, signer_name=CUSTOMER, mode="draw", image_data_uri=A_SIGNATURE
        )
        assert w.record.accepted_at is not None


def test_s4_a_note_only_applied_request_allows_another_request():
    with blank_session() as db:
        w = _world(db)
        first = _apply_note_only(db, w)
        second = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        assert second.status == "open" and str(second.id) != str(first.id)


def test_s4_an_all_rejected_applied_request_leaves_the_issue_signable():
    with blank_session() as db:
        w = _world(db)
        request = _submit(db, w, [_change(w.lines["WC"], quantity="110.00")])
        _decide(db, w, request, {("WC", "quantity"): "rejected"}, reason="No")
        _svc().apply_request(db, request=request, actor_user_id=w.owner)
        db.flush()
        assert qdocs.serialize_sign_page(db, w.record)["can_sign"] is True


def test_s4_an_applied_request_that_revised_keeps_blocking_sign_and_requests():
    with blank_session() as db:
        w = _world(db)
        _apply_with_a_revision(db, w)
        page = qdocs.serialize_sign_page(db, w.record)
        assert page["sign_blocked_reason"] == "amendment_applied"
        _refused(
            lambda: qdocs.accept_issue(
                db, record=w.record, signer_name=CUSTOMER, mode="draw", image_data_uri=A_SIGNATURE
            ),
            409,
            "quotation_amendment_applied",
        )
        _refused(
            lambda: _submit(db, w, [_change(w.lines["BSN"], unit_price="150.00")]),
            409,
            "quotation_amendment_applied",
        )


def test_l2_a_line_amount_beyond_the_column_is_refused():
    """quantity x unit price must fit 9,999,999,999,999.99, using the issued value for a side
    that was not suggested."""
    with blank_session() as db:
        w = _world(db)
        for change in (
            _change(w.lines["WC"], quantity="9999999.99", unit_price="9999999999.99"),
            _change(w.lines["WC"], quantity="9999999.99", unit_price="1000000.01"),
        ):
            _refused(
                lambda change=change: _submit(db, w, [change]),
                422,
                "quotation_amendment_price_invalid",
            )
        assert _all_requests(db) == 0
        # Exactly at the ceiling is allowed: 9,999,999.99 x 1,000,000.00 fits.
        ok = _submit(db, w, [_change(w.lines["WC"], quantity="9999999.99", unit_price="1000000.00")])
        assert ok.status == "open"


def test_l3_the_requester_name_is_stored_on_one_line():
    with blank_session() as db:
        w = _world(db)
        request = _submit(
            db, w, [_change(w.lines["WC"], quantity="110.00")], name="  Kelly\n  Tan\t "
        )
        assert request.requester_name == "Kelly Tan"


def test_wire_the_public_page_carries_no_internal_pricing_or_audit_fields(public):
    client, db, w, token, _hits = public
    submitted = client.post(f"{PUBLIC}/{token}/amendment-request", json=_body(w))
    assert submitted.status_code == 200, submitted.text
    read = client.get(f"{PUBLIC}/{token}")
    import json

    hidden = (
        "floor_value",
        "below_floor",
        "total_issued",
        "total_after",
        "decided_by",
        "ip_address",
    )
    for page in (submitted.json(), read.json()):
        # The signature blocks carry their own `ip_address` on purpose (the page shows it), so
        # the guard is on the page's own keys and on the whole suggestion block.
        assert not set(hidden) & set(page)
        block = json.dumps(page["amendment_request"])
        for key in hidden:
            assert f'"{key}"' not in block, key
