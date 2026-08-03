"""S3 Phase 2 - resolving a printed shop name to a Dealer.

This is where the S3-pre spike's measurements become code
(`documentation/plans/after-sales/S3-pre-extraction-accuracy.md`). Every rule below was
paid for with a real receipt, so the tests name the receipt.

**The output is a STATE, not a score.** Dealer match scores over 38 consumer-track receipts
came back bimodal: 26 matched at exactly 1.00 and NOTHING landed between 0.70 and 0.99.
There is no gradient to threshold. Returning a float invites every caller to invent its own
cutoff, and three receipts in the middle band named a real but WRONG dealer, so the cutoff
somebody invents will eventually pre-fill one of those.

  resolved   - exact after normalisation. Safe to pre-fill.
  candidate  - matched something, not well enough to assert. CS sees it, the consumer never does.
  unmatched  - nothing, or nothing to match on. Submission proceeds anyway (AC-C14).

**Two normalisation rules, both measured.**

1. Corporate suffixes are stripped from both sides. Unstripped, a Sorento delivery order
   printed "SORENTO SDN BHD" and matched "SL & A SDN BHD" at 0.42 - above any sane
   threshold, entirely on the strength of the shared "SDN BHD". Trigram similarity over
   Malaysian legal names measures how Malaysian a company is, not which company it is.

2. Bracketed branch qualifiers are stripped from both sides. Receipts print the branch the
   consumer walked into - "(JLN IPOH BRANCH)", "[A/C III]", "(PUCHONG)" - while `customers`
   stores the company. This lifted exact resolution from 23 to 26 of 38.

**What must NOT be rescued.** "SAINMART" is an OCR misread of "SANIMART": a one-character
typo, not a name variant. It fell out of the auto-accept band when branch stripping landed,
and that is the correct outcome - trigram similarity is not the mechanism that should
rescue it, and quietly widening the threshold until it passes is how the three wrong
dealers get pre-filled.

Run: venv/bin/python -m pytest tests/test_dealer_resolution.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from app.models.order import Customer  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

RESOLVER_MODULE = "app.services.dealer_resolution_service"

STATE_RESOLVED = "resolved"
STATE_CANDIDATE = "candidate"
STATE_UNMATCHED = "unmatched"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _resolver():
    if importlib.util.find_spec(RESOLVER_MODULE) is None:
        raise AssertionError(
            f"{RESOLVER_MODULE} does not exist. The spike's two normalisation rules and the "
            "resolved/candidate/unmatched decision belong in one place - the consumer "
            "portal, CS review and any later dealer-track path must all reach the same "
            "verdict for the same receipt."
        )
    return importlib.import_module(RESOLVER_MODULE)


def _fn(module, name: str, signature: str):
    fn = getattr(module, name, None)
    assert callable(fn), f"{module.__name__}.{name}{signature} must exist."
    return fn


def _customer(db, name: str, *, trading_name: str | None = None) -> Customer:
    row = Customer(
        id=str(uuid.uuid4()),
        customer_code=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}",
        customer_name=name,
        trading_name=trading_name,
    )
    db.add(row)
    db.flush()
    return row


def _resolve(db, printed: str):
    return _fn(_resolver(), "resolve_dealer", "(db, printed_name)")(db, printed)


# ============================================================ the exact matches


def test_an_exact_name_resolves(db):
    """61% of receipts before branch stripping, 68% after. The bread and butter."""
    _customer(db, "TOTAL HOME DIY SDN BHD")
    result = _resolve(db, "TOTAL HOME DIY SDN BHD")
    assert result.state == STATE_RESOLVED
    assert result.customer_id is not None


def test_the_trading_name_matches_as_well_as_the_registered_one(db):
    """A receipt prints the shop's TRADING name; `customer_name` is often the registered
    entity. Matching one column would under-report what is actually resolvable.
    """
    _customer(db, "LSH HOLDINGS SDN BHD", trading_name="LIM SENG HARDWARE")
    result = _resolve(db, "LIM SENG HARDWARE")
    assert result.state == STATE_RESOLVED


def test_case_and_punctuation_do_not_matter(db):
    """"SDN. BHD." with stops, lowercase, stray commas - all the same shop."""
    _customer(db, "SANIMART SDN BHD")
    assert _resolve(db, "sanimart sdn. bhd.").state == STATE_RESOLVED


# ======================================================== rule 1: corporate noise


def test_a_shared_corporate_suffix_is_not_a_match(db):
    """THE finding. "SORENTO SDN BHD" matched "SL & A SDN BHD" at 0.42 unstripped.

    Two companies sharing only "SDN BHD" have nothing in common. If this regresses, the
    portal starts naming a wrong dealer with confidence, on a receipt that named nobody.
    """
    _customer(db, "SL & A SDN BHD")
    result = _resolve(db, "SORENTO SDN BHD")
    assert result.state == STATE_UNMATCHED, (
        f"'SORENTO' matched 'SL & A' as {result.state}. The only shared text is the "
        "corporate suffix, which every Malaysian company has."
    )


def test_generic_trade_words_do_not_carry_a_match(db):
    """"HARDWARE", "TRADING", "ENTERPRISE" are the same problem in a different coat."""
    _customer(db, "KEDAI BESI JAYA HARDWARE SDN BHD")
    result = _resolve(db, "SOON LEE HARDWARE SDN BHD")
    assert result.state == STATE_UNMATCHED


# ========================================================== rule 2: branch names


def test_a_branch_qualifier_on_the_receipt_still_resolves(db):
    """Measured: 0.33 -> 1.00. The consumer walked into the Jalan Ipoh branch; Sorento
    stores the company. Without this rule a CORRECT dealer scores below any threshold.
    """
    _customer(db, "DILOOMA SDN BHD")
    result = _resolve(db, "DiLOOMA SDN. BHD. (JLN IPOH BRANCH)")
    assert result.state == STATE_RESOLVED


def test_a_branch_qualifier_on_the_stored_name_also_resolves(db):
    """Measured: 0.77 -> 1.00. The qualifier can sit on either side, or on both, and it
    is never the thing that distinguishes two dealers.
    """
    _customer(db, "THE LIVING DEPOT (PUCHONG) SDN BHD")
    assert _resolve(db, "THE LIVING DEPOT SDN BHD").state == STATE_RESOLVED


def test_an_account_qualifier_is_stripped(db):
    """"[A/C III]" is Sorento's own account bookkeeping, printed on the document."""
    _customer(db, "SANIMART SDN BHD")
    assert _resolve(db, "SANIMART SDN BHD [A/C III]").state == STATE_RESOLVED


