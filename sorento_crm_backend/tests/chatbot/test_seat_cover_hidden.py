"""SEAT-COVER-HIDDEN: a seat cover fits ask never becomes a file ask (owner, 23 Oct).

Live: "seat cover for SRTWC6031-SH-UF". The WC's only seat cover link points at a cover in a
hidden category (`chat_searchable_products()`), and the parser also tagged the relation's own
word ("seat cover") as an attachment type. `as_linked_products` read the anchor as typed and
kept that entity, so the reply was "Which kind of file do you need?" / "no Installation Guide
matched". Plan `documentation/plans/chatbot/PLAN-seat-cover-hidden-23oct.md`.

* A said `fits` drops the entity whose raw is the fits value as a file type, and an empty
  `file_word` clears the file ask, whether or not a code was replaced.
* A visible WC whose seat cover links are all hidden answers with the existing no-link line
  (`FITS_NONE_LINE`), the hidden cover never named; a WC on no link already does.

Harness from `test_seat_as_product.py`: the parse is mocked, the resolver and answer path are
real. Fake ZZT codes only.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_outstanding_lane import _seed_contact
from tests.chatbot.test_seat_as_product import (
    COVERS_TWO,
    FITS,
    WC_TWO,
    _codes,
    _line_many,
    _product,
    _scoped,
    _turn,
    _verdict,
    _with_line,
)
from tests.chatbot.test_seat_as_product import _seed as _seed_visible

WC_HID, COVER_HID = "ZZTWC6031-SH-UF", "ZZTSCBD289-UF"  # the only cover sits in a hidden category
WC_NOLINK = "ZZTWC6099"
FAMILY, VARIANTS = "ZZTWC8840", ["ZZTWC8840-LID", "ZZTWC8840-SC"]  # no exact code, on no link

#: The parser's misread: the relation's word tagged as a file type (prod v63, 23 Oct).
FILE_TYPES = ("installation guide", "certificate", "photo")


def _as_type(canonical: str) -> dict[str, Any]:
    return {"raw": "seat cover", "hint": "attachment_type", "canonical_code": canonical,
            "current_message": True, "confident": True}


def _seed(session_factory) -> None:
    from app.models.product import ProductCategory
    from app.models.product_compatibility import ProductCompatibility
    from tests._mc_lookup_seed import product as seed_product

    _seed_visible(session_factory)
    db = session_factory()
    rows = {c: seed_product(db, company_id=DEFAULT_COMPANY_ID, code=c) for c in (WC_HID, COVER_HID, WC_NOLINK, *VARIANTS)}
    db.flush()
    db.query(ProductCategory).filter(ProductCategory.id == rows[COVER_HID].category_id).update({"is_searchable": False})
    db.add(ProductCompatibility(
        company_id=DEFAULT_COMPANY_ID, seat_cover_product_id=rows[COVER_HID].id,
        wc_product_id=rows[WC_HID].id, source="manual", kind="seat_cover",
    ))
    db.commit()


def _file_verdict(code: str, canonical: str) -> dict[str, Any]:
    verdict = _verdict(code, domain_hint="product_attachment", intent_hint="check_product_attachment")
    verdict["entities"].append(_as_type(canonical))
    return verdict


def _attachments(verdict: dict[str, Any]) -> list[Any]:
    return [e for e in verdict.get("entities") or [] if e.get("hint") == "attachment_type"]


# --------------------------------------------------------------------------- resolution (unit)


@pytest.mark.parametrize("canonical", FILE_TYPES)
def test_a_wc_whose_only_cover_is_hidden_gets_the_no_link_line(session_factory, canonical) -> None:
    from app.services.chatbot.lanes.business import find as find_lane

    _seed(session_factory)
    _out, lines = find_lane.as_linked_products(
        _scoped(session_factory), _file_verdict(WC_HID, canonical), message=f"seat cover for {WC_HID}",
    )
    assert lines == [f"No seat cover is on record for {WC_HID}."], lines


@pytest.mark.parametrize("canonical", FILE_TYPES)
def test_a_no_link_wc_gets_the_no_link_line(session_factory, canonical) -> None:
    from app.services.chatbot.lanes.business import find as find_lane

    _seed(session_factory)
    _out, lines = find_lane.as_linked_products(
        _scoped(session_factory), _file_verdict(WC_NOLINK, canonical), message=f"seat cover for {WC_NOLINK}",
    )
    assert lines == [f"No seat cover is on record for {WC_NOLINK}."], lines


@pytest.mark.parametrize("canonical", FILE_TYPES)
def test_a_family_code_with_the_relation_word_as_a_file_type_runs_on_with_no_file_ask(session_factory, canonical) -> None:
    """Q3 (a): a code that is no product's exact code runs on as typed, to the resolver's picker;
    the relation's word never rides along as a file type, and the file domain it implied goes."""
    from app.services.chatbot.lanes.business import find as find_lane

    _seed(session_factory)
    out, lines = find_lane.as_linked_products(
        _scoped(session_factory), _file_verdict(FAMILY, canonical), message=f"seat cover for {FAMILY}",
    )
    assert lines == []
    assert _codes(out) == [FAMILY]
    assert _attachments(out) == [], out["entities"]
    assert out["domain_hint"] is None and out["intent_hint"] is None


