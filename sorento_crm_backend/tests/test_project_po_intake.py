"""Customer PO intake and handwriting review cards (P4, P5; UAC groups D and M).

The unit tests here never call a model. They feed the persistence and arithmetic code a
canned page payload shaped exactly like ``document_extraction`` produces, because the
thing worth pinning is not that a vision model can read a page: it is that **what we do
with what it says** is right. Specifically, that

* a wrong amount is caught by our own Decimal multiplication and not believed,
* a strike-through arrives as a PROPOSED card and never as a cancelled line (D11),
* the same pencil note on a re-scan is the same note, carrying its decision forward,
* and a confirm is refused while any card is still proposed.

The last test in the file is different in kind. It runs the REAL extractor over the
client's REAL committed scan and asserts what was measured off it: every printed line,
every line's arithmetic, the cancellation card, and the successor PO number that exists
only in pencil. That is the difference between "we extract POs" and "we extract THIS PO
correctly" (AC-M1, AC-M2). It costs about two minutes and skips without a key.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.project_so import (
    ANNOTATION_ACCEPTED,
    ANNOTATION_PROPOSED,
    ANNOTATION_REJECTED,
    ProjectPOVersion,
)
from app.models.projects import ProjectPurchaseOrderLine
from app.models.user import User
from app.services import project_seed_service
from app.services.document_extraction import PageResult
from app.services.error_handler import AppException
from app.services.project_po_extraction_service import (
    STATE_DONE,
    STATE_QUEUED,
    ProjectPOExtractionService,
    classify_annotation,
    dedup_key,
)

from ._pg_fixture import blank_session

MARKER = "zzt-po-intake"

GOLDEN_PO = (
    Path(__file__).resolve().parents[2]
    / "sorento_crm_frontend"
    / "e2e"
    / "fixtures"
    / "project-cs"
    / "customer-po-buimaco-r1.pdf"
)


def _uid() -> str:
    return str(uuid.uuid4())


def _message(exc: AppException) -> str:
    """AppException stuffs the message into HTTPException.detail as a dict."""
    detail = exc.detail
    return (detail or {}).get("message", "") if isinstance(detail, dict) else str(detail)


def _code(exc: AppException) -> str:
    detail = exc.detail
    return (detail or {}).get("code", "") if isinstance(detail, dict) else ""


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tuju {_uid()[:6]}",
    )


def _po(db, project, owner, number: str):
    from app.services import project_po_service as po_svc

    return po_svc.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={"po_number": number, "po_source": "contractor_direct"},
    )


def _version(db, po, *, version_no: int = 1) -> ProjectPOVersion:
    """A version row with no stored document: every unit test below feeds the pages in
    directly, so nothing here needs object storage."""
    version = ProjectPOVersion(
        company_id=po.company_id,
        purchase_order_id=po.id,
        version_no=version_no,
        source_filename=f"{MARKER}.pdf",
        page_count=1,
        extraction_state=STATE_QUEUED,
    )
    db.add(version)
    db.flush()
    return version


def _page(page_no: int, **payload) -> PageResult:
    return PageResult(page_no=page_no, data=payload)


# A page shaped exactly like `po_extractor` returns one: the printed header, two priced
# lines, one of them crossed out by hand, and the pencil note beside it.
def _buimaco_like_page() -> PageResult:
    return _page(
        1,
        header={
            "po_number": "HQ/26/01/041",
            "po_date": "19/01/2026",
            "term": "60 DAYS",
            "sales_person": "MARYAM",
            "cust_order_no": "TUJU-01",
            "remark": "Deliver to site",
        },
        lines=[
            {
                "no": 1,
                "stock_code": "SRTWC86",
                "description": "SRTWC8613-RL One-Piece WC",
                "qty": 927,
                "uom": "SETS",
                "unit_price": 392.85,
                "amount": 364171.95,
                "struck_through": False,
            },
            {
                "no": 7,
                "stock_code": "SRTFV1001",
                "description": "SRTFV1001 Flush Valve",
                "qty": 16,
                "uom": "NOS",
                "unit_price": 295.85,
                "amount": 4733.60,
                "struck_through": True,
            },
        ],
        annotations=[
            {
                "text": "cancel - refer to New P/O HQ/26/05/087",
                "date": "15/5/26",
                "refers_to_items": [7],
                "meaning": "cancel this line",
            }
        ],
    )


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Yana")
        project = _project(db, company_id, owner)
        yield db, project, owner


# ---------------------------------------------------- the AI proposes, we decide


def test_arithmetic_catches_an_amount_the_model_got_wrong(seeded):
    """The model's own `amount` is never believed: qty * unit_price is recomputed here."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-ARITH"))

    service.persist_pages(
        version,
        [
            _page(
                1,
                header={"po_number": "PO-ARITH"},
                lines=[
                    # 3 x 100.00 is 300.00, as printed.
                    {"no": 1, "stock_code": "A1", "qty": 3, "unit_price": 100.00, "amount": 300.00},
                    # 4 x 25.50 is 102.00, and the page claims 101.00.
                    {"no": 2, "stock_code": "A2", "qty": 4, "unit_price": 25.50, "amount": 101.00},
                ],
            )
        ],
        model="test/canned",
    )

    lines = {line.line_no: line for line in service._lines(version.id)}
    assert lines[1].arithmetic_ok is True
    assert lines[2].arithmetic_ok is False
    assert (version.arithmetic_passed, version.arithmetic_total) == (1, 2)


