"""R3 RED tests - roster cap is data (UAC AC-1710; PLAN-chatbot-answer-half-reattach.md
"Roster cap (owner ruling 20 Sep 2026): configurable, default 10").

New column `chatbot_entity_kinds.roster_cap` (INTEGER NOT NULL, server_default 10),
migration `chatbot_rearch_s10` (down_revision `chatbot_rearch_s9`, the current single
head), exposed on `ChatbotEntityKindBody`/`ChatbotEntityKindResponse`/`_kind_out`
(`app/api/v1/system/chatbot_config.py`), read at the customer roster cap
(`gate.py:938`, today a literal `[:8]`) and the product/attachment roster cap
(`gate.py`'s `specific_options` build, today UNCAPPED). The did-you-mean list cap is
slice R4, out of this file's scope (per the captain's brief).

**MEASURED, flagged, not resolved here: no config seam reaches `gate.run_gate` or
`resolve_gate.run` today, at all.** `did_you_mean`'s own path
(`chatbot_entity_kinds.did_you_mean` -> `turn/policy.py::Policy` ->
`turn/apply.py::_did_you_mean`) is a COMPLETELY SEPARATE system from
`lanes/business/gate.py` - `run_gate`'s signature
(`item, *, parser, resolver, session, tier_gate, aggregate`) carries no `db`, no
config object, nothing `did_you_mean` could be read off. `resolve_gate.run`'s own
signature (`ctx, entry, item, *, services: ResolveGateServices, space_id,
probe_default_start, dry_run`) is the same story - `ResolveGateServices` is three
callables (`access_types`, `resolve_entity`, `probe`), not a config carrier. So
"the existing did_you_mean flag's own path is the precedent" (the plan's own words)
does not hold as a literal code seam to reuse; `roster_cap` needs a NEW plumbing
path from `chatbot_entity_kinds` to `gate.py`, not a rewire of an existing one.

Given that gap, the functional cap tests below thread a `roster_cap` keyword
straight onto `run_gate` (this session's own guess at the name, following the R2
tester's precedent for an unnamed seam - a coder naming it differently only needs
to update the CALL SITE these tests make, not what they assert about the returned
roster's SIZE) via a small shim (`_call_run_gate`) that falls back to a call with no
`roster_cap` kwarg if `run_gate` does not accept one yet - so every cap test is red
today via a SIZE assertion (today's literal `[:8]`, or no cap at all), never via a
`TypeError` on an unknown keyword.
"""
from __future__ import annotations

import inspect
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.services.chatbot.lanes.business import gate as gate_mod
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session, pg_session, unique_code

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GATE_PY = BACKEND_ROOT / "app" / "services" / "chatbot" / "lanes" / "business" / "gate.py"
ALEMBIC_VERSIONS = BACKEND_ROOT / "alembic" / "versions"

VIEW = "system.chat_history.view"
MANAGE = "system.chatbot_config.manage"
ENTITY_KINDS_BASE = "/api/v1/system/chatbot/entity-kinds"


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #


