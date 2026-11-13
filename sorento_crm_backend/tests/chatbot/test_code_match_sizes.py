"""CHATBOT-CODE-MATCH slice 4 (R4): a size comes only from a stored value.

UAC: AC-4, AC-5, AC-6, AC-7, AC-25, AC-26 in `documentation/plans/chatbot/chatbot-code-match-acceptance-criteria.md`
("Slice 4"); behaviour card rule R4 (owner 12 Nov: no size is ever assumed). A number in a typed code counts as a size
ONLY when it equals a value stored on a candidate under the category's size key, in that key's registry unit; such a
candidate is OFFERED with its stored size ("Size: 300 mm"), a candidate with no stored value shows "Size: not
recorded", and nothing is answered on a guess.

Generic: each test seeds its OWN registry size key (numeric, mm, scoped to the test category's class through
`applies_when.class`, `matches_bare_size`) and `product_specifications` values. No seeded key and no company letter
is read. Dealer halves run on the AvailConsole; staff halves on the real staff console (`Console.as_staff()`).

Reply layout of the "Size:" line is the contract assumed here: it sits in the candidate's own entry (the option's line
or the lines under it, before the next numbered option).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from sqlalchemy import text as sql_text

from app.models.product_spec import ProductSpecifications, ProductSpecRegistry

from tests.chatbot._avail_mode_console import Stock
from tests.chatbot._r9_engine_console import product, stock
from tests.chatbot.test_code_match_dealer_offers import TICK, Console, _console, _option_codes
from tests.chatbot.test_engine import stub_access  # noqa: F401 - a pytest fixture

pytestmark = pytest.mark.usefixtures("stub_access")

#: The class the AvailConsole's seeded category carries (`_avail_mode_console._seed`: class_label "am").
CLASS = "am"
FAM = "TWC8152-SH-UF"
FAM_300 = "TWC8152-SH-UF-300"


def _seed_sizes(
    c: Console,
    session_factory,
    keys: list[tuple[str, str, str]],
    stored: dict[str, dict[str, float]],
    class_of: dict[str, str] | None = None,
) -> None:
    """Registry keys `(spec_key, label, unit)` scoped to the test class, then each code's stored values."""
    db = session_factory()
    try:
        for spec_key, label, unit in keys:
            db.add(
                ProductSpecRegistry(
                    id=str(uuid.uuid4()), spec_key=spec_key, label=label, data_type="numeric", unit=unit,
                    synonyms={"_self": [label.lower()]}, applies_when={"class": [CLASS]},
                )
            )
        db.flush()
        db.execute(sql_text("UPDATE product_spec_registry SET matches_bare_size = true WHERE spec_key = ANY(:k)"), {"k": [k[0] for k in keys]})
        unit_of = {k[0]: k[2] for k in keys}
        for code, values in stored.items():
            db.add(
                ProductSpecifications(
                    id=str(uuid.uuid4()), product_id=c.uuid_of[code],
                    values={"class": {"value": (class_of or {}).get(code, CLASS)}, **{k: {"value": v, "unit": unit_of[k]} for k, v in values.items()}},
                )
            )
        db.commit()
    finally:
        db.close()


def _entry(text: str, code: str) -> str:
    """The candidate's own entry, read from the numbered options only (the "Couldn't find ..." header lines are
    skipped): the numbered line holding `code` as a whole code, and the lines under it up to the next numbered
    option. Empty when no numbered option holds the code."""
    lines = text.splitlines()
    numbered = re.compile(r"\s*\d+[.)]\s")
    pattern = re.compile(rf"(?<![A-Za-z0-9-]){re.escape(code)}(?![A-Za-z0-9-])")
    for i, line in enumerate(lines):
        if numbered.match(line) and pattern.search(line):
            out = [line]
            for follower in lines[i + 1 :]:
                if numbered.match(follower):
                    break
                out.append(follower)
            return "\n".join(out)
    return ""


def _header(text: str, who: str, code: str, size: str) -> None:
    """The reply's lead: the code exists but no member holds the size, so it names what is missing."""
    if who == "dealer":
        assert text.startswith(f"Couldn't find {code} with size {size}. Did you mean:"), text
        return
    first = text.splitlines()[0]  # staff keep their own quoted style
    assert f'Couldn\'t find "{code}"' in first and f"with size {size}" in first and "Did you mean" in first, text


def _as_staff(c: Console) -> None:
    c.as_staff()
    c.stock_on_hand = 12


