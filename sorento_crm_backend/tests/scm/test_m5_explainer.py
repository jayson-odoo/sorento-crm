"""SCM M5 Part A — bounded semantic explainer (prose + scoped Q&A + advisory).

The LLM is a hard boundary: it receives already-frozen numbers and emits prose
ONLY. These tests MOCK the provider by monkeypatching
``explainer_service._provider_and_model`` to a fake whose ``chat`` records the
call and returns a ``ChatResult``-like object. Nothing here needs a real API key.

Covered UAC:
  * AC-M5.1 — explain caches frozen-fact prose; second read hits the cache.
  * AC-M5.2 — ask returns ``REFUSAL`` verbatim when the model refuses; passes an
    answerable question + facts through otherwise.
  * AC-M5.3 — no tool/agent loop: ``provider.chat`` gets NO ``tools`` kwarg.
  * AC-M5.8 — LLM boundary: numeric columns are byte-identical before/after
    explain AND ask; only ``explanation`` may change (on explain).
  * no-provider degrade — deterministic sentence (uncached) + ask REFUSAL.
  * auth — bare user is denied on every endpoint.

Fixtures reuse the ``scm_app`` savepoint + the M4 seed helpers.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.scm import ReorderRecommendation
from app.services.scm import explainer_service
from app.services.scm import reorder_run_service as run_svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m4_cash import _client, _seed_two_buys

pytestmark = requires_pg


# ===========================================================================
# fake provider + seed helpers
# ===========================================================================

class _FakeProvider:
    """Records every ``chat`` call and returns a fixed ``.content``."""

    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return SimpleNamespace(
            content=self._content,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            tool_calls=[],
            raw=None,
        )


def _install_provider(monkeypatch, content: str) -> _FakeProvider:
    fake = _FakeProvider(content)
    monkeypatch.setattr(
        explainer_service, "_provider_and_model", lambda db: (fake, "fake-model")
    )
    return fake


def _install_no_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        explainer_service, "_provider_and_model", lambda db: (None, None)
    )


def _seed_buy_rec(db) -> ReorderRecommendation:
    """One frozen BUY recommendation inside the savepoint."""
    _seed_two_buys(db)
    created = run_svc.create_run(db, ["M4W-CASH"], "warehouse", enqueue=False)
    assert run_svc.run_reorder(created["run_id"], db=db)["status"] == "completed"
    rec = (
        db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == created["run_id"],
            ReorderRecommendation.rec_type == "buy",
        )
        .order_by(ReorderRecommendation.rank)
        .first()
    )
    assert rec is not None, "run should produce at least one buy rec"
    assert rec.reorder_point is not None and rec.net_position is not None
    return rec


def _user_block(fake: _FakeProvider, call_index: int = 0) -> str:
    """The user message content of the ``call_index``-th chat call."""
    return fake.calls[call_index]["messages"][1]["content"]


def _facts_json(user_block: str) -> dict:
    """The facts JSON embedded in a user block (line 2 of the prompt)."""
    return json.loads(user_block.split("\n")[1])


def _numeric_snapshot(db, rec_id: str) -> dict:
    row = db.execute(
        text(
            "SELECT rounded_qty, reorder_point, net_position, cash_impact, rank "
            "FROM scm.reorder_recommendation WHERE id = :id"
        ),
        {"id": rec_id},
    ).mappings().first()
    return {k: (None if v is None else str(v)) for k, v in row.items()}


# ===========================================================================
# AC-M5.1 — explain: frozen facts in, cached prose out, second call = cache
# ===========================================================================

def test_explain_passes_frozen_facts_and_caches(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    rec_id = rec.id
    fake = _install_provider(monkeypatch, "Order now to replenish before stockout.")

    out = explainer_service.explain_recommendation(db, rec_id)
    assert out == "Order now to replenish before stockout."

    # the facts the model saw carry the rec's FROZEN reorder_point + net_position verbatim
    facts = _facts_json(_user_block(fake))
    assert facts["reorder_point"] == float(rec.reorder_point)
    assert facts["net_position"] == float(rec.net_position)

    # prose cached onto the rec
    db.flush()
    cached = db.execute(
        text("SELECT explanation FROM scm.reorder_recommendation WHERE id = :id"),
        {"id": rec_id},
    ).scalar()
    assert cached == "Order now to replenish before stockout."

    # SECOND call returns the cache WITHOUT calling the provider again
    again = explainer_service.explain_recommendation(db, rec_id)
    assert again == "Order now to replenish before stockout."
    assert len(fake.calls) == 1, "cached explanation must not re-invoke the LLM"


# ===========================================================================
# AC-M5.2 — ask: verbatim REFUSAL, and answerable question passes through
# ===========================================================================

def test_ask_returns_refusal_verbatim(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    fake = _install_provider(monkeypatch, explainer_service.REFUSAL)

    ans = explainer_service.answer_question(db, rec.id, "What's the supplier's phone number?")
    # exact bytes
    assert ans == explainer_service.REFUSAL
    assert ans == "I can't compute that from this recommendation's data."


def test_ask_passes_question_and_facts_through(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    fake = _install_provider(monkeypatch, "Because net position has hit the reorder point.")

    question = "Why are we ordering this now?"
    ans = explainer_service.answer_question(db, rec.id, question)
    assert ans == "Because net position has hit the reorder point."

    block = _user_block(fake)
    assert question in block, "the planner's question must be forwarded to the model"
    facts = _facts_json(block)
    assert facts["reorder_point"] == float(rec.reorder_point)
    assert facts["net_position"] == float(rec.net_position)


# ===========================================================================
# AC-M5.3 — no tools / no agent loop on explain OR ask
# ===========================================================================

def test_no_tools_passed_to_provider(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    fake = _install_provider(monkeypatch, "some prose")

    explainer_service.explain_recommendation(db, rec.id)
    explainer_service.answer_question(db, rec.id, "why?")

    assert len(fake.calls) == 2
    for call in fake.calls:
        assert call["kwargs"].get("tools") is None, "explainer must never pass tools"


# ===========================================================================
# AC-M5.8 — LLM boundary: numeric columns unchanged by explain AND ask
# ===========================================================================

def test_numeric_columns_untouched_by_llm(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    rec_id = rec.id
    _install_provider(monkeypatch, "Order now — cover is low.")

    before = _numeric_snapshot(db, rec_id)

    explainer_service.explain_recommendation(db, rec_id)
    db.flush()
    after_explain = _numeric_snapshot(db, rec_id)
    assert after_explain == before, "explain must not touch any numeric column"

    explainer_service.answer_question(db, rec_id, "why so much?")
    db.flush()
    after_ask = _numeric_snapshot(db, rec_id)
    assert after_ask == before, "ask must not touch any numeric column"

    # the ONLY column that changed is `explanation` (set by explain)
    assert db.execute(
        text("SELECT explanation FROM scm.reorder_recommendation WHERE id = :id"),
        {"id": rec_id},
    ).scalar() == "Order now — cover is low."


# ===========================================================================
# no-provider degrade — deterministic (uncached) explain + REFUSAL ask
# ===========================================================================

def test_no_provider_deterministic_explain_not_cached(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    rec_id = rec.id
    _install_no_provider(monkeypatch)

    out = explainer_service.explain_recommendation(db, rec_id)
    assert out, "deterministic fallback must be a non-empty sentence"
    # restates the frozen order qty + reorder point (formatted exactly as the service does)
    assert explainer_service._fmt(float(rec.rounded_qty)) in out
    assert explainer_service._fmt(float(rec.reorder_point)) in out

    # deterministic fallback must NOT cache
    db.flush()
    assert db.execute(
        text("SELECT explanation FROM scm.reorder_recommendation WHERE id = :id"),
        {"id": rec_id},
    ).scalar() is None


def test_no_provider_ask_refuses(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    _install_no_provider(monkeypatch)
    assert explainer_service.answer_question(db, rec.id, "why?") == explainer_service.REFUSAL


# ===========================================================================
# market advisory — None until a signal is stored
# ===========================================================================

def test_market_advisory_none_then_value(scm_app):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    assert explainer_service.market_advisory(db, rec.id) is None

    db.execute(
        text("UPDATE scm.reorder_recommendation SET market_advisory = :a WHERE id = :id"),
        {"a": "Copper prices rising — consider buying ahead.", "id": rec.id},
    )
    db.flush()
    db.expire(rec)
    assert explainer_service.market_advisory(db, rec.id) == \
        "Copper prices rising — consider buying ahead."


# ===========================================================================
# endpoints — happy path through the route (gated on scm.dashboard.view)
# ===========================================================================

def test_explanation_endpoint_caches_and_reuses(scm_app, monkeypatch):
    app, db = _client(scm_app, "purchasing")
    rec = _seed_buy_rec(db)
    db.commit()
    fake = _install_provider(monkeypatch, "Replenish now before it stocks out.")

    with TestClient(app) as client:
        r1 = client.get(f"/api/v1/scm/recommendations/{rec.id}/explanation")
        assert r1.status_code == 200, r1.text
        assert r1.json()["explanation"] == "Replenish now before it stocks out."
        # a second view is served from the cached column — no second LLM call
        r2 = client.get(f"/api/v1/scm/recommendations/{rec.id}/explanation")
        assert r2.json()["explanation"] == "Replenish now before it stocks out."

    assert len(fake.calls) == 1


def test_ask_endpoint_returns_refusal(scm_app, monkeypatch):
    app, db = _client(scm_app, "purchasing")
    rec = _seed_buy_rec(db)
    db.commit()
    _install_provider(monkeypatch, explainer_service.REFUSAL)

    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/recommendations/{rec.id}/ask",
            json={"question": "What is the supplier's bank account?"},
        )
    assert res.status_code == 200, res.text
    assert res.json()["answer"] == "I can't compute that from this recommendation's data."


def test_ask_endpoint_rejects_empty_question(scm_app, monkeypatch):
    app, db = _client(scm_app, "purchasing")
    rec = _seed_buy_rec(db)
    db.commit()
    _install_provider(monkeypatch, "unused")

    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/recommendations/{rec.id}/ask", json={"question": ""}
        )
    assert res.status_code == 422, res.text


def test_advisory_endpoint_none_then_value(scm_app):
    app, db = _client(scm_app, "purchasing")
    rec = _seed_buy_rec(db)
    db.commit()

    with TestClient(app) as client:
        r1 = client.get(f"/api/v1/scm/recommendations/{rec.id}/advisory")
        assert r1.status_code == 200, r1.text
        assert r1.json()["advisory"] is None

    db.execute(
        text("UPDATE scm.reorder_recommendation SET market_advisory = :a WHERE id = :id"),
        {"a": "Lead times lengthening this quarter.", "id": rec.id},
    )
    db.commit()

    with TestClient(app) as client:
        r2 = client.get(f"/api/v1/scm/recommendations/{rec.id}/advisory")
        assert r2.json()["advisory"] == "Lead times lengthening this quarter."


# ===========================================================================
# missing recommendation — 404 (not a 500)
# ===========================================================================

def test_explanation_missing_rec_returns_404(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/recommendations/{uuid.uuid4()}/explanation")
    assert res.status_code == 404, res.text


# ===========================================================================
# auth — bare user denied on every explainer endpoint
# ===========================================================================

def test_explanation_denied_without_dashboard_view(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/recommendations/{uuid.uuid4()}/explanation")
    assert res.status_code == 403


def test_ask_denied_without_dashboard_view(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/recommendations/{uuid.uuid4()}/ask", json={"question": "why?"}
        )
    assert res.status_code == 403


def test_advisory_denied_without_dashboard_view(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/recommendations/{uuid.uuid4()}/advisory")
    assert res.status_code == 403


# ===========================================================================
# run overview — aggregate brief, cached onto reorder_run.overview
# ===========================================================================

def _seed_run(db) -> str:
    """Run the M4 cash seed and return the completed run_id (with buys frozen)."""
    _seed_two_buys(db)
    created = run_svc.create_run(db, ["M4W-CASH"], "warehouse", enqueue=False)
    assert run_svc.run_reorder(created["run_id"], db=db)["status"] == "completed"
    return created["run_id"]


def test_explain_run_aggregates_caches_and_boundary(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    fake = _install_provider(monkeypatch, "This run recommends 2 buys worth RM 500.")

    # numeric snapshot of every rec before the overview runs
    before = db.execute(
        text(
            "SELECT id, rounded_qty, reorder_point, net_position, cash_impact "
            "FROM scm.reorder_recommendation WHERE run_id = :r ORDER BY id"
        ),
        {"r": run_id},
    ).mappings().all()

    out = explainer_service.explain_run(db, run_id)
    assert out == "This run recommends 2 buys worth RM 500."

    # the model only saw the run's frozen aggregates (buy_count present)
    facts = _facts_json(_user_block(fake))
    assert facts["buy_count"] >= 1

    # cached onto the run — a second read serves the cache, no second LLM call
    db.flush()
    cached = db.execute(
        text("SELECT overview FROM scm.reorder_run WHERE id = :r"), {"r": run_id}
    ).scalar()
    assert cached == "This run recommends 2 buys worth RM 500."
    again = explainer_service.explain_run(db, run_id)
    assert again == out
    assert len(fake.calls) == 1, "cached overview must not re-invoke the LLM"

    # no recommendation numeric column was touched by the overview
    after = db.execute(
        text(
            "SELECT id, rounded_qty, reorder_point, net_position, cash_impact "
            "FROM scm.reorder_recommendation WHERE run_id = :r ORDER BY id"
        ),
        {"r": run_id},
    ).mappings().all()
    assert [dict(r) for r in after] == [dict(r) for r in before]


def test_explain_run_no_provider_deterministic_not_cached(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    _install_no_provider(monkeypatch)

    out = explainer_service.explain_run(db, run_id)
    assert out and "buy" in out.lower()

    db.flush()
    assert db.execute(
        text("SELECT overview FROM scm.reorder_run WHERE id = :r"), {"r": run_id}
    ).scalar() is None, "deterministic overview must not cache"


def test_run_overview_endpoint_happy(scm_app, monkeypatch):
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.commit()
    fake = _install_provider(monkeypatch, "Run brief: 2 buys, one urgent SKU.")

    with TestClient(app) as client:
        r1 = client.get(f"/api/v1/scm/reorder-runs/{run_id}/overview")
        assert r1.status_code == 200, r1.text
        assert r1.json()["overview"] == "Run brief: 2 buys, one urgent SKU."
        # cached — a second view does not re-invoke the model
        r2 = client.get(f"/api/v1/scm/reorder-runs/{run_id}/overview")
        assert r2.json()["overview"] == "Run brief: 2 buys, one urgent SKU."
    assert len(fake.calls) == 1


def test_run_overview_missing_run_404(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/reorder-runs/{uuid.uuid4()}/overview")
    assert res.status_code == 404, res.text


def test_run_overview_denied_without_dashboard_view(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/reorder-runs/{uuid.uuid4()}/overview")
    assert res.status_code == 403


# ===========================================================================
# disposition explain — the frozen disposition facts reach the model
# ===========================================================================

def test_disposition_explain_surfaces_disposition_facts(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    # Re-cast this frozen rec as a disposition with an overstock reason + hold action.
    inp = dict(rec.inputs or {})
    inp["reason"] = "overstock"
    inp["disposition_action"] = "hold"
    rec.rec_type = "disposition"
    rec.inputs = inp
    db.flush()
    db.expire(rec)

    fake = _install_provider(monkeypatch, "Hold this stock — it is overstocked.")
    out = explainer_service.explain_recommendation(db, rec.id)
    assert out == "Hold this stock — it is overstocked."

    facts = _facts_json(_user_block(fake))
    assert facts["type"] == "disposition"
    assert facts["reason"] == "overstock"
    assert facts["disposition_action"] == "hold"


# ===========================================================================
# plan-chat (M6-A) — grounded, multi-turn conversation over the WHOLE run
# ===========================================================================

def test_run_chat_context_carries_all_recs_and_no_tools(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    fake = _install_provider(monkeypatch, "The most urgent buy is FT-B.")

    out = explainer_service.answer_run_question(db, run_id, "Which buys are most urgent?")
    assert out == "The most urgent buy is FT-B."

    # messages = [system, user(context), assistant(ack), user(question)]
    block = _user_block(fake)  # the context block (messages[1])
    assert '"aggregates"' in block and '"recommendations"' in block
    # a real SKU from the run is present in the grounded context (AC-M6.2)
    sku = db.execute(
        text("SELECT inputs->>'sku' FROM scm.reorder_recommendation WHERE run_id = :r LIMIT 1"),
        {"r": run_id},
    ).scalar()
    assert sku and sku in block
    # AC-M6.4 — plan-chat is a bounded chat, never an agent loop
    assert fake.calls[0]["kwargs"].get("tools") is None
    # the manager's question is the final turn
    assert fake.calls[0]["messages"][-1]["content"] == "Which buys are most urgent?"


def test_run_chat_touches_no_numeric_column(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    _install_provider(monkeypatch, "Here is your answer.")

    before = db.execute(
        text(
            "SELECT id, rounded_qty, reorder_point, net_position, cash_impact, rank "
            "FROM scm.reorder_recommendation WHERE run_id = :r ORDER BY id"
        ),
        {"r": run_id},
    ).mappings().all()

    explainer_service.answer_run_question(db, run_id, "What should I prioritise?")
    db.flush()

    after = db.execute(
        text(
            "SELECT id, rounded_qty, reorder_point, net_position, cash_impact, rank "
            "FROM scm.reorder_recommendation WHERE run_id = :r ORDER BY id"
        ),
        {"r": run_id},
    ).mappings().all()
    assert [dict(r) for r in after] == [dict(r) for r in before]
    # chat is NOT overview — it must not write the cached overview column either
    assert db.execute(
        text("SELECT overview FROM scm.reorder_run WHERE id = :r"), {"r": run_id}
    ).scalar() is None


def test_run_chat_forwards_prior_history(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    fake = _install_provider(monkeypatch, "The next one is FT-B.")
    history = [{"question": "What is the biggest buy?", "answer": "FT-03 at RM 76,860."}]

    explainer_service.answer_run_question(db, run_id, "And the next one?", history=history)

    contents = [m["content"] for m in fake.calls[0]["messages"]]
    assert "What is the biggest buy?" in contents  # prior question forwarded
    assert "FT-03 at RM 76,860." in contents  # prior answer forwarded
    assert fake.calls[0]["messages"][-1]["content"] == "And the next one?"


def test_run_chat_no_provider_graceful(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    run_id = _seed_run(db)
    _install_no_provider(monkeypatch)
    out = explainer_service.answer_run_question(db, run_id, "why so much cash?")
    assert out and "buy" in out.lower()  # falls back to a real aggregate sentence


def test_run_chat_endpoint_happy(scm_app, monkeypatch):
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.commit()
    _install_provider(monkeypatch, "Top risks: FT-B and FT-03.")
    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/reorder-runs/{run_id}/chat",
            json={"question": "What are the top stockout risks?"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["answer"] == "Top risks: FT-B and FT-03."


def test_run_chat_endpoint_rejects_empty_question(scm_app, monkeypatch):
    app, db = _client(scm_app, "purchasing")
    run_id = _seed_run(db)
    db.commit()
    _install_provider(monkeypatch, "unused")
    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/reorder-runs/{run_id}/chat", json={"question": ""}
        )
    assert res.status_code == 422, res.text


def test_run_chat_missing_run_404(scm_app, monkeypatch):
    app, _ = _client(scm_app, "purchasing")
    _install_provider(monkeypatch, "unused")
    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/reorder-runs/{uuid.uuid4()}/chat", json={"question": "hi"}
        )
    assert res.status_code == 404, res.text


def test_run_chat_denied_without_dashboard_view(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/reorder-runs/{uuid.uuid4()}/chat", json={"question": "hi"}
        )
    assert res.status_code == 403
