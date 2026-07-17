"""SCM M5 Part B — market research + advisory.

Two halves, with a hard line between them (mirrors the service docstrings):

  * Fully real, no key needed: topic CRUD, ``list_signals`` (topic-joined label),
    ``get_run``, and the ``run_research`` persistence path (network isolated by
    monkeypatching ``_web_search_topic``). Also ``market_advisory`` matching, cached
    prose (fake provider), and the no-provider degrade.
  * Key-gated: ``run_research`` with NO Anthropic key must record a ``failed`` run
    with the exact honest error and 0 signals — never a crash.

LLM boundary (AC-M5.8): the market service writes ONLY ``market_signal`` (+ its run
log) and ``market_advisory`` writes ONLY ``recommendation.market_advisory`` — never a
numeric column. Both are snapshotted before/after and asserted byte-identical.

Fixtures reuse the ``scm_app`` savepoint + the M4 seed helpers and the M5 explainer
fake-provider pattern. Nothing here reaches the network.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.scm import MarketResearchTopic, MarketSignal, ReorderRecommendation
from app.schemas.scm_market import MarketResearchTopicWrite
from app.services.scm import explainer_service
from app.services.scm import market_research_service as svc
from app.services.scm import reorder_engine
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_m4_cash import _client
from tests.scm.test_m5_explainer import _seed_buy_rec

pytestmark = requires_pg


# ===========================================================================
# fake provider + custom-permission client + fixture builders
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


def _client_with_perms(scm_app, perm_slugs):
    """Seed a bespoke role granting EXACTLY ``perm_slugs`` (the seeded roles all carry
    the full SCM permission set, so wrong-permission denial needs a custom role)."""
    app, db, gcu, gcuak = scm_app
    slug = f"scm-m5-{uuid.uuid4().hex[:8]}"
    rid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, "
            "is_default, created_at) VALUES (:id, :slug, :name, false, false, false, now())"
        ),
        {"id": rid, "slug": slug, "name": slug},
    )
    for p in perm_slugs:
        pid = db.execute(
            text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": p}
        ).scalar()
        assert pid, f"permission {p} not seeded"
        db.execute(
            text(
                "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
                "VALUES (:id, :r, :p, now())"
            ),
            {"id": str(uuid.uuid4()), "r": rid, "p": pid},
        )
    db.flush()
    uid = seed_user(db, slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _mk_topic(db, label, *, active=True, category_ref="SRT-FC", currency="MYR",
              search_prompt="track it", cadence="manual") -> MarketResearchTopic:
    t = MarketResearchTopic(
        label=label,
        category_ref=category_ref,
        currency=currency,
        search_prompt=search_prompt,
        cadence=cadence,
        is_active=active,
        source_system="m5test",
    )
    db.add(t)
    db.flush()
    return t


def _mk_signal(db, topic, summary, *, captured_at, currency="MYR",
               category_ref="SRT-FC", trend=None, value=None) -> MarketSignal:
    s = MarketSignal(
        topic_id=topic.id if topic else None,
        category_ref=category_ref,
        currency=currency,
        value=value,
        trend=trend,
        summary=summary,
        captured_at=captured_at,
        source_system="m5test",
    )
    db.add(s)
    db.flush()
    return s


_REC_NUMERIC_COLS = (
    "rounded_qty", "recommended_qty", "reorder_point", "net_position", "cash_impact",
    "rank", "rank_score", "unit_cost", "days_of_cover", "forecast_daily_demand",
    "urgency_score", "priority_score", "funding_status", "explanation",
)


def _rec_snapshot(db, rec_id: str) -> dict:
    cols = ", ".join(_REC_NUMERIC_COLS + ("market_advisory",))
    row = db.execute(
        text(f"SELECT {cols} FROM scm.reorder_recommendation WHERE id = :id"),
        {"id": rec_id},
    ).mappings().first()
    return {k: (None if v is None else str(v)) for k, v in row.items()}


def _signals_for_topic(db, topic_id: str) -> list[dict]:
    return db.execute(
        text(
            "SELECT summary, trend, currency, category_ref, value "
            "FROM scm.market_signal WHERE topic_id = :t ORDER BY summary"
        ),
        {"t": topic_id},
    ).mappings().all()


# ===========================================================================
# 1. LLM boundary (AC-M5.8) — the highest-risk guarantee
# ===========================================================================

def test_market_advisory_only_writes_market_advisory_column(scm_app, monkeypatch):
    """Generating a market advisory changes ONLY ``market_advisory`` — every numeric
    column (and ``explanation``) is byte-identical before/after."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    rec_id = rec.id
    category = reorder_engine.load_category_code(db, rec.product_id)
    assert category, "seeded product must resolve a category_code for matching"
    _mk_signal(db, _mk_topic(db, "M5-ADV"), "Resin prices climbing.",
               captured_at=datetime.utcnow(), currency=rec.currency, category_ref=category)

    before = _rec_snapshot(db, rec_id)
    _install_provider(monkeypatch, "Buy ahead — resin is trending up.")

    out = explainer_service.market_advisory(db, rec_id)
    assert out == "Buy ahead — resin is trending up."
    db.flush()
    after = _rec_snapshot(db, rec_id)

    changed = {k for k in after if after[k] != before[k]}
    assert changed == {"market_advisory"}, f"only market_advisory may change, got {changed}"
    assert after["market_advisory"] == "Buy ahead — resin is trending up."


