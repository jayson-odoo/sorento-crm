"""S0 - `chatbot_domains` seeded from `DOMAIN_SPEC` (AC-1501, PLAN-chatbot-turn-rearch.md).

Runs against the REAL migrated database, never a blank scratch schema: the rows this
file asserts are written by a MIGRATION BODY (`upgrade()`), and `Base.metadata.
create_all` (what `tests/_pg_fixture.py::blank_session` builds from) never executes a
migration body - see LESSONS-LEARNT "create_all vs migration seed gap" and this repo's
own `scripts/bootstrap_env.py` docstring. `DATABASE_URL` must point at a database
already at `alembic head` (this worktree's private `sorento_ai_automation_rearch_test`
was bootstrapped via `scripts/bootstrap_env.py` and stamped at main's head before this
file was written); re-run `alembic upgrade head` after the coder's S0 migration lands to
pick up the new revision and its seed. These tests READ what that revision seeded, they
do not seed `chatbot_domains` themselves - only `teams` (see `_seed_teams` below), which
AC-1501's own text requires to resolve `escalation_team_id`.

RIGHT NOW every test here is RED: `chatbot_domains` does not exist
(``relation "chatbot_domains" does not exist``, UndefinedTable / ProgrammingError).
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy import text

from app.services.chatbot.contracts import DOMAIN_SPEC
from app.services.chatbot.lanes.business.fetch import DATE_PARAMS
from tests._pg_fixture import pg_session

DOMAINS: list[str] = list(DOMAIN_SPEC)  # dict preserves DOMAIN_SPEC's own declaration order

# system_settings.chatbot_crossdomain_ladder's own server_default (migration
# 491_chatbot_ladder_incoming_po.py): origin domain -> ladder rungs. A domain absent
# from this dict is expected to seed an empty ladder.
DEFAULT_LADDER: dict[str, list[str]] = {
    "inventory": ["incoming", "purchase_order"],
    "incoming": ["inventory", "purchase_order"],
}

# The (domain, entity kind) -> narrowing policy pairs AC-1501/AC-1526 give a literal
# answer for. Not every (domain, kind) combination in the matrix - only the named ones.
EXPECTED_NARROWING: dict[tuple[str, str], str] = {
    ("incoming", "product"): "narrow_to_code",
    ("purchase_cost", "product"): "narrow_to_code",
    ("order", "customer"): "must_narrow_one",
    ("product_attachment", "attachment_type"): "narrow_by_type",
    ("promotion", "tier"): "narrow_by_tier",
    ("inventory", "product"): "list_all",
}

# Every escalation team code a domain in DOMAIN_SPEC names, for the `teams` seed below.
TEAM_CODES: list[str] = sorted(
    {spec.escalation_team for spec in DOMAIN_SPEC.values() if spec.escalation_team}
)


def _seed_teams(db) -> None:
    """`teams` has no `code` column today (only `id`/`name`) - AC-1501's own text
    ("escalation_team_id ... resolving to the teams row whose code matches
    escalation_team") is what requires one. This INSERT is therefore itself part of
    what is under test: it fails with "column teams.code does not exist" until the
    coder adds it, which is a legitimate S0 gap, not a fixture bug.
    """
    company_id = db.execute(text("SELECT id FROM companies LIMIT 1")).scalar()
    for code in TEAM_CODES:
        db.execute(
            text(
                "INSERT INTO teams (id, name, code, company_id) "
                "VALUES (gen_random_uuid(), :n, :c, :co)"
            ),
            {"n": f"ZZT Team {code}", "c": code, "co": company_id},
        )


@pytest.fixture(scope="module")
def seeded():
    """`{"domains": {name: row}, "team_code_by_id": {id: code}}` from the real DB."""
    with pg_session() as db:
        try:
            domain_rows = db.execute(text("SELECT * FROM chatbot_domains")).mappings().all()
        except ProgrammingError as exc:
            pytest.fail(
                "chatbot_domains does not exist yet (AC-1501 migration not written): "
                f"{exc}",
                pytrace=False,
            )
        _seed_teams(db)
        team_rows = db.execute(text("SELECT id, code FROM teams")).mappings().all()
        yield {
            "domains": {row["name"]: dict(row) for row in domain_rows},
            "team_code_by_id": {str(row["id"]): row["code"] for row in team_rows},
        }


def test_one_row_per_domain_spec_entry(seeded):
    assert set(seeded["domains"]) == set(DOMAIN_SPEC)


@pytest.mark.parametrize("domain", DOMAINS)
def test_label_is_present(seeded, domain):
    row = seeded["domains"][domain]
    assert (row.get("label") or "").strip(), row


@pytest.mark.parametrize("domain", DOMAINS)
def test_intents_match_domain_spec(seeded, domain):
    row = seeded["domains"][domain]
    assert list(row["intents"]) == list(DOMAIN_SPEC[domain].intents)


@pytest.mark.parametrize("domain", DOMAINS)
def test_tools_match_domain_spec_in_order(seeded, domain):
    row = seeded["domains"][domain]
    assert list(row["tools"]) == list(DOMAIN_SPEC[domain].tools)


@pytest.mark.parametrize("domain", [d for d in DOMAINS if DOMAIN_SPEC[d].tools])
def test_primary_tool_is_tools_head(seeded, domain):
    row = seeded["domains"][domain]
    assert row["primary_tool"] == DOMAIN_SPEC[domain].tools[0]


@pytest.mark.parametrize("domain", DOMAINS)
def test_switch_words_match_domain_spec(seeded, domain):
    row = seeded["domains"][domain]
    assert set(row["switch_words"]) == set(DOMAIN_SPEC[domain].switch_words)


@pytest.mark.parametrize("domain", DOMAINS)
def test_supported_matches_default_supported(seeded, domain):
    row = seeded["domains"][domain]
    assert bool(row["supported"]) == DOMAIN_SPEC[domain].default_supported


@pytest.mark.parametrize("domain", DOMAINS)
def test_takes_date_filter_is_any_tool_in_fetch_date_params(seeded, domain):
    row = seeded["domains"][domain]
    expected = any(tool in DATE_PARAMS for tool in DOMAIN_SPEC[domain].tools)
    assert bool(row["takes_date_filter"]) == expected


@pytest.mark.parametrize("domain", DOMAINS)
def test_escalation_team_id_resolves_to_team_row_by_code(seeded, domain):
    row = seeded["domains"][domain]
    expected_code = DOMAIN_SPEC[domain].escalation_team
    if expected_code is None:
        assert row["escalation_team_id"] is None, row
        return
    team_id = row["escalation_team_id"]
    assert team_id is not None, row
    assert seeded["team_code_by_id"].get(str(team_id)) == expected_code


@pytest.mark.parametrize(("domain", "kind", "policy"), [
    (d, k, p) for (d, k), p in EXPECTED_NARROWING.items()
])
def test_narrowing_matrix(seeded, domain, kind, policy):
    row = seeded["domains"][domain]
    narrowing = row.get("narrowing") or {}
    assert narrowing.get(kind) == policy, narrowing


@pytest.mark.parametrize("domain", DOMAINS)
def test_ladder_matches_system_settings_default(seeded, domain):
    row = seeded["domains"][domain]
    assert list(row.get("ladder") or []) == DEFAULT_LADDER.get(domain, [])


def test_sort_order_matches_domain_spec_declaration_order(seeded):
    ordered = sorted(seeded["domains"].values(), key=lambda r: r["sort_order"])
    assert [r["name"] for r in ordered] == DOMAINS