def _size_console(session_factory, monkeypatch, stub_access, codes, stored, keys=None, *, other_class=None):  # noqa: F811
    """`other_class`: `{code: class label}` for products created in a second category of that class."""
    c = _console(session_factory, monkeypatch, stub_access, codes, **{k.replace("-", "_"): Stock(on_hand=100) for k in codes})
    for code, label in (other_class or {}).items():
        _add_product_in_class(c, session_factory, code, label)
    _seed_sizes(c, session_factory, keys or [("zz_size", "Size", "mm")], stored, class_of=other_class)
    return c


def _add_product_in_class(c: Console, session_factory, code: str, class_label: str) -> None:
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests.chatbot.test_rearch_s3_attribute_first import SORENTO

    tag = uuid.uuid4().hex[:6]
    db = session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    try:
        cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=f"ZZTC-{class_label}-{tag}", category_name=f"ZZT {class_label}",
            class_label=class_label, search_synonyms=[],
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"ZZTU-{class_label}-{tag}", uom_name="ZZT uom")
        db.add_all([cat, uom])
        db.flush()
        pid = str(uuid.uuid4())
        db.add(Product(id=pid, product_code=code, product_name=f"ZZT {code}", category_id=cat.id, base_uom_id=uom.id, list_price=1))
        db.commit()
    finally:
        db.close()
    c.codes[pid] = code
    c.uuid_of[code] = pid


