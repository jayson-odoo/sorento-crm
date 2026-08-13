"""Certificate entity resolution: what a resolved uuid hands to the MCP tool.

The resolver's output is fed straight to `crm_certificates_list`, so an expired
certificate resolving first means the agent delivers a lapsed PDF. These tests
pin the rule: prefer a LIVE certificate for a token, but never make an expired
one unfindable - "found, but it expired on <date>" beats "I cannot find that".

Postgres only, on an isolated blank schema whose writes are discarded. Every
test seeds its own chain under a ZZTRES marker; nothing is borrowed.
"""
from datetime import date, timedelta
from typing import Any

import pytest

from app.models.base import company_scope
from app.models.certificate import Certificate
from app.services import entity_resolver as er
from app.services.certificate_service import CertificateService
from tests._pg_fixture import blank_session

MARKER = "ZZTRES"
SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _cert(
    db,
    *,
    scheme: str,
    number: str,
    expired: bool,
) -> Any:
    today = date.today()
    window = (
        (today - timedelta(days=800), today - timedelta(days=30))
        if expired
        else (today - timedelta(days=30), today + timedelta(days=400))
    )
    service = CertificateService(db)
    return service.upsert_from_extraction(
        scheme=scheme,
        certificate_number=number,
        certifying_body=f"{MARKER} body",
        valid_from=window[0],
        valid_until=window[1],
        commit=False,
    )


def _states(hits) -> list[tuple[str, bool]]:
    return [(h.display["scheme"], h.display["is_expired"]) for h in hits]


def test_a_live_certificate_wins_over_an_expired_one_on_the_same_number(db):
    """The live case: one IKRAM number approved under two schemes, one lapsed.
    Only the live certificate's uuid should reach the tool."""
    with company_scope(db, frozenset({SORENTO})):
        _cert(db, scheme=f"{MARKER}PPS", number="RES-1", expired=True)
        _cert(db, scheme=f"{MARKER}SPAN", number="RES-1", expired=False)
        db.flush()

        hits = er._probe_certificate(db, ["RES-1"])["RES-1"]
        assert _states(hits) == [(f"{MARKER}SPAN", False)]


def test_an_only_expired_certificate_is_still_found_and_flagged(db):
    """NOT a hard filter. Hiding it would have the agent deny a certificate that
    plainly exists, which is worse than reporting it as expired."""
    with company_scope(db, frozenset({SORENTO})):
        _cert(db, scheme=f"{MARKER}PPS", number="RES-2", expired=True)
        db.flush()

        hits = er._probe_certificate(db, ["RES-2"])["RES-2"]
        assert len(hits) == 1
        assert hits[0].display["is_expired"] is True
        assert hits[0].display["validity_state"] == "expired"


def test_two_live_certificates_both_survive_so_the_token_stays_ambiguous(db):
    """Filtering must not silently pick a winner between two LIVE certificates -
    the agent has to ask which scheme."""
    with company_scope(db, frozenset({SORENTO})):
        _cert(db, scheme=f"{MARKER}PPS", number="RES-3", expired=False)
        _cert(db, scheme=f"{MARKER}SPAN", number="RES-3", expired=False)
        db.flush()

        hits = er._probe_certificate(db, ["RES-3"])["RES-3"]
        assert len(hits) == 2
        assert all(h.display["is_expired"] is False for h in hits)


def test_a_certificate_with_no_expiry_on_file_is_never_dropped(db):
    """`validity_state=unknown` is not expired: the register holds no date. It
    must stay resolvable so the agent can say the expiry is not recorded."""
    with company_scope(db, frozenset({SORENTO})):
        CertificateService(db).upsert_from_extraction(
            scheme=f"{MARKER}PPS",
            certificate_number="RES-4",
            certifying_body=f"{MARKER} body",
            valid_until=None,
            commit=False,
        )
        db.flush()

        hits = er._probe_certificate(db, ["RES-4"])["RES-4"]
        assert len(hits) == 1
        assert hits[0].display["validity_state"] == "unknown"
        assert hits[0].display["is_expired"] is False


def test_the_prefix_probe_applies_the_same_rule(db):
    with company_scope(db, frozenset({SORENTO})):
        _cert(db, scheme=f"{MARKER}PPS", number="RES-5AA", expired=True)
        _cert(db, scheme=f"{MARKER}SPAN", number="RES-5AA", expired=False)
        db.flush()

        hits = er._prefix_probe_certificate(db, "RES-5")
        assert _states(hits) == [(f"{MARKER}SPAN", False)]


def test_resolution_is_unchanged_for_a_product_token(db):
    """The regression guard the whole register depends on: adding certificate
    probes must not alter what a product code resolves to."""
    with company_scope(db, frozenset({SORENTO})):
        _cert(db, scheme=f"{MARKER}PPS", number="RES-6", expired=False)
        db.flush()

        # A token that is not a certificate number returns no certificate match.
        assert er._probe_certificate(db, ["WC8038"])["WC8038"] == []


def test_certificates_created_here_never_leak_out_of_the_scratch_schema(db):
    """Sanity on the fixture itself: the rows live in the blank schema only."""
    with company_scope(db, frozenset({SORENTO})):
        _cert(db, scheme=f"{MARKER}PPS", number="RES-7", expired=False)
        db.flush()
        assert (
            db.query(Certificate)
            .filter(Certificate.certificate_number == "RES-7")
            .count()
            == 1
        )