def test_run_research_never_writes_a_recommendation_column(scm_app, monkeypatch):
    """The market research job persists signals only — it must not touch ANY column of
    an existing recommendation (numeric or the advisory prose)."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    rec_id = rec.id
    _mk_topic(db, "M5-RUN-ISO")

    before = _rec_snapshot(db, rec_id)
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: "fake-key")
    monkeypatch.setattr(
        svc, "_web_search_topic",
        lambda db, topic: [{"value": 1, "trend": "up", "summary": "x", "source_url": None}],
    )

    svc.run_research(db, actor="tester")
    after = _rec_snapshot(db, rec_id)
    assert after == before, "run_research must not write any recommendation column"


# ===========================================================================
# 2. run_research — no Anthropic key: honest failed run, 0 signals, persisted
# ===========================================================================

def test_run_research_no_key_records_failed_run(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    topic = _mk_topic(db, "M5-NOKEY")
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: None)

    out = svc.run_research(db, actor="tester")
    assert out["status"] == "failed"
    assert out["error"] == "Anthropic web-search not configured (set ANTHROPIC_API_KEY)"
    assert out["error"] == svc.NO_KEY_ERROR
    assert out["signal_count"] == 0
    assert out["topic_count"] >= 1  # our active topic was counted

    # the run row persisted for observability — get_run returns it
    again = svc.get_run(db, out["id"])
    assert again["status"] == "failed" and again["error"] == svc.NO_KEY_ERROR

    # no signals were written for our topic
    assert _signals_for_topic(db, topic.id) == []


def test_get_run_missing_raises_404(scm_app):
    _, db, _, _ = scm_app
    from app.services.error_handler import AppException
    import pytest
    with pytest.raises(AppException) as ei:
        svc.get_run(db, str(uuid.uuid4()))
    assert ei.value.status_code == 404


# ===========================================================================
# 3. run_research — persistence path (network isolated via _web_search_topic)
# ===========================================================================

def test_run_research_persists_signals_traps_failures_filters_rows(scm_app, monkeypatch):
    """One good topic yields a valid signal + a bad-trend signal (nulled) + an
    empty-summary signal (skipped); a second topic's search RAISES (trapped, run still
    completes); a third good topic yields one more. An INACTIVE topic is not searched."""
    _, db, _, _ = scm_app
    # run_research scans ALL active topics globally; the prod-copy DB may already hold
    # some. Neutralise them (rolled back with the savepoint) so the count is exact.
    db.execute(text("UPDATE scm.market_research_topic SET is_active = false"))
    good_a = _mk_topic(db, "M5-GOOD-A", currency="MYR", category_ref="SRT-FC")
    raises = _mk_topic(db, "M5-RAISES")
    good_b = _mk_topic(db, "M5-GOOD-B", currency="USD", category_ref="SRT-XX")
    inactive = _mk_topic(db, "M5-INACTIVE", active=False)

    def fake_search(db, topic):
        if topic.label == "M5-RAISES":
            raise RuntimeError("upstream 500")
        if topic.label == "M5-GOOD-A":
            return [
                {"value": 12.5, "trend": "up", "summary": "Copper up 3%", "source_url": "http://a"},
                {"value": None, "trend": "sideways", "summary": "Trend unclear", "source_url": None},
                {"value": 1, "trend": "down", "summary": "   ", "source_url": None},
            ]
        if topic.label == "M5-GOOD-B":
            return [{"value": 3, "trend": "flat", "summary": "Steel flat", "source_url": None}]
        raise AssertionError(f"inactive topic {topic.label} must not be searched")

    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: "fake-key")
    monkeypatch.setattr(svc, "_web_search_topic", fake_search)

    out = svc.run_research(db, actor="tester")
    # some topics captured + one errored → 'completed' (signals landed); the trapped
    # failure is logged on error_text. failed = ALL errored & nothing landed.
    assert out["status"] == "completed"
    assert out["topic_count"] == 3, "only the 3 ACTIVE topics are searched"
    assert out["signal_count"] == 3, "2 from GOOD-A (empty skipped) + 1 from GOOD-B"
    assert out["error"] and "M5-RAISES" in out["error"], "trapped failure logged on the run"

    # GOOD-A: valid signal kept verbatim, bad-trend nulled, empty-summary skipped
    a_rows = _signals_for_topic(db, good_a.id)
    assert len(a_rows) == 2
    by_summary = {r["summary"]: r for r in a_rows}
    assert by_summary["Copper up 3%"]["trend"] == "up"
    assert by_summary["Copper up 3%"]["category_ref"] == "SRT-FC"
    assert by_summary["Copper up 3%"]["currency"] == "MYR"
    assert by_summary["Trend unclear"]["trend"] is None, "invalid trend nulled"
    assert not any(r["summary"].strip() == "" for r in a_rows), "empty-summary signal skipped"

    # GOOD-B persisted with its own topic's category/currency
    b_rows = _signals_for_topic(db, good_b.id)
    assert len(b_rows) == 1 and b_rows[0]["trend"] == "flat"
    assert b_rows[0]["currency"] == "USD" and b_rows[0]["category_ref"] == "SRT-XX"

    # RAISES + INACTIVE persisted nothing
    assert _signals_for_topic(db, raises.id) == []
    assert _signals_for_topic(db, inactive.id) == []


def test_run_research_clean_run_is_completed(scm_app, monkeypatch):
    """No topic errors + signals captured → status 'completed' (the clean path)."""
    _, db, _, _ = scm_app
    db.execute(text("UPDATE scm.market_research_topic SET is_active = false"))
    topic = _mk_topic(db, "M5-CLEAN")
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: "fake-key")
    monkeypatch.setattr(
        svc, "_web_search_topic",
        lambda db, t: [{"value": 9, "trend": "up", "summary": "Nickel up", "source_url": None}],
    )
    out = svc.run_research(db, actor="tester")
    assert out["status"] == "completed" and out["error"] is None
    assert out["topic_count"] == 1 and out["signal_count"] == 1


# ===========================================================================
# 4. advisory matching (category + currency, newest wins, degrade, cache)
# ===========================================================================

def test_advisory_matches_category_and_currency_caches_hit(scm_app, monkeypatch):
    """A signal matching the rec's category + currency drives the advisory; the newest
    captured_at wins; the prose is cached so the second call skips the provider."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    category = reorder_engine.load_category_code(db, rec.product_id)
    topic = _mk_topic(db, "M5-MATCH", category_ref=category, currency=rec.currency)
    _mk_signal(db, topic, "OLD copper note", captured_at=datetime.utcnow() - timedelta(days=5),
               currency=rec.currency, category_ref=category)
    _mk_signal(db, topic, "NEW copper spike", captured_at=datetime.utcnow(),
               currency=rec.currency, category_ref=category)

    fake = _install_provider(monkeypatch, "Copper spiking — bring the buy forward.")
    out = explainer_service.market_advisory(db, rec.id)
    assert out == "Copper spiking — bring the buy forward."

    # the NEWEST signal (not the old one) was the one condensed
    block = fake.calls[0]["messages"][1]["content"]
    assert "NEW copper spike" in block and "OLD copper note" not in block

    # second call is served from the cached column — provider not re-invoked
    again = explainer_service.market_advisory(db, rec.id)
    assert again == "Copper spiking — bring the buy forward."
    assert len(fake.calls) == 1