# ================================================== the middle band, and the typo


def test_a_near_neighbour_is_a_candidate_and_never_resolved(db):
    """The three wrong dealers from the spike, in one test.

    "SENG HUAT" resolving to "CHENG HUAT HARDWARE" is worse than no answer: it attributes a
    consumer's purchase to a dealer who never sold it, in the sell-through ledger this
    module exists to build. `candidate` is how it stays visible to CS without being asserted.
    """
    _customer(db, "CHENG HUAT HARDWARE (SENTUL) SDN BHD")
    result = _resolve(db, "SENG HUAT SDN BHD")
    assert result.state != STATE_RESOLVED, (
        "A near neighbour must never pre-fill. This is the exact pair that made the "
        "68%-with-no-wrong-answers tradeoff worth taking."
    )


def test_an_ocr_typo_is_not_rescued_by_widening_the_net(db):
    """SAINMART / SANIMART - one transposed character.

    It is tempting to loosen the threshold until this passes. Doing so re-admits the wrong
    dealers above, because they sit in the same band. A short-edit-distance rule could
    catch it precisely; a wider trigram net cannot, and pretending otherwise trades a
    correct rejection for three incorrect acceptances.
    """
    _customer(db, "SANIMART SDN BHD")
    result = _resolve(db, "SAINMART SDN BHD [A/C III]")
    assert result.state != STATE_RESOLVED


# ====================================================== nothing to match against


