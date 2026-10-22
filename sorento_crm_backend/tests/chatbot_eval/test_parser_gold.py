"""Red tests for scripts/chatbot_eval/parser_gold.py (CHAT-CODE-LOOKUP R2-1, UAC U7.1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.chatbot_eval import parser_gold as pg  # noqa: E402
from tests.chatbot.conftest import session_factory  # noqa: E402,F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: E402,F401

GOLD = BACKEND / "scripts" / "chatbot_eval" / "gold" / "parser_when_deliver.jsonl"


def _write(tmp_path, lines):
    p = tmp_path / "g.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _row(i="a", m="hello", expect=None):
    return json.dumps({"id": i, "message": m, "expect": expect if expect is not None else {}})


def test_load_gold_reads_rows(tmp_path):
    rows = pg.load_gold(_write(tmp_path, [_row("a"), _row("b", "x", {"status": "outstanding"})]))
    assert [r["id"] for r in rows] == ["a", "b"]
    assert rows[1]["expect"] == {"status": "outstanding"}


@pytest.mark.parametrize(
    "lines",
    [
        [_row("a"), _row("a")],
        [_row("a", "   ")],
        [_row("a", "hi", {"bogus": 1})],
        ["not json"],
    ],
)
def test_load_gold_rejects_bad_input(tmp_path, lines):
    with pytest.raises(ValueError):
        pg.load_gold(_write(tmp_path, lines))


def _v(status=None, domain=None, products=(), customer=False, attrs=()):
    ents = [{"hint": "product", "canonical_code": c} for c in products]
    if customer:
        ents.append({"hint": "customer", "canonical_code": None, "text": "ZZ Demo Trading"})
    return {
        "status": status,
        "domain_hint": domain,
        "entities": ents,
        "requested_attributes": list(attrs),
    }


def test_empty_expect_passes():
    assert pg.grade_parse(_v(), {}) == (True, [])


def test_status_exact():
    assert pg.grade_parse(_v("outstanding"), {"status": "outstanding"})[0] is True
    ok, why = pg.grade_parse(_v("delivered"), {"status": "outstanding"})
    assert ok is False and why


def test_status_null_and_missing_fail_exact():
    assert pg.grade_parse(_v(None), {"status": "outstanding"})[0] is False
    assert pg.grade_parse({"domain_hint": "order"}, {"status": "outstanding"})[0] is False


def test_not_status():
    assert pg.grade_parse(_v("outstanding"), {"not_status": ["outstanding"]})[0] is False
    assert pg.grade_parse(_v("delivered"), {"not_status": ["outstanding"]})[0] is True
    assert pg.grade_parse(_v(None), {"not_status": ["outstanding"]})[0] is True
    assert pg.grade_parse({}, {"not_status": ["outstanding"]})[0] is True


def test_not_status_with_none_forbids_null():
    assert pg.grade_parse(_v(None), {"not_status": [None]})[0] is False
    assert pg.grade_parse({}, {"not_status": [None]})[0] is False
    assert pg.grade_parse(_v("outstanding"), {"not_status": [None]})[0] is True


def test_domain_and_intent_hint():
    assert pg.grade_parse(_v(domain="order"), {"domain_hint": "order"})[0] is True
    assert pg.grade_parse(_v(domain="incoming"), {"domain_hint": "order"})[0] is False
    v = _v()
    v["intent_hint"] = "FILTER"
    assert pg.grade_parse(v, {"intent_hint": "FILTER"})[0] is True
    assert pg.grade_parse(v, {"intent_hint": "LOOKUP"})[0] is False
    assert pg.grade_parse(_v(), {"intent_hint": "FILTER"})[0] is False


def test_product_match_case_and_dash_blind():
    v = _v(products=["SRTKT1636SS-GM"])
    assert pg.grade_parse(v, {"product": "SRTKT1636SS-GM"})[0] is True
    assert pg.grade_parse(v, {"product": "srtkt1636ssgm"})[0] is True
    assert pg.grade_parse(v, {"product": "SRT-KT1636-SS-GM"})[0] is True
    assert pg.grade_parse(v, {"product": "SRTKT1636SS-BK"})[0] is False
    assert pg.grade_parse(_v(), {"product": "SRTKT1636SS-GM"})[0] is False


def test_product_only_counts_product_entities():
    v = {"entities": [{"hint": "customer", "canonical_code": "SRTWB8001"}]}
    assert pg.grade_parse(v, {"product": "SRTWB8001"})[0] is False


def test_product_any_of_several_entities():
    v = _v(products=["SRTWB8001", "SRTWB8002"])
    assert pg.grade_parse(v, {"product": "SRTWB8002"})[0] is True


def test_no_attribute():
    assert pg.grade_parse(_v(attrs=["delivery"]), {"no_attribute": "delivery"})[0] is False
    assert pg.grade_parse(_v(attrs=["price"]), {"no_attribute": "delivery"})[0] is True
    assert pg.grade_parse(_v(), {"no_attribute": "delivery"})[0] is True
    assert pg.grade_parse({}, {"no_attribute": "delivery"})[0] is True


def test_customer_present_absent():
    assert pg.grade_parse(_v(customer=True), {"customer": True})[0] is True
    assert pg.grade_parse(_v(), {"customer": True})[0] is False
    assert pg.grade_parse(_v(), {"customer": False})[0] is True
    assert pg.grade_parse(_v(customer=True), {"customer": False})[0] is False


def test_all_reasons_reported():
    ok, why = pg.grade_parse(_v("x", "inventory"), {"status": "outstanding", "domain_hint": "order"})
    assert ok is False and len(why) == 2


def test_load_gold_accepts_canonical_and_attributes_only(tmp_path):
    rows = pg.load_gold(_write(tmp_path, [_row("a", "x", {"canonical": None, "attributes_only": []})]))
    assert rows[0]["expect"] == {"canonical": None, "attributes_only": []}


def test_canonical_code_case_and_dash_blind():
    v = _v(products=["SRTWT8259-GM"])
    assert pg.grade_parse(v, {"canonical": "SRTWT8259-GM"})[0] is True
    assert pg.grade_parse(v, {"canonical": "srtwt8259gm"})[0] is True
    assert pg.grade_parse(v, {"canonical": "SRTWT8259-GY"})[0] is False
    assert pg.grade_parse(_v(), {"canonical": "SRTWT8259-GM"})[0] is False


def test_canonical_code_must_be_the_product_entitys_not_a_customers():
    v = {"entities": [{"hint": "customer", "canonical_code": "SRTWT8259-GM"}]}
    assert pg.grade_parse(v, {"canonical": "SRTWT8259-GM"})[0] is False


def test_canonical_null_needs_every_product_entity_null():
    assert pg.grade_parse(_v(products=[None]), {"canonical": None})[0] is True
    assert pg.grade_parse(_v(), {"canonical": None})[0] is True
    ok, why = pg.grade_parse(_v(products=[None, "SRTWT8259-GM"]), {"canonical": None})
    assert ok is False and why
    assert pg.grade_parse(_v(products=["SRTWT8259-GM"]), {"canonical": None})[0] is False
    assert pg.grade_parse(_v(products=[""]), {"canonical": None})[0] is True


def test_canonical_null_ignores_non_product_entities():
    v = {"entities": [{"hint": "customer", "canonical_code": "ZZ Demo Trading"}]}
    assert pg.grade_parse(v, {"canonical": None})[0] is True


def test_attributes_only_subset():
    assert pg.grade_parse(_v(attrs=["price"]), {"attributes_only": ["price", "stock"]})[0] is True
    assert pg.grade_parse(_v(attrs=["price", "stock"]), {"attributes_only": ["price", "stock"]})[0] is True
    assert pg.grade_parse(_v(attrs=["Price"]), {"attributes_only": ["price"]})[0] is True
    ok, why = pg.grade_parse(_v(attrs=["price", "discontinued"]), {"attributes_only": ["price"]})
    assert ok is False and why


def test_attributes_only_empty_list_means_no_attribute_at_all():
    assert pg.grade_parse(_v(attrs=["discontinued"]), {"attributes_only": []})[0] is False
    assert pg.grade_parse(_v(), {"attributes_only": []})[0] is True
    assert pg.grade_parse({}, {"attributes_only": []})[0] is True


CODE_PICKS = BACKEND / "scripts" / "chatbot_eval" / "gold" / "parser_code_picks.jsonl"


def test_code_picks_gold_file():
    rows = pg.load_gold(CODE_PICKS)
    ids = [r["id"] for r in rows]
    assert len(rows) >= 16
    assert len(ids) == len(set(ids))
    for prefix in ("cp-typo-", "cp-tie-", "cp-part-", "cp-set-", "cp-amb-", "cp-trans-"):
        assert any(i.startswith(prefix) for i in ids), prefix
    assert sum(i.startswith("cp-typo-") for i in ids) >= 5
    assert sum(i.startswith("cp-tie-") for i in ids) >= 4
    assert sum(i.startswith("cp-part-") for i in ids) >= 3
    assert sum(i.startswith("cp-set-") for i in ids) >= 2
    for r in rows:
        assert "canonical" in r["expect"] and "attributes_only" in r["expect"], r["id"]
        if r["id"].startswith(("cp-tie-", "cp-part-", "cp-amb-")):
            assert r["expect"]["canonical"] is None, r["id"]
        else:
            assert r["expect"]["canonical"], r["id"]


def test_committed_gold_file():
    rows = pg.load_gold(GOLD)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    pos = [r for r in rows if r["expect"].get("status") == "outstanding"]
    neg = [r for r in rows if r["expect"].get("status") != "outstanding"]
    assert len(pos) >= 12
    assert len(neg) >= 6
    for r in pos:
        assert r["expect"].get("status") == "outstanding", r["id"]
        assert r["expect"].get("domain_hint") == "order", r["id"]
        assert r["expect"].get("product"), r["id"]
    for r in rows:
        assert "SRTKT73SS-BL when deliver" not in r["message"]


_BASE = ["live", "--gold", str(GOLD), "--out", "o.jsonl", "--max-usd", "1",
         "--require-key-last4", "abcd", "--prompt-version-id", "1", "--repeats", "1"]


def _without(flag):
    out, skip = [], False
    for a in _BASE:
        if skip:
            skip = False
            continue
        if a == flag:
            skip = True
            continue
        out.append(a)
    return out


@pytest.mark.parametrize("flag", ["--max-usd", "--require-key-last4", "--prompt-version-id"])
def test_live_refusal_prints_refused(flag, capsys):
    rc = pg.main(_without(flag))
    cap = capsys.readouterr()
    assert rc == 2
    assert "refused" in (cap.out + cap.err)


@pytest.mark.parametrize("n", ["0", "-1"])
def test_live_repeats_must_be_positive(n, capsys):
    argv = list(_BASE)
    argv[argv.index("--repeats") + 1] = n
    rc = pg.main(argv)
    assert rc != 0


def test_summarise():
    rows = [
        {"id": "a", "repeat": 0, "passed": True, "reasons": [], "usd": 0.01},
        {"id": "a", "repeat": 1, "passed": False, "reasons": ["status"], "usd": 0.01},
        {"id": "a", "repeat": 2, "passed": True, "reasons": [], "usd": 0.01},
        {"id": "b", "repeat": 0, "passed": False, "reasons": ["x"], "usd": 0.0},
    ]
    s = pg.summarise(rows)
    assert s["a"] == {"n": 3, "passed": 2}
    assert s["b"] == {"n": 1, "passed": 0}
    assert pg.summarise([]) == {}


def test_run_live_smoke_two_rows_by_repeats(session_factory, monkeypatch):
    """run_live must reach the parser module (app.services.chatbot.head.parser), grade each emission and report."""
    from app.services import llm_provider
    from app.services.chatbot.head import parser as parser_mod

    class _Keyed:
        api_key = "sk-synthetic-not-a-real-key-WXYZ"

    def fake_chat(self, messages, **kw):
        return llm_provider.ChatResult(content="{}", prompt_tokens=1000, completion_tokens=100, total_tokens=1100,
                                       cached_tokens=800)

    verdict = {"status": "ok", "domain_hint": "product", "intent_hint": "lookup", "requested_attributes": [],
               "entities": [{"type": "product", "value": "ABC-1"}]}

    def fake_parse(config, user_block):
        llm_provider.OpenAIProvider.chat(_Keyed(), [{"role": "user", "content": "x"}], model="gpt-5.4-mini")
        return dict(verdict)

    config = parser_mod.ParserConfig(system_prompt="x", prompt_version=1, provider="openai", model="gpt-5.4-mini",
                                     api_key="k")
    monkeypatch.setattr(llm_provider.OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, **kw: config)

    rows = [
        {"id": "pass-row", "message": "abc-1 price", "expect": {"status": "ok"}},
        {"id": "fail-row", "message": "abc-1 stock", "expect": {"status": "needs_clarification"}},
    ]
    seen: list[dict] = []
    out = pg.run_live(rows, session_factory=session_factory, version_id="1", repeats=2, max_usd=5.0,
                      require_key_last4="WXYZ", on_row=seen.append)

    assert len(out) == 4
    assert [(r["id"], r["repeat"]) for r in out] == [("pass-row", 0), ("pass-row", 1), ("fail-row", 0), ("fail-row", 1)]
    for r in out:
        for key in ("id", "repeat", "passed", "reasons", "usd", "status", "domain_hint", "intent_hint",
                    "requested_attributes", "entities"):
            assert key in r
        assert r["status"] == "ok" and r["usd"] > 0
    assert all(r["passed"] for r in out[:2]) and all(r["reasons"] == [] for r in out[:2])
    for r, case in zip(out, [rows[0], rows[0], rows[1], rows[1]]):
        assert (r["passed"], r["reasons"]) == pg.grade_parse(verdict, case["expect"])
    assert not any(r["passed"] for r in out[2:])
    assert seen == out


OTHER_COMPANY = "00000000-0000-0000-0000-000000000002"


def test_run_live_registers_the_scope_listener_and_scopes_the_candidate_block(session_factory, monkeypatch):
    """The runner scopes its session to the default company, so it must install the scope filter itself:
    in a fresh process nothing else does, and the candidate block then lists other companies' codes."""
    import uuid

    from app.models.company import Company
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services import company_scope, llm_provider
    from app.services.chatbot.head import parser as parser_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._pg_fixture import unique_code

    db = session_factory()
    for cid, label in ((DEFAULT_COMPANY_ID, "DEF"), (OTHER_COMPANY, "OTH")):
        if db.get(Company, cid) is None:
            db.add(Company(id=cid, name=f"ZZT {label}", code=unique_code(label)[:20]))
    db.flush()
    held = {}
    for cid, code in ((DEFAULT_COMPANY_ID, "ZZQPL7-MINE"), (OTHER_COMPANY, "ZZQPL7-THEIRS")):
        cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat",
                              company_id=cid)
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=cid)
        db.add_all([cat, uom])
        db.flush()
        db.add(Product(id=str(uuid.uuid4()), product_code=code, product_name=f"Name of {code}", category_id=cat.id,
                       base_uom_id=uom.id, list_price=1, company_id=cid, is_searchable=True))
        held[cid] = code
    db.commit()

    class _Keyed:
        api_key = "sk-synthetic-not-a-real-key-WXYZ"

    events: list[str] = []
    blocks: list[str] = []
    real_register = company_scope.register_company_scope_listeners

    def spy_register():
        events.append("register")
        return real_register()

    def fake_chat(self, messages, **kw):
        return llm_provider.ChatResult(content="{}", prompt_tokens=10, completion_tokens=1, total_tokens=11,
                                       cached_tokens=0)

    def fake_parse(config, user_block):
        events.append("parse")
        blocks.append(user_block)
        llm_provider.OpenAIProvider.chat(_Keyed(), [{"role": "user", "content": "x"}], model="gpt-5.4-mini")
        return {"status": "ok", "domain_hint": "product", "entities": [], "requested_attributes": []}

    config = parser_mod.ParserConfig(system_prompt="x", prompt_version=1, provider="openai", model="gpt-5.4-mini",
                                     api_key="k", closed_lists=True, code_lookup=True)
    monkeypatch.setattr(company_scope, "register_company_scope_listeners", spy_register)
    monkeypatch.setattr(llm_provider.OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, **kw: config)

    out = pg.run_live([{"id": "scope", "message": "zzqpl7 price", "expect": {}}], session_factory=session_factory,
                      version_id="1", repeats=1, max_usd=5.0, require_key_last4="WXYZ")

    assert out and out[0]["reasons"] == [], out
    # The red assertion: the runner itself installs the listener, before it builds the user turn.
    assert "register" in events, "run_live never calls register_company_scope_listeners"
    assert events.index("register") < events.index("parse")
    # End to end (can only fail in a process where nothing registered the listener yet).
    assert blocks and held[DEFAULT_COMPANY_ID] in blocks[0]
    assert held[OTHER_COMPANY] not in blocks[0]


