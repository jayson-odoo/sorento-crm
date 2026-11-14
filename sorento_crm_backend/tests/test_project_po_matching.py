"""PO-UPLOAD-MATCHING: how a read PO line finds its product, its qty and its total.

UAC: documentation/plans/projects/po-upload-matching-14nov-acceptance-criteria.md
Contract: documentation/plans/projects/PLAN-po-upload-matching-14nov.md, section "Contract".

Matching runs in three steps and every test below pins one of them:

* exact catalogue code (PO company only) -> ``resolution_source = "code"``, no model call;
* the customer's remembered code (``projects.customer_item_code_map``) -> ``"map"``;
* everything else goes to ONE model call per batch of at most 40 lines
  (``project_po_matching.ask_line_matcher``), with candidates from the bound quotation, the
  customer's map and the catalogue shortlist. A pick outside a line's candidates is dropped.

The model is never reached: ``ask_line_matcher`` is replaced for EVERY test in this file by a
recording fake (autouse fixture ``matcher``). Codes are catalogue shapes, never customer data.
"""
from __future__ import annotations

import copy
import uuid
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

import pytest
from sqlalchemy import func

from app.models.order import Customer
from app.models.project_so import CustomerItemCodeMap, ProjectPOVersion
from app.models.projects import ProjectParty, ProjectPurchaseOrderLine
from app.services import project_seed_service
from app.services.error_handler import AppException
from app.services.project_po_extraction_service import STATE_DONE, ProjectPOExtractionService

from ._pg_fixture import blank_session
from .test_project_po_intake import (
    _catalogue_product,
    _code,
    _message,
    _page,
    _project,
    _quotation,
    _sorento,
    _user,
    _version,
)

MARKER = "zzt-po-match"
BASE = "/api/v1/project-sales"

# The REAL model call, captured at import (before the autouse fake replaces it), for the
# fix-round tests that stub the PROVIDER instead and need the real payload and prompt.
try:
    from app.services import project_po_matching as _pm_at_import

    _REAL_ASK_LINE_MATCHER = _pm_at_import.ask_line_matcher
except ImportError:  # pragma: no cover - red phase only
    _REAL_ASK_LINE_MATCHER = None


def _uid() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ the model stub


class FakeMatcher:
    """Stands in for ``project_po_matching.ask_line_matcher``.

    ``answers`` is keyed by line_no: ``{"product_code": str|None, "confidence": str,
    "options": [code, ...]}``. Only lines in the batch are answered. ``fail`` decides per
    batch whether to raise (it receives the batch's input items).
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.answers: Dict[int, Dict[str, Any]] = {}
        self.fail: Optional[Callable[[List[dict]], Optional[Exception]]] = None

    def __call__(self, db, lines, *, company_id=None, **kwargs):
        self.calls.append({"lines": copy.deepcopy(list(lines)), "company_id": company_id})
        if self.fail is not None:
            exc = self.fail(list(lines))
            if exc is not None:
                raise exc
        out = []
        for item in lines:
            answer = self.answers.get(int(item["line_no"]))
            if answer is None:
                continue
            out.append(
                {
                    "line_no": int(item["line_no"]),
                    "product_code": answer.get("product_code"),
                    "confidence": answer.get("confidence", "high"),
                    "options": list(answer.get("options") or []),
                }
            )
        return out

    def sent_line_nos(self) -> List[int]:
        return [int(item["line_no"]) for call in self.calls for item in call["lines"]]

    def item_for(self, line_no: int) -> Dict[str, Any]:
        for call in self.calls:
            for item in call["lines"]:
                if int(item["line_no"]) == line_no:
                    return item
        raise AssertionError(f"line {line_no} was never sent to the matcher: {self.calls!r}")


@pytest.fixture(autouse=True)
def matcher(monkeypatch):
    """No test in this file ever reaches a provider: the one model call is replaced.

    Tolerates the module not existing yet (red phase) so tests that do not need it fail on
    their own assertion, not on this fixture.
    """
    fake = FakeMatcher()
    try:
        from app.services import project_po_matching
    except ImportError:
        project_po_matching = None
    if project_po_matching is not None:
        monkeypatch.setattr(project_po_matching, "ask_line_matcher", fake)
    return fake


def _matching_module():
    from app.services import project_po_matching

    return project_po_matching


# --------------------------------------------------------------------- the chain


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} CONTACT AH")
        project = _project(db, company_id, owner)
        yield db, project, owner


def _customer(db, company_id: str) -> Customer:
    row = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{_uid()[:8]}",
        customer_name=f"{MARKER} contractor",
    )
    db.add(row)
    db.flush()
    return row


def _customer_po(
    db,
    project,
    owner: str,
    number: str,
    *,
    customer: Optional[Customer] = None,
    quotation_version_id: Optional[str] = None,
):
    """A PO whose issuing party is bridged to a debtor, so the code map has a customer."""
    from app.services import project_po_service as po_svc

    customer = customer or _customer(db, project.company_id)
    party = ProjectParty(
        id=_uid(),
        company_id=project.company_id,
        party_type="main_contractor",
        name=f"{MARKER} party {_uid()[:6]}",
        customer_id=customer.id,
    )
    db.add(party)
    db.flush()
    payload: Dict[str, Any] = {
        "po_number": number,
        "po_source": "contractor_direct",
        "issuing_party_id": party.id,
    }
    if quotation_version_id:
        payload["quotation_version_id"] = quotation_version_id
    po = po_svc.create_po(db, project=project, actor_user_id=owner, payload=payload)
    return po, customer


def _products(db, company_id: str, *codes: str) -> Dict[str, str]:
    return {code: str(_catalogue_product(db, company_id, code).id) for code in codes}


def _map_row(db, *, company_id, customer_id, code, product_id, by=None) -> CustomerItemCodeMap:
    row = CustomerItemCodeMap(
        company_id=company_id,
        customer_id=customer_id,
        customer_code=code,
        product_id=product_id,
        confirmed_by=by,
    )
    db.add(row)
    db.flush()
    return row


def _map_rows(db, customer_id: str, code: str) -> List[CustomerItemCodeMap]:
    return (
        db.query(CustomerItemCodeMap)
        .filter(
            CustomerItemCodeMap.customer_id == customer_id,
            func.upper(CustomerItemCodeMap.customer_code) == code.upper(),
        )
        .all()
    )


def _row(no: int, *, code=None, description=None, qty=1, unit_price=10.0, amount=None):
    if amount is None and qty is not None and unit_price is not None:
        amount = float(Decimal(str(qty)) * Decimal(str(unit_price)))
    return {
        "no": no,
        "stock_code": code,
        "description": description,
        "qty": qty,
        "unit_price": unit_price,
        "amount": amount,
        "struck_through": False,
    }


def _lines(service, version) -> Dict[int, Any]:
    return {line.line_no: line for line in service._lines(version.id)}


def _match(version, line_no: int) -> Dict[str, Any]:
    return ((version.extracted_json or {}).get("line_matches") or {}).get(str(line_no)) or {}


def _serialized(service, version) -> Dict[int, Dict[str, Any]]:
    return {line["line_no"]: line for line in service.serialize_version(version)["lines"]}


# ------------------------------------------------------------------- contract shape


def test_contract_surface_exists():
    """The names the plan's Contract section promises, so the coder and these tests agree."""
    matching = _matching_module()
    from app.services import customer_code_map

    assert matching.MATCH_BATCH_SIZE == 40
    assert callable(matching.ask_line_matcher)
    assert callable(matching.suggest_matches)
    assert callable(customer_code_map.remembered_codes)
    assert callable(customer_code_map.remember_code)
    assert callable(customer_code_map.customer_id_for_po)
    assert callable(getattr(ProjectPOExtractionService, "accept_suggestion", None))
    assert callable(getattr(ProjectPOExtractionService, "accept_all_suggestions", None))