def test_a_line_missing_a_number_is_unchecked_rather_than_passed(seeded):
    """A gap is a different problem from a wrong figure and must not inflate the pass
    count: somebody has to type the missing number in."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-GAP"))

    service.persist_pages(
        version,
        [_page(1, lines=[{"no": 1, "stock_code": "A1", "qty": 3, "amount": 300.00}])],
    )

    line = service._lines(version.id)[0]
    assert line.arithmetic_ok is None
    assert (version.arithmetic_passed, version.arithmetic_total) == (0, 1)


def test_money_survives_as_decimal_and_not_as_a_float(seeded):
    """A float round trip loses cents on a 1.8 million ringgit PO, so the totals are
    asserted to the cent rather than approximately."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-CENTS"))

    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    {"no": n, "stock_code": f"C{n}", "qty": 927, "unit_price": 392.85,
                     "amount": 364171.95}
                    for n in range(1, 4)
                ],
            )
        ],
    )

    totals = service.recompute_totals(version)
    assert totals["lines_total"] == Decimal("1092515.85")
    assert totals["extracted_total"] == Decimal("1092515.85")
    assert totals["arithmetic_passed"] == 3


def test_line_numbering_follows_the_printed_item_numbers_across_pages(seeded):
    """Handwriting refers to lines by the number the customer printed ("cancel item 7"),
    so ours have to be theirs."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-NUMBERING"))

    service.persist_pages(
        version,
        [
            _page(1, lines=[{"no": 1, "stock_code": "A"}, {"no": 2, "stock_code": "B"}]),
            _page(2, lines=[{"no": 3, "stock_code": "C"}, {"stock_code": "D"}]),
        ],
    )

    assert [line.line_no for line in service._lines(version.id)] == [1, 2, 3, 4]


# ------------------------------------------------- handwriting: proposed, not applied


def test_a_strike_through_is_proposed_as_a_card_and_never_cancels_a_line(seeded):
    """D11, the whole point of the slice. The cancellation of item 7 exists only in
    pencil; applying it automatically would move 4,733.60 on a model's opinion."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))

    service.persist_pages(version, [_buimaco_like_page()])

    assert all(line.is_cancelled is False for line in service._lines(version.id))
    cards = service._annotations(version.id)
    assert len(cards) == 1, "the pencil note and the strike-through are one decision"
    card = cards[0]
    assert card.state == ANNOTATION_PROPOSED
    assert card.interpretation == "cancel_line"
    assert card.refers_to_lines == [7]
    assert card.interpretation_json["po_number"] == "HQ/26/05/087"