# ---- review round 2: a pin must resolve to an UNLABELLED parser version before any spend
# (parser_gold.py _parse_one/resolve_config falls back silently to the in-code prompt for an unknown
# id, ai_prompt_registry.py:1495; replay.py:775/809 `_pin_resolves` is the guard to mirror)


def _seed_version(session_factory, number: int, *, label: str | None = None) -> str:
    import uuid

    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from scripts.chatbot_eval import replay

    db = session_factory()
    vid = str(uuid.uuid4())
    db.add(AIPromptVersion(id=vid, name=replay.PARSER_PROMPT_KEY, version=number, template="x"))
    db.flush()
    if label:
        db.add(AIPromptLabel(id=str(uuid.uuid4()), name=replay.PARSER_PROMPT_KEY, label=label, version_id=vid))
    db.commit()
    return vid


def _stub_provider(monkeypatch, session_factory, tmp_path, version_number: int = 7):
    """Count every LLM call and every parser.parse; point the CLI at the blank-schema factory."""
    import app.database
    from app.services import llm_provider
    from app.services.chatbot.head import parser as parser_mod

    calls: list[str] = []

    class _Keyed:
        api_key = "sk-synthetic-not-a-real-key-WXYZ"

    def fake_chat(self, messages, **kw):
        calls.append("chat")
        return llm_provider.ChatResult(content="{}", prompt_tokens=10, completion_tokens=1, total_tokens=11, cached_tokens=0)

    def fake_parse(config, user_block):
        calls.append("parse")
        llm_provider.OpenAIProvider.chat(_Keyed(), [{"role": "user", "content": "x"}], model="gpt-5.4-mini")
        return {"status": "ok", "entities": [], "requested_attributes": []}

    config = parser_mod.ParserConfig(system_prompt="x", prompt_version=version_number, provider="openai",
                                     model="gpt-5.4-mini", api_key="k")
    monkeypatch.setattr(llm_provider.OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, **kw: config)
    monkeypatch.setattr(app.database, "SessionLocal", session_factory)
    monkeypatch.chdir(BACKEND)
    gold = tmp_path / "g.jsonl"
    gold.write_text(json.dumps({"id": "r1", "message": "abc1 price", "expect": {}}) + "\n", encoding="utf-8")
    return calls, gold, tmp_path / "out.jsonl"