def test_advisory_matches_currency_agnostic_signal(scm_app, monkeypatch):
    """A currency-agnostic (NULL currency) signal in the rec's category still matches."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    category = reorder_engine.load_category_code(db, rec.product_id)
    topic = _mk_topic(db, "M5-AGNOSTIC", category_ref=category, currency=None)
    _mk_signal(db, topic, "Global freight easing.", captured_at=datetime.utcnow(),
               currency=None, category_ref=category)

    _install_provider(monkeypatch, "Freight easing — no rush to prebuy.")
    assert explainer_service.market_advisory(db, rec.id) == "Freight easing — no rush to prebuy."


def test_advisory_currency_mismatch_returns_none(scm_app, monkeypatch):
    """A signal in the right category but a DIFFERENT hard currency does not match."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    category = reorder_engine.load_category_code(db, rec.product_id)
    other_ccy = "USD" if rec.currency != "USD" else "SGD"
    topic = _mk_topic(db, "M5-CCY", category_ref=category, currency=other_ccy)
    _mk_signal(db, topic, "USD-denominated index up.", captured_at=datetime.utcnow(),
               currency=other_ccy, category_ref=category)

    _install_provider(monkeypatch, "unused")
    assert explainer_service.market_advisory(db, rec.id) is None


def test_advisory_no_category_returns_none(scm_app, monkeypatch):
    """No resolvable product category → no match key → None (no provider call)."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    monkeypatch.setattr(
        explainer_service.reorder_engine, "load_category_code", lambda db, pid: None
    )
    _mk_signal(db, _mk_topic(db, "M5-NOCAT"), "Some note.", captured_at=datetime.utcnow())

    fake = _install_provider(monkeypatch, "unused")
    assert explainer_service.market_advisory(db, rec.id) is None
    assert fake.calls == [], "no category means the provider is never consulted"


def test_advisory_no_provider_degrades_to_signal_summary(scm_app, monkeypatch):
    """With a matching signal but NO LLM provider, the advisory degrades to the stored
    signal's own summary (invents nothing) and is NOT cached."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    rec_id = rec.id
    category = reorder_engine.load_category_code(db, rec.product_id)
    topic = _mk_topic(db, "M5-DEGRADE", category_ref=category, currency=rec.currency)
    _mk_signal(db, topic, "Aluminium premium widening.", captured_at=datetime.utcnow(),
               currency=rec.currency, category_ref=category)
    _install_no_provider(monkeypatch)

    out = explainer_service.market_advisory(db, rec_id)
    assert out == "Aluminium premium widening."
    # degrade path does not cache — a later LLM-enabled view can still condense it
    db.flush()
    assert db.execute(
        text("SELECT market_advisory FROM scm.reorder_recommendation WHERE id = :id"),
        {"id": rec_id},
    ).scalar() is None


