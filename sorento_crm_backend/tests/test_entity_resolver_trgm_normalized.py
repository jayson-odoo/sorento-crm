"""Tier-2.5 (pg_trgm) scores separator-normalized text, not raw columns.

n8n strips dashes and whitespace from every entity token before calling
`/api/v1/system/references/resolve`. The exact and prefix tiers already
normalize both sides; the trigram tier did not, so a stripped typo scored
against a column that kept its hyphen and collapsed - the live regression was
"STRWC286-SH" typed as "STRWC286SH", which returned ZERO did-you-mean
suggestions where the dash-kept spelling had suggested the right family.

Everything here seeds its own rows on a BLANK schema (CI's database has no
data), so the table each probe queries holds exactly what the test wrote.
"""
import uuid

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.order import Customer
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import entity_resolver as er
from tests._pg_fixture import blank_session

SORENTO = "00000000-0000-0000-0000-000000000001"
SCOPE = frozenset({SORENTO})


@pytest.fixture
def db():
    """Blank schema, plus pg_trgm's schema back on the search_path.

    `blank_session` pins search_path to the scratch schema so a raw-SQL write
    cannot escape into the real tables - which also drops the schema holding
    `similarity()` and the `%` operator, so every trigram probe would raise
    "function similarity(...) does not exist" and be swallowed by the probe's
    own except-block. Appending it LAST keeps the scratch schema winning for
    every table name, so the guard the fixture exists for still holds.
    """
    with blank_session() as session:
        trgm_schema = session.execute(
            text(
                "SELECT n.nspname FROM pg_extension e "
                "JOIN pg_namespace n ON n.oid = e.extnamespace "
                "WHERE e.extname = 'pg_trgm'"
            )
        ).scalar()
        if trgm_schema:
            current = session.execute(text("SHOW search_path")).scalar()
            session.execute(text(f'SET LOCAL search_path TO {current}, "{trgm_schema}"'))
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_products(db, codes: list[str]) -> dict[str, str]:
    cat = ProductCategory(id=_uid(), category_code=f"ZZTC{_uid()[:6]}", category_name="ZZT cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZTU{_uid()[:6]}", uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    out: dict[str, str] = {}
    for code in codes:
        row = Product(
            id=_uid(),
            product_code=code,
            product_name=f"ZZT {code}",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=1,
        )
        db.add(row)
        db.flush()
        out[code] = row.id
    return out


def _seed_customer(db, name: str) -> str:
    """Seed one customer IN SCOPE and return its code.

    `company_id` is set explicitly: the raw-SQL probes filter on
    `company_id::text = ANY(...)`, which a NULL never satisfies, so a customer
    seeded without one is invisible to every trigram probe.
    """
    code = f"ZZT{_uid()[:6]}"
    db.add(
        Customer(id=_uid(), customer_code=code, customer_name=name, company_id=SORENTO)
    )
    db.flush()
    return code


def _codes(hits) -> list[str]:
    return [h.canonical_code for h in hits if h.entity_type == "product"]


# --------------------------------------------------------------------------- #
# _norm_sql must stay in lockstep with its ORM twin and with migration 410
# --------------------------------------------------------------------------- #
def test_norm_sql_matches_the_orm_expression():
    from app.services.entity_resolver import _norm_sql, _ws_insensitive_lower

    compiled = str(
        _ws_insensitive_lower(Product.product_code).compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    # Same function, same character class, same flags - only the column spelling
    # differs (the ORM form qualifies it with the table name).
    assert _norm_sql("product_code") == "lower(regexp_replace(product_code, '[-\\s]+', '', 'g'))"
    assert "regexp_replace" in compiled and "'[-\\s]+'" in compiled


def test_norm_sql_matches_the_index_migration_expression():
    """A divergence here silently drops the functional index (back to seq scan)."""
    import importlib.util
    import pathlib

    from app.services.entity_resolver import _norm_sql

    migration = (
        pathlib.Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "410_trigram_indexes_separator_normalized.py"
    )
    spec = importlib.util.spec_from_file_location("m410", migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for _, _, column in module.INDEXES:
        assert module._norm(column) == _norm_sql(column)


# --------------------------------------------------------------------------- #
# The live regression
# --------------------------------------------------------------------------- #
def test_stripped_typo_below_the_raw_floor_still_surfaces(db):
    """A typo'd stripped token whose RAW similarity is under TRGM_THRESHOLD.

    Measured on Postgres: "zztwt7438gnxl" scores 0.231 against the stored
    "ZZT-WT-7438-GM-XL" and 0.647 against its stripped form. 0.231 is below the
    0.25 floor, so the raw-only probe could not surface this row at all - which
    is the shape of the live regression (zero did-you-mean suggestions).
    """
    _seed_products(db, ["ZZT-WT-7438-GM-XL"])
    with company_scope(db, SCOPE):
        hits = er._trgm_lookup(db, "zztwt7438gnxl", frozenset({"product"}))
    assert "ZZT-WT-7438-GM-XL" in _codes(hits)


def test_stripped_typo_surfaces_the_right_family(db):
    """The reported case: "STRWC286SH" (transposed AND stripped) suggests SRTWC286-SH."""
    _seed_products(db, ["SRTWC286-SH", "SRTWC286-SH-P", "SRTWC200", "SRTWC201"])
    with company_scope(db, SCOPE):
        hits = er._trgm_lookup(db, "STRWC286SH", frozenset({"product"}))
    assert "SRTWC286-SH" in _codes(hits)


def test_stripped_typo_ranks_the_right_family_above_the_wrong_one(db):
    """The dash-stripped query used to score the WRONG family higher (0.50 vs 0.643)."""
    _seed_products(db, ["SRTWC286-SH", "SRTWC200", "SRTWC201"])
    with company_scope(db, SCOPE):
        hits = er._trgm_lookup(db, "SRTWC2086SH", frozenset({"product"}))
    codes = _codes(hits)
    assert codes, "no trigram suggestions at all"
    assert codes[0] == "SRTWC286-SH", f"wrong family ranked first: {codes[:3]}"


@pytest.mark.parametrize(
    "token",
    ["SRTKT71SS", "SRTKT71-SS", "srtkt71ss", "SRTKT71 SS"],
    ids=["stripped", "dashed", "stripped-lower", "spaced"],
)
def test_every_separator_spelling_finds_the_same_neighbours(db, token):
    """A stored dashed code is reachable from every spelling of a near-miss token."""
    _seed_products(db, ["SRTKT71SS-BL", "SRTKT71SS-GM"])
    with company_scope(db, SCOPE):
        hits = er._trgm_lookup(db, token, frozenset({"product"}))
    assert set(_codes(hits)) >= {"SRTKT71SS-BL", "SRTKT71SS-GM"}, token


def test_a_spaced_stored_code_is_reachable_from_any_spelling(db):
    """Dropping the raw comparison costs nothing when the STORED value is spaced.

    Both sides are stripped, so a near-miss token finds the row whether the
    caller spells it with the stored spaces, with dashes, or with neither.
    """
    _seed_products(db, ["SRT WC 286 SH"])
    for token in ("SRT WC 286 SH2", "SRT-WC-286-SH2", "srtwc286sh2"):
        with company_scope(db, SCOPE):
            hits = er._trgm_lookup(db, token, frozenset({"product"}))
        assert "SRT WC 286 SH" in _codes(hits), token


def test_exact_normalized_self_is_excluded(db):
    """A code that IS the token (after stripping) is not offered as an alternative."""
    _seed_products(db, ["SRTWC286-SH", "SRTWC286-SH-P"])
    with company_scope(db, SCOPE):
        hits = er._trgm_lookup(db, "SRTWC286SH", frozenset({"product"}))
    assert "SRTWC286-SH" not in _codes(hits)
    assert "SRTWC286-SH-P" in _codes(hits)


# --------------------------------------------------------------------------- #
# Names, not just codes - the customer probe strips separators on both sides too
# --------------------------------------------------------------------------- #
def test_stripped_name_token_scores_against_the_stripped_customer_name(db):
    """Names, not just codes: the space-bearing column is stripped on its side too.

    Measured: "zztsinhonentrprisesdnbhd" scores 0.310 against the raw stored name
    and 0.821 against its stripped form. Both clear the 0.25 gate, so the teeth
    are in the SCORE - a raw-only probe ranks this row far below where it belongs.
    """
    code = _seed_customer(db, "ZZT SIN HON ENTERPRISE SDN BHD")
    with company_scope(db, SCOPE):
        hits = er._trgm_lookup(db, "zztsinhonentrprisesdnbhd", frozenset({"customer"}))
    # The customers branch emits customer_code as the canonical code, whichever
    # of the two columns scored - so identify the row by its code.
    sims = [h.similarity for h in hits if h.canonical_code == code]
    assert sims, "the seeded customer was not surfaced at all"
    assert max(sims) >= 0.75, f"scored on the raw name, not the stripped one: {sims}"


# --------------------------------------------------------------------------- #
# The variant-graph neighbour probe is scored the same way (SUGGEST_FLOOR)
# --------------------------------------------------------------------------- #
def test_variant_graph_sibling_survives_the_suggest_floor(db):
    """A curated sibling stored dashed must not be cut just because the caller stripped."""
    seeded = _seed_products(db, ["SRT-FH12-CR-DIY", "SRT-FH12-CR-DIY-BL"])
    parent = seeded["SRT-FH12-CR-DIY"]
    child = seeded["SRT-FH12-CR-DIY-BL"]
    db.query(Product).filter(Product.id == child).update({"variant_of_id": parent})
    db.flush()
    # Measured: "srtfh12crdiy" scores 0.280 against the raw sibling code and 0.750
    # against its stripped form. SUGGEST_FLOOR is 0.40, so the raw-only score put
    # a curated variant below the floor and the caller said "no similar products".
    with company_scope(db, SCOPE):
        out = er._find_entity_neighbours_with_data(
            db,
            "srtfh12crdiy",
            has_data=lambda ids: set(ids),
            limit=3,
            suggest_floor=er.SUGGEST_FLOOR,
        )
    assert [c["value"] for c in out] == ["SRT-FH12-CR-DIY-BL"]