def _live_argv(gold, out, version_id: str) -> list[str]:
    return ["live", "--gold", str(gold), "--out", str(out), "--max-usd", "5", "--require-key-last4", "WXYZ",
            "--prompt-version-id", version_id, "--repeats", "1"]


def test_live_refuses_a_pin_that_is_not_a_parser_version_before_any_llm_call(session_factory, monkeypatch, tmp_path, capsys):
    import uuid

    calls, gold, out = _stub_provider(monkeypatch, session_factory, tmp_path)

    rc = pg.main(_live_argv(gold, out, str(uuid.uuid4())))

    assert rc != 0
    assert calls == [], calls
    assert "refused" in capsys.readouterr().err


def test_live_refuses_a_pin_to_a_labelled_version_before_any_llm_call(session_factory, monkeypatch, tmp_path, capsys):
    vid = _seed_version(session_factory, 7, label="production")
    calls, gold, out = _stub_provider(monkeypatch, session_factory, tmp_path)

    rc = pg.main(_live_argv(gold, out, vid))

    assert rc != 0
    assert calls == [], calls
    assert "refused" in capsys.readouterr().err


def test_run_live_rows_carry_the_resolved_prompt_version_number(session_factory, monkeypatch, tmp_path):
    vid = _seed_version(session_factory, 7)
    calls, _gold, _out = _stub_provider(monkeypatch, session_factory, tmp_path, version_number=7)

    out = pg.run_live([{"id": "r1", "message": "abc1 price", "expect": {}}], session_factory=session_factory,
                      version_id=vid, repeats=2, max_usd=5.0, require_key_last4="WXYZ")

    assert len(out) == 2 and calls
    assert [r.get("prompt_version") for r in out] == [7, 7], out


# --- PARSER-TEMPLATE F1-B: context rows and the conflict-pair gold -------------------------------

CONFLICT_PAIRS = BACKEND / "scripts" / "chatbot_eval" / "gold" / "parser_conflict_pairs.jsonl"
CTX = {"previous_reply": "ZZA000: 40 pcs in stock.", "subject": "domain inventory (answered); product ZZA000",
       "open_question": None}


def test_load_gold_keeps_a_context_and_rows_without_one_stay_as_before(tmp_path):
    with_ctx = json.dumps({"id": "c", "message": "ZZA100 x 5", "expect": {}, "context": CTX})
    rows = pg.load_gold(_write(tmp_path, [_row("a"), with_ctx]))
    assert "context" not in rows[0]
    assert rows[1]["context"] == CTX


@pytest.mark.parametrize("bad", ["text", ["x"], {"previous_reply": "a", "bogus": 1}, {"previous_reply": 5}])
def test_load_gold_rejects_a_malformed_context(tmp_path, bad):
    line = json.dumps({"id": "c", "message": "hi", "expect": {}, "context": bad})
    with pytest.raises(ValueError):
        pg.load_gold(_write(tmp_path, [line]))


def test_grade_attributes_include_and_attachment_types():
    v = {"requested_attributes": ["steel_grade"], "entities": [
        {"hint": "attachment_type", "canonical_code": "certificate", "listed_item": "certificate"},
        {"hint": "attachment_type", "canonical_code": "span", "listed_item": "span"}]}
    assert pg.grade_parse(v, {"attributes_include": ["steel grade"], "attachment_types": ["certificate", "span"]}) == (True, [])
    ok, reasons = pg.grade_parse({"requested_attributes": [], "entities": []},
                                 {"attributes_include": ["weight"], "attachment_types": ["photo"]})
    assert not ok and len(reasons) == 2


@pytest.mark.parametrize(
    "entity",
    [
        {"hint": "attachment_type", "canonical_code": "photo", "listed_item": "photo", "confident": False},
        {"hint": "attachment_type", "canonical_code": "photo", "listed_item": "none of these", "confident": True},
    ],
)
def test_grade_attachment_types_ignores_entities_downstream_drops(entity):
    """S3: head/grounding drops an unconfident entity and a NOT_LISTED one, so they name no type."""
    from app.services.chatbot.head.closed_lists_prompt import NOT_LISTED

    assert entity.get("listed_item") != "none of these" or NOT_LISTED == "none of these"
    ok, reasons = pg.grade_parse({"entities": [entity]}, {"attachment_types": ["photo"]})
    assert not ok and reasons, reasons


