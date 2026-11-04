"""PRICETAG-COMBO-RENDER K9 / AC-E1: `scripts/flyer_combo_read.py` reads flyer pages into a seed.

Written test-FIRST; the script does not exist. It is imported inside each test.

The LLM is a stub passed in as `provider=` (never a network call); it answers one reply per
page, in page order, through `provider.chat(messages, ...)` returning a `ChatResult`.

Decisions where the plan is open (simplest reading):
* Entry point: `main(argv, *, provider=None, out=None) -> int`; `provider=None` means
  `app.services.llm_provider.get_provider(...)` in the real run.
* The model answers per page `{"combos": [<seed entry without id/page/flyer>]}` using the
  `import_product_combos.py` keys (host_code, combo_name, combo_description, free_items,
  components, choice_groups, topups, lp, sp, unsure).
* The script adds `page` (1-based), `flyer` (file name) and a unique `id` to each entry.
* "Bounded": module constants `MAX_PAGES` and `MAX_PDF_BYTES`; over either, the script refuses
  (non-zero, a message on `out`, no output file, no model call).
* A page whose answer is not valid JSON of that shape is named in `out` ("page N"); the other
  pages still come out and the exit code stays 0.
* Codes are kept as read (stripped, upper-cased); an empty or missing code stays empty, a
  missing host code stays missing. Nothing is derived from names.
"""
from __future__ import annotations

import io
import json

import pytest

from app.services.llm_provider import ChatResult


def _script():
    from scripts import flyer_combo_read as script

    return script


class StubProvider:
    name = "stub"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        reply = self.answers.pop(0)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return ChatResult(content=content, prompt_tokens=1, completion_tokens=1, total_tokens=2)


def _pdf(path, pages):
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return path


def _run(tmp_path, provider, *pdfs, extra=()):
    out_file = tmp_path / "seed.json"
    out = io.StringIO()
    code = _script().main(
        ["--flyer", *map(str, pdfs), "--company", "SRT", "--out", str(out_file), *extra],
        provider=provider,
        out=out,
    )
    seed = json.loads(out_file.read_text()) if out_file.exists() else None
    return code, out.getvalue(), seed


S1_ANSWER = {
    "combos": [
        {
            "host_code": " srtks7061 ",
            "combo_name": "Sink with tap",
            "components": [],
            "choice_groups": [
                {
                    "role": "Kitchen tap",
                    "options": [
                        {"code": c, "descr": ""}
                        for c in ("srtkt1862ss", "SRTKT1863SS", "SRTKT1871SS", "SRTKT1880SS", "SRTKT1892SS")
                    ],
                }
            ],
            "topups": [{"code": "SRTKT71SS", "descr": "upgrade", "topup": 150}],
            "lp": 2500,
            "sp": 2000,
            "unsure": "",
        }
    ]
}
S2_ANSWER = {
    "combos": [
        {
            "host_code": "SRTWB1419-BL",
            "combo_name": "Basin set",
            "components": [{"code": "SRTWT7449-BL", "role": ""}],
            "choice_groups": [],
            "topups": [],
            "lp": 700,
            "unsure": "",
        }
    ]
}
S3_ANSWER = {
    "combos": [
        {
            "host_code": "SRTWB1419-BL",
            "combo_name": "Basin with tap",
            "components": [],
            "choice_groups": [
                {"role": "Tap colour", "options": [{"code": "SRTWT7449-BL"}, {"code": "SRTWT7449-RG"}]}
            ],
            "topups": [],
            "unsure": "",
        }
    ]
}
S4_ANSWER = {
    "combos": [
        {
            "host_code": "SRTBF11829",
            "combo_name": "Furniture set",
            "components": [
                {"code": "SRTMCB8083-BL", "role": "Mirror"},
                {"code": "SRTWT6203-GM", "role": "Shower"},
            ],
            "choice_groups": [],
            "topups": [],
            "unsure": "",
        }
    ]
}


def test_s1_page_becomes_a_seed_entry_with_group_upgrade_and_prices(tmp_path):
    pdf = _pdf(tmp_path / "a.pdf", ["SRTKS7061 sink"])
    code, _out, seed = _run(tmp_path, StubProvider(S1_ANSWER), pdf)
    assert code == 0
    (entry,) = seed
    assert entry["host_code"] == "SRTKS7061"
    assert entry["combo_name"] == "Sink with tap"
    assert entry["page"] == 1
    assert entry["flyer"] == "a.pdf"
    assert entry["id"]
    (group,) = entry["choice_groups"]
    assert group["role"] == "Kitchen tap"
    assert [o["code"] for o in group["options"]] == [
        "SRTKT1862SS", "SRTKT1863SS", "SRTKT1871SS", "SRTKT1880SS", "SRTKT1892SS",
    ]
    assert entry["topups"][0]["code"] == "SRTKT71SS" and entry["topups"][0]["topup"] == 150
    assert entry["lp"] == 2500 and entry["sp"] == 2000