def test_a_bare_strike_through_still_gets_its_own_card(seeded):
    """A line crossed out with no note beside it is still an act somebody performed."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-BARE-STRIKE"))

    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    {"no": 1, "stock_code": "A", "qty": 1, "unit_price": 10, "amount": 10},
                    {"no": 2, "stock_code": "B", "qty": 1, "unit_price": 10, "amount": 10,
                     "struck_through": True},
                ],
            )
        ],
    )

    cards = service._annotations(version.id)
    assert [card.interpretation for card in cards] == ["cancel_line"]
    assert cards[0].refers_to_lines == [2]
    assert cards[0].state == ANNOTATION_PROPOSED
    assert all(line.is_cancelled is False for line in service._lines(version.id))


def test_accepting_the_card_is_what_cancels_the_line(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])
    card = service._annotations(version.id)[0]

    result = service.accept_annotation(
        annotation=card, actor_user_id=owner, note="Confirmed with Maryam"
    )

    lines = {line.line_no: line for line in service._lines(version.id)}
    assert lines[7].is_cancelled is True
    assert lines[1].is_cancelled is False
    assert card.state == ANNOTATION_ACCEPTED
    assert result["applied"]["cancelled_line_nos"] == [7]
    assert result["applied"]["successor_po_number"] == "HQ/26/05/087"
    # The successor PO has not been uploaded yet, so the pointer stands alone (AC-D7).
    assert result["applied"]["successor_po_linked"] is False
    # The cancelled amount leaves the live total but is still reported, so the gap
    # against what the document says reads as the cancellation it is.
    assert result["totals"]["lines_total"] == Decimal("364171.95")
    assert result["totals"]["cancelled_total"] == Decimal("4733.60")
    assert result["totals"]["extracted_total"] == Decimal("368905.55")


def test_the_successor_po_links_once_that_document_arrives(seeded):
    """AC-D7. The pencil names a PO months before it exists; the link is made from
    whichever side turns up second."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    first = _po(db, project, owner, "HQ/26/01/041")
    version = _version(db, first)
    service.persist_pages(version, [_buimaco_like_page()])
    service.accept_annotation(
        annotation=service._annotations(version.id)[0], actor_user_id=owner
    )
    assert first.superseded_by_po_id is None

    successor = _po(db, project, owner, "HQ/26/05/087")
    service._adopt_pending_successors(successor)

    assert first.superseded_by_po_id == successor.id
    assert successor.supersedes_po_number == "HQ/26/01/041"


def test_a_rejected_card_changes_nothing_and_is_kept(seeded):
    """AC-D4: recorded as rejected, never deleted."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])
    card = service._annotations(version.id)[0]

    service.reject_annotation(
        annotation=card, actor_user_id=owner, note="Pencil belongs to another PO"
    )

    assert card.state == ANNOTATION_REJECTED
    assert card.action_note == "Pencil belongs to another PO"
    assert all(line.is_cancelled is False for line in service._lines(version.id))


def test_an_edited_card_applies_the_readers_reading(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])
    card = service._annotations(version.id)[0]

    service.edit_annotation(
        annotation=card,
        actor_user_id=owner,
        interpretation="amend_code",
        interpretation_json={"line_nos": [1], "code": "SRTWC8608-RL"},
        note="It amends the code, it does not cancel",
    )

    lines = {line.line_no: line for line in service._lines(version.id)}
    assert lines[1].stock_code_raw == "SRTWC8608-RL"
    assert lines[7].is_cancelled is False
    assert card.state == "edited"


def test_an_actioned_card_cannot_be_actioned_twice(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])
    card = service._annotations(version.id)[0]
    service.accept_annotation(annotation=card, actor_user_id=owner)

    with pytest.raises(AppException) as caught:
        service.accept_annotation(annotation=card, actor_user_id=owner)
    assert caught.value.status_code == 409


# ------------------------------------------------------------------ dedup on re-scan


def test_the_same_pencil_note_on_a_re_scan_is_the_same_note(seeded):
    """AC-D5. Re-uploading an annotated scan must not re-propose a decision somebody
    already made, and the decision has to bite on the new version's lines too."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, "HQ/26/01/041")

    first = _version(db, po, version_no=1)
    service.persist_pages(first, [_buimaco_like_page()])
    service.accept_annotation(
        annotation=service._annotations(first.id)[0],
        actor_user_id=owner,
        note="Cancelled by the 15/5 amendment",
    )

    # The second scan reads the same note with different punctuation and casing, which
    # is exactly what a re-scan produces.
    rescan = _buimaco_like_page()
    rescan.data["annotations"][0]["text"] = "Cancel , refer to new P/O HQ/26/05/087."
    second = _version(db, po, version_no=2)
    service.persist_pages(second, [rescan])

    cards = service._annotations(second.id)
    assert len(cards) == 1
    assert cards[0].state == ANNOTATION_ACCEPTED, "the decision carries forward"
    assert cards[0].action_note == "Cancelled by the 15/5 amendment"
    lines = {line.line_no: line for line in service._lines(second.id)}
    assert lines[7].is_cancelled is True, "and so does its consequence"


