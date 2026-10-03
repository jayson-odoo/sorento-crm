"""PRODUCT-REF-COLLISION AC-6/AC-7/AC-8 for billing document lines (code-first ruling).

Substrate: the billing-documents `env` (blank Postgres, real route).
"""
from __future__ import annotations

from app.services.master_ref_resolver import WARN_REF_MISMATCH

from tests.test_ingest_billing_documents import (  # noqa: F401 - fixture reuse
    MARKER,
    _minimal,
    _record,
    env,
)

__all__ = ["env"]

BOOK = "AED_V2_MOCHA"


def _push_line(env, ref_suffix: str, **line_fields):
    ref = f"{MARKER}:IV:{ref_suffix}"
    record = _minimal(ref)
    record["lines"][0].pop("product_code", None)
    record["lines"][0].update(line_fields)
    res = env.push([record])
    out = _record(res, ref)
    line = env.lines(env.doc(ref).id)[0]
    return out, line


class TestBillingLine:
    def test_ac6_ref_hits_a_code_owned_by_b_binds_b(self, env):
        a_id = env.seed_product("MKT4524SS-DIY", env.company_a, ref=f"{BOOK}:2001")
        b_id = env.seed_product("2001", env.company_a)
        env.db.commit()

        out, line = _push_line(env, "B6", product_ref=f"{BOOK}:2001", product_code="2001")

        assert out["outcome"] == "created", out
        assert WARN_REF_MISMATCH in out.get("warnings", []), out
        assert str(line.product_id) == b_id
        assert str(line.product_id) != a_id

    def test_ac7_code_owned_by_nobody_lands_null_with_product_unresolved(self, env):
        a_id = env.seed_product("MKT4528ASS-DIY", env.company_a, ref=f"{BOOK}:2004")
        env.db.commit()

        out, line = _push_line(env, "B7", product_ref=f"{BOOK}:2004", product_code="2004")

        assert out["outcome"] == "created", out
        assert "product_unresolved" in out.get("warnings", []), out
        assert line.product_id is None, f"bound {line.product_id}, ref holder is {a_id}"

    def test_ac8_no_product_code_resolves_by_ref_as_today(self, env):
        a_id = env.seed_product("MKT4524SS-DIY", env.company_a, ref=f"{BOOK}:2001")
        env.db.commit()

        out, line = _push_line(env, "B8", product_ref=f"{BOOK}:2001")

        assert out["outcome"] == "created", out
        assert "product_unresolved" not in out.get("warnings", []), out
        assert str(line.product_id) == a_id