class TestMigrationExistsAndChainsOntoTheCurrentHead:
    def test_chatbot_rearch_s10_file_exists_with_the_right_shape(self) -> None:
        path = ALEMBIC_VERSIONS / "chatbot_rearch_s10.py"
        assert path.exists(), f"missing migration: {path}"
        import importlib.util

        spec = importlib.util.spec_from_file_location("chatbot_rearch_s10", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        assert module.revision == "chatbot_rearch_s10"
        assert len(module.revision) <= 32, "alembic head revision ids must be <= 32 chars"
        assert module.down_revision == "chatbot_rearch_s9", (
            "must chain onto the current single head, chatbot_rearch_s9"
        )
        assert hasattr(module, "upgrade") and hasattr(module, "downgrade")

    def test_no_other_migration_already_claims_chatbot_rearch_s9_as_its_parent(self) -> None:
        """A second head off `chatbot_rearch_s9` breaks CI's `check-migration-heads`
        gate - this is the ONE child s9 may have."""
        import importlib.util

        claimants = []
        for path in sorted(ALEMBIC_VERSIONS.glob("*.py")):
            if path.stem == "chatbot_rearch_s10":
                continue
            text = path.read_text(encoding="utf-8")
            if 'down_revision = "chatbot_rearch_s9"' in text or "down_revision = 'chatbot_rearch_s9'" in text:
                claimants.append(path.name)
        assert claimants == [], f"chatbot_rearch_s9 already has a child: {claimants}"


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


class TestModelColumn:
    def test_chatbot_entity_kind_has_roster_cap_defaulting_to_10(self) -> None:
        from app.models.chatbot_policy import ChatbotEntityKind

        assert hasattr(ChatbotEntityKind, "roster_cap"), (
            "ChatbotEntityKind model has no roster_cap column yet"
        )
        with blank_session() as db:
            row = ChatbotEntityKind(
                id=str(uuid.uuid4()),
                kind=unique_code("kind"),
                label="ZZT kind",
                resolver_source="zzt_source",
                default_narrowing="optional_filter",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            assert row.roster_cap == 10, f"server_default must be 10, got {row.roster_cap!r}"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

_GRANTS: set[str] = set()
_ACTOR: dict = {"id": None, "name": "ZZT Roster Cap Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(VIEW)
    _GRANTS.add(MANAGE)
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in _GRANTS
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def pg_db():
    with pg_session() as db:
        yield db


@pytest.fixture()
def client(pg_db):
    def _override_db():
        try:
            yield pg_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _kind_body(kind: str, *, roster_cap: int = 10) -> dict:
    return {
        "kind": kind,
        "label": f"ZZT {kind}",
        "resolver_source": "zzt_source",
        "did_you_mean": True,
        "default_narrowing": "optional_filter",
        "family_grouping": None,
        "base_property_words": {},
        "roster_cap": roster_cap,
    }


class TestApiRoundTrip:
    def test_post_then_get_carries_roster_cap_in_the_response(self, client) -> None:
        kind = unique_code("kind")
        resp = client.post(ENTITY_KINDS_BASE, json=_kind_body(kind, roster_cap=7))
        assert resp.status_code in (200, 201), resp.text
        body = resp.json()
        assert body.get("roster_cap") == 7, (
            "response_model drops undeclared fields - roster_cap must be a declared "
            f"field on ChatbotEntityKindResponse: {body}"
        )
        get_resp = client.get(f"{ENTITY_KINDS_BASE}/{kind}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json().get("roster_cap") == 7

    def test_put_updates_roster_cap(self, client) -> None:
        kind = unique_code("kind")
        client.post(ENTITY_KINDS_BASE, json=_kind_body(kind, roster_cap=10))
        put_resp = client.put(f"{ENTITY_KINDS_BASE}/{kind}", json=_kind_body(kind, roster_cap=4))
        assert put_resp.status_code == 200, put_resp.text
        assert put_resp.json().get("roster_cap") == 4

    def test_value_1_is_rejected_422(self, client) -> None:
        kind = unique_code("kind")
        resp = client.post(ENTITY_KINDS_BASE, json=_kind_body(kind, roster_cap=1))
        assert resp.status_code == 422, resp.text

    def test_value_2_is_accepted(self, client) -> None:
        kind = unique_code("kind")
        resp = client.post(ENTITY_KINDS_BASE, json=_kind_body(kind, roster_cap=2))
        assert resp.status_code in (200, 201), resp.text
        assert resp.json().get("roster_cap") == 2


# --------------------------------------------------------------------------- #
# gate.py - the two rosters it cuts, cap threaded straight onto run_gate
# --------------------------------------------------------------------------- #


def _call_run_gate(item: dict[str, Any], *, parser: dict[str, Any], resolver: dict[str, Any], roster_cap: int):
    sig = inspect.signature(gate_mod.run_gate)
    if "roster_cap" in sig.parameters:
        return gate_mod.run_gate(dict(item), parser=parser, resolver=resolver, roster_cap=roster_cap)
    return gate_mod.run_gate(dict(item), parser=parser, resolver=resolver)


def _many_customer_matches(n: int) -> list[dict[str, Any]]:
    return [
        {
            "entity_type": "customer",
            "uuid": f"cust-{i:03d}",
            "canonical_code": f"CUST{i:03d}",
            "company_code": "SRT",
            "display": {"customer_name": f"ZZT CUSTOMER {i:03d} SDN BHD"},
        }
        for i in range(n)
    ]


def _many_product_matches(n: int) -> list[dict[str, Any]]:
    return [
        {
            "entity_type": "product",
            "uuid": f"prod-{i:03d}",
            "canonical_code": f"ZZTPROD{i:03d}",
            "match_tier": "prefix",
        }
        for i in range(n)
    ]


class TestCustomerRosterCap:
    @pytest.mark.parametrize("cap", [3, 10])
    def test_customer_roster_never_exceeds_the_cap(self, cap: int) -> None:
        """cap=10 is a MEASURED GREEN CONTROL today: the literal `[:8]` happens to
        satisfy `<= 10` vacuously (8 <= 10) without honouring config at all -
        `TestNoLiteralCapRemainsInGate` is what actually pins the literal's removal.
        cap=3 is genuinely red (8 > 3)."""
        parser = {
            "domain_hint": "order",
            "entities": [{"raw": "zzt", "hint": "customer", "current_message": True}],
        }
        resolver = {
            "resolutions": [
                {"token": "zzt", "matches": _many_customer_matches(12)},
            ],
            "unresolved_tokens": [],
        }
        gate = _call_run_gate({}, parser=parser, resolver=resolver, roster_cap=cap)
        assert gate.get("require_specific") is True, gate
        entities = gate.get("compatible_entities") or []
        assert len(entities) <= cap, (
            f"customer roster held {len(entities)} options, cap was {cap}: {entities}"
        )


class TestProductRosterCap:
    @pytest.mark.parametrize("cap", [3, 10])
    def test_incoming_product_roster_never_exceeds_the_cap(self, cap: int) -> None:
        parser = {
            "domain_hint": "incoming",
            "entities": [{"raw": "zzt", "hint": "product", "current_message": True}],
        }
        resolver = {
            "resolutions": [
                {"token": "zzt", "matches": _many_product_matches(12)},
            ],
            "unresolved_tokens": [],
        }
        gate = _call_run_gate({}, parser=parser, resolver=resolver, roster_cap=cap)
        assert gate.get("require_specific") is True, gate
        clarification = gate.get("gate_clarification") or ""
        numbered_lines = re.findall(r"^\d+\.", clarification, re.MULTILINE)
        assert len(numbered_lines) <= cap, (
            f"product/attachment roster printed {len(numbered_lines)} lines, cap was "
            f"{cap}: {clarification!r}"
        )


class TestNoLiteralCapRemainsInGate:
    def test_no_bare_8_slice_cuts_a_roster(self) -> None:
        source = GATE_PY.read_text(encoding="utf-8")
        hits = [
            f"{i}: {line.strip()}"
            for i, line in enumerate(source.splitlines(), start=1)
            if "[:8]" in line
        ]
        assert hits == [], f"a literal [:8] still cuts a roster in gate.py: {hits}"