def test_dedup_key_ignores_punctuation_but_not_the_line_it_names():
    same = dedup_key("15/5/26", [7], "cancel - refer to New P/O HQ/26/05/087")
    punctuated = dedup_key("15/5/26", [7], "Cancel , refer to new P/O HQ/26/05/087.")
    other_line = dedup_key("15/5/26", [8], "cancel - refer to New P/O HQ/26/05/087")
    other_date = dedup_key("16/5/26", [7], "cancel - refer to New P/O HQ/26/05/087")

    assert same == punctuated
    assert same != other_line
    assert same != other_date


def test_a_note_that_cancels_and_names_a_successor_is_one_card():
    interpretation, payload = classify_annotation(
        "cancel - refer to New P/O HQ/26/05/087", "cancel this line", [7]
    )
    assert interpretation == "cancel_line"
    assert payload["po_number"] == "HQ/26/05/087"
    assert payload["line_nos"] == [7]


def test_a_note_that_only_points_forward_is_a_successor_card():
    interpretation, payload = classify_annotation(
        "refer to New P/O HQ/26/05/087", "new purchase order issued", []
    )
    assert interpretation == "successor_po"
    assert payload["po_number"] == "HQ/26/05/087"


# ------------------------------------------------------------------------- confirm


def test_confirm_is_refused_while_a_card_is_still_proposed(seeded):
    """A cancellation written in pencil is the only place some of these lines exist, so
    nobody confirms a PO before somebody has read the pencil."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])

    with pytest.raises(AppException) as caught:
        service.confirm_version(version=version, actor_user_id=owner)

    assert caught.value.status_code == 409
    assert _code(caught.value) == "po_version_annotations_pending"
    assert version.confirmed_at is None


def test_confirm_writes_the_phase_one_po_lines(seeded):
    """The confirmed state lands on `project_purchase_order_lines`, where the quotation
    cross-check already lives. The version keeps what the document said, untouched."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, "HQ/26/01/041")
    version = _version(db, po)
    service.persist_pages(version, [_buimaco_like_page()])
    service.accept_annotation(
        annotation=service._annotations(version.id)[0], actor_user_id=owner
    )

    result = service.confirm_version(version=version, actor_user_id=owner)

    written = (
        db.query(ProjectPurchaseOrderLine)
        .filter(ProjectPurchaseOrderLine.po_id == po.id)
        .all()
    )
    assert result["line_count"] == 1, "the cancelled line is not a commitment"
    assert [line.product_code for line in written] == ["SRTWC86"]
    assert written[0].quantity == Decimal("927.00")
    assert written[0].line_total == Decimal("364171.95")
    assert po.po_amount == Decimal("364171.95")
    assert po.po_date is not None and po.po_date.isoformat() == "2026-01-19"
    assert po.term_days == 60
    assert po.sales_person == "MARYAM"
    assert po.customer_order_ref == "TUJU-01"
    assert version.confirmed_at is not None
    # The record of what the paper said is untouched by the confirmation.
    assert len(service._lines(version.id)) == 2