def test_the_line_matcher_prompt_is_registered():
    """AC-M3: the model call goes through the prompt registry under `po_line_matcher`."""
    from app.services.ai_prompt_registry import PROMPT_KEYS

    assert "po_line_matcher" in PROMPT_KEYS


# ------------------------------------------------------------------ M: matching


def test_m1_exact_code_resolves_case_insensitively_with_no_model_call_and_no_pill(
    seeded, matcher
):
    db, project, owner = seeded
    ids = _products(db, project.company_id, "SRTWC8518-SH")
    po, _customer_row = _customer_po(db, project, owner, "ZZT-M1")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(version, [_page(1, lines=[_row(3, code="srtwc8518-sh")])])

    line = _lines(service, version)[3]
    assert line.resolved_product_id == ids["SRTWC8518-SH"]
    assert line.resolution_source == "code"
    assert 3 not in matcher.sent_line_nos(), "an exact code must not reach the model"
    serialized = _serialized(service, version)[3]
    assert serialized["match_confidence"] is None
    assert serialized["match_options"] == []
    assert serialized["qty_suggested"] is False


def test_m1_exact_code_is_scoped_to_the_po_company(seeded, matcher):
    """The same code stocked only by ANOTHER company is not an exact hit for this PO."""
    from app.models.company import Company

    db, project, owner = seeded
    other_company = _uid()
    db.add(Company(id=other_company, name=f"{MARKER} Other", code=_uid()[:8]))
    db.flush()
    other = _catalogue_product(db, other_company, "ZZT-ONLY-ELSEWHERE")
    po, _c = _customer_po(db, project, owner, "ZZT-M1B")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(version, [_page(1, lines=[_row(1, code="ZZT-ONLY-ELSEWHERE")])])

    line = _lines(service, version)[1]
    assert line.resolution_source != "code"
    assert line.resolved_product_id != other.id


def test_m2_a_remembered_customer_code_resolves_via_the_map_and_beats_the_model(
    seeded, matcher
):
    db, project, owner = seeded
    ids = _products(db, project.company_id, "CKS903", "SRT73-CR")
    po, customer = _customer_po(db, project, owner, "ZZT-M2")
    _map_row(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        code="BBT-CKS-903",
        product_id=ids["CKS903"],
    )
    # Were the line ever asked about, the model would say something else.
    matcher.answers[1] = {"product_code": "SRT73-CR", "confidence": "high", "options": []}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version, [_page(1, lines=[_row(1, code="bbt-cks-903", description="CABANA BASIN")])]
    )

    line = _lines(service, version)[1]
    assert line.resolved_product_id == ids["CKS903"]
    assert line.resolution_source == "map"
    assert 1 not in matcher.sent_line_nos(), "a map hit must not reach the model"
    assert _serialized(service, version)[1]["match_confidence"] is None


def test_m2_another_customers_map_does_not_apply(seeded, matcher):
    db, project, owner = seeded
    ids = _products(db, project.company_id, "CKS903")
    po, _customer_row = _customer_po(db, project, owner, "ZZT-M2B")
    stranger = _customer(db, project.company_id)
    _map_row(
        db,
        company_id=project.company_id,
        customer_id=stranger.id,
        code="BBT-CKS-903",
        product_id=ids["CKS903"],
    )
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(version, [_page(1, lines=[_row(1, code="BBT-CKS-903")])])

    line = _lines(service, version)[1]
    assert line.resolution_source != "map"
    assert line.resolved_product_id is None


def test_m3_candidates_come_from_the_quotation_the_customer_map_and_the_catalogue(
    seeded, matcher
):
    """The input item carries the line and its candidate list with each source named."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "CKS903", "CB310-CR-L", "CB310-CR-PJ")
    po, customer = _customer_po(
        db, project, owner, "ZZT-M3", quotation_version_id=quoted_version.id
    )
    _map_row(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        code="BBT-OTHER-1",
        product_id=ids["CKS903"],
    )
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [_page(1, lines=[_row(5, code="CB310-CR", description="CABANA CB310-CR")])],
    )

    assert matcher.calls, "an unresolved line must be put to the matcher"
    assert all(call["company_id"] == po.company_id for call in matcher.calls)
    item = matcher.item_for(5)
    assert item["stock_code"] == "CB310-CR"
    assert item["description"] == "CABANA CB310-CR"
    for candidate in item["candidates"]:
        assert set(candidate) >= {"code", "name", "source"}
        assert candidate["source"] in {"quotation", "customer_map", "catalogue"}
    pairs = {(c["code"], c["source"]) for c in item["candidates"]}
    assert ("SRTWC8518-SH", "quotation") in pairs, pairs
    assert ("CKS903", "customer_map") in pairs, pairs
    assert ("CB310-CR-L", "catalogue") in pairs, pairs
    assert ("CB310-CR-PJ", "catalogue") in pairs, pairs


def test_m3_a_pick_is_suggested_and_keeps_its_confidence_and_options(seeded, matcher):
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00"), ("SRT73-CR", "50.00")]
    )
    ids = _products(db, project.company_id, "SRTWC8518-SH", "SRT73-CR")
    po, _c = _customer_po(db, project, owner, "ZZT-M3B", quotation_version_id=quoted_version.id)
    matcher.answers[2] = {
        "product_code": "SRTWC8518-SH",
        "confidence": "medium",
        "options": ["SRTWC8518-SH", "SRT73-CR"],
    }
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version, [_page(1, lines=[_row(2, code="BBT-WC-1", description="WALL HUNG WC")])]
    )

    line = _lines(service, version)[2]
    assert line.resolved_product_id == ids["SRTWC8518-SH"]
    assert line.resolution_source == "suggested"
    meta = _match(version, 2)
    assert meta.get("confidence") == "medium"
    assert set(meta.get("options") or []) == {ids["SRTWC8518-SH"], ids["SRT73-CR"]}
    serialized = _serialized(service, version)[2]
    assert serialized["match_confidence"] == "medium"
    assert {o["product_code"] for o in serialized["match_options"]} == {"SRTWC8518-SH", "SRT73-CR"}
    for option in serialized["match_options"]:
        assert set(option) >= {"product_id", "product_code", "product_name"}


def test_m3_a_pick_not_among_the_candidates_is_dropped(seeded, matcher):
    """No invented products: a code the line was never offered is discarded, pick and options."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    po, _c = _customer_po(db, project, owner, "ZZT-M3C", quotation_version_id=quoted_version.id)
    matcher.answers[1] = {
        "product_code": "ZZT-INVENTED-9",
        "confidence": "high",
        "options": ["ZZT-INVENTED-9", "ZZT-INVENTED-8"],
    }
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version, [_page(1, lines=[_row(1, code="BBT-Q-1", description="SOMETHING")])]
    )

    assert 1 in matcher.sent_line_nos()
    line = _lines(service, version)[1]
    assert line.resolved_product_id is None
    assert line.resolution_source is None
    assert not (_match(version, 1).get("options") or [])
    assert _serialized(service, version)[1]["match_options"] == []


