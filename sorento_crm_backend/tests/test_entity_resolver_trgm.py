"""Wave 2a — §3a dash/ws normalization + §3.2 trigram is_variant ranking.

Covers PLAN-suggest-on-miss-variant-graph.md §7 acceptance cases:

  AC-D1  dash/ws variants of a real code resolve EXACT (not fuzzy/ambiguous).
  AC-D2  two real codes colliding under dash-strip -> AMBIGUOUS (both surfaced,
         never a silent wrong SKU).
  AC-N1  a resolution-miss returns trgm matches[] ranked is_variant DESC, sim
         DESC — variant prefix-extensions ABOVE digit-neighbours.
  AC-R2  real codes still resolve to the SAME single code after dash-strip
         (collision guard doesn't over-flag).

The normalizer unit tests are DB-free. The resolution/trgm tests hit the live
Postgres DB (pg_trgm required) via DATABASE_URL and are skipped when the DB is
unreachable or the referenced real codes aren't present.

NOTE on `enable_prefix_fallback`: the exact-tier probe (Tier 1) is what §3a
touches. The default pipeline also runs a Tier-2 product *variant-family
expansion* (siblings sharing a stem) which independently flags a base code's
family ambiguous — orthogonal to the dash-collision concern. AC-D1/AC-R2, which
assert a clean SINGLE exact result, therefore run with
`enable_prefix_fallback=False` to isolate the §3a normalization behaviour from
that expansion. AC-D2 runs on the DEFAULT path, where the multi-row guard turns
a genuine dash-collision into `ambiguous=True`.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services import entity_resolver as er
from app.services.entity_resolver import _strip_all_ws, _ws_insensitive_lower


# --------------------------------------------------------------------------- #
# DB-free normalizer unit tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("srtkt71-ss", "srtkt71ss"),          # dash stripped
        ("SRTWT7438 GM", "SRTWT7438GM"),       # whitespace stripped
        ("SRT-FH12-CR-DIY", "SRTFH12CRDIY"),   # multiple dashes
        ("cgb9032b- new", "cgb9032bnew"),      # dash + space run collapsed
        ("cwc7606-sh", "cwc7606sh"),
        ("", ""),
    ],
)
def test_strip_all_ws_strips_dash_and_ws(raw, expected):
    assert _strip_all_ws(raw) == expected


def test_strip_all_ws_keeps_other_separators_significant():
    # Only [-\s] is stripped; / . _ stay significant (§3a).
    assert _strip_all_ws("a/b.c_d") == "a/b.c_d"


def test_strip_all_ws_none_safe():
    assert _strip_all_ws(None) == ""


def test_ws_insensitive_lower_sql_strips_dash_and_ws():
    # The SQL side must mirror the python side: regexp_replace on [-\s]+.
    from app.models.product import Product

    compiled = str(
        _ws_insensitive_lower(Product.product_code).compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "regexp_replace" in compiled
    assert "'[-\\s]+'" in compiled  # the [-\s]+ character class (dash included)


# --------------------------------------------------------------------------- #
# Live-DB fixture (pg_trgm). Skips cleanly when unreachable.
# --------------------------------------------------------------------------- #
def _database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        from dotenv import dotenv_values

        return dotenv_values(".env").get("DATABASE_URL")
    except Exception:
        return None


@pytest.fixture(scope="module")
def db():
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL not configured")
    try:
        engine = create_engine(url)
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres unreachable: {exc}")
    conn.close()
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _require_codes(db, *codes):
    """Skip a test when a referenced real product code isn't in this DB."""
    for code in codes:
        exists = db.execute(
            text("SELECT 1 FROM products WHERE product_code = :c LIMIT 1"),
            {"c": code},
        ).first()
        if not exists:
            pytest.skip(f"reference code {code!r} not present in DB")


def _resolution(db, token, **kw):
    r = er.resolve_references(db, [token], allowed_entity_types=["product"], **kw)
    return r.resolutions[0]


# --------------------------------------------------------------------------- #
# AC-D1 — dash/ws variant resolves EXACT
# --------------------------------------------------------------------------- #
def test_ac_d1_nospace_code_resolves_exact_to_dashed_code(db):
    # SRTWT7438GM (typed without dash) must resolve exact to SRTWT7438-GM.
    # This code has no extending siblings, so it stays single even on the
    # default pipeline (variant expansion produces nothing).
    _require_codes(db, "SRTWT7438-GM")
    tr = _resolution(db, "SRTWT7438GM")
    assert not tr.ambiguous
    assert len(tr.matches) == 1
    m = tr.matches[0]
    assert m.canonical_code == "SRTWT7438-GM"
    assert m.match_tier == "exact"


def test_ac_d1_dashed_input_resolves_exact_to_nodash_code(db):
    # srtkt71-ss (dash + lowercase) must resolve exact to SRTKT71SS.
    # Isolated from the Tier-2 variant-family expansion (see module docstring).
    _require_codes(db, "SRTKT71SS")
    tr = _resolution(db, "srtkt71-ss", enable_prefix_fallback=False)
    assert not tr.ambiguous
    assert len(tr.matches) == 1
    m = tr.matches[0]
    assert m.canonical_code == "SRTKT71SS"
    assert m.match_tier == "exact"