# ===========================================================================
# 5. topic CRUD (service + endpoints)
# ===========================================================================

def test_topic_crud_service_roundtrip(scm_app):
    _, db, _, _ = scm_app
    created = svc.create_topic(db, MarketResearchTopicWrite(
        label="Copper", category_ref="SRT-FC", currency="MYR",
        search_prompt="copper price trend", cadence="weekly", is_active=True))
    assert created["label"] == "Copper" and created["cadence"] == "weekly"
    assert created["is_active"] is True and "id" in created

    listed = svc.list_topics(db)
    assert any(t["id"] == created["id"] for t in listed)

    updated = svc.update_topic(db, created["id"], MarketResearchTopicWrite(
        label="Copper (LME)", category_ref="SRT-FC", currency="USD",
        search_prompt="copper price trend", cadence="daily", is_active=False))
    assert updated["label"] == "Copper (LME)"
    assert updated["currency"] == "USD" and updated["is_active"] is False

    svc.delete_topic(db, created["id"])
    assert not any(t["id"] == created["id"] for t in svc.list_topics(db))


def test_topic_endpoints_create_list_update_delete(scm_app):
    app, db = _client(scm_app, "purchasing")
    db.commit()
    with TestClient(app) as c:
        r = c.post("/api/v1/scm/market-topics", json={
            "label": "Steel", "category_ref": "SRT-FC", "currency": "MYR",
            "search_prompt": "steel rebar price", "cadence": "monthly", "is_active": True})
        assert r.status_code == 201, r.text
        topic = r.json()["topic"]
        assert topic["label"] == "Steel" and topic["cadence"] == "monthly"
        tid = topic["id"]

        lst = c.get("/api/v1/scm/market-topics")
        assert lst.status_code == 200
        assert any(t["id"] == tid for t in lst.json()["data"])

        upd = c.put(f"/api/v1/scm/market-topics/{tid}", json={
            "label": "Steel (rebar)", "search_prompt": "steel", "cadence": "weekly",
            "is_active": False})
        assert upd.status_code == 200, upd.text
        assert upd.json()["topic"]["label"] == "Steel (rebar)"

        dele = c.delete(f"/api/v1/scm/market-topics/{tid}")
        assert dele.status_code == 204
        # gone — a follow-up PUT now 404s
        assert c.put(f"/api/v1/scm/market-topics/{tid}", json={
            "label": "x", "search_prompt": "y"}).status_code == 404