def test_m3_unresolved_lines_go_in_batches_of_at_most_forty(seeded, matcher):
    """41 unresolved lines are two model calls: 40 and 1."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    po, _c = _customer_po(db, project, owner, "ZZT-M3D", quotation_version_id=quoted_version.id)
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(n, code=f"BBT-UNK-{n}", description=f"ZZT ITEM {n}")
                    for n in range(1, 42)
                ],
            )
        ],
    )

    assert len(matcher.calls) == 2
    assert sorted(len(call["lines"]) for call in matcher.calls) == [1, 40]
    assert sorted(matcher.sent_line_nos()) == list(range(1, 42))


def test_m3_matching_runs_once_after_every_page(seeded, matcher):
    """Lines from two pages go out together, not one call per page."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    po, _c = _customer_po(db, project, owner, "ZZT-M3E", quotation_version_id=quoted_version.id)
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [
            _page(1, lines=[_row(1, code="BBT-A", description="ZZT A")]),
            _page(2, lines=[_row(2, code="BBT-B", description="ZZT B")]),
        ],
    )

    assert len(matcher.calls) == 1
    assert sorted(matcher.sent_line_nos()) == [1, 2]


def test_m4_a_size_in_the_description_never_resolves_to_that_product(seeded, matcher):
    """"40MM" in the description is a size, not product `40MM`."""
    db, project, owner = seeded
    _products(db, project.company_id, "40MM")
    po, _c = _customer_po(db, project, owner, "ZZT-M4")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [_page(1, lines=[_row(1, code="BBT-PIPE-7", description="PVC ELBOW 40MM GREY")])],
    )

    line = _lines(service, version)[1]
    assert line.resolved_product_id is None
    assert line.resolution_source is None


def test_m4_the_loose_string_tiers_are_gone(seeded, matcher):
    """Punctuation-dropped, reordered and truncated codes no longer resolve by string rules."""
    db, project, owner = seeded
    _products(db, project.company_id, "SRTFH15-CR", "B2155-NL-BLUE", "SRTWC8613-RL")
    po, _c = _customer_po(db, project, owner, "ZZT-M4B")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(1, code="IFH15CR", description="SORENTO SRTFH15CR FLEXIBLE HOSE"),
                    _row(2, code="CB2155-BLUE", description="SORENTO B2155-BLUE-NL ANGLE VALVE"),
                    _row(3, code="SRTWC86", description="SORENTO SRTW8613-RL ONE PIECE WC"),
                ],
            )
        ],
    )

    for line in _lines(service, version).values():
        assert line.resolution_source not in {
            "description",
            "code_normalised",
            "code_reordered",
            "code_truncated",
        }
        assert line.resolved_product_id is None
    assert not hasattr(ProjectPOExtractionService, "_resolve_product_loosely")


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("model timed out"), ValueError("bad JSON"), RuntimeError("model unavailable")],
    ids=["timeout", "bad-json", "unavailable"],
)
def test_m5_a_failing_batch_leaves_its_lines_unmatched_and_the_read_finishes(
    seeded, matcher, failure
):
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "SRTWC8518-SH")
    po, _c = _customer_po(db, project, owner, "ZZT-M5", quotation_version_id=quoted_version.id)
    matcher.fail = lambda batch: failure if any(int(i["line_no"]) == 1 for i in batch) else None
    for n in range(1, 42):
        matcher.answers[n] = {"product_code": "SRTWC8518-SH", "confidence": "high", "options": []}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    summary = service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(n, code=f"BBT-UNK-{n}", description=f"ZZT ITEM {n}")
                    for n in range(1, 42)
                ],
            )
        ],
    )

    assert summary["status"] == STATE_DONE
    assert version.extraction_state == STATE_DONE
    assert len(matcher.calls) == 2
    failed_batch = {int(i["line_no"]) for i in matcher.calls[0]["lines"]}
    assert 1 in failed_batch
    lines = _lines(service, version)
    for n, line in lines.items():
        if n in failed_batch:
            assert line.resolved_product_id is None, f"line {n} of the failed batch matched"
            assert line.resolution_source is None
        else:
            assert line.resolved_product_id == ids["SRTWC8518-SH"]
            assert line.resolution_source == "suggested"


def test_m6_the_catalogue_shapes_come_back_suggested_or_with_options(seeded, matcher):
    """The UAC's worked examples, catalogue only, model stubbed."""
    db, project, owner = seeded
    ids = _products(
        db,
        project.company_id,
        "SRTWC8518-SH",
        "CKS903",
        "TPE-9201-300",
        "SRT73-CR",
        "CB310-CR-L",
        "CB310-CR-PJ",
    )
    po, _c = _customer_po(db, project, owner, "ZZT-M6")
    examples = {
        1: ("SORENTO BBTSRTWC8518 -SH", "SRTWC8518-SH"),
        2: ("CABANA BBTCKS903", "CKS903"),
        3: ("BBTTPE-9201-300", "TPE-9201-300"),
        4: ("SORENTO BBTSRT73-CR **", "SRT73-CR"),
    }
    for n, (_text, code) in examples.items():
        matcher.answers[n] = {"product_code": code, "confidence": "high", "options": []}
    matcher.answers[5] = {
        "product_code": None,
        "confidence": "low",
        "options": ["CB310-CR-L", "CB310-CR-PJ"],
    }
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[_row(n, description=text) for n, (text, _code) in examples.items()]
                + [_row(5, description="CABANA CB310-CR")],
            )
        ],
    )

    lines = _lines(service, version)
    for n, (_text, code) in examples.items():
        assert lines[n].resolved_product_id == ids[code], f"line {n} should suggest {code}"
        assert lines[n].resolution_source == "suggested"
    assert lines[5].resolved_product_id is None
    assert lines[5].resolution_source is None
    assert set(_match(version, 5).get("options") or []) == {
        ids["CB310-CR-L"],
        ids["CB310-CR-PJ"],
    }
    assert {o["product_code"] for o in _serialized(service, version)[5]["match_options"]} == {
        "CB310-CR-L",
        "CB310-CR-PJ",
    }


