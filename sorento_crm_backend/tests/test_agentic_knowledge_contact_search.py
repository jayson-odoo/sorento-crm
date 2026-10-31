"""AGENTIC-KNOWLEDGE P2 W1, slice S2: knowledge for a contact (UAC AC-W11 .. AC-W17).

`knowledge_service.search_for_contact(db, *, access_codes, query, top_k=5, embed=None)` is the
contact's twin of `search`: the same query, but the gate is the contact's ACTIVE access codes
against the file's `access_levels`, by the type's audience. Vectors are hand built (see
tests/_knowledge_seed.py); every refusal is asserted as the absence of an otherwise-matching
passage, with a positive control beside it so a test cannot pass because nothing ever matched.
"""
from __future__ import annotations

import json

import pytest

from app.models.base import UNSET, set_company_scope
from tests._knowledge_seed import (
    SORENTO_COMPANY_ID,
    query_embed,
    seed_attachment,
    seed_chunk,
    seed_company,
    seed_reader,
    seed_team,
    seed_type,
    vec_with_similarity,
)
from tests._pg_fixture import blank_session

EXACT = vec_with_similarity(1.0)


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _file(db, audience, levels, text, *, name=None, company_id=None, team_id=None, att_type=None):
    """One file of a type with `audience`, readable at `levels`, with one exactly matching chunk."""
    att_type = att_type or seed_type(db, audience=audience, team_id=team_id)
    att = seed_attachment(db, att_type, name or f"{text}.pdf", company_id=company_id)
    att.access_levels = list(levels)
    db.flush()
    seed_chunk(db, att, EXACT, text=text)
    return att


def _ask(db, codes, query="what is the warranty on this tile?", **kw):
    from app.services import knowledge_service as ks

    return ks.search_for_contact(db, access_codes=frozenset(codes), query=query, embed=query_embed, **kw)


def _texts(out):
    assert out["status"] == "ok", out
    return [p["text"] for p in out["passages"]]


# ---------------------------------------------------------------- AC-W11 dealer audience


def test_ac_w11_a_dealer_file_is_read_when_a_non_end_user_code_overlaps(db):
    _file(db, "dealer", ["dealer"], "dealer warranty terms")

    assert _texts(_ask(db, {"dealer"})) == ["dealer warranty terms"]
    assert _texts(_ask(db, {"dealer", "end_user"})) == ["dealer warranty terms"]


def test_ac_w11_an_end_user_only_contact_reads_no_dealer_passage(db):
    _file(db, "dealer", ["dealer", "end_user"], "dealer warranty terms")

    assert _texts(_ask(db, {"end_user"})) == []
    # Positive control: the same file, the same query, one dealer code.
    assert _texts(_ask(db, {"dealer"})) == ["dealer warranty terms"]


def test_ac_w11_end_user_is_taken_out_of_the_overlap_for_a_dealer_type(db):
    """The file is open to end_user only; a contact holding dealer AND end_user matches only on end_user."""
    _file(db, "dealer", ["end_user"], "end user level dealer file")

    assert _texts(_ask(db, {"dealer", "end_user"})) == []


def test_ac_w11_a_file_whose_levels_miss_every_code_is_not_read(db):
    _file(db, "dealer", ["sorento_dealer"], "other level file")

    assert _texts(_ask(db, {"dealer"})) == []
    assert _texts(_ask(db, {"dealer", "sorento_dealer"})) == ["other level file"]


# ---------------------------------------------------------------- AC-W12 public audience


def test_ac_w12_a_public_file_is_read_on_any_overlapping_code_end_user_included(db):
    _file(db, "public", ["end_user"], "public brochure text")

    assert _texts(_ask(db, {"end_user"})) == ["public brochure text"]
    assert _texts(_ask(db, {"end_user", "dealer"})) == ["public brochure text"]


def test_ac_w12_a_public_file_still_needs_an_overlap(db):
    _file(db, "public", ["dealer"], "dealer level public file")

    assert _texts(_ask(db, {"end_user"})) == []
    assert _texts(_ask(db, {"dealer"})) == ["dealer level public file"]


# ---------------------------------------------------------------- AC-W13 zero leak


@pytest.mark.parametrize("audience", ["staff", "off"])
def test_ac_w13_a_staff_or_off_passage_is_never_returned_whatever_the_codes(db, audience):
    every_code = ["dealer", "end_user", "sorento_dealer", "public"]
    _file(db, audience, every_code, f"{audience} only secret")
    _file(db, "dealer", every_code, "control dealer passage")

    out = _ask(db, set(every_code))

    assert _texts(out) == ["control dealer passage"]
    assert f"{audience} only secret" not in json.dumps(out)


def test_ac_w13_a_type_switched_to_staff_hides_an_already_read_file_at_once(db):
    att_type = seed_type(db, audience="dealer")
    _file(db, "dealer", ["dealer"], "was dealer visible", att_type=att_type)
    assert _texts(_ask(db, {"dealer"})) == ["was dealer visible"]

    att_type.ai_audience = "staff"
    db.flush()

    assert _texts(_ask(db, {"dealer"})) == []