def test_conflict_pairs_gold_file():
    rows = pg.load_gold(CONFLICT_PAIRS)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for prefix in ("cp2-c1-", "cp2-wd-", "cp2-c2-", "cp2-c3-", "cp2-c6-"):
        assert sum(i.startswith(prefix) for i in ids) >= 3, prefix
    assert all(i.startswith("cp2-") for i in ids)
    by_id = {r["id"]: r for r in rows}
    assert all("context" in r for r in rows if r["id"].startswith(("cp2-c1-0", "cp2-c6-0")) and r["id"] not in
               ("cp2-c1-10", "cp2-c6-03", "cp2-c6-04"))
    # C1, owner ruling 20 Oct: a stated quantity with no ask word is a stock ask after ANY answer
    # (stock or ETA); a message whose own words name another ask (c1-07 "ETA ...") keeps it.
    assert by_id["cp2-c1-01"]["expect"]["domain_hint"] == "inventory"
    assert by_id["cp2-c1-02"]["expect"]["domain_hint"] == "inventory"
    assert by_id["cp2-c1-07"]["expect"]["domain_hint"] == "incoming"
    for r in rows:
        assert not r["expect"]["product"].upper().startswith("ZZ"), r["id"]  # real catalog codes only
        assert r["expect"]["product"].lower() in r["message"].lower(), r["id"]


def _capture(monkeypatch, session_factory, config):
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.head import parser as parser_mod

    seen = {}
    monkeypatch.setattr(parser_mod, "parse", lambda cfg, block: seen.setdefault("block", block) or {})
    for fn in ("active_brands", "promotion_kind_rows", "product_type_names", "product_detail_values"):
        monkeypatch.setattr(turn_runtime, fn, lambda db: None)
    pg._parse_one("ZZA100 x 5", config, session_factory)
    return seen["block"]


def _config(**kw):
    from app.services.chatbot.head import parser as parser_mod

    return parser_mod.ParserConfig(system_prompt="x", prompt_version=1, provider="openai", model="m", api_key="k", **kw)


def test_parse_one_without_a_context_builds_todays_block_byte_equal(session_factory, monkeypatch):
    from app.services.chatbot.turn import context as context_mod

    block = _capture(monkeypatch, session_factory, _config())
    expected, _ = context_mod.assemble(context_mod.ContextLayers(
        level="off", profile_facts=None, summaries=None, earlier_messages=None, previous_response=None,
        current_subject=None, pending_kind=None, pending_options=None, settings_profile_line=None,
        # The engine's own `Current user message` text (`engine.build_latest_user_message`).
        current_message="ZZA100 x 5\n\n", reply_to=None, media_line=None, brands=None, promotion_kinds=None,
        product_types=None, product_details=None, candidate_lines=None,
    ))
    assert block == expected


def test_parse_one_renders_a_context_through_the_legacy_lines(session_factory, monkeypatch):
    from app.services.chatbot.head import parser as parser_mod

    seen = {}
    monkeypatch.setattr(parser_mod, "parse", lambda cfg, block: seen.setdefault("block", block) or {})
    monkeypatch.setattr(pg, "_parse_one", pg._parse_one)
    from app.services.chatbot import turn_runtime
    for fn in ("active_brands", "promotion_kind_rows", "product_type_names", "product_detail_values"):
        monkeypatch.setattr(turn_runtime, fn, lambda db: None)
    ctx = {**CTX, "open_question": "Do you want the ETA as well?"}
    pg._parse_one("ZZA100 x 5", _config(), session_factory, ctx)
    lines = seen["block"].splitlines()
    assert "Previous response: ZZA000: 40 pcs in stock." in lines
    assert "Current user message: ZZA100 x 5" in lines
    assert "Current subject: domain inventory (answered); product ZZA000" in lines
    assert any(ln.startswith("Open question:") and "Do you want the ETA as well?" in ln for ln in lines)


def test_parse_one_renders_a_context_as_the_state_block_when_the_config_has_one(session_factory, monkeypatch):
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.head import parser as parser_mod

    seen = {}
    monkeypatch.setattr(parser_mod, "parse", lambda cfg, block: seen.setdefault("block", block) or {})
    for fn in ("active_brands", "promotion_kind_rows", "product_type_names", "product_detail_values"):
        monkeypatch.setattr(turn_runtime, fn, lambda db: None)
    pg._parse_one("ZZA100 x 5", _config(state_block=True), session_factory, CTX)
    block = seen["block"]
    lines = block.splitlines()
    assert "Previous response: ZZA000: 40 pcs in stock." in lines
    assert "State:" in lines
    assert "- subject: domain inventory (answered); product ZZA000" in lines
    assert "- open question: none" in lines
    assert not any(ln.startswith("Current subject:") for ln in lines)


def test_run_live_hands_a_rows_context_to_the_parse(session_factory, monkeypatch):
    from app.services import llm_provider
    from app.services.chatbot.head import parser as parser_mod

    got = []
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, **kw: _config())
    monkeypatch.setattr(pg, "_parse_one", lambda message, config, factory, context=None: got.append(context) or {"status": "ok"})
    rows = [{"id": "a", "message": "m", "expect": {}, "context": CTX}, {"id": "b", "message": "m", "expect": {}}]
    pg.run_live(rows, session_factory=session_factory, version_id="1", repeats=1, max_usd=5.0, require_key_last4="WXYZ")
    assert got == [CTX, None]


# --- CLOSED-LISTS-INDEX-MODE eval harness: the engine's own user turn, a forced mode, a warehouse key ----------


@pytest.fixture()
def _fresh_prompt_caches():
    from app.services import ai_prompt_registry
    from app.services import chatbot_prompt_vars as pv

    ai_prompt_registry.bust_cache()
    pv.clear_cache()
    yield
    ai_prompt_registry.bust_cache()
    pv.clear_cache()


def _closed_lists_version(session_factory, monkeypatch) -> str:
    """An UNLABELLED parser version carrying the CLOSED LISTS section (the index mode guards' template),
    with the provider config stubbed so the REAL `resolve_config` runs."""
    import types
    import uuid

    from app.models.ai_prompt import AIPromptVersion
    from app.services import ai_assistant_service, llm_provider
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot import test_closed_lists_index_mode as idx

    db = session_factory()
    vid = str(uuid.uuid4())
    db.add(AIPromptVersion(id=vid, name=parser_mod.PROMPT_KEY, version=41, type="text", template=idx.TEMPLATE,
                           variables=["current_date"]))
    db.commit()
    cfg = types.SimpleNamespace(provider="openai", model="gpt-test")
    service = types.SimpleNamespace(get=lambda: cfg)
    monkeypatch.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: service)
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")
    return vid


def _world(session_factory, warehouse: str = "ZZWQ") -> None:
    import uuid

    from app.models.inventory import Warehouse
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests.chatbot import test_closed_lists_index_mode as idx

    idx._seed_world(session_factory)
    db = session_factory()
    db.add(Warehouse(id=str(uuid.uuid4()), warehouse_code=warehouse, warehouse_name=f"ZZ {warehouse}",
                     company_id=DEFAULT_COMPANY_ID))
    from app.models.product_spec import ProductSpecRegistry

    row = db.query(ProductSpecRegistry).filter(ProductSpecRegistry.spec_key == "finish").first()
    if row is None:
        row = ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="finish", label="Finish", data_type="enum")
        db.add(row)
    row.allowed_values = ["french_gold"]
    row.synonyms = {"french_gold": ["french gold"]}
    row.derivation_rules = [{"builder": {"kind": "code", "code_match": "ends_with", "texts": ["-FRG"], "value": "french_gold"}}]
    db.commit()


def _seen_parses(monkeypatch) -> list[tuple[str, str]]:
    """Stub the provider call: every (system prompt, user block) the parser would be sent."""
    from app.services.chatbot.head import parser as parser_mod

    seen: list[tuple[str, str]] = []

    def parse(config, user_block):
        seen.append((config.system_prompt, str(user_block)))
        return {"status": None, "entities": [], "requested_attributes": []}

    monkeypatch.setattr(parser_mod, "parse", parse)
    return seen