# --------------------------------------------------------- A: accepting, remembering


def _suggested_version(db, project, owner, matcher, *, number: str, customer=None):
    """A read version with line 1 suggested to SRTWC8518-SH, plus the ids and customer."""
    _quote, quoted_version = _quotation(
        db, project, owner, f"Scope {number}", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "SRTWC8518-SH", "CKS903")
    po, customer = _customer_po(
        db, project, owner, number, customer=customer, quotation_version_id=quoted_version.id
    )
    matcher.answers[1] = {"product_code": "SRTWC8518-SH", "confidence": "high", "options": []}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(
        version, [_page(1, lines=[_row(1, code="BBT-WC-77", description="WALL HUNG WC")])]
    )
    line = _lines(service, version)[1]
    assert line.resolution_source == "suggested"
    return service, version, line, ids, customer


def test_a1_accepting_a_suggestion_marks_it_accepted_and_remembers_the_code(seeded, matcher):
    db, project, owner = seeded
    service, version, line, ids, customer = _suggested_version(
        db, project, owner, matcher, number="ZZT-A1"
    )

    service.accept_suggestion(version, line, actor_user_id=owner)

    assert line.resolution_source == "accepted"
    assert line.resolved_product_id == ids["SRTWC8518-SH"]
    rows = _map_rows(db, customer.id, "BBT-WC-77")
    assert len(rows) == 1
    assert rows[0].product_id == ids["SRTWC8518-SH"]
    assert rows[0].confirmed_by == owner
    assert _serialized(service, version)[1]["resolution_source"] == "accepted"


def test_a1_accepting_overwrites_an_existing_map_row(seeded, matcher):
    db, project, owner = seeded
    service, version, line, ids, customer = _suggested_version(
        db, project, owner, matcher, number="ZZT-A1B"
    )
    # Somebody mapped the same code differently after this version was read.
    _map_row(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        code="bbt-wc-77",
        product_id=ids["CKS903"],
    )

    service.accept_suggestion(version, line, actor_user_id=owner)

    rows = _map_rows(db, customer.id, "BBT-WC-77")
    assert len(rows) == 1, "insert or overwrite, never a second row for the same code"
    assert rows[0].product_id == ids["SRTWC8518-SH"]
    assert rows[0].confirmed_by == owner


def test_a2_accept_all_takes_every_suggested_product_and_qty_through_one_function(
    seeded, matcher, monkeypatch
):
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "SRTWC8518-SH", "CKS903")
    po, customer = _customer_po(db, project, owner, "ZZT-A2", quotation_version_id=quoted_version.id)
    matcher.answers[1] = {"product_code": "SRTWC8518-SH", "confidence": "high", "options": []}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    # A suggested product.
                    _row(1, code="BBT-WC-77", description="WALL HUNG WC", qty=2, unit_price=100.0),
                    # An exact code with a suggested qty: 37.50 / 12.50 = 3.
                    _row(2, code="CKS903", qty=None, unit_price=12.5, amount=37.5),
                    # Nothing to accept.
                    _row(3, code="CKS903", qty=1, unit_price=12.5),
                ],
            )
        ],
    )
    assert service.serialize_version(version)["suggestion_count"] == 2

    real = ProjectPOExtractionService.accept_suggestion
    seen: List[int] = []

    def spy(self, version_arg, line_arg, *args, **kwargs):
        seen.append(line_arg.line_no)
        return real(self, version_arg, line_arg, *args, **kwargs)

    monkeypatch.setattr(ProjectPOExtractionService, "accept_suggestion", spy)

    accepted = service.accept_all_suggestions(version, actor_user_id=owner)

    assert accepted == 2
    assert sorted(seen) == [1, 2], "accept all must go through accept_suggestion per line"
    lines = _lines(service, version)
    assert lines[1].resolution_source == "accepted"
    assert lines[2].qty == Decimal("3")
    assert not _match(version, 2).get("qty_suggested")
    assert lines[3].resolution_source == "code"
    assert _map_rows(db, customer.id, "BBT-WC-77")[0].product_id == ids["SRTWC8518-SH"]
    assert service.serialize_version(version)["suggestion_count"] == 0


def test_a3_a_manual_pick_remembers_the_code_and_clearing_keeps_the_map(seeded, matcher):
    db, project, owner = seeded
    ids = _products(db, project.company_id, "CKS903")
    po, customer = _customer_po(db, project, owner, "ZZT-A3")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(
        version, [_page(1, lines=[_row(1, code="BBT-BASIN-4", description="ZZT BASIN")])]
    )
    line = _lines(service, version)[1]

    service.update_line(
        version=version,
        line=line,
        payload={"resolved_product_id": ids["CKS903"]},
        actor_user_id=owner,
    )

    assert line.resolution_source == "manual"
    rows = _map_rows(db, customer.id, "BBT-BASIN-4")
    assert len(rows) == 1
    assert rows[0].product_id == ids["CKS903"]
    assert rows[0].confirmed_by == owner

    service.update_line(
        version=version, line=line, payload={"resolved_product_id": None}, actor_user_id=owner
    )

    assert line.resolved_product_id is None
    assert len(_map_rows(db, customer.id, "BBT-BASIN-4")) == 1, "clearing never deletes the map"


def test_a4_the_shared_helper_writes_and_reads_the_map_case_insensitively(seeded):
    from app.services import customer_code_map

    db, project, owner = seeded
    ids = _products(db, project.company_id, "CKS903", "SRT73-CR")
    customer = _customer(db, project.company_id)

    customer_code_map.remember_code(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        customer_code="bbt-mix-2",
        product_id=ids["CKS903"],
        actor_user_id=owner,
    )
    customer_code_map.remember_code(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        customer_code="BBT-MIX-2",
        product_id=ids["SRT73-CR"],
        actor_user_id=owner,
    )
    db.flush()

    assert customer_code_map.remembered_codes(db, customer.id) == {"BBT-MIX-2": ids["SRT73-CR"]}
    assert len(_map_rows(db, customer.id, "BBT-MIX-2")) == 1
    assert customer_code_map.remembered_codes(db, None) == {}


def test_a4_a_po_pick_is_read_back_by_the_shared_helper_and_the_schedule_matcher(
    seeded, matcher
):
    """The schedule and the PO share one map: what a PO pick wrote, the schedule reads."""
    from app.services import customer_code_map
    from app.services.project_schedule_service import ProjectScheduleService

    db, project, owner = seeded
    ids = _products(db, project.company_id, "CKS903")
    po, customer = _customer_po(db, project, owner, "ZZT-A4")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(version, [_page(1, lines=[_row(1, code="BBT-TAP-12")])])
    line = _lines(service, version)[1]

    service.update_line(
        version=version,
        line=line,
        payload={"resolved_product_id": ids["CKS903"]},
        actor_user_id=owner,
    )
    db.flush()

    assert customer_code_map.remembered_codes(db, customer.id).get("BBT-TAP-12") == ids["CKS903"]
    schedule_service = ProjectScheduleService(db)
    reader = getattr(schedule_service, "_remembered_codes", None)
    if reader is not None:
        assert reader(customer.id).get("BBT-TAP-12") == ids["CKS903"]