# --------------------------------------------------------------------------- AC-4


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4_a_typed_size_nothing_holds_is_not_answered_and_each_candidate_shows_its_stored_size(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-UF-250"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert "Couldn't find" in text and typed in text.split("\n")[0].upper().replace('"', ""), text
    assert TICK not in text and "Got stock" not in text and "Stock summary" not in text, f"answered on a guess: {text!r}"
    assert set(_option_codes(c)) == {FAM, FAM_300}, (_option_codes(c), text)
    assert "Size: not recorded" in _entry(text, FAM), (text, _entry(text, FAM))
    assert "Size: 300 mm" in _entry(text, FAM_300), (text, _entry(text, FAM_300))
    assert "250" not in _entry(text, FAM) and "250" not in _entry(text, FAM_300).replace(typed, ""), text


# --------------------------------------------------------------------------- AC-5


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac5_a_number_in_the_code_equal_to_a_stored_value_is_offered_with_that_size(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    code = "TWC8152-SH-300"
    c = _size_console(session_factory, monkeypatch, stub_access, [code], {code: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "8152-300-SH"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    if who == "dealer":
        assert _option_codes(c) == [code], (_option_codes(c), text)
    # Staff (AC-1691): the offer is "Reply with a code to continue, or ... escalate?", its pending question the
    # escalation yes/no, which holds no code; the text carries the offer.
    assert code in text and "Size: 300 mm" in text, text
    assert TICK not in text and "Got stock" not in text and "Stock summary" not in text, f"answered on a guess: {text!r}"


# --------------------------------------------------------------------------- AC-6


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac6_a_number_in_the_code_equal_to_no_stored_value_is_not_a_size(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-UF-777"  # 777 is stored on nothing
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert _option_codes(c), text  # matched as a code only: the family is offered
    assert "777" not in text.replace(typed, ""), text
    assert "None with size" not in text, text
    assert "Size: 777" not in text, text


# --------------------------------------------------------------------------- AC-7


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac7_a_typed_size_no_candidate_holds_names_the_close_codes_with_their_stored_sizes(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-UF-400"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert "Couldn't find" in text and typed in text.upper(), text
    assert "None with size" not in text, text
    assert "Size: 300 mm" in _entry(text, FAM_300) and "Size: not recorded" in _entry(text, FAM), text


# --------------------------------------------------------------------------- AC-25


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac25_a_number_stored_under_two_keys_offers_every_match_with_the_key_it_matched(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    long_code, wide_code = "TWC8152-SH-A", "TWC8152-SH-B"
    c = _size_console(
        session_factory, monkeypatch, stub_access, [long_code, wide_code],
        {long_code: {"zz_len": 300}, wide_code: {"zz_wid": 300}},
        keys=[("zz_len", "Length", "mm"), ("zz_wid", "Width", "mm")],
    )
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-300"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert set(_option_codes(c)) == {long_code, wide_code}, (_option_codes(c), text)
    assert "Length: 300 mm" in _entry(text, long_code), (text, _entry(text, long_code))
    assert "Width: 300 mm" in _entry(text, wide_code), (text, _entry(text, wide_code))
    assert TICK not in text and "Stock summary" not in text, text


# --------------------------------------------------------------------------- AC-7b, AC-26: a size the parser read apart from the code


def _closed_lists(monkeypatch) -> None:
    """The parser config the spec-entity turns need (closed lists, the state gate), as the near-code tests set it."""
    import dataclasses

    from app.services.chatbot.head import parser as parser_mod

    real = parser_mod.resolve_config
    monkeypatch.setattr(
        parser_mod, "resolve_config", lambda db, **k: dataclasses.replace(real(db, **k), closed_lists=True, state_block=True)
    )


def _head_and_size(value: float, unit: str, head_code: str = FAM) -> tuple[dict[str, Any], dict[str, Any]]:
    head = {"raw": head_code, "hint": "product", "canonical_code": head_code, "current_message": True, "confident": True}
    size = {
        "raw": f"{value:g}{unit}", "hint": "specification", "canonical_code": None, "spec_key": "size",
        "spec_value": value, "spec_unit": unit, "current_message": True, "confident": True,
    }
    return head, size


def _head_plus_size(value: float, unit: str, head_code: str = FAM) -> dict[str, Any]:
    return stock(*_head_and_size(value, unit, head_code))


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac7b_a_size_the_parser_read_that_no_candidate_holds_is_never_the_bare_none_with_size_line(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{FAM} 400mm stock", _head_plus_size(400, "mm"))
    # A "None with size ..." clause may appear only inside a reply that leads with "Couldn't find" and offers the close
    # codes with their stored sizes; never bare, never followed by an answer for the code with no stored size.
    # The code exists but no member holds the size: the header names what is missing, not the code itself.
    _header(text, who, FAM, "400 mm")
    assert "None with size" not in text, text
    assert "Size: 300 mm" in _entry(text, FAM_300) and "Size: not recorded" in _entry(text, FAM), text
    assert "Stock summary" not in text and "How many units of" not in text and TICK not in text, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac26_the_none_with_size_line_takes_its_unit_from_the_registry_key(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    """A size key held in centimetres: 30 cm is held by nothing (the variant stores 40), and the line says cm."""
    c = _size_console(
        session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 40}}, keys=[("zz_size", "Size", "cm")]
    )
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{FAM} 30cm stock", _head_plus_size(30, "cm"))
    _header(text, who, FAM, "30 cm")
    assert "None with size" not in text, text
    assert "Size: 40 cm" in _entry(text, FAM_300) and "Size: not recorded" in _entry(text, FAM), text
    assert "Stock summary" not in text and "How many units of" not in text and TICK not in text, text
    assert " mm" not in text, text


# --------------------------------------------------------------------------- slice 4 review round


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac5b_many_other_products_holding_the_number_do_not_crowd_out_the_candidate(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    code = "TWC8152-SH-300"
    crowd = [f"AAA{n:04d}" for n in range(1, 26)]  # 25 products of the class storing 300, sorting before the candidate
    c = _size_console(
        session_factory, monkeypatch, stub_access, [code, *crowd], {code: {"zz_size": 300}, **{k: {"zz_size": 300} for k in crowd}}
    )
    if who == "staff":
        _as_staff(c)
    typed = "8152-300-SH"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert code in text and "Size: 300 mm" in text, text
    assert "AAA0" not in text, text
    assert TICK not in text and "Got stock" not in text and "Stock summary" not in text, text


def _single_miss_header(text: str, who: str, code: str, size: str) -> None:
    if who == "dealer":
        assert text.startswith(f"Couldn't find {code} with size {size}"), text
    else:
        first = text.splitlines()[0]
        assert f'Couldn\'t find "{code}"' in first and f"with size {size}" in first, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4b_a_family_of_one_with_no_stored_size_is_offered_not_answered(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM], {})
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{FAM} 400mm stock", _head_plus_size(400, "mm"))
    _single_miss_header(text, who, FAM, "400 mm")
    assert "Size: not recorded" in text, text
    assert text.count(FAM) >= 2, f"the code is not offered beyond the header: {text!r}"
    assert "How many units of" not in text and "Stock summary" not in text and TICK not in text, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4c_codes_that_do_not_start_letters_then_digits_take_the_same_path(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    base, variant = "8152-SH-UF", "8152-SH-UF-300"
    c = _size_console(session_factory, monkeypatch, stub_access, [base, variant], {variant: {"zz_size": 300}})
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{base} 400mm stock", _head_plus_size(400, "mm", base))
    _header(text, who, base, "400 mm")
    assert "None with size" not in text, text
    assert "Size: 300 mm" in _entry(text, variant) and "Size: not recorded" in _entry(text, base), text
    assert "Stock summary" not in text and "How many units of" not in text and TICK not in text, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac25b_a_size_key_scoped_to_one_class_is_not_read_for_a_product_of_another(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    a_code, b_code = "TWC8152-SH-A", "TWC8152-SH-B"
    c = _size_console(
        session_factory, monkeypatch, stub_access, [a_code], {a_code: {"zz_size": 300}, b_code: {"zz_size": 300}},
        other_class={b_code: "bm"},  # key zz_size is scoped to class "am" only
    )
    if who == "staff":
        _as_staff(c)
    typed = "TWC8152-SH-300"
    text = c.say(f"{typed} x 1", stock(product(typed, 1)))
    assert a_code in text and "Size: 300 mm" in text, text  # control: the class the key scopes still matches
    assert "Size: 300 mm" not in _entry(text, b_code), f"the other class's product was matched on the key: {text!r}"


# --------------------------------------------------------------------------- slice 4 round 3


#: Parser orders of a message naming several product codes and a size. The size-miss rule applies only to a message
#: that names exactly one product code; these keep main's behaviour whichever order the parser emits.
ORDERS = {
    "size_after_fam": lambda zqx, fam, size: [zqx, fam, size],
    "size_after_zqx": lambda zqx, fam, size: [fam, zqx, size],
    "size_before_both": lambda zqx, fam, size: [size, zqx, fam],
    "two_sizes_two_codes": lambda zqx, fam, size: [zqx, dict(size, raw="300mm"), fam, size],
}


@pytest.mark.parametrize("held", [True, False], ids=["300_held", "300_not_held"])
@pytest.mark.parametrize("order", list(ORDERS))
@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4d_several_codes_and_a_size_keep_mains_behaviour_and_answer_the_unrelated_code(session_factory, monkeypatch, stub_access, who, order, held):  # noqa: F811
    other = "ZQX5521"  # in stock, another class, nothing stored, no size relation
    c = _size_console(
        session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300 if held else 250}},
        other_class={other: "bm"},
    )
    c.outcomes[other] = Stock(on_hand=100)
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    head, size = _head_and_size(300, "mm")
    entities = ORDERS[order](product(other, 2), head, size)
    text = c.say(f"{other} x 2, {FAM} 300mm", stock(*entities))
    if who == "dealer":
        assert f"{other} x 2: {TICK} Got stock." in text, text
    else:
        assert f"*Product Code:* {other}" in text, text
    # Never a "Couldn't find" naming a code that exists, the unrelated one included.
    assert not re.search(rf"Couldn't find:? \"?({other}|{re.escape(FAM)})", text), text
    assert other not in _option_codes(c), c.stored_question
    assert not re.search(rf"\d+[.)]\s+{other}", text), f"offered back to itself: {text!r}"


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4e_a_code_typed_with_spaces_and_a_size_takes_the_same_path(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM, FAM_300], {FAM_300: {"zz_size": 300}})
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    spaced = "twc8152 sh uf"
    text = c.say(f"{spaced} 400mm stock", _head_plus_size(400, "mm", spaced))
    _header(text, who, FAM, "400 mm")
    assert "None with size" not in text, text
    assert "Size: 300 mm" in _entry(text, FAM_300) and "Size: not recorded" in _entry(text, FAM), text
    assert "Stock summary" not in text and "How many units of" not in text and TICK not in text, text


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac4e_a_spaced_code_alone_in_its_family_is_offered_with_size_not_recorded(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM], {})
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    spaced = "twc8152 sh uf"
    text = c.say(f"{spaced} 400mm stock", _head_plus_size(400, "mm", spaced))
    _single_miss_header(text, who, FAM, "400 mm")
    assert "Size: not recorded" in text, text
    assert text.count(FAM) >= 2, text
    assert "How many units of" not in text and "Stock summary" not in text and TICK not in text, text


def test_ac26b_a_bare_centimetre_size_still_searches_the_millimetre_dimension_keys(session_factory):  # noqa: F811
    """No class is known. The registry holds an mm length key (centimetres written as 10 mm through its aliases,
    `matches_bare_size`) and a cm key scoped to ANOTHER class: "15cm" grounds as 150 mm over the mm dimension
    keys, as it did before the slice. Adding the cm key beside it is allowed; dropping the mm search is not."""
    from app.models.base import set_company_scope
    from app.services.chatbot.head.bare_size import ground_bare
    from app.services.company_scope import DEFAULT_COMPANY_ID

    db = session_factory()
    try:
        db.add_all(
            [
                ProductSpecRegistry(
                    id=str(uuid.uuid4()), spec_key="zz_dim_len", label="Length", data_type="numeric", unit="mm",
                    unit_aliases={"cm": 10}, synonyms={"_self": ["length"]},
                ),
                ProductSpecRegistry(
                    id=str(uuid.uuid4()), spec_key="zz_cm_other", label="Other", data_type="numeric", unit="cm",
                    synonyms={"_self": ["other"]}, applies_when={"class": ["bm"]},
                ),
            ]
        )
        db.flush()
        db.execute(sql_text("UPDATE product_spec_registry SET matches_bare_size = true WHERE spec_key IN ('zz_dim_len', 'zz_cm_other')"))
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        entity = {"raw": "15cm", "hint": "specification", "spec_key": "size", "spec_value": 15, "spec_unit": "cm"}
        grounded = ground_bare(db, entity, [entity], None, None)
    finally:
        db.close()
    assert grounded is not None, "a bare 15cm grounded to nothing"
    assert grounded.value == 150 and str(grounded.unit).casefold() == "mm", grounded
    assert "zz_dim_len" in (grounded.any_keys or []), grounded


@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_ac20h_a_discontinued_code_is_not_offered_back_by_the_size_miss(session_factory, monkeypatch, stub_access, who):  # noqa: F811
    """The family has one code, discontinued, and no other offerable code: the size miss cannot offer it back."""
    c = _size_console(session_factory, monkeypatch, stub_access, [FAM], {})
    db = session_factory()
    try:
        db.execute(sql_text("UPDATE products SET is_discontinued = true WHERE product_code = :c"), {"c": FAM})
        db.commit()
    finally:
        db.close()
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say(f"{FAM} 400mm stock", _head_plus_size(400, "mm"))
    at = text.find("Did you mean")
    assert FAM not in (text[at:] if at >= 0 else ""), f"offered back: {text!r}"
    assert FAM not in str(c.stored_question), c.stored_question
    # Lead sign-off: nothing offerable is still a size miss, never an answer for a size the code does not store (R4).
    assert text.startswith(f"Couldn't find {FAM} with size 400 mm") and "How many units" not in text and TICK not in text and "Stock summary" not in text, text


# --------------------------------------------------------------------------- live pass A-92: a size beside a corrected code

CORRECTED, WITH_SIZE = "SRTWC8516-SH-UF", "SRTWC8516-300-SH-UF"


def _typed_with_correction(corrected: bool) -> dict[str, Any]:
    """"Wc8516-sh-UF 300mm" as the live parser reads it: the product entity (with its own correction to the code
    without 300, or with none) plus the 300 mm size."""
    head = {
        "raw": "Wc8516-sh-UF", "hint": "product", "canonical_code": CORRECTED if corrected else None,
        "current_message": True, "confident": True,
    }
    _head, size = _head_and_size(300, "mm")
    return stock(head, size)


def _order_after_header(text: str, codes: list[str]) -> list[str]:
    at = text.find("Did you mean")
    tail = text[at:] if at >= 0 else text
    found = sorted((tail.find(c), c) for c in codes if tail.find(c) >= 0)
    return [c for _pos, c in found]


@pytest.mark.parametrize("stored", ["size_stored", "nothing_stored"])
@pytest.mark.parametrize("corrected", [True, False], ids=["parser_correction", "no_correction"])
@pytest.mark.parametrize("who", ["dealer", "staff"])
def test_a92_a_size_beside_a_code_that_does_not_hold_it_offers_the_code_that_does(session_factory, monkeypatch, stub_access, who, corrected, stored):  # noqa: F811
    c = _size_console(
        session_factory, monkeypatch, stub_access, [CORRECTED, WITH_SIZE],
        {WITH_SIZE: {"zz_size": 300}} if stored == "size_stored" else {},
    )
    _closed_lists(monkeypatch)
    if who == "staff":
        _as_staff(c)
    text = c.say("Wc8516-sh-UF 300mm stock", _typed_with_correction(corrected))
    assert "How many units of" not in text and "Stock summary" not in text and TICK not in text, f"answered: {text!r}"
    assert WITH_SIZE in text, text
    if stored == "size_stored":
        assert "Size: 300 mm" in text, text
    else:
        assert "Size: not recorded" in text, text
        order = _order_after_header(text, [WITH_SIZE, CORRECTED])
        assert order[:1] == [WITH_SIZE], (order, text)
