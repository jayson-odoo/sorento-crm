"""Phase 2 RED tests - the report-ask catalogue (lane REPORT-ENGINE, slice 1a).

`documentation/plans/chatbot/PLAN-report-engine.md` section 10 "Catalogue / datasets".

`app.services.reports.ask.CATALOGUE` maps the spec's words to each definition's columns and
param keys. These tests pin that every word resolves to something that really exists in the
definition it names, so a renamed column cannot leave a dead word behind.

Owner direction 4 Oct 2026: every basis (delivered, ordered, outstanding) reads SALES ORDER lines,
so the catalogue holds three bases and none of them points at the delivery order dataset.
SALES-UNIFIED (#1916, owner ruling 27 Oct: Sales = IV + CS + DN - CN net, by document date) adds a
fourth, `invoiced`, on the billing document lines; the bot asks it first ("Invoiced, delivered,
ordered or outstanding?", owner ruling (b)).

Ambiguity flagged to the captain: PLAN section 10 does not fix the shape of a CATALOGUE entry.
Pinned here (tolerantly): an entry exposes `dimensions` and `filters`, each either a mapping
`spec word -> column / param key` or a plain collection of words that ARE the keys. Entries may
be dicts or objects.
"""
from __future__ import annotations

import pytest


def _field(entry, name):
    return entry[name] if isinstance(entry, dict) else getattr(entry, name)


def _keys(collection):
    """The definition-side keys a `spec word -> key` mapping (or a bare word list) points at."""
    return list(collection.values()) if isinstance(collection, dict) else list(collection)


BASES = ["invoiced", "delivered", "ordered", "outstanding"]


def _definition(basis):
    from app.services.reports.ask import CATALOGUE as _DATASETS

    CATALOGUE = _DATASETS["sales"]

    return _field(CATALOGUE[basis], "definition")


def _definitions():
    """Every basis the catalogue HAS (the missing ones are asserted by the four-bases test)."""
    from app.services.reports.ask import CATALOGUE as _DATASETS

    CATALOGUE = _DATASETS["sales"]

    return {basis: _field(CATALOGUE[basis], "definition") for basis in BASES if basis in CATALOGUE}


def test_catalogue_has_the_four_bases():
    """The four sales bases (#1916), plus REPORT-UNIFY's two other outstanding kinds (owner Q2,
    27 Oct 2026), which read DO lines and billing documents (`tests/test_report_unify_outstanding_bases.py`)."""
    from app.services.reports.ask import CATALOGUE as _DATASETS

    CATALOGUE = _DATASETS["sales"]

    assert set(CATALOGUE) == {*BASES, "pending_delivery", "unpaid"}, set(CATALOGUE)


def test_the_basis_labels():
    from app.services.reports.ask import CATALOGUE as _DATASETS

    CATALOGUE = _DATASETS["sales"]

    assert {b: _field(CATALOGUE[b], "label") for b in BASES} == {
        "invoiced": "invoiced sales", "delivered": "delivered sales", "ordered": "ordered sales",
        "outstanding": "outstanding orders"}


def test_no_basis_reads_the_delivery_order_dataset():
    from app.services.reports.datasets.delivery_order_lines import DEFINITION as delivery_orders

    for basis, definition in _definitions().items():
        assert definition is not delivery_orders, basis
        assert definition.dataset.key != delivery_orders.dataset.key, basis


@pytest.mark.parametrize("basis", BASES)
def test_every_dimension_word_maps_to_a_dimension_column(basis):
    from app.services.reports.ask import CATALOGUE as _DATASETS

    CATALOGUE = _DATASETS["sales"]

    definition = _definition(basis)
    dimensions = _keys(_field(CATALOGUE[basis], "dimensions"))
    assert dimensions, basis
    tagged = {c.key for c in definition.dataset.columns if c.tag == "dimension"}
    for key in dimensions:
        assert key in tagged, (basis, key, sorted(tagged))


@pytest.mark.parametrize("basis", BASES)
def test_every_filter_word_maps_to_a_select_param(basis):
    from app.services.reports import registry as reg
    from app.services.reports.ask import CATALOGUE as _DATASETS

    CATALOGUE = _DATASETS["sales"]

    definition = _definition(basis)
    filters = _keys(_field(CATALOGUE[basis], "filters"))
    assert filters, basis
    select_keys = {p.key for p in definition.params if isinstance(p, reg.SelectParam)}
    for key in filters:
        assert key in select_keys, (basis, key, sorted(select_keys))


@pytest.mark.parametrize("basis", BASES)
def test_both_bases_speak_the_same_words(basis):
    """One spec, two bases: the words a caller may use are the same for both."""
    from app.services.reports.ask import CATALOGUE as _DATASETS

    CATALOGUE = _DATASETS["sales"]

    words = {"customer", "product", "brand", "category", "sales_agent", "location", "channel", "month"}
    dims = _field(CATALOGUE[basis], "dimensions")
    assert words <= set(dims), (basis, sorted(set(dims)))


def test_dealer_keys():
    from app.services.reports.ask import DEALER_KEYS

    # Owner 28 Oct 09:30: a dealer's undelivered-orders answer offers its own open sales orders (`sales_order`).
    assert set(DEALER_KEYS) == {"product", "brand", "category", "month", "sales_order"}, DEALER_KEYS


def test_every_ask_basis_is_on_the_reports_screen_as_the_same_definition():
    """REPORT-UNIFY slice 4 (owner Q5 (a), plan 3b): the six ask bases are registered on the Reports API as the very
    definitions the bot runs. (Slice 1 pinned the opposite; the owner reversed it so staff can check the bot's number.)"""
    from app.services.reports.registry import all_definitions, get

    for basis, definition in _definitions().items():
        assert get(definition.key) is definition, basis
        assert any(d is definition for d in all_definitions()), basis
