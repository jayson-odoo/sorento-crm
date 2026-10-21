"""CHAT-PROMO-TIER-PICK-KIND: owner run 21 Oct 06:18 MYT, "Gimme sorento a3 flyer".

Three faults behind one wrong answer (EVAL-BENCH, explore build c899b3ec5d):
1. `turn_runtime.promo_filter` blanked the parser's `promotion_kind` on any message that carries
   a pick, so the answer to the access-level menu ("2") sent every kind.
2. `turn/apply._open_pick_answer` re-used the still-open access-level menu's position on a
   fresh ask that names its own subject.
3. The promotion attachment loader served a soft-deleted attachment.

Contact: Sorento Office + Sorento Dealer (+ Mocha Dealer). A live Sorento A3 flyer at Dealer
(with one live and one DELETED file), a live Mocha A3 flyer, a Sorento standard promo. The MCP
double goes through the real promotions route and the real presenter. Fake names only.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.main import app
from app.models.marketing import Promotion, PromotionAttachment
from app.models.resources import Attachment
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import _session_of
from tests.chatbot.test_promo_brand_category import _mcp
from tests.chatbot.test_promo_kind_subject import PROMO_TOOL, _qf, _say, _seed_world

LIVE_FILE = "ZZT SORENTO A3 FLYER_DEALER USE_LIVE.pdf"
DELETED_FILE = "ZZT SORENTO A3 FLYER_DEALER USE_11062026.pdf"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _world(session_factory) -> dict[str, Any]:
    ids = _seed_world(session_factory, sorento_live_flyer=True)
    db = session_factory()
    db.query(Promotion.id).first()  # a fresh test session answers its first ORM read empty
    promo = db.query(Promotion).filter(Promotion.description == "ZZT SORENTO A3 FLYER 2026").one()
    for name, deleted in ((LIVE_FILE, False), (DELETED_FILE, True)):
        att = Attachment(
            id=str(uuid.uuid4()), original_filename=name, stored_filename=name, file_path=f"/tmp/{name}",
            access_levels=["sorento_dealer"], company_id=DEFAULT_COMPANY_ID, is_deleted=deleted,
        )
        db.add(att)
        db.flush()
        db.add(PromotionAttachment(id=str(uuid.uuid4()), promotion_id=promo.id, attachment_id=att.id, is_primary=False, sort_order=0))
    db.commit()
    ids["promo"] = str(promo.id)
    return ids


def _pick(position: int, **over) -> dict[str, Any]:
    answer = {"mode": "pick", "picked": [position], "items": [], "qty_for_all": None}
    return _parser_output(
        domain_hint=None, intent_hint=None, entities=[], access_levels=[], reference_positions=[position],
        open_question_answer=answer, **over,
    )


def _menu(session_factory, monkeypatch, ids, captured, *, kind="a3_flyer"):
    qf = _qf(kind=kind, typed="sorento")
    qf["contains_flyer"] = True
    reply, _ = _say(session_factory, monkeypatch, qf, "sorento a3 flyer", "zzt-tpk-menu")
    assert reply.startswith("Which access level do you need for Sorento?"), reply
    assert (_session_of(session_factory).get("open_question") or {}).get("kind") == "tier_pick"
    return len(captured)


def _fetches(captured, n):
    return [a for name, a in captured[n:] if name == PROMO_TOOL and "_diagnostics" in a]


def test_the_menu_answer_keeps_the_kind_the_parser_read(session_factory, monkeypatch):
    """Fault 1: the menu was asked with no kind on it ("sorento flyer"); the answer "2, the A3
    flyer" is a pick of the menu AND names the kind, which the fetch keeps, with the brand and
    the picked level: no standard promo, no other brand."""
    ids = _world(session_factory)
    captured = _mcp(monkeypatch, session_factory)
    n = _menu(session_factory, monkeypatch, ids, captured, kind=None)
    reply, _ = _say(
        session_factory, monkeypatch, _pick(2, promotion_kind="a3_flyer", contains_flyer=True), "2, the A3 flyer", "zzt-tpk-pick"
    )
    fetches = _fetches(captured, n)
    assert fetches, captured[n:]
    for a in fetches:
        assert a.get("promotion_types") == ["a3_flyer"], a
        assert a.get("brand_ids") == [str(ids["srt"])], a
        assert a.get("access_levels") == ["Sorento Dealer"], a
    assert LIVE_FILE in reply and "STANDARD" not in reply and "MOCHA" not in reply.upper(), reply


def test_a_fresh_ask_over_the_open_menu_does_not_reuse_the_old_pick(session_factory, monkeypatch):
    """Fault 2: "Gimme sorento a3 flyer" while the menu is open, the parser also scoring it as
    picking option 2: a fresh ask names its own subject, so the old menu is not answered with
    the stale position; the access level is asked again, by kind and brand."""
    ids = _world(session_factory)
    captured = _mcp(monkeypatch, session_factory)
    n = _menu(session_factory, monkeypatch, ids, captured)
    fresh = _qf(kind="a3_flyer", typed="sorento")
    fresh["open_question_answer"] = {"mode": "pick", "picked": [2], "items": [], "qty_for_all": None}
    reply, _ = _say(session_factory, monkeypatch, fresh, "Gimme sorento a3 flyer", "zzt-tpk-fresh")
    assert reply.startswith("Which access level do you need for Sorento?"), reply
    # Only the menu's per-level probes ran, each by kind and brand at its one level.
    calls = [a for name, a in captured[n:] if name == PROMO_TOOL]
    assert sorted(tuple(a.get("access_levels") or []) for a in calls) == [("Sorento Dealer",), ("Sorento Office",)], calls
    assert all(a.get("promotion_types") == ["a3_flyer"] and a.get("brand_ids") == [str(ids["srt"])] for a in calls), calls


def test_a_deleted_promotion_file_is_never_served(session_factory, monkeypatch):
    """Fault 3: the promotions read carries the live file and never the soft-deleted one."""
    from app.services.contact_access_type_service import ContactAccessTypeService
    from app.services.marketing_service import PromotionService

    ids = _world(session_factory)
    db = session_factory()
    db.query(Promotion.id).first()  # a fresh test session answers its first ORM read empty
    served = PromotionService(db).list_promotions(
        page=1, limit=50, serving_policy=True,
        contact_access_codes=ContactAccessTypeService(db).translate_names_to_codes(["Sorento Dealer"]),
        promotion_ids=[ids["promo"]],
    )
    promo = next(p for p in served["data"] if str(p.id) == ids["promo"])
    names = {a.attachment.original_filename for a in promo.attachments}
    assert names == {LIVE_FILE}, names
