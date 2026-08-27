"""F11 / R16 - the supplier's own spelling of a product code, resolved by a ladder.

TEST-FIRST: `app/services/scm/supplier_code_matcher.py` does not exist at the time this file
is written, so every test here is expected to be red (ImportError) until it lands.

The codes are the real ones off the uploaded JINBAICHUAN list, and so are the traps. Token
reorder is safe (`SRTWC8357-RL-300` IS our `SRTWC8357-300-RL`). Dropping a trailing trap size
is NOT: it finds 28 and 16 of them are wrong, because `CWC7606-SH-180` is a different product
from `CWC7606-SH`, which is the 250. So that rung asks the base product's own description
whether it is the size the supplier wrote, and takes silence for a no.

Postgres via `pg_session` (rolled back at teardown), because the ladder's normalisation is
SQL - `entity_resolver._norm_sql`, the expression migration 410 indexes - and a Python copy
of it would be a second spelling of the one rule.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.company import Company
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet
from app.models.scm import SupplierProductCodeAlias
from app.services.company_scope import company_scope
from tests._pg_fixture import pg_session

MARKER = "ZZSCM"


def _u() -> str:
    return str(uuid.uuid4())


class World:
    """A supplier and a catalogue of our OWN codes, marker-prefixed so nothing collides with
    the prod copy this suite runs against."""

    def __init__(self, db):
        self.db = db
        self.tag = uuid.uuid4().hex[:8].upper()
        self.cat = ProductCategory(
            id=_u(), category_code=f"{MARKER}-C-{self.tag}", category_name=f"{MARKER} cat"
        )
        self.uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U-{self.tag}"[:20], uom_name="pcs")
        db.add_all([self.cat, self.uom])
        db.flush()
        self.supplier = Supplier(
            id=_u(), supplier_code=f"{MARKER}-S-{self.tag}",
            supplier_name=f"{MARKER} JINBAICHUAN", is_active=True,
        )
        db.add(self.supplier)
        db.flush()
        self.products: dict[str, Product] = {}

    def product(self, code: str, *, description: str | None = None) -> Product:
        """One of OUR products. `code` is spelled exactly as the catalogue holds it, with
        the marker prefixed so two suites cannot see each other's rows."""
        full = f"{MARKER}{self.tag}-{code}"
        if full not in self.products:
            p = Product(
                id=_u(), product_code=full, product_name=code, description=description,
                category_id=self.cat.id, base_uom_id=self.uom.id, list_price=0,
                is_active=True, is_discontinued=False,
            )
            self.db.add(p)
            self.db.flush()
            self.products[full] = p
        return self.products[full]

    def supplier_code(self, code: str) -> str:
        """The same marker prefix, so a supplier code lines up with our catalogue."""
        return f"{MARKER}{self.tag}-{code}"

    def product_set(
        self, code: str, members: list, *, company_id: str | None = None
    ) -> "ProductSet":
        """One of OUR sets, marker-prefixed like a product code (F12, R19).

        `members` are `(product, quantity, sort_order)`, in the order a person authored
        them - `sort_order` is one of the driver's tie-breaks, so the tests hand it in
        rather than letting the enumeration invent one.
        """
        from app.models.product_set import ProductSet, ProductSetMember

        product_set = ProductSet(
            id=_u(),
            set_code=f"{MARKER}{self.tag}-{code}",
            name=code,
            is_active=True,
            **({"company_id": company_id} if company_id else {}),
        )
        self.db.add(product_set)
        self.db.flush()
        for product, quantity, sort_order in members:
            self.db.add(
                ProductSetMember(
                    id=_u(),
                    product_set_id=product_set.id,
                    product_id=product.id,
                    quantity=quantity,
                    sort_order=sort_order,
                )
            )
        self.db.flush()
        return product_set


def _resolve(db, w: World, *codes: str):
    from app.services.scm import supplier_code_matcher

    return supplier_code_matcher.resolve(db, str(w.supplier.id), list(codes))


def _aliases(db, w: World) -> list[SupplierProductCodeAlias]:
    return (
        db.query(SupplierProductCodeAlias)
        .filter(SupplierProductCodeAlias.supplier_id == w.supplier.id)
        .all()
    )


# --------------------------------------------------------------------------------- #
# Rung 1 - exact
# --------------------------------------------------------------------------------- #


def test_a_code_we_hold_verbatim_binds_exactly_and_writes_no_alias():
    """An exact match needs no memory: the codes already agree, and a row saying so would be
    a row to maintain for nothing."""
    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-RL")

        out = _resolve(db, w, w.supplier_code("SRTWC8357-RL"))

        match = out[w.supplier_code("SRTWC8357-RL")]
        assert match.product_id == str(product.id)
        assert match.rung == "exact"
        assert _aliases(db, w) == []


