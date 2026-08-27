"""F12 / R19-R20 - a supplier code can name one of our product SETS.

TEST-FIRST: rungs 5-7 do not exist when this file is written, so every test here is expected
to be red until they land.

The supplier sells the whole WC. `CWC605-RL` is our SET - pedestal `CWCX605-RL` plus cistern
`CWCY605` - and no product carries that code, so every rung of the product ladder misses it
by construction. The set rungs run AFTER the four product ones and answer the same three
questions the product rungs do: is it spelled as ours, is it ours with their separators, is
it ours with the tokens in another order.

What deliberately does NOT exist is a size-drop rung for sets. `CWC605-RL-180` stays
unmatched: a set carries no description to confirm a size against, and the product rung only
earned its size drop by asking the base product whether it IS that size.

Postgres via `pg_session`, because rung 6 normalises in SQL (`entity_resolver._norm_sql`) and
a Python copy of that rule would be a second spelling of it.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.company import Company
from app.models.scm import SupplierProductCodeAlias
from app.services.company_scope import company_scope
from tests._pg_fixture import pg_session
from tests.scm.test_supplier_code_matcher import MARKER, World, _resolve, _u


def _wc(w: World):
    """The real shape: a pedestal, a cistern, and the set code the supplier writes."""
    pedestal = w.product("CWCX605-RL")
    cistern = w.product("CWCY605")
    product_set = w.product_set("CWC605-RL", [(pedestal, 1, 0), (cistern, 1, 1)])
    return pedestal, cistern, product_set


def _aliases(db, w: World) -> list[SupplierProductCodeAlias]:
    return (
        db.query(SupplierProductCodeAlias)
        .filter(SupplierProductCodeAlias.supplier_id == w.supplier.id)
        .all()
    )


# --------------------------------------------------------------------------------- #
# Rung 5 - the set code, spelled as we spell it
# --------------------------------------------------------------------------------- #


def test_a_code_spelled_as_one_of_our_set_codes_binds_to_the_set():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL")

        out = _resolve(db, w, code)

        assert out[code].product_set_id == str(product_set.id)
        assert out[code].product_id is None
        assert out[code].rung == "set_exact"


def test_a_set_bind_is_written_down_so_the_next_upload_reads_a_decision():
    """Unlike a product exact match, nothing in the CATALOGUE carries this code, so the
    binding is invisible unless it is recorded. Every screen that says what a code means
    reads the alias table."""
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL")

        _resolve(db, w, code)

        rows = _aliases(db, w)
        assert len(rows) == 1
        assert str(rows[0].product_set_id) == str(product_set.id)
        assert rows[0].product_id is None
        assert rows[0].source == "auto"
        assert rows[0].matched_by == "set_exact"


def test_a_remembered_set_alias_answers_before_any_rung_runs():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL")
        _resolve(db, w, code)

        out = _resolve(db, w, code)

        assert out[code].product_set_id == str(product_set.id)
        assert out[code].rung == "alias"
        assert len(_aliases(db, w)) == 1


# --------------------------------------------------------------------------------- #
# Rungs 6 and 7 - their separators, their token order
# --------------------------------------------------------------------------------- #


def test_a_set_code_without_the_dashes_still_binds():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        code = w.supplier_code("CWC605-RL").replace("-RL", "RL")

        out = _resolve(db, w, code)

        assert out[code].product_set_id == str(product_set.id)
        assert out[code].rung == "set_separator"


def test_a_set_code_with_the_tokens_in_another_order_binds():
    with pg_session() as db:
        w = World(db)
        pedestal = w.product("CWCX605-RL")
        cistern = w.product("CWCY605")
        product_set = w.product_set("CWC605-300-RL", [(pedestal, 1, 0), (cistern, 1, 1)])
        code = w.supplier_code("CWC605-RL-300")

        out = _resolve(db, w, code)

        assert out[code].product_set_id == str(product_set.id)
        assert out[code].rung == "set_token_set"


# --------------------------------------------------------------------------------- #
# What the set ladder deliberately refuses
# --------------------------------------------------------------------------------- #


def test_a_size_suffix_never_auto_binds_a_set():
    """R20. `CWC605-RL-180` stays unmatched and is answered by a person from the picker: a
    set carries no description, so nothing can confirm that 180 is a real variant of ours
    rather than the supplier's own trap size."""
    with pg_session() as db:
        w = World(db)
        _wc(w)
        code = w.supplier_code("CWC605-RL-180")

        out = _resolve(db, w, code)

        assert code not in out
        assert _aliases(db, w) == []


