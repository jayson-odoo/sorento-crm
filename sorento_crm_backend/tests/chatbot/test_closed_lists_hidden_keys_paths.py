"""H1b HIDDEN-KEYS-AT-THE-PATHS (security review of H1; crew ruling a29310107 (3)(a) and R6-6:
"a contact-hidden key never filters, narrows or prints on any path"; ZZ data).

The hidden set is applied once at each ENTRY: the candidate block (H1), the GROUNDING OUTPUT (not
only the raw parse, which H1 strips before grounding rebuilds a hidden key from the raw words), and
the Shape B route entry (the unknown-value branch returns before the route's hidden drop).

B1 / B3 run whole turns with the real `spec_visibility_policies` read through head/access (as
test_closed_lists_hidden_keys_entries.py does) and read the verdict APPLY recorded. B2 calls the
resolve route in process, as the business lane does (`lanes/business/services._resolve_entity`),
with the `hidden_spec_keys` the lane sends.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_hidden_keys_entries import _hide, _run
from tests.chatbot.test_closed_lists_spec_over_held import _stock_ask
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

BASIN = "ZZ Wash Basin"


# --- B1 / B3: the grounding output ----------------------------------------------------------


def _seed(session_factory) -> None:
    """A ZZ basin class, a colour key (the one the contact hides) and a finish key (visible)."""
    db = session_factory()
    db.add_all([
        ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key="class", label="Class", data_type="enum", allowed_values=[],
            synonyms={BASIN: ["zz basin", "zzbasin"]},
        ),
        ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key="zz_colour", label="Colour", data_type="enum",
            allowed_values=["ivory", "charcoal"], synonyms={"ivory": ["ivory", "cream"]},
        ),
        ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key="zz_finish", label="Finish", data_type="enum",
            allowed_values=["matt", "gloss"], synonyms={"matt": ["matt", "matte"]},
        ),
    ])
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("C")[:50], category_name=BASIN, class_label=BASIN,
        company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    db.add_all([cat, uom])
    db.flush()
    for code, values in (
        ("ZZHB-IV", {"zz_colour": "ivory", "zz_finish": "gloss"}),
        ("ZZHB-CH", {"zz_colour": "charcoal", "zz_finish": "matt"}),
    ):
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name {code}", category_id=cat.id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(p)
        db.flush()
        db.add(ProductSpecifications(
            id=str(uuid.uuid4()), product_id=p.id,
            values={"class": {"value": BASIN}, **{k: {"value": v} for k, v in values.items()}},
        ))
    db.commit()


def _ent(raw: str, hint: str, **kw) -> dict:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True, **kw}


def _applied(records) -> list[dict]:
    """The entities of the verdict APPLY read (the one every lane and tool call is built from)."""
    applied = [r for r in records if r.get("kind") == "apply"]
    assert applied, [r.get("kind") or r.get("stage") for r in records]
    return [e for e in (applied[-1].get("verdict") or {}).get("entities") or [] if isinstance(e, dict)]


def _keys(entities: list[dict]) -> list[str]:
    return [str(e.get("spec_key") or "").strip() for e in entities]


def _turn(session_factory, stub_access, monkeypatch, message: str, *entities: dict) -> list[dict]:
    _block, records = _run(session_factory, stub_access, monkeypatch, message, _stock_ask(*entities))
    return _applied(records)


def test_b1_a_spec_on_a_visible_key_whose_raw_word_is_a_hidden_value_never_grounds_to_the_hidden_key(
    session_factory, seeded, stub_access, monkeypatch
):
    """`_validate` -> `ground_words` reads the unfiltered registry: the parser put "ivory" on
    zz_finish (no such finish), and grounding rebuilds it from the raw word as zz_colour."""
    _seed(session_factory)
    _hide(session_factory, "zz_colour")

    entities = _turn(
        session_factory, stub_access, monkeypatch, "any ivory zz basin in stock",
        _ent("zz basin", "category"), _ent("ivory", "specification", spec_key="zz_finish", spec_value="ivory"),
    )

    assert "zz_colour" not in _keys(entities), entities


def test_b1_a_class_word_holding_a_hidden_value_never_grounds_to_the_hidden_key(session_factory, seeded, stub_access, monkeypatch):
    """The class-hint path: the parser emits NO spec entity; grounding splits "cream" off the
    category's raw words with the unfiltered registry and makes it zz_colour = ivory."""
    _seed(session_factory)
    _hide(session_factory, "zz_colour")

    entities = _turn(session_factory, stub_access, monkeypatch, "cream zz basin got?", _ent("cream zz basin", "category"))

    assert "zz_colour" not in _keys(entities), entities