def test_case_and_stray_whitespace_do_not_stop_an_exact_match():
    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-RL")
        typed = f"  {w.supplier_code('srtwc8357-rl')}  "

        out = _resolve(db, w, typed)

        assert out[typed].product_id == str(product.id)


# --------------------------------------------------------------------------------- #
# Rung 2 - the separators are theirs, not ours
# --------------------------------------------------------------------------------- #


def test_a_code_spelled_without_the_dashes_still_binds():
    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-RL")
        code = w.supplier_code("SRTWC8357RL").replace("-SRTWC", "SRTWC")

        out = _resolve(db, w, code)

        assert out[code].product_id == str(product.id)
        assert out[code].rung == "separator"


# --------------------------------------------------------------------------------- #
# Rung 3 - the same tokens in another order (4 of the 79)
# --------------------------------------------------------------------------------- #


def test_the_same_tokens_in_another_order_bind():
    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-300-RL")
        code = w.supplier_code("SRTWC8357-RL-300")

        out = _resolve(db, w, code)

        assert out[code].product_id == str(product.id)
        assert out[code].rung == "token_set"


def test_a_token_reorder_that_two_products_answer_is_refused():
    """Ambiguity is not a bind. Two products carrying the same tokens cannot both be what
    the supplier meant, and guessing which one puts stock against the wrong item."""
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-300-RL")
        w.product("SRTWC8357-RL-300-X").product_code = f"{MARKER}{w.tag}-RL-300-SRTWC8357"
        db.flush()
        code = w.supplier_code("SRTWC8357-RL-300")

        out = _resolve(db, w, code)

        assert code not in out


# --------------------------------------------------------------------------------- #
# Rung 4 - the trap size ours omits, CONFIRMED by the description
# --------------------------------------------------------------------------------- #


def test_a_trailing_trap_size_our_code_omits_binds_when_the_description_says_so():
    with pg_session() as db:
        w = World(db)
        product = w.product(
            "SRTWC8357-RL",
            description="SORENTO ONE PIECE (RIMLESS) TOILET (S-TRAP 250MM)",
        )
        code = w.supplier_code("SRTWC8357-RL-250")

        out = _resolve(db, w, code)

        assert out[code].product_id == str(product.id)
        assert out[code].rung == "size_drop"


def test_a_trap_size_the_base_product_is_not_is_refused():
    """The 16 wrong ones. `CWC7606-SH-180` is not `CWC7606-SH`: that product is the 250, and
    its description says so. Dropping the size without asking bound 16 lines to the wrong
    item and nothing on screen would have disagreed."""
    with pg_session() as db:
        w = World(db)
        w.product("CWC7606-SH", description="CABANA ONE PIECE TOILET (S-TRAP 250MM)")
        code = w.supplier_code("CWC7606-SH-180")

        out = _resolve(db, w, code)

        assert code not in out


def test_a_base_product_with_no_description_is_never_bound_by_size():
    """Silence is a no. A product that says nothing about its trap cannot confirm one."""
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL", description=None)
        code = w.supplier_code("SRTWC8357-RL-250")

        out = _resolve(db, w, code)

        assert code not in out


def test_a_glued_suffix_after_the_size_stays_unmatched():
    """`SRTWC286-SH-250UF` is the 250 AND something else - a UF seat. The size rung answers
    only where the size is the whole of what was added; the rest is a human's call."""
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC286-SH", description="SORENTO TOILET (S-TRAP 250MM)")
        code = w.supplier_code("SRTWC286-SH-250UF")

        out = _resolve(db, w, code)

        assert code not in out


def test_a_number_that_is_not_a_trap_size_is_not_dropped():
    """100..499 is the trap-size range. `-600` is part of the model, not a trap."""
    with pg_session() as db:
        w = World(db)
        w.product("SRTWB890", description="SORENTO BASIN (600MM)")
        code = w.supplier_code("SRTWB890-600")

        out = _resolve(db, w, code)

        assert code not in out


# --------------------------------------------------------------------------------- #
# Rung 0 - what somebody already decided
# --------------------------------------------------------------------------------- #


