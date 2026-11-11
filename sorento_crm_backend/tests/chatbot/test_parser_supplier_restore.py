"""PARSER-SUPPLIER-RESTORE (11 Nov 2026): the production-candidate parser text carries the supplier lines again.

Prod v72 (md5 d29c1983) dropped the two lines v71 (md5 d106ff95, migration `sask_0002_span_supplier`) put right after
`== LOOKUP SPANS ==`, so `parser.SUPPLIER_ID_ASK` was gone and the supplier path never switched on ("outstiang for
taiyang" -> 'Couldn't find "taiyang" (customer)'). 289da7e5 (REPORT-FILTER-ALL) is built on v72. The candidate is
289da7e5 plus those two lines, built with the migration's own frozen functions, and the span candidate is the
production span text with the migration's supplier type line. Plan: documentation/plans/chatbot/PLAN-parser-supplier-restore-11nov.md.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

from app.services.chatbot.head import parser as parser_mod

_BACKEND = Path(__file__).resolve().parents[2]
_PLANS = _BACKEND.parent / "documentation" / "plans" / "chatbot"
_MIGRATION = _BACKEND / "alembic" / "versions" / "sask_0002_span_supplier.py"

PARSER_BASE_MD5 = "289da7e56130a489ecb624031996acc2"  # REPORT-FILTER-ALL round 5 (dev v79)
PARSER_CANDIDATE_MD5 = "b1c5934301f23a5c43ca90670aacb81b"
SPAN_BASE_MD5 = "1685b3af11542871e9ee48d469eb0149"  # production span v2 on the dev copy
SPAN_CANDIDATE_MD5 = "e42387fd1804df730dfb5bfe7a66efd4"  # unlabelled span v3 on the dev copy (SUPPLIER-ASK)


def _sask():
    spec = importlib.util.spec_from_file_location("zz_sask_0002_span_supplier", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_the_parser_candidate_is_289da7e5_plus_the_two_v71_lines_after_the_span_marker() -> None:
    sask = _sask()
    base, cand = _PLANS / "prompt-report-filter-all.txt", _PLANS / "prompt-parser-supplier-restore.txt"
    assert _md5(base) == PARSER_BASE_MD5
    base_text, cand_text = base.read_text(encoding="utf-8"), cand.read_text(encoding="utf-8")
    assert cand_text == sask.with_after_year(sask.with_supplier_line(base_text)), "built by the migration's own functions"
    assert _md5(cand) == PARSER_CANDIDATE_MD5
    marker_line = sask.SPAN_MARKER + "\n" + sask.PARSER_SUPPLIER_LINE + "\n" + sask.AFTER_YEAR_SENTENCE + "\n"
    assert cand_text.count(marker_line) == 1, "the two lines sit right after the marker, as v71 has them"
    assert cand_text.replace(sask.PARSER_SUPPLIER_LINE + "\n" + sask.AFTER_YEAR_SENTENCE + "\n", "", 1) == base_text


def test_the_parser_candidate_switches_the_supplier_path_on_and_keeps_the_289da7e5_gates() -> None:
    text = (_PLANS / "prompt-parser-supplier-restore.txt").read_text(encoding="utf-8")
    assert parser_mod.SUPPLIER_ID_ASK in text, "without it supplier lines carry no id and nothing binds a supplier"
    assert parser_mod.PARTY_SIDE_LINE in text and parser_mod.REPORT_ASK_LINE in text
    assert "ALL" in parser_mod.report_ask_defined_in(text), "REPORT-FILTER-ALL's ALL stays on"
    assert _sask().SUPPLIER_ID_ASK == parser_mod.SUPPLIER_ID_ASK, "the migration's frozen copy is the parser's gate"


def test_the_span_candidate_is_the_production_span_text_plus_the_supplier_type_line() -> None:
    sask = _sask()
    base, cand = _PLANS / "prompt-span-prod-v2.txt", _PLANS / "prompt-span-supplier-restore.txt"
    assert _md5(base) == SPAN_BASE_MD5 and _md5(cand) == SPAN_CANDIDATE_MD5
    cand_text = cand.read_text(encoding="utf-8")
    assert cand_text == sask.with_supplier_type(base.read_text(encoding="utf-8"))
    assert sask.SUPPLIER_TYPE_LINE in cand_text.split("\n")


#: Committed parser texts from before this lane that lack the supplier lines on purpose (history, never published again).
_SUPPLIER_LESS_HISTORY = frozenset({"prompt-prod-v72-d29c1983.txt", "prompt-report-filter-all.txt"})


def test_every_committed_span_pass_parser_text_keeps_the_supplier_id_sentence() -> None:
    """Review round 1: the next prompt lane that builds its candidate on a supplier-less base (as REPORT-FILTER-ALL built
    on v72) and commits it here fails CI instead of shipping the regression again. Texts published on the Prompts page
    without a committed file are out of this test's reach (see the plan's guard proposal)."""
    marker = _sask().SPAN_MARKER
    texts = sorted(_PLANS.glob("prompt-*.txt"))
    span_pass = [t for t in texts if marker in t.read_text(encoding="utf-8").splitlines()]
    assert span_pass, "no committed span-pass parser text found"
    missing = [t.name for t in span_pass if t.name not in _SUPPLIER_LESS_HISTORY
               and parser_mod.SUPPLIER_ID_ASK not in t.read_text(encoding="utf-8")]
    assert missing == [], f"span-pass parser texts without parser.SUPPLIER_ID_ASK: {missing}"
