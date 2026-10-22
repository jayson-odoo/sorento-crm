"""REPORT-SMART-L round S1 P1 (UAC AC9, AC10): the parser schema carries the count measures and compare_to."""
from __future__ import annotations

from app.services.chatbot.head import parser as P
from app.services.chatbot.lanes.business import report_ask as RA

SCHEMAS = {
    "plain": lambda: P.PARSE_OUTPUT_JSON_SCHEMA,
    "state": lambda: P.PARSE_OUTPUT_JSON_SCHEMA_WITH_STATE,
    "closed": lambda: P.closed_lists_schema(["a", "b"]),
    "closed_state": lambda: P.closed_lists_schema(["a", "b"], state=True),
}


def _props(name):
    return SCHEMAS[name]()["properties"]


def test_measure_enum_is_the_lane_metrics_plus_null():
    for name in SCHEMAS:
        assert set(_props(name)["measure"]["enum"]) == {*RA.METRICS, None}, name


def test_measure_enum_names_the_five_values():
    assert set(_props("plain")["measure"]["enum"]) == {"qty", "amount", "customers", "orders", "products", None}


def test_compare_to_enum_is_the_lane_constant_plus_null():
    for name in SCHEMAS:
        prop = _props(name)["compare_to"]
        assert set(prop["enum"]) == {*RA.COMPARE_TO, None}, name
        assert set(prop["enum"]) == {"previous_period", "last_year", None}


def test_compare_to_is_required_and_tolerated_absent():
    for name in SCHEMAS:
        assert "compare_to" in SCHEMAS[name]()["required"], name
    assert "compare_to" in P.TOLERATED_ABSENT
    assert "compare_to" in P.DECLARED_KEYS
