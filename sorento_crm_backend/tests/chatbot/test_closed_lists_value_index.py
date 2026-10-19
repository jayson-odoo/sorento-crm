"""F3-a ONE VALUE INDEX (crew ruling a30139843 (a); plan "F3-a acceptance" A1-A5; ZZ synthetic data).

Every spec line under a word of the message comes from one registry-driven index of (key, value)
pairs, each carrying its data support: how many chat-searchable products in the contact's scope hold
it, and how many of the held family do (A1). Under one word the lines of different keys rank by data:
the held family's key first, then the most held, then key name as a stable tiebreak, for a size AND
for an enum phrase two keys share (A2). Every holding key keeps its line; the per-word cap no longer
cuts spec lines (A3). A size no key holds offers every key of its unit, uncut (A4). Code and near-code
rows keep the cap (ruling a29691875 (2)(a)); the bare-size line, boolean phrases, hidden keys and the
contact's scope are unchanged (A5).

Seeding is real-shaped: the mm keys and `has_massage` are built from `SPEC_REGISTRY_SEED` with the
dev / prod overlay of crew/state/migrations/CHAT-CLOSED-LISTS-L.sql (`matches_bare_size` on dim_width
and dim_length, trap_length scoped to the Water Closet class); `product_specifications.values` stores a
size as a JSON number with its unit (an int, or a float the way a derived row writes one), an enum as
its JSON string slug and a yes as JSON true. The public seam is `candidates.shortlist(db, message,
held_ids, hidden=...)` read through `candidates.candidate_lines`.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event

import app.main  # noqa: F401  isort:skip
from app.models.base import set_company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.chatbot.head import candidates
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.product_spec_registry import SPEC_REGISTRY_SEED
from tests._pg_fixture import blank_session, unique_code

OTHER_COMPANY = "00000000-0000-0000-0000-000000000002"
#: Every mm key the shipped registry carries, in key-name order.
MM_KEYS = ("depth", "diameter", "dim_height", "dim_length", "dim_width", "hose_length", "thickness", "trap_length")
#: The data overlay on the seed (crew/state/migrations/CHAT-CLOSED-LISTS-L.sql).
BARE_SIZE_KEYS = frozenset({"dim_width", "dim_length"})
APPLIES_WHEN = {"trap_length": {"class": ["Water Closet"]}}
_SEED_FIELDS = (
    "label", "data_type", "unit", "allowed_values", "synonyms", "applies_when", "measured_coverage",
    "rank_weight", "match_tolerance", "match_decay",
)


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        from app.models.company import Company

        session.add(Company(id=OTHER_COMPANY, name="Other", code=unique_code("OTH")[:20]))
        session.flush()
        yield session


# --- seeding --------------------------------------------------------------------------------


def _seed_keys(db, *keys: str) -> None:
    """Registry rows exactly as the shipped seed has them, plus the dev / prod data overlay."""
    shipped = {entry["spec_key"]: entry for entry in SPEC_REGISTRY_SEED}
    for key in keys:
        entry = shipped[key]
        fields = {name: entry[name] for name in _SEED_FIELDS if name in entry}
        if key in APPLIES_WHEN:
            fields["applies_when"] = APPLIES_WHEN[key]
        db.add(ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key=key, matches_bare_size=key in BARE_SIZE_KEYS, source="seed", **fields,
        ))
    db.flush()


def _enum(db, key: str, label: str, values: list[str], synonyms: dict[str, list[str]] | None = None) -> None:
    db.add(ProductSpecRegistry(
        id=str(uuid.uuid4()), spec_key=key, label=label, data_type="enum", allowed_values=values,
        synonyms=synonyms or {}, source="seed",
    ))
    db.flush()


def _stored(key: str, value) -> dict:
    """One `product_specifications.values` entry the way a real row stores it."""
    if key in MM_KEYS:
        return {"value": value, "unit": "mm"}
    return {"value": value}


def _products(db, rows, *, company_id: str = DEFAULT_COMPANY_ID, searchable: bool = True) -> dict[str, str]:
    """rows: (code, {key: value}). family_code comes from the ORM listener (head of the code)."""
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", company_id=company_id,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=company_id)
    db.add_all([cat, uom])
    db.flush()
    ids: dict[str, str] = {}
    for code, values in rows:
        product = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name of {code}", category_id=cat.id,
            base_uom_id=uom.id, list_price=1, company_id=company_id, is_searchable=searchable,
        )
        db.add(product)
        db.flush()
        ids[code] = product.id
        db.add(ProductSpecifications(
            id=str(uuid.uuid4()), product_id=product.id, values={k: _stored(k, v) for k, v in values.items()},
        ))
    db.flush()
    return ids


def _scoped(db) -> None:
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))


def _lines(db, message: str, held: list[str] | None = None, hidden: frozenset[str] = frozenset()) -> list[str]:
    return candidates.candidate_lines(candidates.shortlist(db, message, held, hidden=hidden))


def _items(db, message: str, gram: str, held: list[str] | None = None, hidden: frozenset[str] = frozenset()) -> list[str]:
    """The items of the line for `gram`, in order; [] when the word has no line."""
    lines = _lines(db, message, held, hidden)
    head = f'- "{gram}": '
    line = next((ln for ln in lines if ln.startswith(head)), None)
    return line[len(head):].split("; ") if line else []


#: Six mm keys hold 450, with distinct support: thickness 3, dim_width 2 (one stored as a float),
#: depth / diameter / dim_height / dim_length 1 each; hose_length and trap_length hold other numbers.
HOLDS_450 = (
    ("ZZK450-A", {"thickness": 450, "dim_width": 450}),
    ("ZZK451-B", {"thickness": 450, "dim_width": 450.0}),
    ("ZZK452-C", {"thickness": 450, "depth": 450}),
    ("ZZK453-D", {"diameter": 450, "dim_height": 450}),
    ("ZZK454-E", {"dim_length": 450, "trap_length": 300, "hose_length": 500}),
)
SIX_HOLDING_BY_DATA = ("thickness", "dim_width", "depth", "diameter", "dim_height", "dim_length")


def _seed_shared_phrase(db) -> None:
    """"ivory" is a value of two keys (a colour word on zz_colour and zz_finish)."""
    _enum(db, "zz_colour", "Colour", ["ivory", "charcoal"])
    _enum(db, "zz_finish", "Finish", ["ivory", "satin"], {"satin": ["satin matt"]})


def _spec_item(items: list[str], key: str) -> int:
    return next((n for n, item in enumerate(items) if item.startswith(f"spec {key} = ")), -1)


# --- reds -----------------------------------------------------------------------------------


def test_r1_every_mm_key_that_holds_the_size_has_its_line_none_cut(db):
    """A3. Fails on HEAD: `shortlist` cuts the word's items to CAP_PER_WORD (5), so with the bare-size
    line first only four of the six holding keys survive (dim_length is lost)."""
    _seed_keys(db, *MM_KEYS)
    _products(db, HOLDS_450)
    _scoped(db)

    items = _items(db, "got 450mm ones?", "450mm")

    assert items[0] == "size 450 mm (no dimension named)", items
    assert [i for i in items if i.startswith("spec ")] == [f"spec {key} = 450" for key in SIX_HOLDING_BY_DATA], items


def test_r2_a_shared_enum_phrase_lists_the_more_held_key_first_though_its_name_sorts_later(db):
    """A2. Fails on HEAD: an enum phrase's lines keep registry (key name) order, so zz_colour, held
    by one product, is listed before zz_finish, held by three."""
    _seed_shared_phrase(db)
    _products(db, (
        ("ZZMB201", {"zz_colour": "ivory"}),
        ("ZZMB305", {"zz_finish": "ivory"}),
        ("ZZMB409", {"zz_finish": "ivory"}),
        ("ZZMB512", {"zz_finish": ["satin", "ivory"]}),  # a list value, as real rows store two finishes
    ))
    _scoped(db)

    items = _items(db, "any ivory ones in stock", "ivory")

    finish, colour = _spec_item(items, "zz_finish"), _spec_item(items, "zz_colour")
    assert finish >= 0 and colour >= 0, items
    assert finish < colour, items


def test_r3_a_shared_enum_phrase_lists_the_held_familys_key_first_though_fewer_hold_it(db):
    """A2. Fails on HEAD (registry name order puts zz_colour first) and against a count-only
    ranking (zz_colour is held by three products, zz_finish by one): the held family's sibling
    ZZVC100-IV holds zz_finish = ivory, so zz_finish comes first."""
    _seed_shared_phrase(db)
    ids = _products(db, (
        ("ZZVC100", {"zz_finish": "satin"}),
        ("ZZVC100-IV", {"zz_finish": "ivory"}),
        ("ZZMB201", {"zz_colour": "ivory"}),
        ("ZZMB305", {"zz_colour": "ivory"}),
        ("ZZMB409", {"zz_colour": "ivory"}),
    ))
    _scoped(db)

    items = _items(db, "same one but ivory", "ivory", held=[ids["ZZVC100"]])

    finish, colour = _spec_item(items, "zz_finish"), _spec_item(items, "zz_colour")
    assert finish >= 0 and colour >= 0, items
    assert finish < colour, items


def test_r4_a_size_no_key_holds_offers_every_key_of_its_unit_in_name_order_uncut(db):
    """A4. Fails on HEAD: the `or keys` fallback lists the unit's keys in name order and the
    per-word cut keeps the first five of the eight."""
    _seed_keys(db, *MM_KEYS)
    _products(db, HOLDS_450)
    _scoped(db)

    items = _items(db, "need a 999 mm one", "999 mm")

    assert items == [f"spec {key} = 999" for key in MM_KEYS], items


@contextmanager
def _spec_reads(db):
    """Every SELECT the session sends that reads product_specifications, while the block runs."""
    seen: list[str] = []
    engine = db.get_bind().engine

    def before(conn, cursor, statement, parameters, context, executemany):
        sql = statement.lstrip().upper()
        if "PRODUCT_SPECIFICATIONS" in sql and sql.startswith(("SELECT", "WITH")):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", before)


def test_r5_one_scoped_count_query_per_message_for_every_pair(db):
    """A1. Fails on HEAD: each size word costs its own count query (two here, one for the bare-size
    keys and one for the unit's keys, per word: four), and the shared enum phrase none."""
    _seed_keys(db, *MM_KEYS)
    _seed_shared_phrase(db)
    ids = _products(db, (
        *HOLDS_450,
        ("ZZK600-F", {"dim_width": 600}),
        ("ZZMB201", {"zz_colour": "ivory"}),
        ("ZZMB305", {"zz_finish": "ivory"}),
    ))
    _scoped(db)

    with _spec_reads(db) as seen:
        lines = _lines(db, "600mm by 450 mm, ivory finish?", held=[ids["ZZK450-A"]])

    assert any(ln.startswith('- "ivory": ') for ln in lines), lines  # the listener saw a real call
    assert len(seen) <= 1, (len(seen), seen)


# --- guards (pass on HEAD) ------------------------------------------------------------------


def test_guard_code_and_near_code_rows_keep_the_per_word_cap(db):
    """Ruling a29691875 (2)(a): code rows are #1761's; seven codes hold the word, seven are spelt near it."""
    _products(db, (
        *((f"ZZQ4417-{n:02d}", {}) for n in range(1, 8)),
        *((f"ZZR8812{letter}", {}) for letter in "ABCDEFG"),
    ))
    _scoped(db)

    holding = _items(db, "price for zzq4417 pls", "zzq4417")
    near = _items(db, "price for zzr88123 pls", "zzr88123")

    assert len(holding) == candidates.CAP_PER_WORD and all(i.startswith("code ZZQ4417-") for i in holding), holding
    assert len(near) == candidates.CAP_PER_WORD and all(i.startswith("near code ZZR8812") for i in near), near


def test_guard_the_bare_size_line_is_first_when_a_flagged_key_holds_the_number(db):
    _seed_keys(db, *MM_KEYS)
    _products(db, (("ZZBW600", {"dim_width": 600, "dim_height": 850}),))
    _scoped(db)

    assert _items(db, "a 600mm one?", "600mm") == ["size 600 mm (no dimension named)", "spec dim_width = 600"]


def test_guard_a_boolean_phrase_line_is_unchanged(db):
    _seed_keys(db, "has_massage")
    _products(db, (("ZZTB770", {"has_massage": True}),))
    _scoped(db)

    assert '- "jetted": spec has_massage = true (Massage jets)' in _lines(db, "any jetted tub in stock")


def test_guard_a_hidden_key_is_never_named_on_a_size_or_a_shared_phrase(db):
    _seed_keys(db, *MM_KEYS)
    _seed_shared_phrase(db)
    _products(db, (*HOLDS_450, ("ZZMB201", {"zz_colour": "ivory"}), ("ZZMB305", {"zz_finish": "ivory"})))
    _scoped(db)

    sizes = _lines(db, "got 450mm ones?", hidden=frozenset({"dim_height"}))
    phrase = _lines(db, "any ivory ones in stock", hidden=frozenset({"zz_finish"}))

    assert any(ln.startswith('- "450mm": ') for ln in sizes), sizes
    assert not any("dim_height" in ln for ln in sizes), sizes
    assert any(ln.startswith('- "ivory": ') and "zz_colour" in ln for ln in phrase), phrase
    assert not any("zz_finish" in ln for ln in phrase), phrase


def test_guard_a_product_outside_the_scope_or_not_chat_searchable_does_not_count(db):
    """Four OTHER-company products and two non-searchable ones hold depth = 12; one in-scope product
    holds thickness = 12. Only thickness holds the size for this contact."""
    _seed_keys(db, *MM_KEYS)
    _products(db, (("ZZSC12-A", {"thickness": 12}),))
    _products(db, tuple((f"ZZSC12-{s}", {"depth": 12}) for s in "BCDE"), company_id=OTHER_COMPANY)
    _products(db, (("ZZSC12-F", {"depth": 12}), ("ZZSC12-G", {"depth": 12})), searchable=False)
    _scoped(db)

    assert _items(db, "a 12mm panel", "12mm") == ["spec thickness = 12"]


def test_guard_a_product_type_stays_ahead_of_a_spec_under_the_same_phrase(db):
    """A2: product type before spec stays, even when more products hold the spec."""
    _enum(db, "product_type", "Product type", ["zz_pedestal_basin"], {"zz_pedestal_basin": ["pedestal"]})
    _enum(db, "zz_mounting", "Mounting", ["pedestal", "wall_hung"])
    _products(db, (
        ("ZZPD100", {"product_type": "zz_pedestal_basin", "zz_mounting": "pedestal"}),
        ("ZZPD200", {"zz_mounting": "pedestal"}),
        ("ZZPD300", {"zz_mounting": "pedestal"}),
    ))
    _scoped(db)

    items = _items(db, "pedestal ones?", "pedestal")

    assert items[0].startswith("product type "), items
    assert _spec_item(items, "zz_mounting") > 0, items


# --- after F3-a: the lead's rulings on what stays (20 Oct) ------------------------------------


def test_guard_an_enum_value_no_product_holds_keeps_its_line_after_the_holders(db):
    """Lead ruling on ambiguity 1: a value no product holds is still listed, ranked after the
    keys that hold it (a shared phrase), and alone (a phrase of one key)."""
    _seed_shared_phrase(db)
    _products(db, (("ZZMB305", {"zz_finish": "ivory"}), ("ZZMB409", {"zz_finish": "ivory"})))
    _scoped(db)

    lines = _lines(db, "ivory or charcoal ones")

    assert '- "ivory": spec zz_finish = ivory (Ivory); spec zz_colour = ivory (Ivory)' in lines, lines
    assert '- "charcoal": spec zz_colour = charcoal (Charcoal)' in lines, lines


def test_r6_near_spellings_keep_the_per_word_cap_while_exact_holding_lines_stay_uncut(db):
    """A3 exempts only the EXACT spec lines of keys that hold the value: near rows (spec and code
    together) still share CAP_PER_WORD, as before F3-a. Seven board keys share the phrase
    "450x450mm", spelt near the size word "450mm", whose six holding mm keys keep every line."""
    _seed_keys(db, *MM_KEYS)
    for n in range(1, 8):
        _enum(db, f"zz_board_size_{n}", f"Board size {n}", ["450x450mm"])
    _products(db, HOLDS_450)
    _scoped(db)

    items = _items(db, "got 450mm ones?", "450mm")

    near = [i for i in items if i.startswith("near ")]
    assert [i for i in items if i.startswith("spec ")] == [f"spec {key} = 450" for key in SIX_HOLDING_BY_DATA], items
    assert near, items  # the seven near spellings are found at all
    assert len(near) <= candidates.CAP_PER_WORD, (len(near), items)


def test_r7_a_list_valued_spec_counts_for_each_of_its_values(db):
    """Real rows store a LIST for a product with two values (SRTWT9605-RG "Rose Gold + Matt Black";
    product_spec_search.py `_states` and the containment branch of `filter_specs`). Fails on HEAD:
    the value index compares `lower(values->key->>'value')` with the value, so a list never counts
    and zz_colour (one scalar holder) ranks ahead of zz_finish (three list holders)."""
    _seed_shared_phrase(db)
    _products(db, (
        ("ZZLV101", {"zz_finish": ["ivory", "satin"]}),
        ("ZZLV102", {"zz_finish": ["satin", "ivory"]}),
        ("ZZLV103", {"zz_finish": ["ivory"]}),
        ("ZZLV201", {"zz_colour": "ivory"}),
    ))
    _scoped(db)

    items = _items(db, "got these in ivory?", "ivory")

    finish, colour = _spec_item(items, "zz_finish"), _spec_item(items, "zz_colour")
    assert finish >= 0 and colour >= 0, items
    assert finish < colour, items