def test_topic_create_missing_label_is_422(scm_app):
    app, db = _client(scm_app, "purchasing")
    db.commit()
    with TestClient(app) as c:
        # missing label → 422 (label is required, min_length=1)
        assert c.post("/api/v1/scm/market-topics",
                      json={"search_prompt": "x"}).status_code == 422
        # empty label → 422 (min_length=1)
        assert c.post("/api/v1/scm/market-topics",
                      json={"label": "", "search_prompt": "x"}).status_code == 422
        # missing search_prompt → 422 (required; the prompt drives the search)
        assert c.post("/api/v1/scm/market-topics",
                      json={"label": "OnlyLabel"}).status_code == 422


def test_topic_update_delete_missing_is_404(scm_app):
    app, db = _client(scm_app, "purchasing")
    db.commit()
    with TestClient(app) as c:
        assert c.put(f"/api/v1/scm/market-topics/{uuid.uuid4()}",
                     json={"label": "x", "search_prompt": "y"}).status_code == 404
        assert c.delete(f"/api/v1/scm/market-topics/{uuid.uuid4()}").status_code == 404


# ===========================================================================
# 6. signals endpoint — topic_label resolved, newest-captured first
# ===========================================================================

def test_signals_endpoint_resolves_label_and_orders_newest_first(scm_app):
    app, db = _client(scm_app, "purchasing")
    label = f"M5-SIG-{uuid.uuid4().hex[:6]}"
    topic = _mk_topic(db, label)
    _mk_signal(db, topic, "older signal", captured_at=datetime.utcnow() - timedelta(days=2))
    _mk_signal(db, topic, "newer signal", captured_at=datetime.utcnow())
    db.commit()

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/market-signals")
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    mine = [s for s in data if s["topic_label"] == label]
    assert len(mine) == 2
    # topic_label resolved to the human label (never a UUID)
    assert all(s["topic_label"] == label for s in mine)
    # newest captured_at first (contract: captured_at desc)
    assert mine[0]["summary"] == "newer signal"
    assert mine[1]["summary"] == "older signal"


def test_run_endpoint_no_key_then_fetch_run(scm_app, monkeypatch):
    """POST /market-research/run with no key → 200 failed run; GET the run reflects it."""
    app, db = _client(scm_app, "purchasing")
    _mk_topic(db, "M5-EP-RUN")
    db.commit()
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: None)

    with TestClient(app) as c:
        run = c.post("/api/v1/scm/market-research/run")
        assert run.status_code == 200, run.text
        body = run.json()["run"]
        assert body["status"] == "failed" and body["error"] == svc.NO_KEY_ERROR
        run_id = body["id"]

        got = c.get(f"/api/v1/scm/market-research/runs/{run_id}")
        assert got.status_code == 200
        assert got.json()["run"]["status"] == "failed"

        assert c.get(f"/api/v1/scm/market-research/runs/{uuid.uuid4()}").status_code == 404


# ===========================================================================
# 7. auth — bare user denied everywhere + wrong-permission denial
# ===========================================================================

def test_all_market_endpoints_deny_bare_user(scm_app):
    app, _ = _client(scm_app, None)  # authenticated but no permissions
    tid = str(uuid.uuid4())
    with TestClient(app) as c:
        assert c.get("/api/v1/scm/market-signals").status_code == 403
        assert c.post("/api/v1/scm/market-research/run").status_code == 403
        assert c.get(f"/api/v1/scm/market-research/runs/{tid}").status_code == 403
        assert c.get("/api/v1/scm/market-topics").status_code == 403
        assert c.post("/api/v1/scm/market-topics",
                      json={"label": "x", "search_prompt": "y"}).status_code == 403
        assert c.put(f"/api/v1/scm/market-topics/{tid}",
                     json={"label": "x", "search_prompt": "y"}).status_code == 403
        assert c.delete(f"/api/v1/scm/market-topics/{tid}").status_code == 403


def test_dashboard_only_user_can_view_but_not_manage_or_run(scm_app):
    """A user with ONLY scm.dashboard.view reads signals/topics but is denied the
    run (scm.reorder.run) and topic-write (scm.policy.manage) surfaces."""
    app, db = _client_with_perms(scm_app, ["scm.dashboard.view"])
    db.commit()
    with TestClient(app) as c:
        assert c.get("/api/v1/scm/market-signals").status_code == 200
        assert c.get("/api/v1/scm/market-topics").status_code == 200
        assert c.post("/api/v1/scm/market-research/run").status_code == 403
        assert c.post("/api/v1/scm/market-topics",
                      json={"label": "x", "search_prompt": "y"}).status_code == 403