def _gold_run(session_factory, vid, message, mode, **kw):
    return pg.run_live([{"id": "r", "message": message, "expect": {}}], session_factory=session_factory,
                       version_id=vid, repeats=1, max_usd=5.0, require_key_last4="WXYZ", closed_lists_mode=mode, **kw)


def test_index_mode_renders_the_index_block_and_no_full_list(session_factory, monkeypatch, _fresh_prompt_caches):
    from tests.chatbot import test_closed_lists_index_mode as idx

    vid = _closed_lists_version(session_factory, monkeypatch)
    _world(session_factory)
    seen = _seen_parses(monkeypatch)
    out = _gold_run(session_factory, vid, "frg", "index")
    assert out[0]["reasons"] == [] and out[0]["closed_lists_mode"] == "index", out
    system, block = seen[0]
    lines = block.splitlines()
    assert any("french_gold" in ln for ln in lines), block
    assert not any(ln.startswith("Warehouse") for ln in lines), block
    assert idx.SPEC_LINE not in system and idx.PHOTOS_LINE not in system, system
    assert not any(ln.startswith(("Product types:", "Product details:")) for ln in lines), block


def test_block_mode_renders_the_full_lists_even_when_the_db_says_index(session_factory, monkeypatch,
                                                                      _fresh_prompt_caches):
    from tests.chatbot import test_closed_lists_index_mode as idx

    vid = _closed_lists_version(session_factory, monkeypatch)
    _world(session_factory)
    idx._set_mode(session_factory, "index")
    seen = _seen_parses(monkeypatch)
    out = _gold_run(session_factory, vid, "stock at ZZWQ", "block")
    assert out[0]["reasons"] == [] and out[0]["closed_lists_mode"] == "block", out
    system, block = seen[0]
    assert idx.SPEC_LINE in system and idx.PHOTOS_LINE in system, system
    assert not any(ln.startswith("Warehouse") for ln in block.splitlines()), block


def test_without_the_flag_the_db_mode_is_used(session_factory, monkeypatch, _fresh_prompt_caches):
    from tests.chatbot import test_closed_lists_index_mode as idx

    vid = _closed_lists_version(session_factory, monkeypatch)
    _world(session_factory)
    idx._set_mode(session_factory, "index")
    seen = _seen_parses(monkeypatch)
    out = _gold_run(session_factory, vid, "stock at ZZWQ", None)
    assert out[0]["closed_lists_mode"] == "index", out
    assert idx.SPEC_LINE not in seen[0][0]


@pytest.mark.parametrize("mode", ["index", "block"])
def test_the_user_block_is_the_engines_own_for_a_fresh_turn(mode, session_factory, seeded, stub_access, monkeypatch,
                                                           _fresh_prompt_caches):
    """Byte-equal to the user block the engine sends the parser for the same message on a fresh turn."""
    from app.models.ai_prompt import AIPromptVersion
    from app.services.chatbot.head import parser as parser_mod
    from tests.chatbot import test_closed_lists_index_mode as idx

    _world(session_factory)
    idx._set_mode(session_factory, mode)
    [(engine_system, engine_block, _result)] = idx._turns(
        session_factory, stub_access, monkeypatch, [("stock at ZZWQ", idx._quiet())])
    vid = session_factory().query(AIPromptVersion.id).filter(AIPromptVersion.name == parser_mod.PROMPT_KEY).scalar()
    seen = _seen_parses(monkeypatch)
    _gold_run(session_factory, vid, "stock at ZZWQ", mode)
    assert seen[0] == (engine_system, engine_block)


def test_the_forced_mode_never_writes_system_settings_and_is_undone(session_factory, monkeypatch, _fresh_prompt_caches):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.models.user import SystemSetting
    from app.services.chatbot.head import closed_lists_index
    from tests.chatbot import test_closed_lists_index_mode as idx

    vid = _closed_lists_version(session_factory, monkeypatch)
    _world(session_factory)
    idx._set_mode(session_factory, "block")
    real_read_mode = closed_lists_index.read_mode
    _seen_parses(monkeypatch)
    written: list[str] = []

    def spy(session, _ctx, _instances):
        written.extend(type(o).__name__ for o in [*session.new, *session.dirty] if isinstance(o, SystemSetting))

    event.listen(Session, "before_flush", spy)
    try:
        out = _gold_run(session_factory, vid, "stock at ZZWQ", "index")
    finally:
        event.remove(Session, "before_flush", spy)
    assert out[0]["closed_lists_mode"] == "index", out
    assert written == [], written
    assert closed_lists_index.read_mode is real_read_mode
    assert closed_lists_index.read_mode(session_factory()) == "block"


def test_an_unknown_forced_mode_is_refused():
    with pytest.raises(ValueError):
        pg.run_live([], session_factory=None, version_id="1", repeats=1, max_usd=1.0, require_key_last4="WXYZ",
                    closed_lists_mode="lists")


def test_cli_flag_reaches_the_run_and_the_header_names_the_mode(session_factory, monkeypatch, tmp_path, capsys,
                                                               _fresh_prompt_caches):
    import app.database

    vid = _closed_lists_version(session_factory, monkeypatch)
    _world(session_factory)
    _seen_parses(monkeypatch)
    monkeypatch.setattr(app.database, "SessionLocal", session_factory)
    monkeypatch.chdir(BACKEND)
    gold = tmp_path / "g.jsonl"
    gold.write_text(json.dumps({"id": "r1", "message": "stock at ZZWQ", "expect": {}}) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    rc = pg.main([*_live_argv(gold, out, vid), "--closed-lists-mode", "index"])
    printed = capsys.readouterr().out
    assert rc == 0, printed
    assert "closed_lists_mode index" in printed.splitlines()[0], printed
    rows = [json.loads(ln) for ln in out.read_text().splitlines()]
    assert [r["closed_lists_mode"] for r in rows] == ["index"], rows


def test_cli_refuses_an_unknown_mode(tmp_path):
    with pytest.raises(SystemExit):
        pg.main([*_BASE, "--closed-lists-mode", "lists"])


def _wh(*raws):
    return {"entities": [{"hint": "warehouse", "raw": r, "canonical_code": None} for r in raws]}


@pytest.mark.parametrize(
    ("verdict", "expected", "ok"),
    [
        (_wh("BRW"), ["brw"], True),
        (_wh("BRW-IB"), ["brwib"], True),
        (_wh("ib", "Brw"), ["BRW", "IB"], True),
        (_wh(), [], True),
        ({"entities": [{"hint": "product", "raw": "BRW"}]}, [], True),
        (_wh("frg"), [], False),
        (_wh(), ["BRW"], False),
        (_wh("BRW"), ["BRW", "IB"], False),
        (_wh("BRW", "IB"), ["BRW"], False),
    ],
)
def test_grade_warehouse_is_the_folded_raw_set(verdict, expected, ok):
    passed, reasons = pg.grade_parse(verdict, {"warehouse": expected})
    assert passed is ok, reasons
    assert bool(reasons) is (not ok)


def test_load_gold_accepts_a_warehouse_list_and_refuses_anything_else(tmp_path):
    rows = pg.load_gold(_write(tmp_path, [_row("a", "stock at BRW", {"warehouse": ["BRW"]})]))
    assert rows[0]["expect"] == {"warehouse": ["BRW"]}
    for bad in ("BRW", [1], None):
        with pytest.raises(ValueError):
            pg.load_gold(_write(tmp_path, [_row("a", "stock at BRW", {"warehouse": bad})]))


def test_run_live_rows_record_the_warehouse_raws(session_factory, monkeypatch):
    from app.services.chatbot.head import parser as parser_mod

    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, **kw: _config())
    verdict = {"entities": [{"hint": "warehouse", "raw": "BRW"}, {"hint": "product", "raw": "ZZA1"}]}
    monkeypatch.setattr(pg, "_parse_one", lambda message, config, factory, context=None: dict(verdict))
    out = pg.run_live([{"id": "a", "message": "m", "expect": {"warehouse": ["brw"]}}], session_factory=session_factory,
                      version_id="1", repeats=1, max_usd=5.0, require_key_last4="WXYZ")
    assert out[0]["passed"] is True and out[0]["warehouse"] == ["BRW"], out
    assert out[0]["closed_lists_mode"] == "off", out