def test_b3_a_hidden_spec_key_with_whitespace_round_it_is_stripped_too(session_factory, seeded, stub_access, monkeypatch):
    """The raw-parse strip compares the key exactly; grounding binds on the stripped key."""
    _seed(session_factory)
    _hide(session_factory, "zz_colour")

    entities = _turn(
        session_factory, stub_access, monkeypatch, "ivory zz basin pls",
        _ent("zz basin", "category"), _ent("ivory", "specification", spec_key=" zz_colour ", spec_value="ivory"),
    )

    assert "zz_colour" not in _keys(entities), entities


def test_guard_a_visible_key_still_grounds_from_the_raw_words(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)
    _hide(session_factory, "zz_colour")

    entities = _turn(session_factory, stub_access, monkeypatch, "matte zz basin got?", _ent("matte zz basin", "category"))

    assert any(e.get("spec_key") == "zz_finish" and e.get("spec_value") == "matt" for e in entities), entities


def test_guard_a_contact_with_no_policy_still_grounds_the_colour(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory)

    entities = _turn(session_factory, stub_access, monkeypatch, "cream zz basin got?", _ent("cream zz basin", "category"))

    assert any(e.get("spec_key") == "zz_colour" and e.get("spec_value") == "ivory" for e in entities), entities


# --- B2: the Shape B route entry, unknown-value branch ---------------------------------------


@pytest.fixture
def route_db():
    """The shipped registry (trap_type's P trap / S trap; thickness default-hidden) and four ZZ
    water closets: two P trap, two S trap; one P trap is 25 mm thick, one of each trap is white."""
    from app.services.product_class_signal import backfill_category_signals
    from app.services.product_spec_registry import seed_spec_registry

    with blank_session() as db:
        cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code("WC")[:50], category_name="ZZ WC", class_label="Water Closet",
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each")
        db.add_all([cat, uom])
        db.flush()
        backfill_category_signals(db)
        seed_spec_registry(db)
        for code, trap, thick, finish in (
            ("ZZHW-P1", "p_trap", 25, "white"), ("ZZHW-P2", "p_trap", None, None),
            ("ZZHW-S1", "s_trap", None, "white"), ("ZZHW-S2", "s_trap", None, None),
        ):
            p = Product(
                id=str(uuid.uuid4()), product_code=code, product_name=f"ZZ closet {code}", category_id=cat.id,
                base_uom_id=uom.id, list_price=Decimal("1.00"),
            )
            db.add(p)
            db.flush()
            values = {"class": {"value": "Water Closet"}, "trap_type": {"value": trap}}
            if thick is not None:
                values["thickness"] = {"value": thick, "unit": "mm"}
            if finish is not None:
                values["finish"] = {"value": finish}
            db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=p.id, values=values))
        db.flush()
        yield db


def _resolve(db, query: str, hidden: list[str], **extra) -> dict:
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings

    body = {
        "query": query, "require": {"stock": True}, "scope_terms": ["water closet"], "hidden_spec_keys": hidden,
        "understand_phrase": False, **extra,
    }
    principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
    return resolve_reference_post(ResolveReferenceRequest(**body), current_user=principal, db=db)


HIDDEN_TRAP_WORDS = ("trap_type", "p_trap", "s_trap", "P trap", "S trap", '"Trap"')


def test_b2_an_unknown_value_on_a_hidden_key_gives_no_breakdown_naming_the_key_or_its_values(route_db):
    """references.py's unknown-value branch returns before the hidden drop: `unknown_spec_values`
    reads the full registry and `_unknown_value_members` breaks the set down by trap_type."""
    result = _resolve(route_db, "which water closet t trap has stock", ["trap_type", "thickness", "board_thickness"])

    said = json.dumps(result.get("predicate") or {}, default=str)
    assert not [w for w in HIDDEN_TRAP_WORDS if w in said], said