def test_a_product_answer_outranks_a_set_answer():
    """The set rungs run AFTER the four product ones. A code our catalogue holds verbatim is
    that product, whatever else happens to be spelled the same way."""
    with pg_session() as db:
        w = World(db)
        product = w.product("CWC605-RL")
        cistern = w.product("CWCY605")
        w.product_set("CWC605-RL", [(product, 1, 0), (cistern, 1, 1)])
        code = w.supplier_code("CWC605-RL")

        out = _resolve(db, w, code)

        assert out[code].product_id == str(product.id)
        assert out[code].product_set_id is None
        assert out[code].rung == "exact"


def test_an_inactive_set_is_not_an_answer():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        product_set.is_active = False
        db.flush()
        code = w.supplier_code("CWC605-RL")

        out = _resolve(db, w, code)

        assert code not in out


def test_two_sets_answering_one_code_bind_nothing():
    with pg_session() as db:
        w = World(db)
        pedestal = w.product("CWCX605-RL")
        cistern = w.product("CWCY605")
        w.product_set("CWC605-RL", [(pedestal, 1, 0)])
        second = w.product_set("CWC605RL", [(cistern, 1, 0)])
        # Two spellings of one normalised code: rung 6 cannot choose between them.
        code = w.supplier_code("CWC605--RL")
        assert second.set_code != code

        out = _resolve(db, w, code)

        assert code not in out


def test_a_set_of_another_company_never_binds():
    """AC-F12.8. A Sorento supplier's list naming a Mocha set code stays unmatched: the stock
    rows, the invoice lines and the alias about to be written all belong to the supplier's
    own company, so a set from anywhere else would file the answer where the people reading
    it cannot see it."""
    with pg_session() as db:
        w = World(db)
        pedestal = w.product("CWCX605-RL")
        elsewhere = Company(
            id=_u(),
            name=f"{MARKER} other company {w.tag}",
            code=f"{MARKER}{w.tag}"[:50],
            is_active=True,
        )
        db.add(elsewhere)
        db.flush()
        theirs = w.product_set(
            "CWC605-RL", [(pedestal, 1, 0)], company_id=str(elsewhere.id)
        )
        code = w.supplier_code("CWC605-RL")

        with company_scope(db, frozenset({str(pedestal.company_id), str(elsewhere.id)})):
            out = _resolve(db, w, code)

        assert code not in out, f"bound {theirs.set_code} from another company"


# --------------------------------------------------------------------------------- #
# The database's own guard (AC-F12.9)
# --------------------------------------------------------------------------------- #


def test_an_alias_naming_both_a_product_and_a_set_is_refused():
    with pg_session() as db:
        w = World(db)
        pedestal, _, product_set = _wc(w)
        db.add(
            SupplierProductCodeAlias(
                id=_u(),
                supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("CWC605-RL"),
                product_id=str(pedestal.id),
                product_set_id=str(product_set.id),
                source="manual",
                matched_by="manual",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_an_alias_naming_nothing_is_refused_unless_it_is_a_dismissal():
    with pg_session() as db:
        w = World(db)
        _wc(w)
        db.add(
            SupplierProductCodeAlias(
                id=_u(),
                supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("CWC605-RL"),
                product_id=None,
                product_set_id=None,
                source="manual",
                matched_by="manual",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_a_dismissal_still_names_nothing_at_all():
    with pg_session() as db:
        w = World(db)
        _, _, product_set = _wc(w)
        db.add(
            SupplierProductCodeAlias(
                id=_u(),
                supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("THEIR-OWN-SPARE"),
                product_id=None,
                product_set_id=str(product_set.id),
                source="dismissed",
                matched_by="dismissed",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