def test_a4_no_second_copy_of_the_map_query():
    """Only `customer_code_map` touches `CustomerItemCodeMap` among the matchers."""
    import inspect

    from app.services import (
        customer_code_map,
        project_po_intake_lifecycle,
        project_po_matching,
        project_schedule_service,
    )

    assert "CustomerItemCodeMap" in inspect.getsource(customer_code_map)
    for module in (project_schedule_service, project_po_intake_lifecycle, project_po_matching):
        assert "CustomerItemCodeMap" not in inspect.getsource(module), module.__name__


def test_a4_customer_for_a_po_is_the_issuer_then_the_projects_lead(seeded):
    from app.models.projects import ProjectLead
    from app.services import customer_code_map
    from app.services import project_po_service as po_svc

    db, project, owner = seeded
    po, issuer_customer = _customer_po(db, project, owner, "ZZT-A4C")
    assert customer_code_map.customer_id_for_po(db, po) == issuer_customer.id

    buyer = _customer(db, project.company_id)
    lead = ProjectLead(
        id=_uid(),
        company_id=project.company_id,
        lead_code=f"ZZT-L-{_uid()[:6]}",
        customer_id=buyer.id,
        title=f"{MARKER} lead",
        normalised_title=f"{MARKER} lead",
    )
    db.add(lead)
    db.flush()
    project.lead_id = lead.id
    db.flush()
    bare = po_svc.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={"po_number": "ZZT-A4D", "po_source": "contractor_direct"},
    )
    assert customer_code_map.customer_id_for_po(db, bare) == buyer.id


def test_a5_the_next_po_from_the_same_customer_resolves_through_the_map(seeded, matcher):
    db, project, owner = seeded
    service, version, line, ids, customer = _suggested_version(
        db, project, owner, matcher, number="ZZT-A5"
    )
    service.accept_suggestion(version, line, actor_user_id=owner)
    matcher.calls.clear()
    matcher.answers.clear()

    second_po, _same = _customer_po(db, project, owner, "ZZT-A5-2", customer=customer)
    second = _version(db, second_po)
    service.persist_pages(
        second, [_page(1, lines=[_row(1, code="BBT-WC-77", description="WALL HUNG WC")])]
    )

    again = _lines(service, second)[1]
    assert again.resolved_product_id == ids["SRTWC8518-SH"]
    assert again.resolution_source == "map"
    assert 1 not in matcher.sent_line_nos()


# ------------------------------------------------------------------- Q: quantity


def test_q2_an_empty_qty_is_suggested_when_amount_over_price_is_whole(seeded, matcher):
    db, project, owner = seeded
    _products(db, project.company_id, "CKS903")
    po, _c = _customer_po(db, project, owner, "ZZT-Q2")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(1, code="CKS903", qty=None, unit_price=12.5, amount=37.5),
                    _row(2, code="CKS903", qty=None, unit_price=10.0, amount=25.0),
                    _row(3, code="CKS903", qty=4, unit_price=10.0, amount=40.0),
                ],
            )
        ],
    )

    lines = _lines(service, version)
    assert lines[1].qty == Decimal("3")
    assert _match(version, 1).get("qty_suggested") is True
    assert lines[2].qty is None, "2.5 is not a whole quantity, so nothing is suggested"
    assert not _match(version, 2).get("qty_suggested")
    assert lines[3].qty == Decimal("4")
    assert not _match(version, 3).get("qty_suggested")
    serialized = _serialized(service, version)
    assert serialized[1]["qty_suggested"] is True
    assert serialized[2]["qty_suggested"] is False
    assert serialized[3]["qty_suggested"] is False


def _attention_version(db, project, owner, matcher, number: str):
    """Line 4: suggested product. Line 9: suggested qty. Line 12: qty empty and not derivable.
    Line 15: clean. Line 20: qty empty but cancelled (never blocks)."""
    _quote, quoted_version = _quotation(
        db, project, owner, f"Scope {number}", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "SRTWC8518-SH", "CKS903")
    po, customer = _customer_po(
        db, project, owner, number, quotation_version_id=quoted_version.id
    )
    matcher.answers[4] = {"product_code": "SRTWC8518-SH", "confidence": "high", "options": []}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(4, code="BBT-WC-77", description="WALL HUNG WC", qty=2, unit_price=100.0),
                    _row(9, code="CKS903", qty=None, unit_price=12.5, amount=37.5),
                    _row(12, code="CKS903", qty=None, unit_price=12.5, amount=None),
                    _row(15, code="CKS903", qty=1, unit_price=12.5),
                    _row(20, code="CKS903", qty=None, unit_price=12.5, amount=None),
                ],
            )
        ],
    )
    lines = _lines(service, version)
    service.update_line(version=version, line=lines[20], payload={"is_cancelled": True})
    return service, version, lines, ids, po


def test_q3_confirm_names_every_line_that_still_needs_attention(seeded, matcher):
    db, project, owner = seeded
    service, version, _lines_by_no, _ids, _po = _attention_version(
        db, project, owner, matcher, "ZZT-Q3"
    )

    with pytest.raises(AppException) as caught:
        service.confirm_version(version=version, actor_user_id=owner)

    assert caught.value.status_code == 422
    assert _code(caught.value) == "po_version_lines_need_attention"
    message = _message(caught.value)
    import re

    named = {int(n) for n in re.findall(r"\d+", message)}
    assert {4, 9, 12} <= named, message
    assert 15 not in named and 20 not in named, message
    assert version.confirmed_at is None


def test_q3_typing_the_qty_clears_the_suggested_flag(seeded, matcher):
    db, project, owner = seeded
    service, version, lines, _ids, _po = _attention_version(
        db, project, owner, matcher, "ZZT-Q3B"
    )
    assert _match(version, 9).get("qty_suggested") is True

    service.update_line(
        version=version, line=lines[9], payload={"qty": Decimal("3")}, actor_user_id=owner
    )

    assert not _match(version, 9).get("qty_suggested")
    assert _serialized(service, version)[9]["qty_suggested"] is False


