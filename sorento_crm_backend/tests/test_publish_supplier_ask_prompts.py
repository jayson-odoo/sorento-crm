"""The SUPPLIER-ASK republish script fails loudly when the parser version it would have the console pin lacks the
after-year sentence (crew, fix round 4: it printed "no" and the sweep ran on a version without it)."""
import types

import pytest

from scripts import publish_supplier_ask_prompts as script


class _Query:
    def __init__(self, template):
        self.template = template

    def filter(self, *a, **k):
        return self

    def first(self):
        return types.SimpleNamespace(template=self.template)


class _Db:
    def __init__(self, template):
        self.template = template

    def query(self, *a):
        return _Query(self.template)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.mark.parametrize("template,ok", [("rules\nAFTER\n", True), ("rules only", False)])
def test_the_republish_fails_loudly_without_the_sentence(monkeypatch, capsys, template, ok):
    import app.database

    fake = types.SimpleNamespace(publish=lambda db: (5, 195), PARSER="chatbot_semantic_parser", AFTER_YEAR_SENTENCE="AFTER")
    monkeypatch.setattr(script, "_migration", lambda: fake)
    monkeypatch.setattr(app.database, "SessionLocal", lambda: _Db(template))
    if ok:
        script.main()
        assert "Pin parser v195" in capsys.readouterr().out
    else:
        with pytest.raises(SystemExit) as raised:
            script.main()
        assert "FAILED" in str(raised.value)