def test_an_alias_wins_over_every_other_rung():
    """A human said this code is that product. No ladder outranks that - and this is how a
    wrong automatic bind is corrected once rather than re-derived on every upload."""
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL")
        theirs = w.product("SRTWC8357-RL-SPECIAL")
        code = w.supplier_code("SRTWC8357-RL")
        db.add(SupplierProductCodeAlias(
            id=_u(), supplier_id=w.supplier.id, supplier_code=code,
            product_id=theirs.id, source="manual", matched_by="manual",
        ))
        db.flush()

        out = _resolve(db, w, code)

        assert out[code].product_id == str(theirs.id)
        assert out[code].rung == "alias"


def test_an_alias_belonging_to_another_supplier_is_not_consulted():
    with pg_session() as db:
        w = World(db)
        other = World(db)
        ours = w.product("SRTWC8357-RL")
        code = w.supplier_code("SRTWC8357-RL")
        db.add(SupplierProductCodeAlias(
            id=_u(), supplier_id=other.supplier.id, supplier_code=code,
            product_id=other.product("SOMETHING-ELSE").id, source="manual",
            matched_by="manual",
        ))
        db.flush()

        out = _resolve(db, w, code)

        assert out[code].product_id == str(ours.id)


# --------------------------------------------------------------------------------- #
# The answer is remembered
# --------------------------------------------------------------------------------- #


def test_every_worked_out_bind_is_written_down_with_the_rung_that_found_it():
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-300-RL")
        w.product("CWB247-BASE", description="CABANA BASIN (S-TRAP 250MM)")
        reorder = w.supplier_code("SRTWC8357-RL-300")

        _resolve(db, w, reorder)

        alias = _aliases(db, w)
        assert [a.supplier_code for a in alias] == [reorder]
        assert alias[0].source == "auto"
        assert alias[0].matched_by == "token_set"


def test_a_second_pass_reads_the_alias_rather_than_walking_the_ladder_again():
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-300-RL")
        code = w.supplier_code("SRTWC8357-RL-300")

        first = _resolve(db, w, code)
        second = _resolve(db, w, code)

        assert second[code].product_id == first[code].product_id
        assert second[code].rung == "alias"
        assert len(_aliases(db, w)) == 1


def test_a_code_nothing_answers_is_simply_absent():
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL")

        out = _resolve(db, w, w.supplier_code("NOTHING-LIKE-THIS"))

        assert out == {}
        assert _aliases(db, w) == []


def test_one_code_carried_by_two_companies_is_one_answer_not_an_ambiguity():
    """Real data. `products.product_code` is NOT unique across companies - the dev copy holds
    11,390 codes once for Sorento and once for Mocha - so a caller who may see both reads
    every code twice. Treating that as two products refused every rung on the whole
    JINBAICHUAN list: 79 codes unbound, 0 answered, and the exact rung would have dropped the
    36 that bind today.

    Two products means two CODES. One code spelled once per company is one product wearing
    one name, and the supplier's own company says which row is the one to bind.

    The scope is set to both companies on purpose: a single-company caller never sees the
    twin, so under the suite's Sorento default this test would pass without the ladder doing
    anything, and a superadmin (granted every company) is exactly who uploads a stock list.
    """
    with pg_session() as db:
        w = World(db)
        ours = w.product("SRTWC8357-300-RL")
        # A company of its own, seeded here rather than read off the dev copy: CI's database
        # holds no companies, so a hard-coded Mocha id would make this pass locally only.
        # `uq_products_company_product_code` is what makes the twin a twin - the same code is
        # only allowed to appear twice if the second one belongs somewhere else.
        elsewhere = Company(
            id=_u(), name=f"{MARKER} other company {w.tag}", code=f"{MARKER}{w.tag}"[:50],
            is_active=True,
        )
        db.add(elsewhere)
        db.flush()
        twin = Product(
            id=_u(),
            product_code=ours.product_code,
            product_name="the same model, another company's row",
            category_id=w.cat.id, base_uom_id=w.uom.id, list_price=0,
            is_active=True, is_discontinued=False,
            company_id=str(elsewhere.id),
        )
        db.add(twin)
        db.flush()
        code = w.supplier_code("SRTWC8357-RL-300")

        with company_scope(db, frozenset({str(ours.company_id), str(elsewhere.id)})):
            out = _resolve(db, w, code)

        assert code in out, "one code in two companies read as two products and bound nothing"
        assert out[code].product_id == str(ours.id), "bound another company's row"
        assert out[code].rung == "token_set"


def test_two_genuinely_different_products_are_still_an_ambiguity():
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-300-RL")
        other = w.product("SRTWC8357-RL-300-OTHER")
        other.product_code = f"{MARKER}{w.tag}-RL-300-SRTWC8357"
        db.flush()
        code = w.supplier_code("SRTWC8357-RL-300")

        out = _resolve(db, w, code)

        assert code not in out