def test_a_confirmed_version_is_frozen(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])
    service.accept_annotation(
        annotation=service._annotations(version.id)[0], actor_user_id=owner
    )
    service.confirm_version(version=version, actor_user_id=owner)

    line = service._lines(version.id)[0]
    with pytest.raises(AppException) as caught:
        service.update_line(version=version, line=line, payload={"qty": Decimal("1")})
    assert caught.value.status_code == 409


def test_editing_a_line_recomputes_its_arithmetic_and_the_totals(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-EDIT"))
    service.persist_pages(
        version,
        [_page(1, lines=[{"no": 1, "stock_code": "A", "qty": 4, "unit_price": 25.50,
                          "amount": 101.00}])],
    )
    line = service._lines(version.id)[0]
    assert line.arithmetic_ok is False

    service.update_line(version=version, line=line, payload={"amount": Decimal("102.00")})

    assert line.arithmetic_ok is True
    assert version.arithmetic_passed == 1
    assert service.recompute_totals(version)["lines_total"] == Decimal("102.00")


# ------------------------------------------------------------ upload and versioning


@pytest.fixture()
def stored_document(monkeypatch):
    """Object storage stubbed out. The bytes going to S3 are not what these tests are
    about, and a unit test that needs credentials is a test nobody runs."""
    monkeypatch.setattr(
        ProjectPOExtractionService,
        "_store_document",
        lambda self, **kwargs: None,
    )


def _one_page_pdf() -> bytes:
    import fitz

    document = fitz.open()
    document.new_page()
    try:
        return document.tobytes()
    finally:
        document.close()


def test_a_second_upload_of_the_same_po_number_becomes_version_two(seeded, stored_document):
    """A revision is a new VERSION of one commitment, never a second purchase order."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    content = _one_page_pdf()

    first = service.create_version_from_upload(
        project=project,
        actor_user_id=owner,
        filename="po-r1.pdf",
        mime="application/pdf",
        content=content,
        po_number="HQ/26/01/041",
    )
    second = service.create_version_from_upload(
        project=project,
        actor_user_id=owner,
        filename="po-r2.pdf",
        mime="application/pdf",
        content=content,
        po_number="hq/26/01/041 ",
    )

    assert first.purchase_order_id == second.purchase_order_id
    assert (first.version_no, second.version_no) == (1, 2)
    assert first.extraction_state == STATE_QUEUED


def test_an_unnumbered_upload_adopts_the_extracted_number(seeded, stored_document):
    """Extraction fills the number in; the confirm screen is where a human agrees to it."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)

    version = service.create_version_from_upload(
        project=project,
        actor_user_id=owner,
        filename="scan.pdf",
        mime="application/pdf",
        content=_one_page_pdf(),
    )
    assert service.get_po(version.purchase_order_id).po_number == ""

    service.persist_pages(version, [_buimaco_like_page()])

    assert service.get_po(version.purchase_order_id).po_number == "HQ/26/01/041"


def test_an_unnumbered_upload_of_a_po_we_already_hold_joins_it(seeded, stored_document):
    """Contract 2: if the extracted number matches an existing PO on the project, the
    upload is a new version of that PO rather than a second one."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    existing = _po(db, project, owner, "HQ/26/01/041")
    _version(db, existing, version_no=1)

    version = service.create_version_from_upload(
        project=project,
        actor_user_id=owner,
        filename="rescan.pdf",
        mime="application/pdf",
        content=_one_page_pdf(),
    )
    shell_id = version.purchase_order_id
    assert shell_id != existing.id

    service.persist_pages(version, [_buimaco_like_page()])

    assert version.purchase_order_id == existing.id
    assert version.version_no == 2
    from app.models.projects import ProjectPurchaseOrder

    assert (
        db.query(ProjectPurchaseOrder).filter(ProjectPurchaseOrder.id == shell_id).first()
        is None
    ), "the empty shell row must not be left on the project"


def test_an_unsupported_file_is_refused_with_a_readable_reason(seeded, stored_document):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)

    with pytest.raises(AppException) as caught:
        service.create_version_from_upload(
            project=project,
            actor_user_id=owner,
            filename="schedule.xlsx",
            mime="application/vnd.ms-excel",
            content=b"not a document",
        )
    assert caught.value.status_code == 422
    assert "PDF" in _message(caught.value)


# ---------------------------------------------------------------- approval handshake


def test_approval_then_countersignature_by_a_second_person(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, "HQ/26/01/041")
    version = _version(db, po)
    service.persist_pages(version, [_buimaco_like_page()])
    service.accept_annotation(
        annotation=service._annotations(version.id)[0], actor_user_id=owner
    )
    service.confirm_version(version=version, actor_user_id=owner)

    service.approve_po(po=po, actor_user_id=owner)
    assert po.status == "approved"

    with pytest.raises(AppException) as caught:
        service.countersign_po(po=po, actor_user_id=owner)
    assert caught.value.status_code == 409

    manager = _user(db, f"{MARKER} Manager")
    service.countersign_po(po=po, actor_user_id=manager)
    assert po.countersigned_by == manager


def test_a_po_with_no_lines_cannot_be_approved(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, "HQ/26/01/041")

    with pytest.raises(AppException) as caught:
        service.approve_po(po=po, actor_user_id=owner)
    assert _code(caught.value) == "po_nothing_to_approve"


def test_a_po_carrying_an_unconfirmed_document_cannot_be_approved(seeded):
    """Approving a PO nobody has checked against the scan is what the confirm screen
    exists to prevent. A hand-keyed PO with no documents is unaffected."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, "HQ/26/01/041")
    version = _version(db, po)
    service.persist_pages(version, [_buimaco_like_page()])
    # Lines exist on the phase-1 PO from an earlier hand entry, so the "nothing to
    # approve" guard would not fire on its own.
    from app.services import project_po_service as po_svc

    po_svc.upsert_line(
        db, po=po, payload={"product_code": "SRTWC86", "unit_price": Decimal("1"), "quantity": 1}
    )

    with pytest.raises(AppException) as caught:
        service.approve_po(po=po, actor_user_id=owner)
    assert _code(caught.value) == "po_version_not_confirmed"


# ------------------------------------------------- what the confirm screen renders


def test_every_line_carries_the_page_it_was_printed_on(seeded):
    """The side-by-side viewer keys the page turn on this; without it the sync silently
    does nothing and the screen still looks right, which is the worst kind of broken."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-PAGES"))
    service.persist_pages(
        version,
        [
            _page(1, lines=[{"no": 1, "stock_code": "A"}, {"no": 2, "stock_code": "B"}]),
            _page(2, lines=[{"no": 3, "stock_code": "C"}]),
        ],
    )

    body = service.serialize_version(version)

    assert [(line["line_no"], line["page_no"]) for line in body["lines"]] == [
        (1, 1),
        (2, 1),
        (3, 2),
    ]


def test_the_version_reports_how_much_of_the_document_was_read(seeded):
    """"Only 1 of 2 pages were read" cannot be said from a state of "done" plus a
    sentence, so the counts travel with the version."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-PARTIAL-READ"))
    service.persist_pages(
        version,
        [
            _page(1, lines=[{"no": 1, "stock_code": "A"}]),
            PageResult(page_no=2, data=None, error="rate limited"),
        ],
    )

    body = service.serialize_version(version)

    assert body["pages_extracted"] == 1
    assert body["failed_pages"] == [2]


