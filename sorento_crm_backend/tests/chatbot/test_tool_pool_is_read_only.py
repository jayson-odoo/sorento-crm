"""H58 / AC-813: the Tool-RAG pool holds READ tools only, walked against the real catalogue.

The chatbot picks one tool per turn by cosine similarity and calls the single top hit
(`lanes/business/fetch.py::tool_filter`), so every tool in the embedding pool is a tool a
customer's phrasing can cause to be CALLED. Five write tools were in it -
`crm_it_support_ticket_create`, `crm_complaint_close`, `crm_order_cancel`,
`crm_purchase_request_approve`, `crm_purchase_request_reject` - with nothing between them
and a live conversation but the fact that no phrasing had scored them first.

The catalogue's own `method` is the source of truth, and this file walks the REAL one
(`sorento_crm_mcp/catalog.py`, via `_load_catalog_specs`) rather than a fixture: a fixture
would go stale on the day the next POST tool is added, which is exactly the day this test
exists for.
"""
from __future__ import annotations

import pytest

from app.services.mcp_tool_capability_service import (
    _load_catalog_specs,
    build_capability_documents,
    read_only_tool_names,
)


def _catalog_by_name() -> dict[str, object]:
    return {spec.name: spec for spec in _load_catalog_specs()}


def test_the_catalogue_still_carries_non_get_tools() -> None:
    """The guard's own precondition: if every tool were GET this file would pass for the
    wrong reason. It is asserted rather than assumed so a catalogue change that removed
    the write tools would announce itself instead of quietly turning the two tests below
    into tautologies."""
    non_get = [s.name for s in _load_catalog_specs() if str(s.method).upper() != "GET"]

    assert non_get, (
        "the MCP catalogue no longer holds a single non-GET tool - this file's two "
        "exclusion tests now prove nothing; retire them or re-point them"
    )


def test_every_embedded_tool_is_a_get_tool() -> None:
    """AC-813: nothing that can write is retrievable by similarity."""
    catalog = _catalog_by_name()

    offenders = []
    for doc in build_capability_documents(include_planned=False):
        spec = catalog.get(doc.source_key)
        if spec is None:
            # A tool-definitions FILE entry, not a catalogue entry: it has no method and
            # no path, so it is not an HTTP tool this rule can speak about.
            continue
        if str(spec.method).upper() != "GET":
            offenders.append(f"{doc.source_key} ({spec.method})")

    assert not offenders, (
        "these NON-GET tools are in the Tool-RAG embedding pool, so a business question "
        "can select one and the chatbot will call it: " + ", ".join(sorted(offenders))
    )


@pytest.mark.parametrize(
    "tool_name",
    [
        "crm_it_support_ticket_create",
        "crm_complaint_close",
        "crm_order_cancel",
        "crm_purchase_request_approve",
        "crm_purchase_request_reject",
    ],
)
def test_the_five_write_tools_are_named_and_excluded(tool_name: str) -> None:
    """The five the audit found, by name, so a regression says WHICH one came back."""
    assert tool_name not in read_only_tool_names(), (
        f"{tool_name} is being treated as a read tool - check its `method` in "
        "sorento_crm_mcp/catalog.py"
    )
    embedded = {doc.source_key for doc in build_capability_documents(include_planned=False)}
    assert tool_name not in embedded


def test_read_only_names_are_derived_from_the_catalogue_not_a_list() -> None:
    """One source of truth: the set IS the catalogue's GET tools, no more and no less.

    A hand-kept allow-list would pass the tests above on the day it was written and fail
    silently on the day the next tool landed, so the derivation itself is the thing worth
    pinning.
    """
    expected = {s.name for s in _load_catalog_specs() if str(s.method).upper() == "GET"}

    assert read_only_tool_names() == expected