def test_q1_q3_confirm_goes_through_once_resolved_and_never_writes_a_silent_qty_of_one(
    seeded, matcher
):
    db, project, owner = seeded
    service, version, lines, ids, po = _attention_version(
        db, project, owner, matcher, "ZZT-Q1"
    )

    service.accept_all_suggestions(version, actor_user_id=owner)
    # Still blocked: line 12 has no qty and nothing to work it out from.
    with pytest.raises(AppException) as caught:
        service.confirm_version(version=version, actor_user_id=owner)
    assert _code(caught.value) == "po_version_lines_need_attention"
    assert "12" in _message(caught.value)
    assert (
        db.query(ProjectPurchaseOrderLine).filter(ProjectPurchaseOrderLine.po_id == po.id).count()
        == 0
    ), "a refused confirm writes no PO line, so no line can be saved with qty 1"

    service.update_line(
        version=version, line=lines[12], payload={"qty": Decimal("7")}, actor_user_id=owner
    )
    service.confirm_version(version=version, actor_user_id=owner)

    written = {
        row.sort_order: row
        for row in db.query(ProjectPurchaseOrderLine)
        .filter(ProjectPurchaseOrderLine.po_id == po.id)
        .all()
    }
    assert written[4].product_id == ids["SRTWC8518-SH"]
    assert written[9].quantity == Decimal("3")
    assert written[12].quantity == Decimal("7")
    assert 20 not in written


def test_q1_confirm_has_no_qty_of_one_fallback():
    import inspect

    from app.services import project_po_confirm

    source = inspect.getsource(project_po_confirm)
    assert 'or Decimal("1")' not in source


# --------------------------------------------------------------------- T: totals


def test_t1_the_page_schema_and_prompt_ask_for_the_printed_total():
    from app.services.ai_prompt_registry import _po_extractor_fallback
    from app.services.project_po_reading import PO_PAGE_SCHEMA

    props = PO_PAGE_SCHEMA["properties"]
    assert "printed_total" in props
    assert set(props["printed_total"]["type"]) == {"number", "null"}
    assert "printed_total" in PO_PAGE_SCHEMA["required"]
    assert "printed_total" in _po_extractor_fallback()


def test_t1_the_last_printed_total_read_wins_and_is_the_document_total(seeded, matcher):
    db, project, owner = seeded
    po, _c = _customer_po(db, project, owner, "ZZT-T1")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [
            _page(1, lines=[_row(1, code="ZZT-A", qty=1, unit_price=100.0)], printed_total=100.0),
            _page(2, lines=[_row(2, code="ZZT-B", qty=1, unit_price=140.0)], printed_total=250.0),
            _page(3, lines=[], printed_total=None),
        ],
    )

    assert Decimal(str(version.extracted_json["printed_total"])) == Decimal("250")
    totals = service.recompute_totals(version)
    assert totals["extracted_total"] == Decimal("250")
    assert totals["lines_total"] == Decimal("240.00")
    assert service.serialize_version(version)["totals"]["printed_total_read"] is True


def test_t2_without_a_printed_total_the_api_says_the_total_is_the_sum_read(seeded, matcher):
    db, project, owner = seeded
    po, _c = _customer_po(db, project, owner, "ZZT-T2")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [_page(1, lines=[_row(1, code="ZZT-A", qty=2, unit_price=50.0)], printed_total=None)],
    )

    totals = service.serialize_version(version)["totals"]
    assert totals["printed_total_read"] is False
    assert Decimal(str(totals["extracted_total"])) == Decimal("100")


def test_serialized_version_carries_the_suggestion_fields(seeded, matcher):
    db, project, owner = seeded
    service, version, _line, _ids, _customer_row = _suggested_version(
        db, project, owner, matcher, number="ZZT-SER"
    )

    body = service.serialize_version(version)

    assert body["suggestion_count"] == 1
    assert "printed_total_read" in body["totals"]
    line = body["lines"][0]
    assert line["resolution_source"] == "suggested"
    assert line["match_confidence"] == "high"
    assert isinstance(line["match_options"], list)
    assert line["qty_suggested"] is False


# --------------------------------------------------------------------- the routes


@pytest.fixture()
def api(monkeypatch, matcher):
    from app.models.base import company_scope

    from .test_project_po_document_save import _client, _restore

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        service, version, line, ids, customer = _suggested_version(
            db, project, owner, matcher, number="ZZT-ROUTE"
        )
        db.commit()
        client, originals = _client(db, owner)
        try:
            with company_scope(db, frozenset({company_id})):
                yield {
                    "client": client,
                    "db": db,
                    "owner": owner,
                    "version": version,
                    "line": line,
                    "ids": ids,
                    "customer": customer,
                }
        finally:
            _restore(originals)


def _deny_edit():
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug != "projects.projects.edit"
    )


def test_route_accept_one_suggestion(api):
    client, version, line = api["client"], api["version"], api["line"]

    response = client.post(
        f"{BASE}/purchase-order-versions/{version.id}/lines/{line.id}/accept-suggestion"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    row = next(item for item in body["lines"] if item["id"] == str(line.id))
    assert row["resolution_source"] == "accepted"
    assert row["qty_suggested"] is False
    assert "match_confidence" in row and "match_options" in row
    assert body["suggestion_count"] == 0
    assert "printed_total_read" in body["totals"]
    assert len(_map_rows(api["db"], api["customer"].id, "BBT-WC-77")) == 1


def test_route_accept_all_suggestions(api):
    client, version = api["client"], api["version"]

    response = client.post(f"{BASE}/purchase-order-versions/{version.id}/accept-suggestions")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["suggestion_count"] == 0
    assert {item["resolution_source"] for item in body["lines"]} == {"accepted"}


def test_route_accept_one_needs_edit_rights(api):
    _deny_edit()
    client, version, line = api["client"], api["version"], api["line"]

    response = client.post(
        f"{BASE}/purchase-order-versions/{version.id}/lines/{line.id}/accept-suggestion"
    )

    assert response.status_code == 403, response.text


def test_route_accept_all_needs_edit_rights(api):
    _deny_edit()
    client, version = api["client"], api["version"]

    response = client.post(f"{BASE}/purchase-order-versions/{version.id}/accept-suggestions")

    assert response.status_code == 403, response.text


def test_route_accept_one_refuses_a_line_id_that_is_not_an_id(api):
    client, version = api["client"], api["version"]

    response = client.post(
        f"{BASE}/purchase-order-versions/{version.id}/lines/not-a-uuid/accept-suggestion"
    )

    assert response.status_code in (400, 404, 422), response.text
    assert response.status_code != 405


# ======================================================== fix round 1 (review findings)


class _FakeProvider:
    """Stands in for the LLM provider ``ask_line_matcher`` builds; records every message."""

    name = "stub"

    def __init__(self, answer: Callable[[dict], dict]) -> None:
        self.answer = answer
        self.messages: List[List[dict]] = []
        self.kwargs: List[dict] = []

    def chat(self, messages, **kwargs):
        import json

        from app.services.llm_provider import ChatResult

        self.messages.append(list(messages))
        self.kwargs.append(kwargs)
        user = next(m for m in messages if m["role"] == "user")["content"]
        return ChatResult(
            content=json.dumps(self.answer(json.loads(user))),
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )

    def system_text(self) -> str:
        return "\n".join(m["content"] for m in self.messages[0] if m["role"] == "system")

    def payload(self) -> dict:
        import json

        return json.loads(next(m for m in self.messages[0] if m["role"] == "user")["content"])


@pytest.fixture()
def provider(monkeypatch):
    """The REAL ``ask_line_matcher`` over a fake provider: payload and prompt are real."""
    from app.services import ai_prompt_registry, llm_provider, project_po_matching

    assert _REAL_ASK_LINE_MATCHER is not None
    monkeypatch.setattr(project_po_matching, "ask_line_matcher", _REAL_ASK_LINE_MATCHER)
    fake = _FakeProvider(lambda payload: {"matches": []})
    monkeypatch.setattr(llm_provider, "get_provider", lambda *a, **k: fake)
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda *a, **k: "ZZT-key")
    monkeypatch.setattr(
        ai_prompt_registry, "agent_model", lambda *a, **k: ("openai", "zzt-model"), raising=False
    )
    return fake


