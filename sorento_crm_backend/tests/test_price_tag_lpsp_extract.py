"""PRICETAG-LPSP S5: the price tag AI extract reads LP/SP, typed prices and "+" sets.

UAC: documentation/plans/dealer-kit/pricetag-lpsp-acceptance-criteria.md, AC-14 to AC-17.

Written test-FIRST (PRINCIPLES.md Phase 2). `ExtractedProductLine` has no `price_type`,
`typed_list_price`, `typed_sell_price`, `set_parts`, `combo_id` or `combo_name` yet, so each
case is red on a missing attribute or an unchanged prompt, never on a harness error.

Owner ruling 4 Nov: a "+" line matches an EXISTING stored combo (host + exactly its fixed
parts) or it is an unmatched row (`match` None, `combo_id` None), like an unknown code.

Contract assumptions made here, to be confirmed by the coder against the plan (S5):

* `set_parts` is a list of objects with `product_code` (canonical on a hit, the raw text on a
  miss) and `product_id` (None on a miss). It is filled whenever `set_codes` is sent, whether
  or not a stored combo matched.
* An unmatched set line asserts only `match is None` and `combo_id is None`.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest

from app.models.base import company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.ai_extract.extract_service import (
    AIExtractService,
    ExtractFieldSpec,
    ExtractFile,
)
from app.services.llm_provider import ChatResult
from tests import _ptag_combo_seed as combo_seed
from tests._pg_fixture import blank_session
from tests.fixtures import price_tag_paste_gold as gold

SORENTO = "00000000-0000-0000-0000-000000000001"
FORM = "portal.price_tag_request"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _fresh_prompt_cache():
    from app.services.ai_prompt_registry import bust_cache

    bust_cache()
    yield
    bust_cache()


def _uid() -> str:
    return str(uuid.uuid4())


def _product(db, code: str, *, list_price="100.00") -> Product:
    cat = ProductCategory(id=_uid(), category_code=f"c{_uid()[:12]}", category_name="ZZT cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"u{_uid()[:10]}", uom_name="Each")
    db.add_all([cat, uom])
    db.flush()
    row = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=code,
        product_name=f"ZZT {code}",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=list_price,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _extract(db, *items: dict):
    with company_scope(db, frozenset({SORENTO})):
        return AIExtractService(db)._extract_products({"products": list(items)})


def _item(code: str, **extra) -> dict:
    return {"product_code": code, "product_name": "raw", **extra}


# --------------------------------------------------------------------------- AC-14
PRICE_TYPE_CASES = [
    pytest.param("selling", "selling", id="selling"),
    pytest.param("SP", "selling", id="SP-upper"),
    pytest.param("sp", "selling", id="sp-lower"),
    pytest.param("Selling", "selling", id="Selling-mixed"),
    pytest.param("list", "list", id="list"),
    pytest.param("LP", "list", id="LP"),
    pytest.param("junk", None, id="junk"),
    pytest.param("", None, id="blank"),
    pytest.param(None, None, id="none"),
    pytest.param(5, None, id="number"),
    pytest.param(["selling"], None, id="list-value"),
]


@pytest.mark.parametrize("raw, expected", PRICE_TYPE_CASES)
def test_price_type_is_coerced(db, raw, expected):
    _product(db, "SRTPT001")
    (line,) = _extract(db, _item("SRTPT001", price_type=raw))
    assert line.price_type == expected


PRICE_CASES = [
    pytest.param(599, 599.0, id="int"),
    pytest.param(599.5, 599.5, id="float"),
    pytest.param("599", 599.0, id="numeric-string"),
    pytest.param(None, None, id="none"),
    pytest.param("", None, id="blank"),
    pytest.param("RM599 or so", None, id="non-numeric"),
    pytest.param(-1, None, id="negative"),
    pytest.param(-0.01, None, id="slightly-negative"),
    pytest.param(1e7 + 1, None, id="huge"),
    pytest.param(1e12, None, id="very-huge"),
    pytest.param([599], None, id="list-value"),
    pytest.param({"v": 1}, None, id="dict-value"),
]


@pytest.mark.parametrize("raw, expected", PRICE_CASES)
def test_typed_prices_are_numeric_or_none(db, raw, expected):
    _product(db, "SRTPT002")
    (line,) = _extract(
        db, _item("SRTPT002", typed_list_price=raw, typed_sell_price=raw)
    )
    assert line.typed_list_price == expected
    assert line.typed_sell_price == expected


def test_typed_prices_default_to_none_when_absent(db):
    _product(db, "SRTPT003")
    (line,) = _extract(db, _item("SRTPT003"))
    assert line.price_type is None
    assert line.typed_list_price is None
    assert line.typed_sell_price is None
    assert line.set_parts == []
    assert line.combo_id is None
    assert line.combo_name is None


def test_set_codes_resolve_through_the_resolver_in_the_order_written(db):
    _product(db, "SRTSC-HOST")
    first = _product(db, "SRTSC-PART-BL")
    second = _product(db, "SRTSC-PART2")
    (line,) = _extract(
        db, _item("srtsc host", set_codes=["srtsc part2", "SRTSC PART BL"])
    )
    assert [p.product_code for p in line.set_parts] == ["SRTSC-PART2", "SRTSC-PART-BL"]
    assert [p.product_id for p in line.set_parts] == [second.id, first.id]


def test_unresolved_set_code_is_kept_as_its_raw_text(db):
    _product(db, "SRTSC2-HOST")
    _product(db, "SRTSC2-PART")
    (line,) = _extract(
        db, _item("SRTSC2-HOST", set_codes=["SRTSC2-PART", "ZZT-NOT-A-CODE"])
    )
    parts = {p.product_code: p.product_id for p in line.set_parts}
    assert parts["SRTSC2-PART"] is not None
    assert parts["ZZT-NOT-A-CODE"] is None


def test_set_codes_are_capped_at_ten(db):
    _product(db, "SRTCAP-HOST")
    codes = []
    for index in range(12):
        code = f"SRTCAP-P{index:02d}"
        _product(db, code)
        codes.append(code)
    (line,) = _extract(db, _item("SRTCAP-HOST", set_codes=codes))
    assert [p.product_code for p in line.set_parts] == codes[:10]
    assert line.combo_id is None


def test_set_codes_drop_non_strings_and_overlong_strings(db):
    _product(db, "SRTJNK-HOST")
    _product(db, "SRTJNK-PART")
    too_long = "X" * 65
    (line,) = _extract(
        db,
        _item("SRTJNK-HOST", set_codes=["SRTJNK-PART", 12, None, {"a": 1}, too_long, ""]),
    )
    assert [p.product_code for p in line.set_parts] == ["SRTJNK-PART"]


@pytest.mark.parametrize("junk", ["SRTJNK2-PART", 5, {"a": 1}, None])
def test_set_codes_that_is_not_a_list_is_ignored(db, junk):
    _product(db, "SRTJNK2-HOST")
    _product(db, "SRTJNK2-PART")
    (line,) = _extract(db, _item("SRTJNK2-HOST", set_codes=junk))
    assert line.set_parts == []
    assert line.match == "product"


def test_a_single_code_line_is_resolved_exactly_as_before(db):
    host = _product(db, "SRTBASE-ONE")
    (line,) = _extract(db, _item("srtbase one", price_type="SP", typed_sell_price="499"))
    assert line.match == "product"
    assert line.product_id == host.id
    assert line.product_code == "SRTBASE-ONE"
    assert line.price_type == "selling"
    assert line.typed_sell_price == 499.0


# --------------------------------------------------------------------------- AC-15
def _combo_world(db):
    host = _product(db, "SRTCMB-HOST")
    p1 = _product(db, "SRTCMB-P1")
    p2 = _product(db, "SRTCMB-P2")
    extra = _product(db, "SRTCMB-P3")
    stored = combo_seed.combo(
        db, host, "SRTCMB-HOST + SRTCMB-P1 + SRTCMB-P2", parts=[{"product": p1}, {"product": p2}]
    )
    return host, p1, p2, extra, stored


def test_exact_fixed_parts_return_the_stored_combo(db):
    host, _p1, _p2, _extra, stored = _combo_world(db)
    (line,) = _extract(
        db, _item("SRTCMB-HOST", set_codes=["SRTCMB-P1", "SRTCMB-P2"], typed_sell_price=1729)
    )
    assert line.combo_id == stored.id
    assert line.combo_name == stored.name
    assert line.match == "product"
    assert line.product_id == host.id
    assert line.typed_sell_price == 1729.0


def test_part_order_does_not_matter(db):
    _host, _p1, _p2, _extra, stored = _combo_world(db)
    (line,) = _extract(db, _item("SRTCMB-HOST", set_codes=["SRTCMB-P2", "SRTCMB-P1"]))
    assert line.combo_id == stored.id


def test_one_extra_part_is_an_unmatched_row(db):
    _combo_world(db)
    (line,) = _extract(
        db, _item("SRTCMB-HOST", set_codes=["SRTCMB-P1", "SRTCMB-P2", "SRTCMB-P3"])
    )
    assert line.combo_id is None
    assert line.combo_name is None
    assert line.match is None


def test_one_missing_part_is_an_unmatched_row(db):
    _combo_world(db)
    (line,) = _extract(db, _item("SRTCMB-HOST", set_codes=["SRTCMB-P1"]))
    assert line.combo_id is None
    assert line.match is None


def test_an_unresolvable_part_is_an_unmatched_row(db):
    _combo_world(db)
    (line,) = _extract(db, _item("SRTCMB-HOST", set_codes=["SRTCMB-P1", "ZZT-NOT-A-CODE"]))
    assert line.combo_id is None
    assert line.match is None


def test_a_combo_on_another_host_never_matches(db):
    _combo_world(db)
    other = _product(db, "SRTCMB-OTHER")
    (line,) = _extract(db, _item("SRTCMB-OTHER", set_codes=["SRTCMB-P1", "SRTCMB-P2"]))
    assert line.combo_id is None
    assert line.match is None
    assert other


def test_the_combo_with_exactly_those_parts_wins_among_several(db):
    host = _product(db, "SRTMULTI-HOST")
    p1 = _product(db, "SRTMULTI-P1")
    p2 = _product(db, "SRTMULTI-P2")
    combo_seed.combo(db, host, "small", parts=[{"product": p1}])
    big = combo_seed.combo(db, host, "big", parts=[{"product": p1}, {"product": p2}])
    (line,) = _extract(db, _item("SRTMULTI-HOST", set_codes=["SRTMULTI-P1", "SRTMULTI-P2"]))
    assert line.combo_id == big.id
    assert line.combo_name == "big"


def test_only_fixed_parts_count_a_choice_group_is_ignored(db):
    host = _product(db, "SRTGRP-HOST")
    fixed = _product(db, "SRTGRP-FIX")
    opt_a = _product(db, "SRTGRP-A")
    opt_b = _product(db, "SRTGRP-B")
    stored = combo_seed.combo(
        db,
        host,
        "with a basin choice",
        parts=[
            {"product": fixed},
            {"product": opt_a, "group": "Basin"},
            {"product": opt_b, "group": "Basin"},
        ],
    )
    (line,) = _extract(db, _item("SRTGRP-HOST", set_codes=["SRTGRP-FIX"]))
    assert line.combo_id == stored.id


def test_a_set_line_without_a_stored_combo_is_unmatched(db):
    _product(db, "SRTNOC-HOST")
    _product(db, "SRTNOC-P1")
    (line,) = _extract(db, _item("SRTNOC-HOST", set_codes=["SRTNOC-P1"], typed_sell_price=999))
    assert line.combo_id is None
    assert line.match is None
    assert line.typed_sell_price == 999.0


# --------------------------------------------------------------------------- AC-16
def _messages(db, form_key=FORM):
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]
    return AIExtractService(db)._build_messages(form_key, schema, {}, has_line_items=True)


def _content(messages, role):
    return next(m for m in messages if m["role"] == role)["content"]


def test_price_tag_entry_shape_names_the_new_fields(db):
    user = _content(_messages(db), "user")
    for name in ("product_code", "product_name", "notes", "price_type",
                 "typed_list_price", "typed_sell_price", "set_codes"):
        assert name in user, name


def test_price_tag_clause_no_longer_forbids_prices_but_still_forbids_quantities(db):
    user = _content(_messages(db), "user")
    assert "their prices" not in user
    assert "quantity" not in user
    system = _content(_messages(db), "system")
    assert "quantit" in system.lower()
    assert "never copy a quantity" in system


def test_price_tag_prompt_carries_the_lp_sp_section_rule(db):
    system = _content(_messages(db), "system")
    assert "(10)" in system
    assert "LP" in system and "SP" in system
    assert "set_codes" in system
    assert "price_type" in system
    assert "notes" in system, "a second price of the same kind goes to notes"


def test_fallback_text_is_the_shared_base_plus_the_price_tag_rules():
    from app.services.ai_prompt_registry import (
        _ai_extract_base_fallback,
        _ai_extract_price_tag_fallback,
    )

    text = _ai_extract_price_tag_fallback()
    assert text.startswith(_ai_extract_base_fallback())
    assert "(8)" in text and "(9)" in text and "(10)" in text
    assert "set_codes" in text


def test_other_forms_keep_the_shared_base_prompt(db):
    from app.services.ai_prompt_registry import _ai_extract_base_fallback

    messages = _messages(db, "portal.purchase_request")
    system = _content(messages, "system")
    user = _content(messages, "user")
    assert system == _ai_extract_base_fallback()
    assert "set_codes" not in system and "set_codes" not in user
    assert "price_type" not in user
    assert "quantity" in user


# --------------------------------------------------------------------------- AC-17
def _seed_gold_world(db) -> dict[str, str]:
    """Catalogue + stored combos of the gold set. Returns combo name -> combo id."""
    by_code = {code: _product(db, code, list_price=price) for code, price in gold.CATALOGUE.items()}
    ids = {}
    for spec in gold.COMBOS:
        row = combo_seed.combo(
            db,
            by_code[spec["host"]],
            spec["name"],
            parts=[{"product": by_code[code]} for code in spec["parts"]],
        )
        ids[spec["name"]] = row.id
    return ids


def _compare(case, lines, combo_ids) -> None:
    assert len(lines) == len(case.expected), (
        f"{case.id}: {len(lines)} lines, expected {len(case.expected)}"
    )
    for position, (line, want) in enumerate(zip(lines, case.expected)):
        where = f"{case.id}[{position}]"
        if want.get("product_code") is not None:
            assert line.product_code == want["product_code"], where
        assert line.match == want["match"], where
        assert line.price_type == want["price_type"], where
        assert line.typed_list_price == want["typed_list_price"], where
        assert line.typed_sell_price == want["typed_sell_price"], where
        combo_name = want["combo_name"]
        assert line.combo_name == combo_name, where
        assert line.combo_id == (combo_ids[combo_name] if combo_name else None), where
        if "set_parts" in want:
            assert [p.product_code for p in line.set_parts] == want["set_parts"], where
        if "notes_contains" in want:
            assert want["notes_contains"] in (line.notes or ""), where


class _StubProvider:
    """Answers each pasted message with its gold JSON and records what it was sent."""

    def __init__(self, answers: dict[str, dict]):
        self.answers = answers
        self.sent: list[list[dict]] = []

    def chat(self, **kwargs):
        messages = kwargs["messages"]
        self.sent.append(messages)
        user = next(m["content"] for m in messages if m["role"] == "user")
        for text, answer in self.answers.items():
            if text in user:
                return ChatResult(
                    content=json.dumps(answer),
                    prompt_tokens=10,
                    completion_tokens=10,
                    total_tokens=20,
                )
        raise AssertionError("the provider was sent a message that is in no gold case")


def test_the_gold_set_has_eight_messages_and_only_fake_outlets():
    assert len(gold.CASES) == 8
    assert len({case.id for case in gold.CASES}) == 8
    assert gold.OUTLET == "Outlet Example Sdn Bhd"
    for case in gold.CASES:
        assert case.expected, case.id
        assert len(case.model_json["products"]) == len(case.expected), case.id


@pytest.mark.parametrize("case", gold.CASES, ids=lambda case: case.id)
def test_gold_case_parses_to_the_expected_lines(db, monkeypatch, case):
    from app.services.ai_extract import extract_service as svc_mod

    combo_ids = _seed_gold_world(db)
    provider = _StubProvider({case.text: case.model_json})
    monkeypatch.setattr(
        svc_mod.AIExtractService,
        "_resolve_provider",
        lambda self, form_key=None: (provider, "gemini", "stub-model"),
    )
    with company_scope(db, frozenset({SORENTO})):
        result = AIExtractService(db).extract(
            FORM, [ExtractFile(filename="paste.txt", mime="text/plain", data=case.text.encode())]
        )

    _compare(case, result.products, combo_ids)
    # the paste reached the model inside the extract prompt, and nowhere else
    assert len(provider.sent) == 1
    assert case.text in _content(provider.sent[0], "user")


def test_gold_set_through_parse_only_matches_expected(db):
    """Same expectations without the provider seam: JSON text -> parsed -> lines."""
    combo_ids = _seed_gold_world(db)
    svc = AIExtractService(db)
    with company_scope(db, frozenset({SORENTO})):
        for case in gold.CASES:
            parsed = svc._parse_json(json.dumps(case.model_json))
            _compare(case, svc._extract_products(parsed), combo_ids)


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_LLM") != "1",
    reason="opt-in: RUN_LIVE_LLM=1 with GEMINI_API_KEY (dev key); cap USD 0.25",
)
@pytest.mark.parametrize("case", gold.CASES, ids=lambda case: case.id)
def test_gold_case_with_the_real_model(db, monkeypatch, case):
    """The real model against the same expectations. Eight small prompts: far below
    the USD 0.25 cap, but the token total is asserted anyway."""
    from app.services.ai_extract import extract_service as svc_mod
    from app.services.llm_provider import get_provider

    key = os.environ["GEMINI_API_KEY"]
    live = get_provider("gemini", key, model=os.environ.get("RUN_LIVE_LLM_MODEL") or None)
    spent = {"tokens": 0}

    class _Metered:
        def chat(self, **kwargs):
            result = live.chat(**kwargs)
            spent["tokens"] += int(result.total_tokens or 0)
            return result

    combo_ids = _seed_gold_world(db)
    monkeypatch.setattr(
        svc_mod.AIExtractService,
        "_resolve_provider",
        lambda self, form_key=None: (_Metered(), "gemini", "live"),
    )
    with company_scope(db, frozenset({SORENTO})):
        result = AIExtractService(db).extract(
            FORM, [ExtractFile(filename="paste.txt", mime="text/plain", data=case.text.encode())]
        )
    assert spent["tokens"] < 60_000
    _compare(case, result.products, combo_ids)
