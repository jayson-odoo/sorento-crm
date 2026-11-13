"""WA-COMPLAINT-INTAKE T-4: the parser rule routes a problem with the CRM / the assistant to ideate (moved
here from tests/test_wa_issue_submissions.py: a core test may not import app.services.chatbot)."""
import re


# --------------------------------------------------------------------------- #
# T-4: parser routing (a text contract on the prompt's intent)                #
# --------------------------------------------------------------------------- #
def _ideate_rule() -> str:
    from app.services.chatbot.head.parser_template import TEMPLATE

    (line,) = [ln for ln in TEMPLATE.splitlines() if ln.startswith("- ideate / submit_idea:")]
    return line


def test_T4_the_ideate_rule_takes_problems_with_the_crm_or_the_assistant():
    line = _ideate_rule()
    assert "CRM" in line
    assert re.search(r"\bassistant\b", line, re.I)
    assert re.search(r"\b(problem|wrong|broken|not working|error)", line, re.I)


def test_T4_a_product_or_order_complaint_still_routes_to_portal_link():
    line = _ideate_rule()
    tail = line[line.lower().find("complaint"):]
    assert "portal_link" in tail
    assert re.search(r"\bproduct\b", tail) and re.search(r"\border\b", tail)