def _top_level_keys_holding(payload: dict, text: str) -> List[str]:
    import json

    return [key for key, value in payload.items() if text in json.dumps(value)]


def test_fix1_a_one_line_batch_sends_every_candidate_under_a_key_the_prompt_names(
    seeded, provider
):
    """(1a) quotation + customer_map + catalogue candidates all reach the model, and each one
    sits under a top-level payload key that the system prompt actually describes."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "CKS903", "CB310-CR-L", "CB310-CR-PJ")
    po, customer = _customer_po(
        db, project, owner, "ZZT-F1A", quotation_version_id=quoted_version.id
    )
    _map_row(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        code="BBT-OTHER-1",
        product_id=ids["CKS903"],
    )
    version = _version(db, po)
    ProjectPOExtractionService(db).persist_pages(
        version, [_page(1, lines=[_row(5, code="CB310-CR", description="CABANA CB310-CR")])]
    )

    assert len(provider.messages) == 1, "one unresolved line is one model call"
    system = provider.system_text()
    payload = provider.payload()
    for code in ("SRTWC8518-SH", "CKS903", "CB310-CR-L", "CB310-CR-PJ"):
        keys = _top_level_keys_holding(payload, f'"{code}"')
        assert keys, f"{code} never reached the model: {payload!r}"
        assert any(key in system for key in keys), (
            f"{code} is sent under {keys}, which the system prompt never mentions"
        )


def test_fix1_b_the_system_prompt_describes_every_top_level_payload_key(seeded, provider):
    """(1b) whatever the user payload's top-level keys are, the prompt names each one."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    po, _c = _customer_po(db, project, owner, "ZZT-F1B", quotation_version_id=quoted_version.id)
    version = _version(db, po)
    ProjectPOExtractionService(db).persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(1, code="BBT-A-1", description="ZZT ITEM A"),
                    _row(2, code="CB310-CR", description="CABANA CB310-CR"),
                ],
            )
        ],
    )

    assert provider.messages, "the unresolved lines must reach the model"
    system = provider.system_text()
    missing = [key for key in provider.payload() if key not in system]
    assert not missing, f"payload keys the prompt never describes: {missing}"


def test_fix1_c_a_pick_of_a_shared_quotation_product_is_kept(seeded, provider):
    """(1c) the quotation product is offered to every line; picking it is not dropped."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "SRTWC8518-SH")
    po, _c = _customer_po(db, project, owner, "ZZT-F1C", quotation_version_id=quoted_version.id)
    provider.answer = lambda payload: {
        "matches": [
            {"line_no": 1, "product_code": "SRTWC8518-SH", "confidence": "high", "options": []},
            {"line_no": 2, "product_code": "SRTWC8518-SH", "confidence": "medium", "options": []},
        ]
    }
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(1, code="BBT-WC-1", description="WALL HUNG WC"),
                    _row(2, code="BBT-WC-2", description="WALL HUNG WC RIGHT"),
                ],
            )
        ],
    )

    lines = _lines(service, version)
    for n in (1, 2):
        assert lines[n].resolved_product_id == ids["SRTWC8518-SH"], f"line {n} pick dropped"
        assert lines[n].resolution_source == "suggested"


def test_fix2_a_description_only_line_is_remembered_by_its_description(seeded, matcher):
    """(2) no stock code: accepting keys the map on the description, and the next PO from
    the same customer with the same description resolves through the map."""
    db, project, owner = seeded
    _quote, quoted_version = _quotation(
        db, project, owner, "House Units", [("SRTWC8518-SH", "100.00")]
    )
    ids = _products(db, project.company_id, "SRTWC8518-SH")
    po, customer = _customer_po(db, project, owner, "ZZT-F2", quotation_version_id=quoted_version.id)
    matcher.answers[1] = {"product_code": "SRTWC8518-SH", "confidence": "high", "options": []}
    description = "ZZT WALL HUNG WC SET 77"
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(version, [_page(1, lines=[_row(1, description=description)])])
    line = _lines(service, version)[1]
    assert line.resolution_source == "suggested"

    service.accept_suggestion(version, line, actor_user_id=owner)

    rows = _map_rows(db, customer.id, description)
    assert len(rows) == 1, "a description-only line must be remembered by its description"
    assert rows[0].product_id == ids["SRTWC8518-SH"]

    matcher.calls.clear()
    matcher.answers.clear()
    second_po, _same = _customer_po(db, project, owner, "ZZT-F2-2", customer=customer)
    second = _version(db, second_po)
    service.persist_pages(second, [_page(1, lines=[_row(1, description=description)])])

    again = _lines(service, second)[1]
    assert again.resolved_product_id == ids["SRTWC8518-SH"]
    assert again.resolution_source == "map"
    assert 1 not in matcher.sent_line_nos()


def _other_company(db, code_hint: str = "MCH") -> str:
    from sqlalchemy import text

    from app.models.company import Company

    existing = db.execute(text("select id from companies where code = :c"), {"c": code_hint}).scalar()
    if existing:
        return str(existing)
    company_id = _uid()
    db.add(Company(id=company_id, name=f"{MARKER} {code_hint}", code=f"Z{_uid()[:7]}"))
    db.flush()
    return company_id


def _named_product(db, company_id: str, code: str, name: str):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    uom = UnitOfMeasure(
        id=_uid(), company_id=company_id, uom_code=f"ZZT{uuid.uuid4().hex}", uom_name="Piece"
    )
    category = ProductCategory(
        id=_uid(), company_id=company_id, category_code=f"ZZT-{_uid()[:8]}", category_name=name
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=company_id,
        product_code=code,
        product_name=name,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def test_fix3_a_manual_pick_of_another_companys_product_is_refused(seeded, matcher):
    """(3) the line's company decides which products it may name; a refused pick maps nothing."""
    db, project, owner = seeded
    other = _named_product(db, _other_company(db), "ZZT-OTHERCO-1", f"{MARKER} other co item")
    po, customer = _customer_po(db, project, owner, "ZZT-F3")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(version, [_page(1, lines=[_row(1, code="BBT-X-31")])])
    line = _lines(service, version)[1]

    with pytest.raises(AppException) as caught:
        service.update_line(
            version=version,
            line=line,
            payload={"resolved_product_id": other.id},
            actor_user_id=owner,
        )

    assert caught.value.status_code in (404, 422)
    assert line.resolved_product_id != other.id
    assert _map_rows(db, customer.id, "BBT-X-31") == []


