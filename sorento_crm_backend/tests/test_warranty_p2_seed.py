"""AFTER-SALES-P2 red tests: seed and data (UAC S1, S2) .

Seed contract: `app.services.warranty_seed.seed_warranty_policy_v15(db, company_id)`, idempotent, writes
the `after_sales_defect_type` option set, 31 kinds (shared by every company, unique on code), the company's
policy "v15" (effective_from 2000-01-01, open-ended, policy text kept) with 41 terms, and the 2 kind rules
the policy document states. No guessed rules (S3): the three dev fixture products reach no kind.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import func

from ._warranty_p2_support import (
    BA,
    CB,
    WC,
    DEFECT_SET_KEY,
    env,  # noqa: F401
    kind_by_code,
    make_company,
    seed_v15,
)

ROOT = Path(__file__).resolve().parents[1]


def counts(env):
    from app.models.warranty import WarrantyKindRule, WarrantyPolicy, WarrantyProductKind, WarrantyTerm

    env.db.expire_all()
    q = env.db.query
    return {
        "kinds": q(func.count(WarrantyProductKind.id)).scalar(),
        "terms": q(func.count(WarrantyTerm.id)).scalar(),
        "rules": q(func.count(WarrantyKindRule.id)).scalar(),
        "policies": q(func.count(WarrantyPolicy.id)).scalar(),
    }


def test_s2_the_seed_writes_31_kinds_41_terms_2_rules_and_one_policy(env):
    seed_v15(env)
    assert counts(env) == {"kinds": 31, "terms": 41, "rules": 2, "policies": 1}


def test_s2_the_policy_is_v15_backdated_to_2000_and_open_ended_with_its_text(env):
    from app.models.warranty import WarrantyPolicy

    seed_v15(env)
    (policy,) = env.db.query(WarrantyPolicy).all()
    assert (policy.version, policy.effective_from, policy.effective_to, str(policy.company_id)) == (
        "v15", date(2000, 1, 1), None, str(env.company_id),
    )
    assert policy.policy_text and "warranty" in policy.policy_text.lower()


def test_s2_running_the_seed_twice_changes_nothing(env):
    from app.models.warranty import WarrantyKindRule, WarrantyPolicy, WarrantyProductKind, WarrantyTerm

    def snapshot():
        env.db.expire_all()
        return [
            sorted((r.id, r.updated_at) for r in env.db.query(m).all())
            for m in (WarrantyProductKind, WarrantyKindRule, WarrantyPolicy, WarrantyTerm)
        ]

    seed_v15(env)
    first, before = counts(env), snapshot()
    seed_v15(env)
    assert counts(env) == first
    assert snapshot() == before


def test_s2_the_seed_creates_the_defect_type_set(env):
    from app.models.lookup import LookupOption, LookupSet

    seed_v15(env)
    lookup_set = env.db.query(LookupSet).filter(LookupSet.set_key == DEFECT_SET_KEY).one()
    labels = {o.label.casefold() for o in env.db.query(LookupOption).filter(LookupOption.set_id == lookup_set.id)}
    assert {"crack line", "leakage", "rust", "broken holder"} <= labels
    seed_v15(env)
    assert env.db.query(LookupOption).filter(LookupOption.set_id == lookup_set.id).count() == len(labels)


def test_s2_the_ceramic_body_term_is_lifetime_and_limited_to_crack_line_and_leakage(env):
    from app.models.lookup import LookupOption
    from app.models.warranty import WarrantyTerm

    seed_v15(env)
    term = env.db.query(WarrantyTerm).filter(
        WarrantyTerm.kind_id == kind_by_code(env, "water_closet").id, WarrantyTerm.part_name == "Ceramic Body"
    ).one()
    assert term.is_lifetime and term.duration_months is None and term.installation_included
    labels = {env.db.get(LookupOption, i).label.casefold() for i in term.covered_defect_type_ids}
    assert labels == {"crack line", "leakage"}


def test_s2_the_two_seeded_rules_are_the_honeycomb_series_and_the_mirror_cabinet_list(env):
    from app.models.warranty import WarrantyKindRule

    seed_v15(env)
    rules = {r.kind_id: r for r in env.db.query(WarrantyKindRule).all()}
    assert set(rules) == {kind_by_code(env, "bathroom_furniture").id, kind_by_code(env, "mirror_cabinet").id}
    assert rules[kind_by_code(env, "bathroom_furniture").id].match_type == "series"
    assert rules[kind_by_code(env, "mirror_cabinet").id].match_type == "model_list"


def test_s3_no_guessed_rules_the_dev_fixture_products_reach_no_kind(env):
    from app.services import warranty_service

    seed_v15(env)
    for code, category in (WC, CB, BA):
        assert warranty_service.resolve_kind(env.db, product_code=code, category_code=category, product_name="x") is None


def test_s2_a_second_company_gets_its_own_policy_and_terms_but_shares_the_kinds(env):
    seed_v15(env)
    seed_v15(env, make_company(env))
    from app.models.warranty import WarrantyProductKind
    from sqlalchemy import text

    assert env.db.query(func.count(WarrantyProductKind.id)).scalar() == 31
    assert env.db.execute(text("select count(*) from warranty_policies")).scalar() == 2
    assert env.db.execute(text("select count(*) from warranty_terms")).scalar() == 82


def test_s1_one_migration_creates_the_five_tables_and_touches_no_complaint_table():
    tables = ("warranty_product_kinds", "warranty_kind_rules", "warranty_policies", "warranty_terms", "service_job_products")
    hits = [
        p for p in (ROOT / "alembic" / "versions").glob("*.py")
        if all(t in p.read_text() for t in tables)
    ]
    assert len(hits) == 1, f"expected one migration creating all five tables, found {hits}"
    body = hits[0].read_text()
    assert not re.search(r"""["']complaint[a-z_]*["']""", body), "the migration must not touch a complaint table"
    assert "warranty_assessments" not in body


def test_s3_seeding_never_adds_rules_beyond_the_two_even_when_run_again(env):
    seed_v15(env)
    seed_v15(env)
    assert counts(env)["rules"] == 2