def test_b2_a_hidden_enum_key_in_the_same_message_does_not_narrow_the_counted_members(route_db):
    """trap_type is visible (the unknown value is said back with its breakdown), finish is hidden:
    `_unknown_value_members` binds "white" off the query with the full registry, so the four water
    closets are counted as the two white ones and the description names the hidden finish."""
    result = _resolve(route_db, "which white water closet t trap has stock", ["finish", "thickness", "board_thickness"])

    predicate = result.get("predicate") or {}
    assert (predicate.get("members") or {}).get("total") == 4, predicate
    assert '"finish"' not in json.dumps(predicate, default=str), predicate


def test_guard_a_hidden_thickness_in_the_same_message_does_not_narrow_the_counted_members(route_db):
    """The lead's numeric shape (default-hidden thickness): measured on HEAD, a numeric spec does not
    cut this branch's member count, so it is a guard; the enum shape above is the red."""
    result = _resolve(route_db, "which water closet t trap 25mm thick has stock", ["thickness", "board_thickness"])

    predicate = result.get("predicate") or {}
    assert (predicate.get("members") or {}).get("total") == 4, predicate
    assert "thickness" not in json.dumps(predicate, default=str), predicate


def test_guard_an_unknown_value_on_a_visible_key_keeps_its_breakdown(route_db):
    result = _resolve(route_db, "which water closet t trap has stock", ["thickness", "board_thickness"])

    predicate = result.get("predicate") or {}
    assert [u.get("key") for u in predicate.get("unknown_values") or []] == ["trap_type"], predicate
    assert (predicate.get("members") or {}).get("total") == 4, predicate
    assert "P trap" in json.dumps(predicate.get("members") or {}, default=str), predicate


# --- B4: a keyless unknown value picks its own splitting attribute ---------------------------


@pytest.fixture
def split_db():
    """Four ZZ water closets whose FIRST splitting attribute in registry order is finish (white /
    black), with trap_type (P / S) splitting them later; brand and class split nothing."""
    from app.services.product_class_signal import backfill_category_signals
    from app.services.product_spec_registry import seed_spec_registry

    with blank_session() as db:
        cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code("WC")[:50], category_name="ZZ WC", class_label="Water Closet",
        )
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each")
        db.add_all([cat, uom])
        db.flush()
        backfill_category_signals(db)
        seed_spec_registry(db)
        for code, trap, finish in (
            ("ZZHX-P1", "p_trap", "white"), ("ZZHX-P2", "p_trap", "black"),
            ("ZZHX-S1", "s_trap", "white"), ("ZZHX-S2", "s_trap", "black"),
        ):
            p = Product(
                id=str(uuid.uuid4()), product_code=code, product_name=f"ZZ closet {code}", category_id=cat.id,
                base_uom_id=uom.id, list_price=Decimal("1.00"),
            )
            db.add(p)
            db.flush()
            db.add(ProductSpecifications(
                id=str(uuid.uuid4()), product_id=p.id,
                values={"class": {"value": "Water Closet"}, "trap_type": {"value": trap}, "finish": {"value": finish}},
            ))
        db.flush()
        yield db


#: What the lane sends for a word grounding placed on no key ("pnk" in "pnk water closet").
KEYLESS = [{"key": "", "label": "", "said": "pnk", "known": []}]
HIDDEN_FINISH_WORDS = ('"finish"', "Finish or colour", "White", "Black")


def test_b4_a_keyless_unknown_never_breaks_the_set_down_by_a_hidden_key(split_db):
    """`_unknown_value_members` calls `resolve_product_set(..., breakdown_over=0)` for a keyless
    unknown, and `_set_breakdown` takes the first registry key that splits the set: the hidden
    finish. `unknown_values_reply` prints `members.breakdown` and `members.description`."""
    result = _resolve(split_db, "which pnk water closet has stock", ["finish", "thickness", "board_thickness"], unknown_values=KEYLESS)

    said = json.dumps(result.get("predicate") or {}, default=str)
    assert not [w for w in HIDDEN_FINISH_WORDS if w in said], said


def test_guard_a_keyless_unknown_for_a_contact_with_no_policy_breaks_down_by_finish(split_db):
    result = _resolve(split_db, "which pnk water closet has stock", ["thickness", "board_thickness"], unknown_values=KEYLESS)

    members = (result.get("predicate") or {}).get("members") or {}
    assert members.get("total") == 4, result.get("predicate")
    assert (members.get("breakdown") or {}).get("key") == "finish", members