def test_ac_w13_a_deleted_attachment_is_not_returned(db):
    att = _file(db, "dealer", ["dealer"], "gone soon")
    assert _texts(_ask(db, {"dealer"})) == ["gone soon"]

    att.is_deleted = True
    db.flush()

    assert _texts(_ask(db, {"dealer"})) == []


def test_ac_w13_the_search_ranks_best_first_and_honours_top_k(db):
    att_type = seed_type(db, audience="dealer")
    for i, sim in enumerate((0.95, 0.80, 0.99)):
        att = seed_attachment(db, att_type, f"f{i}.pdf")
        att.access_levels = ["dealer"]
        db.flush()
        seed_chunk(db, att, vec_with_similarity(sim), text=f"sim {sim}")

    out = _ask(db, {"dealer"}, top_k=2)

    assert _texts(out) == ["sim 0.99", "sim 0.95"]


# ---------------------------------------------------------------- AC-W14 no code, no query


def test_ac_w14_a_contact_with_no_code_reads_nothing_and_no_query_runs(db):
    from app.services import knowledge_service as ks

    _file(db, "public", ["end_user"], "public brochure text")
    calls = []

    def spy_embed(texts):
        calls.append(texts)
        return query_embed(texts)

    out = ks.search_for_contact(db, access_codes=frozenset(), query="warranty", embed=spy_embed)

    assert out["status"] == "ok"
    assert out["passages"] == []
    assert calls == [], "the embed seam must not be called with no access code"
    # Positive control: one code, the embed seam is used and the passage comes back.
    out = ks.search_for_contact(db, access_codes=frozenset({"end_user"}), query="warranty", embed=spy_embed)
    assert [p["text"] for p in out["passages"]] == ["public brochure text"]
    assert len(calls) == 1


# ---------------------------------------------------------------- AC-W15 company scope and shared types


def test_ac_w15_another_companys_file_is_not_returned_to_a_contact_scoped_to_mine(db):
    other = seed_company(db)
    att_type = seed_type(db, audience="dealer")
    _file(db, "dealer", ["dealer"], "my company passage", company_id=SORENTO_COMPANY_ID, att_type=att_type)
    _file(db, "dealer", ["dealer"], "other company passage", company_id=other, att_type=att_type)

    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    assert _texts(_ask(db, {"dealer"})) == ["my company passage"]

    # Positive control: scoped to the other company, the same query sees only its file.
    set_company_scope(db, frozenset({other}))
    assert _texts(_ask(db, {"dealer"})) == ["other company passage"]


def test_ac_w15_an_unset_company_scope_returns_nothing(db):
    _file(db, "dealer", ["dealer"], "any passage")
    assert _texts(_ask(db, {"dealer"})) == ["any passage"]

    set_company_scope(db, UNSET)

    assert _texts(_ask(db, {"dealer"})) == []


def test_ac_w15_a_shared_type_file_is_visible_to_every_company(db):
    other = seed_company(db)
    att_type = seed_type(db, audience="dealer")
    att_type.is_shared = True
    att = seed_attachment(db, att_type, "Shared brochure.pdf")
    att.company_id = None
    att.access_levels = ["dealer"]
    db.flush()
    seed_chunk(db, att, EXACT, text="shared passage", company_id=None)

    set_company_scope(db, frozenset({other}))
    assert _texts(_ask(db, {"dealer"})) == ["shared passage"]

    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    assert _texts(_ask(db, {"dealer"})) == ["shared passage"]


# ---------------------------------------------------------------- AC-W16 no team names


def test_ac_w16_the_contact_result_carries_no_handoff_teams(db):
    team_id = seed_team(db, "ZZT Marketing Product Team")
    _file(db, "dealer", ["dealer"], "dealer warranty terms", team_id=team_id)

    out = _ask(db, {"dealer"})

    assert _texts(out) == ["dealer warranty terms"], "positive control: a passage came back"
    assert "handoff_teams" not in out
    assert "ZZT Marketing Product Team" not in json.dumps(out)


def test_ac_w16_an_empty_result_carries_no_handoff_teams_either(db):
    team_id = seed_team(db, "ZZT Marketing Product Team")
    _file(db, "dealer", ["dealer"], "dealer warranty terms", team_id=team_id)

    out = _ask(db, {"end_user"})

    assert out["passages"] == []
    assert "handoff_teams" not in out
    assert "ZZT Marketing Product Team" not in json.dumps(out)


# ---------------------------------------------------------------- AC-W17 inactive codes


