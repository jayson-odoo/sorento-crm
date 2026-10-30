"""AGENTIC-P2 slice 1: `scripts/chatbot_eval/router_eval.py` (plan "Build contract", eval harness).

No database, no network: a fake client is injected, or `jev_client.choose` is monkeypatched.

Interface assumed (flagged in the report): `router_eval.main(argv, *, choose=None) -> int`; flags
`--gold`, `--out` (a DIRECTORY holding `results.jsonl` and `summary.json`), `--limit`, `--threshold`
(default 0.7), `--max-input-tokens`; result rows carry `id, label, route, score, ms, input_tokens`;
the summary carries `n, agreement, missed_agent_rate, wasted_agent_rate, per_language, p50_ms,
p95_ms, input_tokens`; `per_language[lang]` is `{"n", "agreement"}`. With `choose` None the harness
calls `jev_client.choose` (looked up at call time) with the key from env `JEV_API_KEY`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# (id, text, label, language, P(agent) the fake returns)
ITEMS = [
    ("g1", "compare Q3 vs Q4 sales", "agent", "en", 0.90),
    ("g2", "why did Penang drop", "agent", "en", 0.30),
    ("g3", "stock of ABC123", "chat", "en", 0.10),
    ("g4", "any order for Lim", "chat", "en", 0.80),
    ("g5", "banding jualan bulan ini", "agent", "ms", 0.95),
    ("g6", "stok ABC123 ada tak", "chat", "ms", 0.20),
    ("g7", "ABC123 还有货吗", "chat", "zh", 0.90),
    ("g8", "比较两个季度的销售", "agent", "zh", 0.90),
]
KEY = "ZZT-jev-eval-key-4321"


class FakeChoose:
    def __init__(self, tokens: int = 100):
        self.tokens = tokens
        self.calls: list[dict] = []
        self.by_text = {text: p for _, text, _, _, p in ITEMS}

    def __call__(self, *args, **kw):
        key = args[0] if args else kw.get("key")
        self.calls.append(dict(kw, key=key))
        p = next((v for t, v in self.by_text.items() if t in kw["state"]), 0.5)
        return {
            "choice": "agent" if p >= 0.5 else "chat",
            "confidence": max(p, 1 - p),
            "probabilities": {"chat": 1 - p, "agent": p},
            "input_tokens": self.tokens,
            "output_tokens": 3,
        }


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", KEY)


def _gold(tmp_path, items=ITEMS):
    path = tmp_path / "gold.jsonl"
    rows = [
        {"id": i, "text": t, "previous_3": [{"text": f"PREV-{i}", "reply": "r"}], "label": lab, "language": lang}
        for i, t, lab, lang, _ in items
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


def _run(tmp_path, *extra, choose=None, items=ITEMS):
    from scripts.chatbot_eval import router_eval

    out = tmp_path / "out"
    rc = router_eval.main(["--gold", str(_gold(tmp_path, items)), "--out", str(out), *extra], choose=choose)
    return rc, out


def _results(out):
    return [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines() if line]


def _summary(out):
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def test_every_gold_item_gets_a_result_row(tmp_path):
    fake = FakeChoose()
    rc, out = _run(tmp_path, choose=fake)
    assert rc == 0
    rows = _results(out)
    assert [r["id"] for r in rows] == [i for i, *_ in ITEMS]
    assert len(fake.calls) == len(ITEMS)
    first = rows[0]
    assert first["label"] == "agent" and first["route"] == "agent"
    assert first["score"] == pytest.approx(0.9)
    assert first["input_tokens"] == 100
    assert isinstance(first["ms"], (int, float)) and first["ms"] >= 0
    assert [r["route"] for r in rows] == ["agent", "chat", "chat", "agent", "agent", "chat", "agent", "agent"]


def test_the_request_carries_the_text_and_the_previous_exchanges(tmp_path):
    fake = FakeChoose()
    _run(tmp_path, choose=fake, items=ITEMS[:1])
    call = fake.calls[0]
    assert "compare Q3 vs Q4 sales" in call["state"]
    assert "PREV-g1" in call["state"]
    assert set(call["criteria"]) == {"chat", "agent"}
    assert call["key"] == KEY


def test_the_summary_measures_agreement_and_both_error_rates(tmp_path):
    _, out = _run(tmp_path, choose=FakeChoose())
    s = _summary(out)
    assert s["n"] == 8
    assert s["agreement"] == pytest.approx(5 / 8)
    assert s["missed_agent_rate"] == pytest.approx(1 / 4)  # g2: labelled agent, routed chat
    assert s["wasted_agent_rate"] == pytest.approx(2 / 4)  # g4, g7: labelled chat, routed agent
    assert s["input_tokens"] == 800


def test_the_summary_is_broken_down_per_language(tmp_path):
    _, out = _run(tmp_path, choose=FakeChoose())
    per = _summary(out)["per_language"]
    assert set(per) == {"en", "ms", "zh"}
    assert per["en"]["n"] == 4 and per["en"]["agreement"] == pytest.approx(2 / 4)
    assert per["ms"]["n"] == 2 and per["ms"]["agreement"] == pytest.approx(1.0)
    assert per["zh"]["n"] == 2 and per["zh"]["agreement"] == pytest.approx(1 / 2)


def test_the_summary_has_latency_percentiles(tmp_path):
    _, out = _run(tmp_path, choose=FakeChoose())
    s = _summary(out)
    assert isinstance(s["p50_ms"], (int, float)) and isinstance(s["p95_ms"], (int, float))
    assert 0 <= s["p50_ms"] <= s["p95_ms"]


def test_the_threshold_decides_the_route(tmp_path):
    _, out = _run(tmp_path, "--threshold", "0.95", choose=FakeChoose())
    routes = {r["id"]: r["route"] for r in _results(out)}
    assert routes["g5"] == "agent"  # 0.95 is at the threshold
    assert routes["g1"] == "chat" and routes["g8"] == "chat"
    s = _summary(out)
    assert s["wasted_agent_rate"] == pytest.approx(0.0)
    assert s["missed_agent_rate"] == pytest.approx(3 / 4)


def test_limit_caps_the_items_and_the_calls(tmp_path):
    fake = FakeChoose()
    _, out = _run(tmp_path, "--limit", "3", choose=fake)
    assert len(fake.calls) == 3
    assert [r["id"] for r in _results(out)] == ["g1", "g2", "g3"]
    assert _summary(out)["n"] == 3


def test_the_spend_guard_stops_the_run(tmp_path):
    fake = FakeChoose(tokens=100)
    _, out = _run(tmp_path, "--max-input-tokens", "250", choose=fake)
    assert 2 <= len(fake.calls) <= 3  # never anywhere near all 8
    rows = _results(out)
    assert len(rows) == len(fake.calls)
    assert _summary(out)["n"] == len(rows)
    assert _summary(out)["input_tokens"] <= 300


def test_without_the_guard_the_same_run_goes_through(tmp_path):  # positive control for the guard
    fake = FakeChoose(tokens=100)
    _run(tmp_path, "--max-input-tokens", "100000", choose=fake)
    assert len(fake.calls) == 8


def test_without_a_key_and_without_a_fake_it_refuses_and_calls_nothing(tmp_path, monkeypatch):
    from app.services.chatbot import jev_client

    monkeypatch.delenv("JEV_API_KEY", raising=False)
    called = []
    monkeypatch.setattr(jev_client, "choose", lambda *a, **k: called.append(1) or {})
    try:
        rc, out = _run(tmp_path)
    except SystemExit as exc:
        rc, out = exc.code, tmp_path / "out"
    assert rc not in (0, None)
    assert called == []
    assert not (out / "summary.json").exists()


def test_with_a_key_and_no_fake_it_uses_the_jev_client_with_the_env_key(tmp_path, monkeypatch):
    from app.services.chatbot import jev_client

    fake = FakeChoose()
    monkeypatch.setattr(jev_client, "choose", fake)
    rc, out = _run(tmp_path)
    assert rc == 0
    assert len(fake.calls) == 8
    assert {c["key"] for c in fake.calls} == {KEY}


def test_the_key_is_not_written_to_the_output(tmp_path):
    _, out = _run(tmp_path, choose=FakeChoose())
    for path in out.iterdir():
        assert KEY not in path.read_text(encoding="utf-8")