def test_fix3_the_map_never_resolves_to_another_companys_product(seeded, matcher):
    db, project, owner = seeded
    other = _named_product(db, _other_company(db), "ZZT-OTHERCO-2", f"{MARKER} other co item")
    po, customer = _customer_po(db, project, owner, "ZZT-F3B")
    _map_row(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        code="BBT-X-32",
        product_id=other.id,
    )
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(version, [_page(1, lines=[_row(1, code="BBT-X-32")])])

    line = _lines(service, version)[1]
    assert line.resolved_product_id != other.id
    assert line.resolution_source != "map"


def test_fix4_the_catalogue_shortlist_never_offers_the_same_code_from_another_company(
    seeded, matcher
):
    """(4) the same code stocked by MCH and SRT: an SRT PO is only ever offered SRT's row."""
    db, project, owner = seeded
    ours = _named_product(db, project.company_id, "ZZT-SAME-5", f"{MARKER} SRT same five")
    theirs = _named_product(db, _other_company(db), "ZZT-SAME-5", f"{MARKER} MCH same five")
    po, _c = _customer_po(db, project, owner, "ZZT-F4")
    matcher.answers[1] = {"product_code": "ZZT-SAME-5", "confidence": "high", "options": []}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version, [_page(1, lines=[_row(1, code="ZZTSAME5", description="ZZT SAME FIVE")])]
    )

    names = {c.get("name") for c in matcher.item_for(1)["candidates"]}
    assert theirs.product_name not in names, names
    assert ours.product_name in names, names
    line = _lines(service, version)[1]
    assert line.resolved_product_id == ours.id
    assert line.resolved_product_id != theirs.id


def test_fix5_a_catalogue_product_offered_only_to_another_line_is_dropped(seeded, matcher):
    """(5) CKS903 is real and offered to line 1 (BBTCKS903), never to line 2. Line 2's pick
    of it, and the option, are dropped."""
    db, project, owner = seeded
    ids = _products(db, project.company_id, "CKS903")
    po, _c = _customer_po(db, project, owner, "ZZT-F5")
    for n in (1, 2):
        matcher.answers[n] = {"product_code": "CKS903", "confidence": "high", "options": ["CKS903"]}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(1, code="BBTCKS903", description="CABANA BBTCKS903"),
                    _row(2, code="BBT-Q-2", description="ZZT PLAIN THING"),
                ],
            )
        ],
    )

    offered_1 = {c["code"] for c in matcher.item_for(1)["candidates"]}
    offered_2 = {c["code"] for c in matcher.item_for(2)["candidates"]}
    assert "CKS903" in offered_1 and "CKS903" not in offered_2, (offered_1, offered_2)
    lines = _lines(service, version)
    assert lines[1].resolved_product_id == ids["CKS903"]
    assert lines[2].resolved_product_id is None
    assert lines[2].resolution_source is None
    assert not (_match(version, 2).get("options") or [])


@pytest.mark.parametrize(
    "unit_price, amount",
    [(-10.0, -30.0), (10.0, -30.0), (-10.0, 30.0), (0.0, 0.0), (10.0, 0.0), (0.0, 30.0)],
    ids=["both-negative", "negative-amount", "negative-price", "both-zero", "zero-amount", "zero-price"],
)
def test_fix6_a_negative_or_zero_amount_or_price_never_suggests_a_qty(
    seeded, matcher, unit_price, amount
):
    db, project, owner = seeded
    _products(db, project.company_id, "CKS903")
    po, _c = _customer_po(db, project, owner, "ZZT-F6")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    service.persist_pages(
        version,
        [_page(1, lines=[_row(1, code="CKS903", qty=None, unit_price=unit_price, amount=amount)])],
    )

    assert _lines(service, version)[1].qty is None
    assert not _match(version, 1).get("qty_suggested")


def test_fix6_confirm_treats_a_zero_qty_like_an_empty_one(seeded, matcher):
    db, project, owner = seeded
    _products(db, project.company_id, "CKS903")
    po, _c = _customer_po(db, project, owner, "ZZT-F6B")
    version = _version(db, po)
    service = ProjectPOExtractionService(db)
    service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(1, code="CKS903", qty=2, unit_price=10.0),
                    _row(6, code="CKS903", qty=0, unit_price=10.0, amount=0.0),
                ],
            )
        ],
    )

    with pytest.raises(AppException) as caught:
        service.confirm_version(version=version, actor_user_id=owner)

    import re

    assert caught.value.status_code == 422
    assert _code(caught.value) == "po_version_lines_need_attention"
    assert 6 in {int(n) for n in re.findall(r"\d+", _message(caught.value))}
    assert version.confirmed_at is None


def test_fix7_a_failing_quotation_lookup_never_fails_the_read(seeded, matcher, monkeypatch):
    """(7) the quotation-version lookup raising leaves the read done, with its lines, and the
    map and catalogue still suggest."""
    db, project, owner = seeded
    ids = _products(db, project.company_id, "CKS903", "CB310-CR-L", "SRT73-CR")
    po, customer = _customer_po(db, project, owner, "ZZT-F7")
    _map_row(
        db,
        company_id=project.company_id,
        customer_id=customer.id,
        code="BBT-TAP-7",
        product_id=ids["CKS903"],
    )

    def boom(self, *args, **kwargs):
        raise RuntimeError("ZZT quotation lookup failed")

    monkeypatch.setattr(ProjectPOExtractionService, "_quotation_version_for", boom)
    matcher.answers[2] = {"product_code": "SRT73-CR", "confidence": "high", "options": []}
    version = _version(db, po)
    service = ProjectPOExtractionService(db)

    summary = service.persist_pages(
        version,
        [
            _page(
                1,
                lines=[
                    _row(1, code="BBT-TAP-7", description="ZZT TAP"),
                    _row(2, code="BBTSRT73-CR", description="SORENTO BBTSRT73-CR"),
                ],
            )
        ],
    )

    assert summary["status"] == STATE_DONE
    assert version.extraction_state == STATE_DONE
    lines = _lines(service, version)
    assert set(lines) == {1, 2}
    assert lines[1].resolution_source == "map"
    assert lines[1].resolved_product_id == ids["CKS903"]
    assert lines[2].resolution_source == "suggested"
    assert lines[2].resolved_product_id == ids["SRT73-CR"]


def test_fix8_the_schema_tells_the_model_what_printed_total_is():
    """(8) the instruction travels with the schema, so a published `po_extractor` prompt
    version that predates the field still gets it."""
    from app.services.project_po_reading import PO_PAGE_SCHEMA

    description = (PO_PAGE_SCHEMA["properties"]["printed_total"].get("description") or "").lower()
    assert description.strip(), "printed_total carries no description for the model"
    assert "total" in description
    assert "printed" in description or "grand" in description

