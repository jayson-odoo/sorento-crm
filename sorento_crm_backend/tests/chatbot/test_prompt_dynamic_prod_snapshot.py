"""PROMPT-DYNAMIC: the live production parser prompt (owner-supplied, 1 Oct 2026) published
as ONE unlabelled version that uses registry variables where, and only where, the
registry reproduces the exact text (migration `pdyn_0003_prod_identical`).

The rendered prompt must equal the owner's file byte for byte, whatever the tables hold:
a registry that differs keeps its list literal and is reported, never silently reworded.
"""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import re

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry, chatbot_prompt_vars as pv
from tests._pg_fixture import pg_session

KEY = "chatbot_semantic_parser"
BACKEND = pathlib.Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"
SNAPSHOT = BACKEND / "alembic" / "data" / "chatbot_semantic_parser.prod-20261001.txt"


def _load():
    path = VERSIONS / "pdyn_0003_prod_identical.py"
    spec = importlib.util.spec_from_file_location("_t_pdyn_0003", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_cache():
    pv.clear_cache()
    ai_prompt_registry.bust_cache()
    yield
    pv.clear_cache()
    ai_prompt_registry.bust_cache()


def _source() -> str:
    return SNAPSHOT.read_text(encoding="utf-8")


def _expected(date: str = "TODAY") -> str:
    return _source().replace("{{current_date}}", date)


def _render(db, version_id: str) -> str:
    out, _ = ai_prompt_registry.render(db, KEY, current_date="TODAY", override_version_id=version_id)
    return out


def _row(db, version: int) -> AIPromptVersion:
    return db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY, AIPromptVersion.version == version).one()


def _seed_registries_to_the_file(db) -> None:
    """Tables shaped like the owner's text: the policy block's 14 domains (no `sales`, and
    master_products narrowing product list_all), only the two order statuses, the five
    agents and the seven access levels."""
    db.execute(text("DELETE FROM chatbot_domains WHERE name = 'sales'"))
    db.execute(
        text("UPDATE chatbot_domains SET narrowing = '{\"product\": \"list_all\"}'::jsonb WHERE name = 'master_products'")
    )
    db.execute(text("DELETE FROM chatbot_status_words WHERE value NOT IN ('outstanding', 'delivered')"))
    db.execute(text("UPDATE access_agents SET is_active = false"))
    for code in ("general_enquiries", "order_enquiries", "incoming_stock_enquiries", "marketing_form", "it_support"):
        db.execute(
            text(
                "INSERT INTO access_agents (id, code, name, is_active, assign_to_new_internal_contacts, "
                "synced_to_excel, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :c, :c, true, false, false, now(), now()) "
                "ON CONFLICT (code) DO UPDATE SET is_active = true"
            ),
            {"c": code},
        )
    db.execute(text("UPDATE contact_access_types SET is_active = false"))
    for i, name in enumerate(
        ["Sorento Dealer", "Mocha Dealer", "Mocha Office", "Cabana Dealer", "Cabana Office", "End User", "Sorento Office"]
    ):
        db.execute(
            text(
                "INSERT INTO contact_access_types (code, name, is_active, sort_order, keywords, created_at, updated_at) "
                "VALUES (:c, :n, true, :s, '[]', now(), now())"
            ),
            {"c": f"zzt{i}", "n": name, "s": -100 + i},
        )
    db.flush()
    pv.clear_cache()


def _actions(row: AIPromptVersion) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in (row.config_json or {}).get("identical_report") or []:
        out.setdefault(r["action"], []).append(r["variable"])
    return out


def test_the_snapshot_is_the_owner_text_verbatim():
    raw = SNAPSHOT.read_bytes()
    assert hashlib.sha256(raw).hexdigest().startswith("fdbf2ea1ba0cc019")
    assert raw.count(b"\n") == 1741


def test_seeded_registries_become_variables_and_the_render_equals_the_file():
    mod = _load()
    with pg_session() as db:
        _seed_registries_to_the_file(db)
        top = db.execute(text("SELECT max(version) FROM ai_prompt_versions WHERE name = :n"), {"n": KEY}).scalar()
        version = mod.apply(db.connection())
        assert version == int(top) + 1
        row = _row(db, version)
        replaced = set(_actions(row).get("replaced", []))
        assert {"teams", "status_values", "agents", "access_levels", "domains_detail", "entity_kinds_detail"} <= replaced
        for name in replaced:
            assert "{{" + name + "}}" in row.template
        assert _render(db, row.id) == _expected()


def test_a_registry_that_differs_keeps_its_list_literal_and_is_reported():
    """Unseeded tables carry the `sales` domain and statuses the owner's text does not."""
    mod = _load()
    with pg_session() as db:
        version = mod.apply(db.connection())
        row = _row(db, version)
        kept = {r["variable"]: r for r in row.config_json["identical_report"] if r["action"] == "kept literal"}
        assert "domains" in kept and "sales" in kept["domains"]["only_in_registry"]
        assert "{{domains}}" not in row.template
        assert re.search(r"domain_hint = ONE of: master_products \| .* \| purchase_cost \| null", row.template)
        assert _render(db, row.id) == _expected()


def test_never_labels_and_never_touches_an_existing_version():
    mod = _load()
    with pg_session() as db:
        before = {
            r.id: (r.version, r.template)
            for r in db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY)
        }
        labels = {(l.label, l.version_id) for l in db.query(AIPromptLabel).filter(AIPromptLabel.name == KEY)}
        version = mod.apply(db.connection())
        db.expire_all()
        after = {r.id: (r.version, r.template) for r in db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY)}
        assert {k: v for k, v in after.items() if k in before} == before
        assert len(after) == len(before) + 1
        assert {(l.label, l.version_id) for l in db.query(AIPromptLabel).filter(AIPromptLabel.name == KEY)} == labels
        assert not db.query(AIPromptLabel).filter(AIPromptLabel.version_id == _row(db, version).id).count()


def test_idempotent():
    mod = _load()
    with pg_session() as db:
        assert mod.apply(db.connection()) is not None
        count = db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY).count()
        assert mod.apply(db.connection()) is None
        assert db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY).count() == count


def test_downgrade_deletes_only_its_own_unlabelled_row():
    mod = _load()
    with pg_session() as db:
        count = db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY).count()
        version = mod.apply(db.connection())
        mod.remove(db.connection())
        db.expire_all()
        assert db.query(AIPromptVersion).filter(AIPromptVersion.name == KEY).count() == count
        assert not db.query(AIPromptVersion).filter(
            AIPromptVersion.name == KEY, AIPromptVersion.version == version
        ).count()