def test_ac_w17_an_inactive_access_code_does_not_open_a_file_through_the_agent(db, monkeypatch):
    """End to end: build_context drops the inactive code, the tool then finds nothing."""
    from app.services import knowledge_service
    from app.services.chatbot.agent import tools
    from app.services.chatbot.agent.access import build_context
    from tests.chatbot.agent._seed import seed_contact
    from tests.chatbot.agent.test_agent_w1_contact_principal import _give_codes

    monkeypatch.setattr(knowledge_service, "_default_embed", lambda db_, timeout=None: query_embed)
    _file(db, "dealer", ["dealer", "zzt_retired"], "dealer file text")
    live = seed_contact(db)
    _give_codes(db, live["pk"], active=("dealer",))
    retired = seed_contact(db)
    _give_codes(db, retired["pk"], inactive=("zzt_retired",))

    def ask(contact):
        ctx = build_context(db, contact["respond_id"])
        set_company_scope(db, None)  # the contact has no company mapping in this blank world
        out = tools.dispatch(
            db, ctx, "crm_knowledge_search", {"query": "warranty"},
            call=lambda n, a: pytest.fail("knowledge is local, never the MCP call"), catalog={}, timeout=5.0,
        )
        assert out.status in ("ok", "empty"), out.message
        return [p["text"] for p in (out.data or {}).get("passages", [])]

    assert ask(live) == ["dealer file text"]
    assert ask(retired) == []


# ---------------------------------------------------------------- agent dispatch uses the contact search


def _contact_ctx(**kw):
    from app.services.chatbot.agent.access import AgentContext

    base = dict(
        contact_pk="pk-1", contact_respond_id="ZZT-RESPOND-1", space_id="364817", user_id="", user_name="",
        grants=frozenset(), principal="contact", access_codes=frozenset({"dealer"}),
    )
    base.update(kw)
    return AgentContext(**base)


def _dispatch_knowledge(db, ctx, query="warranty"):
    from app.services.chatbot.agent import tools

    def no_mcp(name, args):
        raise AssertionError("knowledge is local, never the MCP call")

    return tools.dispatch(db, ctx, "crm_knowledge_search", {"query": query}, call=no_mcp, catalog={}, timeout=5.0)


def test_agent_dispatch_for_a_contact_never_returns_a_staff_audience_passage(db, monkeypatch):
    from app.services import knowledge_service

    monkeypatch.setattr(knowledge_service, "_default_embed", lambda db_, timeout=None: query_embed)
    team_id = seed_team(db, "ZZT Marketing Product Team")
    _file(db, "staff", ["dealer", "end_user"], "STAFF ONLY payroll note", team_id=team_id)
    _file(db, "dealer", ["dealer"], "dealer warranty terms", team_id=team_id)
    set_company_scope(db, None)

    out = _dispatch_knowledge(db, _contact_ctx())

    assert out.status == "ok", out.message
    assert [p["text"] for p in out.data["passages"]] == ["dealer warranty terms"]
    body = json.dumps(out.data, default=str)
    assert "STAFF ONLY" not in body
    assert "ZZT Marketing Product Team" not in body


def test_agent_dispatch_for_a_contact_uses_search_for_contact_and_not_the_staff_search(db, monkeypatch):
    from app.services import knowledge_service

    def staff_search(*a, **k):
        raise AssertionError("a contact principal must never reach the staff `search`")

    seen = {}
    real = knowledge_service.search_for_contact

    def spy(db_, **kw):
        seen.update(kw)
        return real(db_, **{**kw, "embed": query_embed})

    monkeypatch.setattr(knowledge_service, "search", staff_search)
    monkeypatch.setattr(knowledge_service, "search_for_contact", spy)
    _file(db, "dealer", ["dealer"], "dealer warranty terms")
    set_company_scope(db, None)

    out = _dispatch_knowledge(db, _contact_ctx(access_codes=frozenset({"dealer", "end_user"})))

    assert out.status == "ok", out.message
    assert seen["access_codes"] == frozenset({"dealer", "end_user"})
    assert seen["query"] == "warranty"
    assert [p["text"] for p in out.data["passages"]] == ["dealer warranty terms"]


def test_agent_dispatch_for_a_contact_with_no_code_finds_nothing(db, monkeypatch):
    from app.services import knowledge_service

    monkeypatch.setattr(
        knowledge_service, "_default_embed",
        lambda db_, timeout=None: (lambda texts: pytest.fail("no query may run with no access code")),
    )
    _file(db, "public", ["end_user"], "public brochure text")
    set_company_scope(db, None)

    out = _dispatch_knowledge(db, _contact_ctx(access_codes=frozenset()))

    assert out.status in ("ok", "empty"), out.message
    assert (out.data or {}).get("passages", []) == []


def test_agent_dispatch_keeps_the_operator_check_when_an_operator_drives_the_turn(db, monkeypatch):
    import dataclasses

    from app.services import knowledge_service

    monkeypatch.setattr(knowledge_service, "_default_embed", lambda db_, timeout=None: query_embed)
    _file(db, "dealer", ["dealer"], "dealer warranty terms")
    set_company_scope(db, None)
    outsider = seed_reader(db, slugs=("inventory.stock.view",))
    reader = seed_reader(db)
    base = _contact_ctx()

    denied = _dispatch_knowledge(db, dataclasses.replace(base, operator_user_id=outsider))
    allowed = _dispatch_knowledge(db, dataclasses.replace(base, operator_user_id=reader))

    assert denied.status == "denied"
    assert allowed.status == "ok", allowed.message
    assert [p["text"] for p in allowed.data["passages"]] == ["dealer warranty terms"]