def test_the_version_carries_the_approval_stamps(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, "HQ/26/01/041")
    version = _version(db, po)
    service.persist_pages(version, [_buimaco_like_page()])
    service.accept_annotation(
        annotation=service._annotations(version.id)[0], actor_user_id=owner
    )
    service.confirm_version(version=version, actor_user_id=owner)

    before = service.serialize_version(version)["purchase_order"]
    assert before["approved_at"] is None and before["countersigned_at"] is None

    service.approve_po(po=po, actor_user_id=owner)
    manager = _user(db, f"{MARKER} Manager")
    service.countersign_po(po=po, actor_user_id=manager)

    after = service.serialize_version(version)["purchase_order"]
    assert after["status"] == "approved"
    assert after["approved_by_name"] == f"{MARKER} Yana"
    assert after["countersigned_by_name"] == f"{MARKER} Manager"


def test_a_gap_that_is_exactly_the_cancellation_still_reconciles(seeded):
    """Compared exactly, not with a tolerance: on the client's own PO the gap is 4,733.60
    to the cent, and treating it as a mismatch would block a correct PO for ever."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])
    assert service.recompute_totals(version)["reconciles"] is True

    service.accept_annotation(
        annotation=service._annotations(version.id)[0], actor_user_id=owner
    )

    totals = service.recompute_totals(version)
    assert totals["cancelled_total"] == Decimal("4733.60")
    assert totals["reconciles"] is True


def test_a_misread_amount_does_not_reconcile(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    version = _version(db, _po(db, project, owner, "PO-MISREAD"))
    service.persist_pages(
        version,
        [_page(1, lines=[{"no": 1, "stock_code": "A", "qty": 4, "unit_price": 25.50,
                          "amount": 101.00}])],
    )

    assert service.recompute_totals(version)["reconciles"] is False


def test_the_header_is_editable_before_confirmation(seeded):
    """AC-D3, and the edit is what the confirm then adopts, so there is one path by
    which a header value reaches the purchase order."""
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, "HQ/26/01/041")
    version = _version(db, po)
    service.persist_pages(version, [_buimaco_like_page()])

    from datetime import date as _date

    service.update_header(
        version=version,
        payload={
            "po_number": "HQ/26/01/121",
            "po_date": _date(2026, 1, 16),
            "term_days": 90,
            "sales_person": "VALERIE",
            "admin_ref": "PS26-0143",
        },
    )

    body = service.serialize_version(version)
    assert body["header"]["po_number"] == "HQ/26/01/121"
    assert body["header"]["po_date"].isoformat() == "2026-01-16"
    assert body["header"]["term_days"] == 90
    assert body["header"]["sales_person"] == "VALERIE"
    # D24: the filing reference is ours, so it lands on the PO and not in the record of
    # what the paper said.
    assert po.admin_ref == "PS26-0143"

    service.accept_annotation(
        annotation=service._annotations(version.id)[0], actor_user_id=owner
    )
    service.confirm_version(version=version, actor_user_id=owner)
    assert po.po_number == "HQ/26/01/121"
    assert po.term_days == 90
    assert po.sales_person == "VALERIE"


def test_the_header_cannot_take_a_number_another_po_already_has(seeded):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    _po(db, project, owner, "HQ/26/05/087")
    version = _version(db, _po(db, project, owner, "HQ/26/01/041"))
    service.persist_pages(version, [_buimaco_like_page()])

    with pytest.raises(AppException) as caught:
        service.update_header(version=version, payload={"po_number": "HQ/26/05/087"})
    assert _code(caught.value) == "po_number_already_on_project"


# --------------------------------------------------------------------- golden set
#
# AC-M1, AC-M1a, AC-M2 (UAC group M). Runs the real model over the client's real scan,
# which takes about two minutes, and is the objective done condition for this slice: an
# extraction change that regresses it does not merge.
#
# One correction to the acceptance criteria, from reading the paper rather than the
# summary of it. AC-M1 and the fixture README both say 52 lines; the document's own last
# printed item number is 51 (page 9, `51 CB6645-NL ... 7,020.00`, followed by the
# delivery block). The 52nd "row" is the description of item 49 spilling onto page 9
# above item 50, which is not a line and must not become one. The count is therefore
# asserted at 51 and the load-bearing assertion is the TOTAL: 1,810,640.62 to the cent,
# which cannot come out right if a priced line were missed.

GOLDEN_PO_NUMBER = "HQ/26/01/121"
GOLDEN_LINE_COUNT = 51
GOLDEN_EXTRACTED_TOTAL = Decimal("1810640.62")
# 1,810,640.62 minus the handwritten cancellation of item 7 (4,733.60). The same figure
# is written by hand on page 10 of the scan and is the quotation total.
GOLDEN_LIVE_TOTAL = Decimal("1805907.02")


@pytest.fixture()
def golden_document(monkeypatch):
    """Feed the real committed scan straight to the extractor, skipping object storage."""
    content = GOLDEN_PO.read_bytes()
    monkeypatch.setattr(
        ProjectPOExtractionService,
        "_document_bytes",
        lambda self, version: (content, "application/pdf"),
    )


@pytest.mark.skipif(
    not GOLDEN_PO.exists(), reason="the client's PO scan is not in this checkout"
)
@pytest.mark.skipif(
    not __import__("app.config", fromlist=["settings"]).settings.gemini_api_key,
    reason="GEMINI_API_KEY is not configured",
)
def test_golden_set_the_real_buimaco_po(seeded, golden_document):
    db, project, owner = seeded
    service = ProjectPOExtractionService(db)
    po = _po(db, project, owner, GOLDEN_PO_NUMBER)
    version = _version(db, po)

    summary = service.run_extraction(str(version.id))

    assert summary["status"] == STATE_DONE, summary
    # Pinned by measurement, not by preference: flash matched both pro models exactly at
    # a fraction of the cost, and gpt-4o-mini missed the cancellation entirely (PLAN 5b).
    assert version.extraction_model == "gemini/gemini-2.5-flash"
    assert version.page_count == 10

    # AC-M1: the printed header and every printed line.
    header = (version.extracted_json or {})["header"]
    assert header["po_number"] == GOLDEN_PO_NUMBER
    assert header["term"] == "60 DAYS"
    lines = service._lines(version.id)
    assert len(lines) == GOLDEN_LINE_COUNT, f"read {len(lines)} lines"
    assert [line.line_no for line in lines] == list(range(1, GOLDEN_LINE_COUNT + 1))

    # AC-M1a: every line's own arithmetic holds, computed here in Decimal.
    assert (version.arithmetic_passed, version.arithmetic_total) == (
        GOLDEN_LINE_COUNT,
        GOLDEN_LINE_COUNT,
    )
    totals = service.recompute_totals(version)
    assert totals["extracted_total"] == GOLDEN_EXTRACTED_TOTAL
    assert totals["lines_total"] == GOLDEN_EXTRACTED_TOTAL

    # AC-M2: both dated handwritten amendments arrive as cards, and NOTHING is applied.
    cards = service._annotations(version.id)
    assert all(card.state == ANNOTATION_PROPOSED for card in cards)
    assert all(line.is_cancelled is False for line in lines)

    dated = {card.written_date: card for card in cards if card.written_date}
    assert "26/1/26" in dated, [card.raw_text for card in cards]
    amend = dated["26/1/26"]
    assert amend.refers_to_lines == [5, 20, 23]

    assert "15/5/26" in dated, [card.raw_text for card in cards]
    cancellation = dated["15/5/26"]
    assert cancellation.interpretation == "cancel_line"
    assert cancellation.refers_to_lines == [7]
    # AC-D7: the successor PO exists only in this pencil note.
    assert cancellation.interpretation_json["po_number"] == "HQ/26/05/087"

    # The self-proving reconciliation (PLAN 5b): accept that one card and the live total
    # is the quotation total to the cent.
    service.accept_annotation(annotation=cancellation, actor_user_id=owner)
    after = service.recompute_totals(version)
    assert after["lines_total"] == GOLDEN_LIVE_TOTAL
    assert after["cancelled_total"] == Decimal("4733.60")
    assert {line.line_no for line in lines if line.is_cancelled} == {7}