# ===========================================================================
# 8. ad-hoc market search fired from planning (M6-B) — soft, advisory-only
# ===========================================================================

def test_search_adhoc_caches_signals_and_completes(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: "fake-key")
    monkeypatch.setattr(
        svc, "_web_search_topic",
        lambda db, topic: [
            {"value": None, "trend": "up", "summary": "Ice blue is trending in 2026.",
             "source_url": "http://example.com/trends"}
        ],
    )
    out = svc.search_adhoc(db, "trending bathroom colours 2026", category_ref="SRT-FC", currency="MYR")

    assert out["run"]["status"] == "completed"
    assert out["run"]["signal_count"] == 1
    assert len(out["signals"]) == 1
    sig = out["signals"][0]
    assert sig["summary"] == "Ice blue is trending in 2026."
    assert sig["trend"] == "up"
    assert sig["category_ref"] == "SRT-FC"

    # ad-hoc topic is created inactive so no scheduled sweep re-runs it (AC-M6.8)
    t = (
        db.query(MarketResearchTopic)
        .filter(MarketResearchTopic.source_system == "adhoc")
        .first()
    )
    assert t and t.is_active is False and t.label == "trending bathroom colours 2026"


def test_search_adhoc_no_key_records_failed_run(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: None)
    out = svc.search_adhoc(db, "anything")
    assert out["run"]["status"] == "failed"
    assert out["run"]["error"] == svc.NO_KEY_ERROR
    assert out["signals"] == []


def test_search_adhoc_reuses_topic_on_repeat(scm_app, monkeypatch):
    _, db, _, _ = scm_app
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: "fake-key")
    monkeypatch.setattr(
        svc, "_web_search_topic",
        lambda db, topic: [{"summary": "s", "trend": None, "value": None, "source_url": None}],
    )
    svc.search_adhoc(db, "green tiles", category_ref=None)
    svc.search_adhoc(db, "green tiles", category_ref=None)
    topics = (
        db.query(MarketResearchTopic)
        .filter(
            MarketResearchTopic.source_system == "adhoc",
            MarketResearchTopic.label == "green tiles",
        )
        .all()
    )
    assert len(topics) == 1, "repeat search must reuse the ad-hoc topic, not duplicate it"


def test_search_adhoc_empty_query_rejected(scm_app):
    from app.services.error_handler import AppException

    _, db, _, _ = scm_app
    with pytest.raises(AppException):
        svc.search_adhoc(db, "   ")


def test_search_adhoc_signal_drives_advisory(scm_app, monkeypatch):
    """A signal cached by an ad-hoc search immediately drives the per-rec advisory on
    a matching rec — no engine re-run (AC-M6.10)."""
    _, db, _, _ = scm_app
    rec = _seed_buy_rec(db)
    category = reorder_engine.load_category_code(db, rec.product_id)
    assert category

    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: "fake-key")
    monkeypatch.setattr(
        svc, "_web_search_topic",
        lambda db, topic: [{"summary": "Resin up.", "trend": "up", "value": None, "source_url": None}],
    )
    svc.search_adhoc(db, "resin price outlook", category_ref=category, currency=rec.currency)

    _install_provider(monkeypatch, "Buy ahead — resin trending up.")
    out = explainer_service.market_advisory(db, rec.id)
    assert out == "Buy ahead — resin trending up."


def test_market_search_endpoint_happy(scm_app, monkeypatch):
    app, db = _client(scm_app, "purchasing")
    db.commit()
    monkeypatch.setattr(svc, "_anthropic_api_key", lambda _db=None: "fake-key")
    monkeypatch.setattr(
        svc, "_web_search_topic",
        lambda db, topic: [{"summary": "Trend up.", "trend": "up", "value": None, "source_url": None}],
    )
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/scm/market-search",
            json={"query": "colour trends 2026", "category_ref": "SRT-FC"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["run"]["status"] == "completed"
        assert len(body["signals"]) == 1


def test_market_search_endpoint_denied_without_run_perm(scm_app):
    app, db = _client_with_perms(scm_app, ["scm.dashboard.view"])
    db.commit()
    with TestClient(app) as c:
        res = c.post("/api/v1/scm/market-search", json={"query": "x"})
    assert res.status_code == 403