# --- LEAN-INDEX M2: each row records what the parse cost (tokens) and how long the parser call took ----------

USAGE_KEYS = ("prompt_tokens", "cached_tokens", "completion_tokens")


def _usage_run(session_factory, monkeypatch, parse):
    from app.services.chatbot.head import parser as parser_mod

    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, **kw: _config())
    monkeypatch.setattr(parser_mod, "parse", parse)
    return pg.run_live([{"id": "u", "message": "ZZA100 price", "expect": {}}], session_factory=session_factory,
                       version_id="1", repeats=1, max_usd=5.0, require_key_last4="WXYZ")


def test_rows_record_the_parse_tokens_the_provider_reported(session_factory, monkeypatch):
    from app.services.chatbot.head import parser as parser_mod

    usage = {"provider": "openai", "model": "m", "prompt_tokens": 18318, "cached_tokens": 17920,
             "completion_tokens": 214, "total_tokens": 18532}
    out = _usage_run(session_factory, monkeypatch,
                     lambda config, block: parser_mod.ParsedOutput({"status": None, "entities": []}, usage))
    assert out[0]["reasons"] == [], out
    assert {k: out[0].get(k) for k in USAGE_KEYS} == {"prompt_tokens": 18318, "cached_tokens": 17920,
                                                       "completion_tokens": 214}, out


def test_rows_record_the_parser_call_ms(session_factory, monkeypatch):
    import time

    def slow(config, block):
        time.sleep(0.05)
        return {"status": None, "entities": []}

    out = _usage_run(session_factory, monkeypatch, slow)
    ms = out[0].get("parser_ms")
    assert isinstance(ms, int) and 50 <= ms < 5000, out


def test_a_parse_that_reports_no_usage_records_none_not_zero(session_factory, monkeypatch):
    out = _usage_run(session_factory, monkeypatch, lambda config, block: {"status": None, "entities": []})
    assert all(k in out[0] and out[0][k] is None for k in USAGE_KEYS), out
    assert isinstance(out[0].get("parser_ms"), int), out


# ---- LEAN v90: expect keys promotion_kind / is_active / continues + the typo battery (red) ----

TYPO_BATTERY = BACKEND / "scripts" / "chatbot_eval" / "gold" / "parser_typo_battery.jsonl"


def test_load_gold_accepts_the_v90_expect_keys(tmp_path):
    rows = pg.load_gold(_write(tmp_path, [
        _row("a", "x", {"promotion_kind": "a3_flyer"}),
        _row("b", "x", {"promotion_kind": None}),
        _row("c", "x", {"is_active": False}),
        _row("d", "x", {"is_active": None}),
        _row("e", "x", {"continues": True}),
    ]))
    assert [r["id"] for r in rows] == ["a", "b", "c", "d", "e"]


@pytest.mark.parametrize("good, bad", [
    ({"is_active": False}, {"is_active": "false"}),
    ({"continues": True}, {"continues": None}),
    ({"continues": False}, {"continues": "yes"}),
    ({"promotion_kind": "special"}, {"promotion_kind": 3}),
])
def test_load_gold_rejects_malformed_v90_values(tmp_path, good, bad):
    # the well-typed sibling must load first, so a bare unknown-key refusal cannot pass this test
    assert pg.load_gold(_write(tmp_path, [_row("a", "x", good)]))[0]["expect"] == good
    with pytest.raises(ValueError):
        pg.load_gold(_write(tmp_path, [_row("a", "x", bad)]))


def test_promotion_kind_is_folded_equality():
    ok, _ = pg.grade_parse({"promotion_kind": "a3_flyer"}, {"promotion_kind": "A3 Flyer"})
    assert ok
    ok, reasons = pg.grade_parse({"promotion_kind": "special"}, {"promotion_kind": "a3_flyer"})
    assert not ok and any("promotion_kind" in r for r in reasons), reasons
    ok, reasons = pg.grade_parse({"promotion_kind": None}, {"promotion_kind": "a3_flyer"})
    assert not ok and any("promotion_kind" in r for r in reasons), reasons
    ok, _ = pg.grade_parse({}, {"promotion_kind": None})
    assert ok
    ok, reasons = pg.grade_parse({"promotion_kind": "pp"}, {"promotion_kind": None})
    assert not ok and any("promotion_kind" in r for r in reasons), reasons


def test_is_active_is_exact_on_true_false_null():
    for value in (True, False, None):
        ok, reasons = pg.grade_parse({"is_active": value}, {"is_active": value})
        assert ok, reasons
    for got, want in ((True, False), (False, True), (None, True), (None, False), (True, None), (False, None)):
        ok, reasons = pg.grade_parse({"is_active": got}, {"is_active": want})
        assert not ok and any("is_active" in r for r in reasons), (got, want, reasons)
    ok, reasons = pg.grade_parse({}, {"is_active": None})
    assert ok, reasons


def _more(**over):
    return {"continuation": True, "domain_hint": None, "intent_hint": None, "entities": [], **over}


def test_continues_true_needs_the_continuation_flag():
    ok, reasons = pg.grade_parse(_more(), {"continues": True})
    assert ok, reasons
    ok, reasons = pg.grade_parse(_more(continuation=False), {"continues": True})
    assert not ok and any("continues" in r for r in reasons), reasons
    ok, reasons = pg.grade_parse({"entities": []}, {"continues": True})
    assert not ok and any("continues" in r for r in reasons), reasons


def test_continues_true_fails_on_a_new_file_type_ask():
    entity = {"hint": "attachment_type", "listed_item": "product_photos", "confident": True}
    ok, reasons = pg.grade_parse(_more(entities=[entity]), {"continues": True})
    assert not ok and any("continues" in r for r in reasons), reasons
    ok, reasons = pg.grade_parse(
        _more(domain_hint="product_attachment", intent_hint="check_product_attachment"), {"continues": True})
    assert not ok and any("continues" in r for r in reasons), reasons


def test_continues_false_means_the_verdict_does_not_continue_the_set():
    ok, reasons = pg.grade_parse(_more(continuation=False), {"continues": False})
    assert ok, reasons
    ok, reasons = pg.grade_parse({"entities": []}, {"continues": False})
    assert ok, reasons
    ok, reasons = pg.grade_parse(_more(), {"continues": False})
    assert not ok and any("continues" in r for r in reasons), reasons


def test_typo_battery_file_shape_and_counts():
    rows = pg.load_gold(TYPO_BATTERY)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for cls in ("c1", "c2", "c3", "c4"):
        mine = [i for i in ids if i.startswith(f"tb-{cls}-")]
        controls = [i for i in mine if i.startswith(f"tb-{cls}-ctl-")]
        assert len(mine) - len(controls) >= 8, cls
        assert len(controls) >= 2, cls
    by_id = {r["id"]: r for r in rows}
    for i, r in by_id.items():
        if i.startswith("tb-c1-"):
            assert "promotion_kind" in r["expect"], i
        if i.startswith("tb-c4-"):
            assert "is_active" in r["expect"], i
        if i.startswith("tb-c3-"):
            assert "continues" in r["expect"], i
        if i.startswith("tb-c2-") and "-ctl-" not in i:
            assert r["expect"].get("product") and r["expect"].get("attachment_types"), i
    for i, r in by_id.items():
        if i.startswith("tb-c3-") and "-ctl-" not in i:
            assert r["expect"]["continues"] is True, i
            assert "Showing 10 of" in (r.get("context") or {}).get("previous_reply", ""), i
    assert any(r["expect"].get("is_active") is True for i, r in by_id.items() if i.startswith("tb-c4-") and "-ctl-" not in i)
    assert any(r["expect"].get("is_active") is False for i, r in by_id.items() if i.startswith("tb-c4-ctl-"))


