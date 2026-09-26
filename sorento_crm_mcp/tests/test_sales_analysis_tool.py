"""S1 (#1267): `crm_sales_analysis`, the chatbot's text + Excel answer over the sales dataset.

UAC: AC-S1-19 (catalogue, PRESENTER_TOOLS, reveal key), AC-S1-20 (the compare golden),
AC-R4-1 / AC-R4-2 (the whole answer as text AND the file, one figure or twelve months),
AC-R4-3 (a question or a refusal carries no file), AC-R4-4 (pending ends "The Excel
follows here."; a failed build is said, never promised), AC-X-1 (no UUID in a reply).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import PRESENTER_TOOLS, present_response

TOOL = "crm_sales_analysis"
SAMPLES = Path(__file__).resolve().parents[2] / "documentation" / "plans" / "sales" / "samples"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _sample(name):
    return json.loads((SAMPLES / f"sales-analysis-{name}.json").read_text())


def _golden(name):
    return (SAMPLES / f"sales-analysis-{name}.txt").read_text().rstrip("\n")


def _envelope(payload):
    return json.loads(present_response(TOOL, json.dumps(payload)))


def _spec():
    return next(s for s in CATALOG if s.name == TOOL)


def test_ac_s1_19_the_tool_is_catalogued_as_a_contact_scoped_get():
    spec = _spec()
    assert spec.path == "/api/v1/sales/analysis"
    assert spec.method == "GET"
    for param in ("rows", "cols", "channel", "basis", "company", "date_from", "date_to", "n",
                  "contact_id", "space_id"):
        assert param in spec.query_params, param
    assert spec.domain == "orders"
    assert spec.restricted_fields == (("sales_orders.sales_report", "Sales report"),)
    assert TOOL in PRESENTER_TOOLS
    for word in ("page", "page_size", "limit", "offset"):
        assert word not in spec.query_params


def test_contact_and_space_are_required():
    from sorento_crm_mcp.server import TOOL_REQUIRED_QUERY_HINTS

    assert TOOL_REQUIRED_QUERY_HINTS[TOOL] == ("contact_id", "space_id")


def test_ac_s1_20_ac_r4_2_compare_by_month_prints_every_month_and_attaches_the_file():
    payload = _sample("compare")
    env = _envelope(payload)
    assert env["response"] == _golden("compare")
    assert env["attachments"] == payload["attachments"]
    assert env["has_result"] is True
    for word in ("more", "next", "lagi", "Full table"):
        assert word not in env["response"]
    assert not _UUID_RE.search(env["response"])


def test_ac_r4_1_one_figure_is_text_and_file_too():
    payload = _sample("total")
    env = _envelope(payload)
    assert env["response"] == _golden("total")
    assert len(env["attachments"]) == 1


def test_ac_r4_4_pending_sends_the_text_now_and_says_the_excel_follows():
    env = _envelope(_sample("pending"))
    assert env["response"] == _golden("pending")
    assert env["response"].endswith("The Excel follows here.")
    assert env["attachments"] == []


def test_ac_r4_4_a_failed_build_is_said_not_promised():
    payload = dict(_sample("compare"), status="error", attachments=[])
    env = _envelope(payload)
    assert env["response"].startswith(_golden("compare"))
    assert env["response"].endswith("Could not build the sales report Excel right now.")
    assert "follows" not in env["response"]
    assert env["attachments"] == []


def test_ac_r4_3_a_question_or_a_refusal_carries_no_file():
    for payload in (
        {"status": "clarify", "message": "Sorento or Mocha?"},
        {"status": "refused", "message": "Sorry, I can only share sales figures for your own account."},
    ):
        env = _envelope(payload)
        assert env["response"] == payload["message"]
        assert env["attachments"] == []
        assert env["has_result"] is True


def test_an_error_body_is_one_plain_line():
    env = _envelope({"message": "Permission required", "code": "sales_report_not_enabled"})
    assert env["response"] == "Could not run the sales report right now."
    assert env["attachments"] == []


def test_a_month_with_no_sales_reads_as_a_dash_not_rm_dash():
    payload = dict(_sample("total"), columns=["2026"], rows=[
        {"label": "SEP", "values": ["75428.55"], "total": "75428.55"},
        {"label": "OCT", "values": [None], "total": None},
    ])
    text = _envelope(payload)["response"]
    assert "SEP: RM 75,428.55" in text
    assert "OCT: -" in text and "RM -" not in text