def test_each_page_is_its_own_model_call_and_entries_carry_their_page(tmp_path):
    pdf = _pdf(tmp_path / "b.pdf", ["page one", "page two", "page three", "page four"])
    provider = StubProvider(S2_ANSWER, S3_ANSWER, {"combos": []}, S4_ANSWER)
    code, _out, seed = _run(tmp_path, provider, pdf)
    assert code == 0
    assert len(provider.calls) == 4
    assert [(e["combo_name"], e["page"]) for e in seed] == [
        ("Basin set", 1), ("Basin with tap", 2), ("Furniture set", 4),
    ]
    assert len({e["id"] for e in seed}) == 3, "ids are unique"
    s2, s3, s4 = seed
    assert [c["code"] for c in s2["components"]] == ["SRTWT7449-BL"]
    assert [o["code"] for o in s3["choice_groups"][0]["options"]] == ["SRTWT7449-BL", "SRTWT7449-RG"]
    assert [c["code"] for c in s4["components"]] == ["SRTMCB8083-BL", "SRTWT6203-GM"]


def test_the_page_text_goes_to_the_model(tmp_path):
    pdf = _pdf(tmp_path / "c.pdf", ["SRTBF11829 WALL HUNG"])
    provider = StubProvider({"combos": []})
    _run(tmp_path, provider, pdf)
    assert "SRTBF11829" in json.dumps(provider.calls[0]["messages"])


def test_two_flyers_are_read_in_the_order_given(tmp_path):
    first = _pdf(tmp_path / "first.pdf", ["x"])
    second = _pdf(tmp_path / "second.pdf", ["y"])
    code, _out, seed = _run(tmp_path, StubProvider(S2_ANSWER, S4_ANSWER), first, second)
    assert code == 0
    assert [(e["flyer"], e["page"]) for e in seed] == [("first.pdf", 1), ("second.pdf", 1)]


def test_codes_are_kept_as_read_and_never_invented(tmp_path):
    answer = {
        "combos": [
            {
                "combo_name": "No host read",
                "components": [{"code": "", "role": "Mirror"}, {"role": "Shelf"}, {"code": " srtwt6203-gm "}],
                "choice_groups": [],
                "topups": [],
                "unsure": "host code not legible",
            }
        ]
    }
    pdf = _pdf(tmp_path / "d.pdf", ["blurred"])
    code, _out, seed = _run(tmp_path, StubProvider(answer), pdf)
    assert code == 0
    (entry,) = seed
    assert not entry.get("host_code"), "a host the model did not read stays empty"
    assert [c.get("code") or "" for c in entry["components"]] == ["", "", "SRTWT6203-GM"]
    assert entry["unsure"] == "host code not legible"


def test_too_many_pages_is_refused_before_any_model_call(tmp_path, monkeypatch):
    script = _script()
    monkeypatch.setattr(script, "MAX_PAGES", 2)
    pdf = _pdf(tmp_path / "e.pdf", ["1", "2", "3"])
    provider = StubProvider(S2_ANSWER, S2_ANSWER, S2_ANSWER)
    code, out, seed = _run(tmp_path, provider, pdf)
    assert code != 0
    assert provider.calls == []
    assert seed is None
    assert "e.pdf" in out


def test_an_oversize_pdf_is_refused(tmp_path, monkeypatch):
    script = _script()
    pdf = _pdf(tmp_path / "f.pdf", ["1"])
    monkeypatch.setattr(script, "MAX_PDF_BYTES", pdf.stat().st_size - 1)
    provider = StubProvider(S2_ANSWER)
    code, out, seed = _run(tmp_path, provider, pdf)
    assert code != 0
    assert provider.calls == []
    assert seed is None
    assert "f.pdf" in out


@pytest.mark.parametrize(
    "bad",
    [
        "this is not json",
        '{"combos": "nope"}',
        '{"combos": [{"combo_name": 5, "components": "x"}]}',
        '["a list, not an object"]',
    ],
)
def test_a_malformed_answer_names_the_page_and_does_not_stop_the_rest(tmp_path, bad):
    pdf = _pdf(tmp_path / "g.pdf", ["1", "2", "3"])
    code, out, seed = _run(tmp_path, StubProvider(S2_ANSWER, bad, S4_ANSWER), pdf)
    assert code == 0
    assert [e["page"] for e in seed] == [1, 3]
    assert "page 2" in out.lower()


def test_a_model_that_raises_is_reported_for_its_page(tmp_path):
    class Boom(StubProvider):
        def chat(self, messages, **kwargs):
            if len(self.calls) == 1:
                self.calls.append({})
                raise RuntimeError("provider down")
            return super().chat(messages, **kwargs)

    pdf = _pdf(tmp_path / "h.pdf", ["1", "2"])
    code, out, seed = _run(tmp_path, Boom(S2_ANSWER, S4_ANSWER), pdf)
    assert code == 0
    assert "page 2" in out.lower()
    assert [e["page"] for e in seed] == [1]


def test_a_file_that_is_not_a_pdf_is_refused(tmp_path):
    bogus = tmp_path / "notes.pdf"
    bogus.write_text("hello")
    provider = StubProvider()
    code, out, seed = _run(tmp_path, provider, bogus)
    assert code != 0
    assert provider.calls == []