# --- LEAN: --reasoning-effort forces the STORED parser setting in-process (never the DB, never the provider) ------


def _effort_version(session_factory, monkeypatch, provider: str = "openai") -> str:
    """An unlabelled parser version and a stubbed provider config, so the REAL `resolve_config` runs."""
    import types
    import uuid

    from app.models.ai_prompt import AIPromptVersion
    from app.services import ai_assistant_service, llm_provider
    from app.services.chatbot.head import parser as parser_mod

    db = session_factory()
    vid = str(uuid.uuid4())
    db.add(AIPromptVersion(id=vid, name=parser_mod.PROMPT_KEY, version=43, type="text",
                           template="Rules for {{current_date}}.", variables=["current_date"]))
    db.commit()
    service = types.SimpleNamespace(get=lambda: types.SimpleNamespace(provider=provider, model="gpt-test"))
    monkeypatch.setattr(ai_assistant_service, "AIAssistantConfigService", lambda d: service)
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")
    return vid


def _stored_effort(session_factory, value: str | None = None) -> str | None:
    """Set the stored setting (when `value`), and return what the DB holds."""
    from app.models.user import SystemSetting

    db = session_factory()
    row = db.query(SystemSetting).first()
    if value is not None:
        if row is None:
            row = SystemSetting()
            db.add(row)
        row.chatbot_parser_reasoning_effort = value
        db.commit()
    return row.chatbot_parser_reasoning_effort if row is not None else None


def _effort_gold(session_factory, monkeypatch, effort, *, provider="openai", on_start=None):
    from app.services.chatbot.head import parser as parser_mod

    vid = _effort_version(session_factory, monkeypatch, provider)
    seen: list[str] = []

    def parse(config, block):
        seen.append(config.reasoning_effort)
        return {"status": None, "entities": []}

    monkeypatch.setattr(parser_mod, "parse", parse)
    out = pg.run_live([{"id": "e", "message": "ZZA100 price", "expect": {}}], session_factory=session_factory,
                      version_id=vid, repeats=1, max_usd=5.0, require_key_last4="WXYZ", reasoning_effort=effort,
                      on_start=on_start)
    return out, seen


@pytest.mark.parametrize("effort", ["off", "low"])
def test_a_forced_effort_is_the_stored_setting_the_parse_reads(effort, session_factory, monkeypatch,
                                                               _fresh_prompt_caches):
    from app.services.chatbot.head import parser as parser_mod

    real = parser_mod.reasoning_effort_setting
    _stored_effort(session_factory, "low" if effort == "off" else "off")
    headers: list[dict] = []
    out, seen = _effort_gold(session_factory, monkeypatch, effort, on_start=headers.append)
    assert out[0]["reasons"] == [], out
    assert seen == [effort], seen
    assert out[0]["reasoning_effort"] == effort, out
    assert headers and headers[0]["reasoning_effort"] == effort and headers[0]["reasoning_forced"] is True, headers
    assert parser_mod.reasoning_effort_setting is real


def test_without_the_flag_the_stored_setting_is_used_and_rows_say_so(session_factory, monkeypatch,
                                                                     _fresh_prompt_caches):
    _stored_effort(session_factory, "low")
    headers: list[dict] = []
    out, seen = _effort_gold(session_factory, monkeypatch, None, on_start=headers.append)
    assert seen == ["low"], seen
    assert out[0]["reasoning_effort"] == "low", out
    assert headers[0]["reasoning_effort"] == "low" and headers[0]["reasoning_forced"] is False, headers


def test_the_forced_effort_never_writes_system_settings(session_factory, monkeypatch, _fresh_prompt_caches):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.models.user import SystemSetting

    _stored_effort(session_factory, "off")
    written: list[str] = []

    def spy(session, _ctx, _instances):
        written.extend(type(o).__name__ for o in [*session.new, *session.dirty] if isinstance(o, SystemSetting))

    event.listen(Session, "before_flush", spy)
    try:
        out, seen = _effort_gold(session_factory, monkeypatch, "low")
    finally:
        event.remove(Session, "before_flush", spy)
    assert seen == ["low"] and written == [], (seen, written)
    assert _stored_effort(session_factory) == "off"


@pytest.mark.parametrize("bad", ["max", "none", "xhigh", "minimal", "medium", "high"])
def test_an_unknown_effort_is_refused(bad):
    with pytest.raises(ValueError):
        pg.run_live([], session_factory=None, version_id="1", repeats=1, max_usd=1.0, require_key_last4="WXYZ",
                    reasoning_effort=bad)


def test_a_forced_effort_on_a_provider_other_than_openai_is_refused_before_any_parse(session_factory, monkeypatch,
                                                                                     _fresh_prompt_caches):
    with pytest.raises(ValueError):
        _effort_gold(session_factory, monkeypatch, "low", provider="gemini")


@pytest.mark.parametrize("bad", ["max", "none", "medium"])
def test_cli_reasoning_effort_choices(bad):
    with pytest.raises(SystemExit):
        pg.main([*_BASE, "--reasoning-effort", bad])


def test_rows_record_the_reasoning_tokens_the_provider_reported(session_factory, monkeypatch):
    from app.services.chatbot.head import parser as parser_mod

    usage = {"provider": "openai", "model": "m", "prompt_tokens": 100, "cached_tokens": 0,
             "completion_tokens": 40, "total_tokens": 140, "reasoning_tokens": 37}
    out = _usage_run(session_factory, monkeypatch,
                     lambda config, block: parser_mod.ParsedOutput({"status": None, "entities": []}, usage))
    assert out[0]["reasons"] == [], out
    assert out[0].get("reasoning_tokens") == 37, out


def test_a_parse_that_reports_no_reasoning_tokens_records_none(session_factory, monkeypatch):
    out = _usage_run(session_factory, monkeypatch, lambda config, block: {"status": None, "entities": []})
    assert "reasoning_tokens" in out[0] and out[0]["reasoning_tokens"] is None, out
    assert "reasoning_tokens" in pg.USAGE_KEYS


# --- parser gold reads last list, pending task and the answer fields ------------------------------


def _loads(tmp_path, expect):
    return pg.load_gold(_write(tmp_path, [_row("a", "x", expect)]))[0]["expect"]


@pytest.mark.parametrize("good, bad", [
    ({"topic_reset": True}, {"topic_reset": None}),
    ({"answer_mode": "pick"}, {"answer_mode": 3}),
    ({"picked": [2]}, {"picked": "2"}),
    ({"reference_positions": [1]}, {"reference_positions": 1}),
    ({"entity_op": "reuse"}, {"entity_op": True}),
    ({"broaden_axis": None}, {"broaden_axis": 4}),
    ({"state_ops_include": ["pick"]}, {"state_ops_include": "pick"}),
    ({"state_ops_exclude": ["pick"]}, {"state_ops_exclude": "pick"}),
])
def test_load_gold_types_the_answer_and_state_expect_keys(tmp_path, good, bad):
    assert _loads(tmp_path, good) == good
    with pytest.raises(ValueError):
        _loads(tmp_path, bad)


def test_grade_topic_reset():
    assert pg.grade_parse({"topic_reset": True}, {"topic_reset": True})[0]
    assert pg.grade_parse({"topic_reset": None}, {"topic_reset": False})[0]
    assert not pg.grade_parse({"topic_reset": False}, {"topic_reset": True})[0]


def test_grade_answer_mode_and_picked():
    v = {"open_question_answer": {"mode": "pick", "picked": [2]}}
    assert pg.grade_parse(v, {"answer_mode": "pick", "picked": [2]})[0]
    assert not pg.grade_parse(v, {"answer_mode": None})[0]
    assert not pg.grade_parse(v, {"picked": [1]})[0]
    assert pg.grade_parse({}, {"answer_mode": None, "picked": []})[0]


