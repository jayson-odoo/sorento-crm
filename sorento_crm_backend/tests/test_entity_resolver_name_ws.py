"""Dash/whitespace-insensitive matching across EVERY resolver tier.

n8n strips dashes and whitespace from every entity token before calling
`/api/v1/system/references/resolve` (it has to: STT spaces product codes, so
"SRT WC286SH" must flatten to "SRTWC286SH"). Product and the other code fields
already normalized both sides via `_strip_all_ws` / `_ws_insensitive_lower`;
names and free text did not, so a stripped multi-word value ("MASTILEKLANG")
missed a row the spaced token ("MASTILE KLANG") hit.

The resolver now routes every ILIKE through two primitives -- `_norm_prefix`
and `_norm_contains` -- which keep the plain ILIKE and OR a normalized twin
onto it. The normalized clause can only ADD matches, never remove one, so a
spaced token keeps working everywhere.

Tiers covered here: Tier 1 exact probes, Tier 2 prefix/substring probes, Tier 3
AND-mode probes. DB tests run inside a rolled-back Postgres session and seed
every row they assert on (ZZT prefix), so they hold on an empty CI database.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.forms import Form
from app.models.order import Customer, Order, Transporter
from app.models.resources import Attachment, AttachmentType
from app.services import entity_resolver as er
from app.services.entity_resolver import _NORM_MIN_LEN, _norm_contains, _norm_prefix
from tests._pg_fixture import pg_session, unique_code


# --------------------------------------------------------------------------- #
# DB-free clause-shape tests
# --------------------------------------------------------------------------- #
def _sql(clause) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def test_norm_prefix_keeps_plain_ilike_and_adds_normalized_twin():
    sql = _sql(_norm_prefix(Customer.customer_name, "MASTILE KLANG"))
    assert "LIKE lower('MASTILE KLANG%')" in sql     # plain ILIKE half survives
    assert "regexp_replace" in sql                   # normalized half added
    assert "'mastileklang%'" in sql                  # both sides stripped + lowered


def test_norm_contains_keeps_plain_ilike_and_adds_normalized_twin():
    sql = _sql(_norm_contains(Customer.customer_name, "MASTILE-KLANG"))
    assert "LIKE lower('%MASTILE-KLANG%')" in sql
    assert "'%mastileklang%'" in sql                 # dash stripped too


def test_norm_contains_guards_short_tokens():
    # Below _NORM_MIN_LEN the unanchored normalized clause would span word
    # boundaries, so only the plain ILIKE is emitted.
    short = "a" * (_NORM_MIN_LEN - 1)
    assert "regexp_replace" not in _sql(_norm_contains(Customer.customer_name, short))
    # An anchored prefix carries no such risk and stays unguarded.
    assert "regexp_replace" in _sql(_norm_prefix(Customer.customer_name, short))


# --------------------------------------------------------------------------- #
# Live-DB fixture. Skips cleanly when Postgres is unreachable.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def db():
    ctx = pg_session()
    try:
        session = ctx.__enter__()
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres unreachable: {exc}")
    try:
        yield session
    finally:
        ctx.__exit__(None, None, None)


def _customer(db: Session, name: str) -> Customer:
    row = Customer(id=str(uuid.uuid4()), customer_code=unique_code("CUST"), customer_name=name)
    db.add(row)
    db.flush()
    return row


def _order(db: Session, debtor_name: str) -> Order:
    row = Order(
        id=str(uuid.uuid4()),
        order_number=unique_code("DO"),
        debtor_name=debtor_name,
        debtor_code=unique_code("DBT")[:100],
    )
    db.add(row)
    db.flush()
    return row


def _transporter(db: Session, name: str) -> Transporter:
    row = Transporter(
        id=str(uuid.uuid4()),
        code=unique_code("TRP")[:100],
        name=name,
        normalized_name=name.upper(),
    )
    db.add(row)
    db.flush()
    return row


def _attachment_type(db: Session, type_name: str, code: str | None = None) -> AttachmentType:
    row = AttachmentType(
        id=str(uuid.uuid4()),
        code=code or unique_code("AT")[:50],
        type_name=type_name,
        allowed_extensions="pdf",
    )
    db.add(row)
    db.flush()
    return row


def _attachment(db: Session, filename: str, type_id: str | None = None) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"/zzt/{filename}",
        attachment_type_id=type_id,
    )
    db.add(row)
    db.flush()
    return row


def _form(db: Session, code: str, name: str) -> Form:
    row = Form(id=str(uuid.uuid4()), code=code, name=name, purpose="ZZT purpose")
    db.add(row)
    db.flush()
    return row


def _uuids(matches) -> set[str]:
    return {m.uuid for m in matches}


def _codes(matches) -> set[str]:
    return {m.canonical_code for m in matches}


# --------------------------------------------------------------------------- #
# Tier 1 — customers.customer_name
# --------------------------------------------------------------------------- #
CUST_NAME = "ZZTMASTILE KLANG SDN BHD"


@pytest.mark.parametrize(
    "token",
    [
        "ZZTMASTILEKLANGSDNBHD",  # fully stripped
        "ZZTMASTILEKLANG",        # stripped partial (the reported miss)
        "ZZTMASTILE KLANG",       # spaced — must keep working
        "ZZTMASTILE-KLANG",       # dashed — normalizes to the same form
        "ZZTMASTILE",             # single word, unchanged behaviour
    ],
)
def test_customer_name_matches_regardless_of_separators(db, token):
    cust = _customer(db, CUST_NAME)
    out = er._probe_customer(db, [token])
    # `_probe_customer` surfaces customer_code as the canonical code, so match on uuid.
    hits = [m for m in out[token] if m.uuid == str(cust.id)]
    assert hits, f"{token!r} missed {CUST_NAME!r}"
    # A row pulled in by the normalized clause must still be labelled a name hit.
    assert hits[0].match_field == "customer_name"
    assert hits[0].canonical_code == cust.customer_code


def test_customer_name_hyphen_is_normalized_away(db):
    """Standardized behaviour: names strip dashes too, exactly like codes."""
    cust = _customer(db, "ZZTSIME-DARBY PROPERTY")
    for token in ("ZZTSIME-DARBYPROPERTY", "ZZTSIMEDARBYPROPERTY", "ZZTSIME DARBY PROPERTY"):
        assert str(cust.id) in _uuids(er._probe_customer(db, [token])[token]), token


def test_customer_name_short_token_does_not_span_words(db):
    # "ZZTQ ABCD" normalizes to "zztqabcd", which contains "qab". A token below
    # _NORM_MIN_LEN must NOT be allowed to match across the word boundary.
    cust = _customer(db, "ZZTQ ABCD")
    assert str(cust.id) not in _uuids(er._probe_customer(db, ["QAB"])["QAB"])


# --------------------------------------------------------------------------- #
# Tier 1 + Tier 2 — orders.debtor_name
# --------------------------------------------------------------------------- #
DEBTOR_NAME = "ZZTFIRA VENTURE ENTERPRISE"


@pytest.mark.parametrize(
    "token",
    [
        "ZZTFIRA VENTURE ENTERPRISE",  # exact, spaced
        "ZZTFIRAVENTUREENTERPRISE",    # exact, stripped
        "ZZTFIRAVENTURE",              # partial, stripped
        "ZZTFIRA VENTURE",             # partial, spaced
        "ZZTFIRA-VENTURE",             # partial, dashed
    ],
)
def test_debtor_name_matches_regardless_of_separators(db, token):
    _order(db, DEBTOR_NAME)
    assert DEBTOR_NAME in _codes(er._probe_customer_debtor_name(db, [token])[token])


def test_debtor_name_prefix_probe_normalizes(db):
    _order(db, DEBTOR_NAME)
    assert DEBTOR_NAME in _codes(er._prefix_probe_customer_debtor_name(db, "ZZTFIRAVENTURE"))


# --------------------------------------------------------------------------- #
# Tier 1 + Tier 2 — transporters
# --------------------------------------------------------------------------- #
TRP_NAME = "ZZTGT Delivery Services"


@pytest.mark.parametrize("token", ["ZZTGTDELIVERYSERVICES", "ZZTGT Delivery", "ZZTGTDELIVERY"])
def test_transporter_name_matches_regardless_of_separators(db, token):
    trp = _transporter(db, TRP_NAME)
    for probe in (er._probe_transporter, er._probe_transporter_freeword):
        assert trp.code in _codes(probe(db, [token])[token]), f"{probe.__name__} missed {token!r}"
    assert trp.code in _codes(er._prefix_probe_transporter(db, token))


# --------------------------------------------------------------------------- #
# Tier 1 + Tier 2 — attachments / attachment types
# --------------------------------------------------------------------------- #
def test_attachment_filename_exact_probe_normalizes(db):
    att = _attachment(db, "ZZT Price List 2026.pdf")
    for token in ("ZZT Price List 2026.pdf", "ZZTPriceList2026.pdf", "ZZT-Price-List-2026.pdf"):
        assert str(att.id) in _uuids(er._probe_attachment(db, [token])[token]), token


def test_attachment_prefix_probe_normalizes(db):
    att = _attachment(db, "ZZT Price List 2026.pdf")
    assert str(att.id) in _uuids(er._prefix_probe_attachment(db, "ZZTPriceList"))


def test_attachment_type_exact_probe_normalizes(db):
    at = _attachment_type(db, "ZZT Spec Sheet")
    for token in ("ZZT Spec Sheet", "ZZTSpecSheet", "ZZT-Spec-Sheet"):
        assert str(at.id) in _uuids(er._probe_attachment_type(db, [token])[token]), token


def test_attachment_type_prefix_probe_normalizes(db):
    at = _attachment_type(db, "ZZT Spec Sheet")
    assert str(at.id) in _uuids(er._prefix_probe_attachment_type(db, "ZZTSpecSheet"))


# --------------------------------------------------------------------------- #
# Tier 2 — forms
# --------------------------------------------------------------------------- #
def test_form_prefix_probe_normalizes(db):
    form = _form(db, unique_code("FRM")[:100], "ZZT Sponsorship Request")
    assert str(form.id) in _uuids(er._prefix_probe_form(db, "ZZTSponsorshipRequest"))


# --------------------------------------------------------------------------- #
# Tier 3 — AND-mode probes (every ILIKE funnels through _and_token_match_counts)
# --------------------------------------------------------------------------- #
def test_and_probe_customer_normalizes(db):
    cust = _customer(db, CUST_NAME)
    hits = er._and_probe_customer(db, ["ZZTMASTILEKLANG"])
    assert str(cust.id) in _uuids(hits)


def test_and_probe_customer_order_normalizes(db):
    order = _order(db, DEBTOR_NAME)
    stripped = order.order_number.replace("-", "")
    assert str(order.id) in _uuids(er._and_probe_customer_order(db, [stripped]))
