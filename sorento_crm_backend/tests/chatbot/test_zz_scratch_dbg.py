import json
from tests.chatbot.test_engine import stub_access  # noqa
from tests.chatbot.test_code_match_retrieval import _console, _facts, stock, product
from app.services.chatbot.lanes.business import code_sizes as CS

def test_dbg(session_factory, monkeypatch, stub_access):
    codes = ["BRC21120UW-2-MY", "ZQX5521"]
    c = _console(session_factory, monkeypatch, stub_access, codes, **_facts(codes))
    real = CS.annotate
    def spy(db, parser, resolved):
        print("RES", json.dumps({k: resolved.get(k) for k in ("match_mode","tokens")}), [(r.get("token"), r.get("resolved"), [(m.get("canonical_code"), m.get("match_tier")) for m in r.get("matches") or []]) for r in resolved.get("resolutions") or []], [(m.get("canonical_code"), m.get("match_tier")) for m in resolved.get("intersection") or []])
        return real(db, parser, resolved)
    monkeypatch.setattr(CS, "annotate", spy)
    print("TXT", repr(c.say("C21120UW-2-MY stock", stock(product("C21120UW-2-MY")))))