def test_a_real_file_word_keeps_its_file_type_on_the_as_typed_path(session_factory) -> None:
    """Only the entity that IS the relation's word goes: "seat cover photo for <family>"."""
    from app.services.chatbot.lanes.business import find as find_lane

    _seed(session_factory)
    photo = {"raw": "photo", "hint": "attachment_type", "canonical_code": "photo", "current_message": True}
    find = {"filters": [{"key": "fits", "value": "seat cover", "unit": None, "file_word": "photo", "kind": "seat_cover"}]}
    verdict = _verdict(FAMILY, find=find, domain_hint="product_attachment", intent_hint="check_product_attachment")
    verdict["entities"] += [_as_type("installation guide"), photo]
    out, lines = find_lane.as_linked_products(
        _scoped(session_factory), verdict, message=f"seat cover photo for {FAMILY}",
    )
    assert lines == []
    assert _attachments(out) == [photo], out["entities"]
    assert out["domain_hint"] == "product_attachment"


@pytest.mark.parametrize("canonical", FILE_TYPES)
def test_a_visible_cover_control_still_swaps_and_drops_the_file_type(session_factory, canonical) -> None:
    from app.services.chatbot.lanes.business import find as find_lane

    _seed(session_factory)
    out, lines = find_lane.as_linked_products(
        _scoped(session_factory), _file_verdict(WC_TWO, canonical), message=f"seat cover for {WC_TWO}",
    )
    assert lines == [] and _codes(out) == COVERS_TWO
    assert _attachments(out) == []
    assert out["domain_hint"] is None


# --------------------------------------------------------------------------- the whole turn


@pytest.mark.parametrize("canonical", FILE_TYPES)
@pytest.mark.parametrize("wc", [WC_HID, WC_NOLINK])
def test_the_turn_is_the_no_link_line_and_nothing_is_fetched(session_factory, monkeypatch, wc, canonical) -> None:
    _seed(session_factory)
    _seed_contact(session_factory, variables={})
    reply, calls = _turn(
        session_factory, monkeypatch, text=f"seat cover for {wc}", msg_id="ZZT-sch-none",
        domain_hint="product_attachment", intent_hint="check_product_attachment",
        entities=[_product(wc), _as_type(canonical)], find=FITS, domain_in_message=True,
    )
    assert calls == [], calls
    assert reply.strip() == f"No seat cover is on record for {wc}.", reply
    assert COVER_HID not in reply and "file" not in reply.lower(), reply


def test_the_family_turn_is_the_bare_family_code_turn(session_factory, monkeypatch) -> None:
    """"seat cover for <family>" misread with a photo type answers as the bare family code does
    (the resolver's own variant picker), never a file-annotated picker."""
    _seed(session_factory)
    _seed_contact(session_factory, variables={})
    conn = session_factory().get_bind()
    conn.exec_driver_sql("SAVEPOINT zzt_sch_family")
    c_reply, c_calls = _turn(
        session_factory, monkeypatch, text=FAMILY, msg_id="ZZT-sch-family-control",
        domain_hint=None, intent_hint=None, entities=[_product(FAMILY)], domain_in_message=False,
    )
    conn.exec_driver_sql("ROLLBACK TO SAVEPOINT zzt_sch_family")
    a_reply, a_calls = _turn(
        session_factory, monkeypatch, text=f"seat cover for {FAMILY}", msg_id="ZZT-sch-family-asked",
        domain_hint="product_attachment", intent_hint="check_product_attachment",
        entities=[_product(FAMILY), _as_type("photo")], find=FITS, domain_in_message=True,
    )
    assert "Photos" not in a_reply and "kind of file" not in a_reply, a_reply
    assert a_calls == c_calls, (a_calls, c_calls)
    assert a_reply == c_reply, (a_reply, c_reply)


@pytest.mark.parametrize("canonical", FILE_TYPES)
def test_the_visible_cover_turn_is_the_fit_line_then_the_bare_covers(session_factory, monkeypatch, canonical) -> None:
    _seed(session_factory)
    _seed_contact(session_factory, variables={})
    conn = session_factory().get_bind()
    conn.exec_driver_sql("SAVEPOINT zzt_sch_visible")
    c_reply, c_calls = _turn(
        session_factory, monkeypatch, text=" ".join(COVERS_TWO), msg_id="ZZT-sch-visible-control",
        domain_hint=None, intent_hint=None, entities=[_product(c) for c in COVERS_TWO], domain_in_message=False,
    )
    conn.exec_driver_sql("ROLLBACK TO SAVEPOINT zzt_sch_visible")
    a_reply, a_calls = _turn(
        session_factory, monkeypatch, text=f"seat cover for {WC_TWO}", msg_id="ZZT-sch-visible-asked",
        domain_hint="product_attachment", intent_hint="check_product_attachment",
        entities=[_product(WC_TWO), _as_type(canonical)], find=FITS, domain_in_message=True,
    )
    assert a_calls == c_calls, (a_calls, c_calls)
    assert a_reply == _with_line(_line_many(WC_TWO, COVERS_TWO), c_reply), (a_reply, c_reply)