def test_no_printed_name_is_unmatched_not_an_error(db):
    """13% of receipts print no trading name at all. Submission proceeds (AC-C14)."""
    _customer(db, "TOTAL HOME DIY SDN BHD")
    for printed in (None, "", "   "):
        result = _resolve(db, printed)
        assert result.state == STATE_UNMATCHED
        assert result.customer_id is None


def test_a_document_number_mistaken_for_a_shop_name_matches_nothing(db):
    """Measured: "B10-2-26050837" matched "SHOPEE - 260508URPXRRJ4" at 0.16.

    When the extractor hands back a document number as the shop name, the honest answer is
    nothing at all - not the nearest string in a table of 3,284.
    """
    _customer(db, "SHOPEE MALAYSIA SDN BHD")
    assert _resolve(db, "B10-2-26050837").state == STATE_UNMATCHED


def test_an_empty_customer_table_is_unmatched_rather_than_a_crash(db):
    assert _resolve(db, "TOTAL HOME DIY SDN BHD").state == STATE_UNMATCHED


# ================================================================ what CS receives


def test_a_candidate_carries_its_suggestion_for_cs(db):
    """`candidate` exists to be useful to CS. A state with nothing attached is just a
    slower `unmatched`.
    """
    target = _customer(db, "CHENG HUAT HARDWARE (SENTUL) SDN BHD")
    result = _resolve(db, "SENG HUAT SDN BHD")
    if result.state == STATE_CANDIDATE:
        assert result.suggestion_customer_id == str(target.id)
        assert result.suggestion_name


def test_the_raw_printed_text_always_survives(db):
    """Whatever the verdict, what the receipt actually said is kept (AC-C14). It is the
    only thing CS can act on when the match fails, and the only record of what was read.
    """
    _customer(db, "TOTAL HOME DIY SDN BHD")
    for printed in ("TOTAL HOME DIY SDN BHD", "SENG HUAT SDN BHD", "B10-2-26050837"):
        assert _resolve(db, printed).printed_name == printed


def test_resolution_is_deterministic(db):
    """Two identical receipts must reach the same verdict. An ordering-dependent answer
    would make the sell-through ledger disagree with itself.
    """
    _customer(db, "ALPHA HARDWARE SDN BHD")
    _customer(db, "ALPHA HARDWARE SDN BHD")
    first = _resolve(db, "ALPHA HARDWARE SDN BHD")
    second = _resolve(db, "ALPHA HARDWARE SDN BHD")
    assert first.customer_id == second.customer_id
    assert first.suggestion_customer_id == second.suggestion_customer_id
    assert first.state == second.state


def test_two_dealers_that_normalise_identically_are_a_question_not_a_match(db):
    """Determinism is not correctness, and this test used to assert the wrong thing.

    Normalisation strips corporate suffixes and bracketed branches, so two genuinely
    different `customers` rows can end up as the same string - and a duplicated customer
    row does it trivially. The first version broke that tie alphabetically and returned
    `resolved`, which binds the purchase to whichever display name sorts first and reports
    it as fact. In the ledger that is a sale attributed to a dealer who may never have made
    it, which is the precise failure the resolved/candidate split exists to prevent.
    """
    _customer(db, "ALPHA HARDWARE SDN BHD")
    _customer(db, "ALPHA HARDWARE SDN BHD")
    result = _resolve(db, "ALPHA HARDWARE SDN BHD")
    assert result.state == STATE_CANDIDATE, (
        "A tie at the resolve threshold was asserted as the dealer. Two rows matched "
        "equally well, so the honest answer is that CS decides."
    )
    assert result.customer_id is None
    # Still useful to CS: one of the tied rows is shown as the suggestion.
    assert result.suggestion_customer_id is not None


def test_a_single_dealer_still_resolves_when_a_duplicate_name_is_absent(db):
    """The tie rule must not cost the ordinary case. One match is still a match."""
    _customer(db, "ALPHA HARDWARE SDN BHD")
    assert _resolve(db, "ALPHA HARDWARE SDN BHD").state == STATE_RESOLVED
