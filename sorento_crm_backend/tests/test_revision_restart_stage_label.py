"""The confirm dialog can name where a revision sends the form back to (UAC E1/E1a).

Without ``restart_stage_label`` the portal copy falls back to "goes back to the start
of its approval flow", which is the sentence for when we genuinely cannot name it -
not the target copy. E1a also forbids hardcoding "the purchasing team": three of the
four types do not route to purchasing, so the destination is read from config.

Two shapes, both covered here:

* ``restart_stage_code`` set  -> that stage, labelled;
* ``restart_stage_code`` NULL -> the first stage of the type's SLA chain (the one the
  form's own submit event starts), labelled.

It is a DISPLAY label in both. A contact never sees ``project_sales``.

Postgres only, blank scratch schema. Every config, policy and stage row is seeded
here: CI's database is empty, so "the live stock_inquiry stage config" is None there.
"""
from __future__ import annotations

import pytest

from app.services.portal_revision_service import PortalRevisionService
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    seed_config,
    seed_contact,
    seed_entity,
    seed_policy,
    seed_stage_config,
    seed_system_settings,
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _si_chain(db, policy_id):
    """The real stock inquiry shape: project_sales on submit, then purchasing."""
    seed_stage_config(
        db,
        "stock_inquiry",
        policy_id,
        stage_code="project_sales",
        team_set_code="project_sales",
        start_event="submit",
    )
    seed_stage_config(
        db,
        "stock_inquiry",
        policy_id,
        stage_code="purchasing",
        team_set_code="purchasing",
        start_event="project_sales_approve",
    )


def test_a_configured_restart_stage_is_labelled(db):
    policy_id = seed_policy(db)
    _si_chain(db, policy_id)
    seed_config(db, "stock_inquiry", restart_stage_code="purchasing")

    assert PortalRevisionService(db).restart_stage_label("stock_inquiry") == "Purchasing"


def test_a_null_restart_stage_names_the_first_stage_of_the_chain(db):
    policy_id = seed_policy(db)
    _si_chain(db, policy_id)
    seed_config(db, "stock_inquiry", restart_stage_code=None)

    assert PortalRevisionService(db).restart_stage_label("stock_inquiry") == "Project Sales"


def test_the_label_is_never_a_stage_code(db):
    """E1a: a display label. Underscores and raw codes are a bug the contact reads."""
    policy_id = seed_policy(db)
    _si_chain(db, policy_id)
    seed_config(db, "stock_inquiry", restart_stage_code=None)

    label = PortalRevisionService(db).restart_stage_label("stock_inquiry")
    assert "_" not in label
    assert label != "project_sales"


def test_a_positional_first_stage_is_named_by_the_team_that_works_it(db):
    """Purchase request and sponsorship form both start at stage_code ``main`` -
    "Main" tells the contact nothing, so the label comes from the team set behind
    it, which is what the chain actually routes to."""
    policy_id = seed_policy(db)
    seed_stage_config(
        db,
        "purchase_request",
        policy_id,
        stage_code="main",
        team_set_code="project_sales",
        start_event="submit",
    )
    seed_stage_config(
        db,
        "purchase_request",
        policy_id,
        stage_code="customer_service",
        team_set_code="customer_service",
        start_event="approved",
    )
    seed_config(db, "purchase_request", restart_stage_code=None)

    service = PortalRevisionService(db)
    assert service.restart_stage_label("purchase_request") == "Project Sales"
    # And the override list keeps the acronym-ish codes readable.
    seed_config(db, "sponsorship_form", restart_stage_code="customer_service")
    seed_stage_config(
        db,
        "sponsorship_form",
        policy_id,
        stage_code="customer_service",
        team_set_code="customer_service",
        start_event="approved",
    )
    assert service.restart_stage_label("sponsorship_form") == "Customer Service"


def test_a_configured_stage_with_no_chain_still_reads_as_a_label(db):
    """The config names a stage the SLA chain does not carry (not seeded yet, or
    renamed). Better to name what config says than to say nothing."""
    seed_config(db, "stock_inquiry", restart_stage_code="project_sales")

    assert PortalRevisionService(db).restart_stage_label("stock_inquiry") == "Project Sales"


def test_nothing_to_name_returns_none_rather_than_a_guess(db):
    """No chain and no configured stage: the generic sentence is the honest copy."""
    seed_config(db, "stock_inquiry", restart_stage_code=None)

    assert PortalRevisionService(db).restart_stage_label("stock_inquiry") is None


def test_the_policy_block_carries_the_label(db):
    """It has to reach the portal on the same call as the Revise action (UAC B1) -
    the dialog cannot fire a second request to find out where the form goes."""
    policy_id = seed_policy(db)
    _si_chain(db, policy_id)
    seed_system_settings(db, cap=3)
    seed_config(db, "stock_inquiry", restart_stage_code=None)
    contact = seed_contact(db)
    row = seed_entity(db, "stock_inquiry", contact, status="pending_purchasing")

    policy = PortalRevisionService(db).resolve_policy("stock_inquiry", row)
    assert policy.allowed is True
    assert policy.as_dict()["restart_stage_label"] == "Project Sales"


def test_a_blocked_but_enabled_type_still_names_the_destination(db):
    """The cap being spent does not change where the flow would restart, and the
    block sentence and the destination are read from one policy block."""
    policy_id = seed_policy(db)
    _si_chain(db, policy_id)
    seed_system_settings(db, cap=1)
    seed_config(db, "stock_inquiry", restart_stage_code=None)
    contact = seed_contact(db)
    row = seed_entity(db, "stock_inquiry", contact, status="pending_purchasing", revision_no=1)

    policy = PortalRevisionService(db).resolve_policy("stock_inquiry", row)
    assert policy.allowed is False
    assert policy.restart_stage_label == "Project Sales"


def test_a_disabled_type_names_nothing(db):
    """Nothing to confirm, so nothing to name - and no SLA query fired for it."""
    policy_id = seed_policy(db)
    _si_chain(db, policy_id)
    seed_config(db, "stock_inquiry", is_enabled=False)
    contact = seed_contact(db)
    row = seed_entity(db, "stock_inquiry", contact, status="pending_purchasing")

    policy = PortalRevisionService(db).resolve_policy("stock_inquiry", row)
    assert policy.enabled is False
    assert policy.restart_stage_label is None


def test_the_label_names_the_stage_the_revision_actually_restarts_at(db):
    """The contract that matters: the label and the restart are ONE selection. If
    they ever came from two places the dialog would promise the wrong destination."""
    policy_id = seed_policy(db)
    _si_chain(db, policy_id)
    seed_config(db, "stock_inquiry", restart_stage_code="purchasing")

    service = PortalRevisionService(db)
    stage_code, _start_event = service._restart_stage("stock_inquiry")  # noqa: SLF001
    assert stage_code == "purchasing"
    assert service.restart_stage_label("stock_inquiry") == "Purchasing"