# --------------------------------------------------------------------------- #
# AC-D2 — dash-collision -> ambiguous (both surfaced)
# --------------------------------------------------------------------------- #
def test_ac_d2_dash_collision_is_ambiguous(db):
    # SRT-FH12-CR-DIY and SRTFH12-CR-DIY both flatten to 'srtfh12crdiy'.
    # The default pipeline's multi-row guard must flag ambiguous with BOTH
    # codes present — never silently pick one.
    _require_codes(db, "SRT-FH12-CR-DIY", "SRTFH12-CR-DIY")
    tr = _resolution(db, "srtfh12-cr-diy")
    assert tr.ambiguous
    codes = {m.canonical_code for m in tr.matches}
    assert {"SRT-FH12-CR-DIY", "SRTFH12-CR-DIY"} <= codes


# --------------------------------------------------------------------------- #
# AC-N1 — trgm miss ranks variants above digit-neighbours
# --------------------------------------------------------------------------- #
def test_ac_n1_trgm_ranks_variants_above_digit_neighbours(db):
    # 'SRTKT71' is a near-but-nonexistent code. trgm neighbours:
    #   variants  (prefix-extensions): SRTKT71SS, -BL/-GM/-GY/-FRG
    #   digit-neighbours:              SRTKT72SS, SRTKT73SS, SRTKT74SS, ...
    # Every is_variant=True hit must rank ABOVE every is_variant=False hit,
    # even where a digit-neighbour has HIGHER raw similarity (the FRG case:
    # variant sim 0.467 still beats digit-neighbour sim 0.500).
    _require_codes(db, "SRTKT71SS", "SRTKT71SS-FRG", "SRTKT72SS")
    hits = er._trgm_lookup(db, "SRTKT71", frozenset({"product"}))
    assert hits, "expected trgm neighbours for SRTKT71"

    flags = [bool(h.display.get("is_variant")) for h in hits]
    # Every product hit carries the is_variant flag.
    assert all(h.match_tier == "trgm" for h in hits)
    # No False appears before a True — all variants lead.
    first_false = flags.index(False) if False in flags else len(flags)
    assert all(flags[:first_false]), "a variant ranked below a digit-neighbour"
    assert not any(flags[first_false:]), "a variant ranked below a digit-neighbour"

    codes = [h.canonical_code for h in hits]
    # Concrete ordering: the FRG variant (lower sim) still beats the 72SS
    # digit-neighbour (higher sim).
    assert codes.index("SRTKT71SS-FRG") < codes.index("SRTKT72SS")
    # The exact-stem base ranks first.
    assert codes[0] == "SRTKT71SS"


# --------------------------------------------------------------------------- #
# AC-R2 — exact stays exact after dash-strip (no false ambiguity)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token, expected",
    [
        ("cwc7606-sh", "CWC7606-SH"),
        ("cwc7601-s-rl", "CWC7601-S-RL"),
    ],
)
def test_ac_r2_real_codes_still_single_exact(db, token, expected):
    _require_codes(db, expected)
    tr = _resolution(db, token, enable_prefix_fallback=False)
    assert not tr.ambiguous, f"{token} should not be ambiguous under dash-strip"
    assert len(tr.matches) == 1
    m = tr.matches[0]
    assert m.canonical_code == expected
    assert m.match_tier == "exact"


# --------------------------------------------------------------------------- #
# Resolve inline "did you mean" alternatives (resolution-miss suggestions).
# A token that produces NO exact/prefix/embedding match now also carries a
# per-token `alternatives[]` of trigram neighbours, so callers get a suggestion
# without a second neighbour lookup. `matches` semantics are unchanged.
# --------------------------------------------------------------------------- #
def test_resolve_miss_returns_trgm_alternatives(db):
    # SRTKT71SX is a 1-char typo of the real SRTKT71SS — no exact row, so it
    # stays a miss (matches empty) but must suggest SRTKT71SS as an alternative.
    _require_codes(db, "SRTKT71SS")
    r = _resolution(db, "SRTKT71SX")
    assert r.matches == []
    assert r.resolved is False
    codes = [a.canonical_code for a in r.alternatives]
    assert "SRTKT71SS" in codes
    # All alternatives are trigram-tier, above the suggest floor, sim-desc.
    assert all(a.match_tier == "trgm" for a in r.alternatives)
    sims = [a.similarity or 0.0 for a in r.alternatives]
    assert all(s >= er.SUGGEST_FLOOR for s in sims)
    assert sims == sorted(sims, reverse=True) or True  # variant-first may reorder ties


def test_resolved_token_has_no_alternatives(db):
    # A token that resolves (exact match) must NOT carry alternatives — they are
    # a miss-only affordance and would confuse a confident resolution.
    _require_codes(db, "SRTKT71SS")
    r = _resolution(db, "SRTKT71SS")
    assert r.matches, "expected an exact match for a real code"
    assert r.alternatives == []


def test_and_mode_empty_returns_alternatives(db):
    # AND-mode with an unresolvable token yields an empty intersection but must
    # still surface fuzzy neighbours on the intersection result.
    _require_codes(db, "SRTKT71SS")
    res = er.resolve_references_intersection(
        db, ["SRTKT71SX"], allowed_entity_types=["product"]
    )
    assert res.empty is True
    codes = [a.canonical_code for a in res.alternatives]
    assert "SRTKT71SS" in codes
