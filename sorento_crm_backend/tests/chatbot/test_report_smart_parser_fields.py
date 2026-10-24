"""REPORT-SMART-L round S1 P1 (UAC AC9, AC10): the parser schema carries the count measures and compare_to."""
from __future__ import annotations

from app.services.chatbot.head import parser as P
from tests.chatbot.test_report_smart_schema_by_prompt import BASE, DECLARES, VARIANTS, schema_for
from app.services.chatbot.lanes.business import report_ask as RA

def _schema(monkeypatch, variant):
    """The per-prompt rule: a prompt version declaring `compare_to` gets the extended schema."""
    return schema_for(monkeypatch, BASE + DECLARES + VARIANTS[variant])


SCHEMAS = list(VARIANTS)


def _props(monkeypatch, name):
    return _schema(monkeypatch, name)["properties"]


def test_measure_enum_is_the_lane_metrics_plus_null(monkeypatch):
    for name in SCHEMAS:
        assert set(_props(monkeypatch, name)["measure"]["enum"]) == {*RA.METRICS, None}, name


def test_measure_enum_names_the_five_values(monkeypatch):
    assert set(_props(monkeypatch, "plain")["measure"]["enum"]) == {"qty", "amount", "customers", "orders", "products", None}


def test_compare_to_enum_is_the_lane_constant_plus_null(monkeypatch):
    for name in SCHEMAS:
        prop = _props(monkeypatch, name)["compare_to"]
        assert set(prop["enum"]) == {*RA.COMPARE_TO, None}, name
        assert set(prop["enum"]) == {"previous_period", "last_year", None}


def test_compare_to_is_required_and_tolerated_absent(monkeypatch):
    for name in SCHEMAS:
        assert "compare_to" in _schema(monkeypatch, name)["required"], name
    assert "compare_to" in P.TOLERATED_ABSENT
    assert "compare_to" in P.DECLARED_KEYS