def test_grade_reference_positions():
    assert pg.grade_parse({"reference_positions": [2]}, {"reference_positions": [2]})[0]
    assert not pg.grade_parse({"reference_positions": []}, {"reference_positions": [2]})[0]


@pytest.mark.parametrize("key", ["entity_op", "broaden_axis"])
def test_grade_entity_op_and_broaden_axis(key):
    assert pg.grade_parse({key: "reuse"}, {key: "reuse"})[0]
    assert pg.grade_parse({}, {key: None})[0]
    assert not pg.grade_parse({key: "clear"}, {key: "reuse"})[0]


def test_grade_state_ops_include_and_exclude():
    v = {"state_changes": [{"op": "pick", "position": 2}]}
    assert pg.grade_parse(v, {"state_ops_include": ["pick"], "state_ops_exclude": ["new_subject"]})[0]
    assert not pg.grade_parse(v, {"state_ops_include": ["keep"]})[0]
    assert not pg.grade_parse(v, {"state_ops_exclude": ["pick"]})[0]


def test_grade_state_ops_skip_when_the_verdict_has_no_state_changes():
    assert pg.grade_parse({}, {"state_ops_include": ["pick"], "state_ops_exclude": ["keep"]})[0]


def test_state_block_renders_last_list_and_pending_task():
    ctx = {"last_list": "(inventory, 3): 1 CL8109A; 2 C9109A; 3 CB3109A", "pending_task": "the open question"}
    lines = pg._state_block(ctx).splitlines()
    assert "- last list (inventory, 3): 1 CL8109A; 2 C9109A; 3 CB3109A" in lines
    assert "- pending task: the open question" in lines
    lines = pg._state_block({"last_list": "x", "pending_task": '{"kind": "quantities"}'}).splitlines()
    assert "- last list: x" in lines
    assert '- pending task: {"kind": "quantities"}' in lines
    assert "- last list: none" in pg._state_block({"subject": "s"}).splitlines()
    assert "- pending task: none" in pg._state_block({"subject": "s"}).splitlines()


def test_a_context_of_only_a_last_list_or_pending_task_still_gets_a_state_block(session_factory, monkeypatch):
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.head import parser as parser_mod

    seen = {}
    monkeypatch.setattr(parser_mod, "parse", lambda cfg, block: seen.setdefault("block", block) or {})
    for fn in ("active_brands", "promotion_kind_rows", "product_type_names", "product_detail_values"):
        monkeypatch.setattr(turn_runtime, fn, lambda db: None)
    pg._parse_one("2", _config(state_block=True), session_factory, {"pending_task": "the open question"})
    assert "- pending task: the open question" in seen["block"].splitlines()


def test_open_question_object_is_valid_and_rendered_as_json(tmp_path, session_factory, monkeypatch):
    oq = {"kind": "quantities", "items": [{"position": 1, "code": "CL8109A"}], "owed": [1]}
    line = json.dumps({"id": "c", "message": "2", "expect": {}, "context": {"open_question": oq}})
    assert pg.load_gold(_write(tmp_path, [line]))[0]["context"]["open_question"] == oq
    bad = json.dumps({"id": "c", "message": "2", "expect": {}, "context": {"subject": {"a": 1}}})
    with pytest.raises(ValueError):
        pg.load_gold(_write(tmp_path, [bad]))
    assert "- open question: " + json.dumps(oq, ensure_ascii=False) in pg._state_block({"open_question": oq}).splitlines()

    from app.services.chatbot import turn_runtime
    from app.services.chatbot.head import parser as parser_mod

    seen = {}
    monkeypatch.setattr(parser_mod, "parse", lambda cfg, block: seen.setdefault("block", block) or {})
    for fn in ("active_brands", "promotion_kind_rows", "product_type_names", "product_detail_values"):
        monkeypatch.setattr(turn_runtime, fn, lambda db: None)
    pg._parse_one("2", _config(state_block=False), session_factory, {"open_question": oq})
    assert parser_mod.open_question_line(oq) in seen["block"].splitlines()


def test_a_quoted_message_reaches_the_user_block_and_adds_no_state_block(session_factory, monkeypatch):
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.head import parser as parser_mod

    seen = {}
    monkeypatch.setattr(parser_mod, "parse", lambda cfg, block: seen.setdefault("block", block) or {})
    for fn in ("active_brands", "promotion_kind_rows", "product_type_names", "product_detail_values"):
        monkeypatch.setattr(turn_runtime, fn, lambda db: None)
    quote = "Did you mean: 1. ZZA100 2. ZZA200"
    pg._parse_one("2", _config(state_block=True), session_factory, {"reply_to": quote})
    lines = seen["block"].splitlines()
    assert f"reply to: {quote}" in lines
    assert "State:" not in lines


def test_load_gold_accepts_a_reply_to_and_refuses_a_non_text_one(tmp_path):
    ok = json.dumps({"id": "c", "message": "2", "expect": {}, "context": {"reply_to": "quoted text"}})
    assert pg.load_gold(_write(tmp_path, [ok]))[0]["context"]["reply_to"] == "quoted text"
    bad = json.dumps({"id": "c", "message": "2", "expect": {}, "context": {"reply_to": 5}})
    with pytest.raises(ValueError):
        pg.load_gold(_write(tmp_path, [bad]))


def test_products_only_limits_the_product_entities():
    def v(*codes, hint="product"):
        return {"entities": [{"hint": hint, "canonical_code": c} for c in codes]}

    assert pg.grade_parse(v("zza-100", "ZZA200"), {"products_only": ["ZZA100", "ZZA200", "ZZA300"]})[0]
    assert pg.grade_parse(v(), {"products_only": ["ZZA100"]})[0]
    assert pg.grade_parse(v(), {"products_only": []})[0]
    assert pg.grade_parse(v("ZZA100", hint="customer"), {"products_only": []})[0]
    assert not pg.grade_parse(v("ZZA100", "ZZB900"), {"products_only": ["ZZA100"]})[0]
    assert not pg.grade_parse(v("ZZA100"), {"products_only": []})[0]


def test_load_gold_types_products_only(tmp_path):
    assert _loads(tmp_path, {"products_only": ["ZZA100"]}) == {"products_only": ["ZZA100"]}
    for bad in ("ZZA100", [1], None):
        with pytest.raises(ValueError):
            _loads(tmp_path, {"products_only": bad})


def test_run_live_rows_carry_the_answer_and_state_fields(session_factory, monkeypatch):
    from app.services.chatbot.head import parser as parser_mod

    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, **kw: _config())
    verdict = {
        "topic_reset": True, "entity_op": "clear", "broaden_axis": "all", "reference_positions": [2],
        "open_question_answer": {"mode": "pick", "picked": [2], "items": [{"qty": 2}], "qty_for_all": None},
        "state_changes": [{"op": "pick", "axis": None, "position": 2, "extra": "x"}],
    }
    monkeypatch.setattr(pg, "_parse_one", lambda message, config, factory, context=None: dict(verdict))
    run = lambda: pg.run_live([{"id": "a", "message": "m", "expect": {}}], session_factory=session_factory,  # noqa: E731
                              version_id="1", repeats=1, max_usd=5.0, require_key_last4="WXYZ")
    row = run()[0]
    assert (row["topic_reset"], row["entity_op"], row["broaden_axis"], row["reference_positions"]) == (
        True, "clear", "all", [2])
    assert row["open_question_answer"] == {"mode": "pick", "picked": [2], "items": [{"qty": 2}]}
    assert row["state_changes"] == [{"op": "pick", "axis": None, "position": 2}]
    verdict.pop("state_changes"), verdict.pop("open_question_answer")
    row = run()[0]
    assert row["state_changes"] is None and row["open_question_answer"] is None
