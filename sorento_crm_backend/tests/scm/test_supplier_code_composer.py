"""Bare model code composition (S1, `PLAN-stock-list-bare-model-codes.md` D3-D5).

TEST-FIRST (Phase 2): `app/services/scm/supplier_code_composer.py` does not exist yet, so
every test below is expected to be RED with a collection-time `ModuleNotFoundError` until
S1 lands. Pure functions only, except `TestWordListForSupplier`, which needs Postgres to
prove the supplier-wins-over-shared lookup rule (AC-W3's twin, exercised here because the
composer is what actually calls it).

The D7 seed (word -> token) is restated here rather than imported from the migration, so
this file is provable on its own: a change to the migration's seed values that silently
drifted from D7 would show up as a failure here, not disappear because both sides read the
same constant.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.scm.supplier_code_composer import (
    WORD_DOC_TYPE,
    WORD_TOKENS,
    SpecParts,
    WordList,
    compose,
    is_bare,
    parse_spec,
    raw_key,
)
from tests._pg_fixture import pg_session, unique_code


def d7_words() -> WordList:
    """The migration's own D7 seed (shared rows, `supplier_id` NULL), restated as a plain
    mapping for the pure-function tests."""
    return WordList(
        {
            "SORENTO": "SRT",
            "S": "SRT",
            "CABANA": "C",
            "C": "C",
            "MOCHA": "M",
            "M": "M",
            "连体马桶": "WC",
            "分体马桶": "WC",
            "座头": "WCX",
            "分体座头": "WCX",
            "水箱": "WCY",
            "盆": "WB",
            "盆小孔": "WB",
            "盖板": "SC",
            "横排": "P",
        }
    )


class TestWordTokens:
    def test_word_tokens_covers_the_closed_vocabulary(self):
        for token in ("SRT", "C", "M", "WC", "WCX", "WCY", "WB", "SC", "P"):
            assert token in WORD_TOKENS

    def test_word_doc_type_is_the_alias_table_doc_type(self):
        assert WORD_DOC_TYPE == "supplier_inventory_word"


class TestWordListLookup:
    def test_lookup_is_case_and_whitespace_insensitive(self):
        words = d7_words()
        assert words.lookup("SORENTO ") == "SRT"
        assert words.lookup("sorento") == "SRT"
        assert words.lookup("S") == "SRT"
        assert words.lookup(" s ") == "SRT"

    def test_lookup_of_an_unknown_word_is_none(self):
        assert d7_words().lookup("对冲") is None


class TestIsBare:
    def test_a_digit_led_model_is_bare(self):
        assert is_bare("8613") is True

    def test_a_negative_model_is_bare(self):
        assert is_bare("-7055") is True

    def test_a_letter_led_model_is_not_bare(self):
        assert is_bare("SRTWC8357-RL-250") is False

    def test_is_bare_trims_whitespace_first(self):
        assert is_bare("  8613") is True


# AC-R6: parse_spec over every distinct 规格 value on the 0915 copy plus this file's.
_PARSE_SPEC_CASES = [
    ("250", SpecParts(size=250, trap=None, extras=[])),
    ("200", SpecParts(size=200, trap=None, extras=[])),
    ("180横排", SpecParts(size=180, trap="P", extras=[])),
    ("180", SpecParts(size=180, trap=None, extras=[])),
    ("300", SpecParts(size=300, trap=None, extras=[])),
    ("150", SpecParts(size=150, trap=None, extras=[])),
    ("250UF", SpecParts(size=250, trap=None, extras=["UF"])),
    ("250A", SpecParts(size=250, trap=None, extras=["A"])),
    ("250PP", SpecParts(size=250, trap=None, extras=["PP"])),
    ("250-PP", SpecParts(size=250, trap=None, extras=["PP"])),
    ("250NEW", SpecParts(size=250, trap=None, extras=["NEW"])),
    ("250对冲", None),  # 对冲 unseeded in D7 - abort.
    ("180A横排", SpecParts(size=180, trap="P", extras=["A"])),
    ("180横排对冲", None),  # 对冲 unseeded even though 横排 resolves.
    ("250mm", SpecParts(size=250, trap=None, extras=[])),
    ("150mm", SpecParts(size=150, trap=None, extras=[])),
    ("横排180mm", SpecParts(size=180, trap="P", extras=[])),
    ("600*450*200mm", SpecParts(size=None, trap=None, extras=[])),
    ("背部没有孔", None),
    ("四面施釉", None),
    (None, SpecParts(size=None, trap=None, extras=[])),
]


class TestParseSpec:
    @pytest.mark.parametrize("spec, expected", _PARSE_SPEC_CASES)
    def test_ac_r6_parse_spec_over_the_measured_vocabulary(self, spec, expected):
        assert parse_spec(spec, d7_words()) == expected

    def test_ac_r6_an_unseeded_cjk_word_resolves_once_a_row_exists(self):
        mapping = {
            "SORENTO": "SRT",
            "S": "SRT",
            "CABANA": "C",
            "MOCHA": "M",
            "连体马桶": "WC",
            "分体马桶": "WC",
            "座头": "WCX",
            "分体座头": "WCX",
            "水箱": "WCY",
            "盆": "WB",
            "盆小孔": "WB",
            "盖板": "SC",
            "横排": "P",
            "对冲": "SH",
        }
        words = WordList(mapping)
        assert parse_spec("250对冲", words) == SpecParts(size=250, trap=None, extras=["SH"])


# AC-R4: bare 型号, every word known.
_COMPOSE_CASES = [
    ("8613", "250mm", "SORENTO", "连体马桶", "SRTWC8613-250"),
    ("8613", "横排180mm", "SORENTO", "连体马桶", "SRTWC8613-P-180"),
    ("8066-PP", "150mm", "SORENTO", "连体马桶", "SRTWC8066-PP-150"),
    ("-7055", None, "SORENTO", "盆", "SRTWB7055"),
    ("8605-RL", None, "SORENTO", "水箱", "SRTWCY8605-RL"),
    ("1009", "250mm", "CABANA", "分体马桶", "CWC1009-250"),
    ("888", "600*450*200mm", "SORENTO", "盆", "SRTWB888"),
    ("8613", "250mm", "S", "连体马桶", "SRTWC8613-250"),
]


class TestCompose:
    @pytest.mark.parametrize("model_no, spec, brand, product_name, expected", _COMPOSE_CASES)
    def test_ac_r4_bare_model_composes_from_brand_type_and_trap(
        self, model_no, spec, brand, product_name, expected
    ):
        assert compose(model_no, spec, brand, product_name, d7_words()) == expected

    def test_ac_r5_a_blank_brand_aborts_composition(self):
        assert compose("7609对冲", "150mm", None, "连体马桶", d7_words()) is None

    def test_ac_r5_an_unknown_cjk_run_in_the_model_aborts_composition(self):
        assert compose("7604-RL高压", "横排180mm", "CABANA", "座头", d7_words()) is None

    def test_ac_r5_a_letter_led_model_never_composes(self):
        assert compose("SRTWC8357-RL-250", "250", "S", "连体马桶", d7_words()) is None

    def test_an_unknown_product_name_aborts_composition(self):
        assert compose("8613", "250mm", "SORENTO", "飞机", d7_words()) is None


class TestRawKey:
    def test_ac_r5_raw_key_joins_present_parts_in_order_space_separated(self):
        assert raw_key("7609对冲", "150mm", None, "连体马桶") == "7609对冲 150mm 连体马桶"

    def test_ac_r5_raw_key_with_every_part_present(self):
        assert (
            raw_key("7604-RL高压", "横排180mm", "CABANA", "座头")
            == "7604-RL高压 横排180mm CABANA 座头"
        )

    def test_raw_key_strips_each_part(self):
        assert raw_key(" 7609对冲 ", " 150mm ", None, " 连体马桶 ") == "7609对冲 150mm 连体马桶"


class TestWordListForSupplier:
    """AC-W3's rule, exercised through the composer's own consumer - a supplier's own row
    wins over the shared one, and composing with it changes the outcome."""

    def test_for_supplier_builds_a_word_list_that_composes(self):
        with pg_session() as db:
            from app.models.import_alias import ImportFieldAlias
            from app.models.procurement import Supplier

            supplier = Supplier(
                id=str(uuid.uuid4()),
                supplier_code=unique_code("SUP"),
                supplier_name="composer test supplier",
                is_active=True,
            )
            db.add(supplier)
            db.flush()
            db.add_all(
                [
                    ImportFieldAlias(
                        id=str(uuid.uuid4()),
                        doc_type=WORD_DOC_TYPE,
                        field="SRT",
                        alias="SORENTO",
                        supplier_id=None,
                    ),
                    ImportFieldAlias(
                        id=str(uuid.uuid4()),
                        doc_type=WORD_DOC_TYPE,
                        field="WB",
                        alias="盆",
                        supplier_id=None,
                    ),
                ]
            )
            db.flush()

            words = WordList.for_supplier(db, str(supplier.id))

            assert compose("-7055", None, "SORENTO", "盆", words) == "SRTWB7055"

    def test_for_supplier_row_wins_over_the_shared_row(self):
        with pg_session() as db:
            from app.models.import_alias import ImportFieldAlias
            from app.models.procurement import Supplier

            supplier = Supplier(
                id=str(uuid.uuid4()),
                supplier_code=unique_code("SUP"),
                supplier_name="composer override supplier",
                is_active=True,
            )
            db.add(supplier)
            db.flush()
            db.add_all(
                [
                    ImportFieldAlias(
                        id=str(uuid.uuid4()),
                        doc_type=WORD_DOC_TYPE,
                        field="SRT",
                        alias="SORENTO",
                        supplier_id=None,
                    ),
                    ImportFieldAlias(
                        id=str(uuid.uuid4()),
                        doc_type=WORD_DOC_TYPE,
                        field="M",
                        alias="SORENTO",
                        supplier_id=str(supplier.id),
                    ),
                ]
            )
            db.flush()

            words = WordList.for_supplier(db, str(supplier.id))

            assert words.lookup("SORENTO") == "M"
