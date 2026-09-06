"""H58 / AC-813: the Tool-RAG pool holds READ tools only, walked against the real catalogue.

The chatbot picks one tool per turn by cosine similarity and calls the single top hit
(`lanes/business/fetch.py::tool_filter`), so every tool in the embedding pool is a tool a
customer's phrasing can cause to be CALLED. Five write tools were in it -
`crm_it_support_ticket_create`, `crm_complaint_close`, `crm_order_cancel`,
`crm_purchase_request_approve`, `crm_purchase_request_reject` - with nothing between them
and a live conversation but the fact that no phrasing had scored them first.

**The test is "does the catalogue declare it a read", not "is it a GET".** Method is
TRANSPORT: three catalogue tools are POST purely because their input does not fit in a
query string (`crm_lookup_resolve`, `crm_portal_link_get`, `user_guides_read`) and they
write nothing, so the ToolSpec carries an explicit `read_only=True` for them. The flag
defaults to False, which is what keeps a genuinely writing tool out by construction.

Everything here walks the REAL catalogue (`sorento_crm_mcp/catalog.py`, via
`_load_catalog_specs`) rather than a fixture: a fixture would go stale on the day the next
writing tool is added, which is exactly the day this file exists for.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.services.mcp_tool_capability_service import (
    _load_catalog_specs,
    build_capability_documents,
    read_only_tool_names,
)

# The five the audit found. Named, so a regression says WHICH one came back rather than
# just that the count moved, and so flipping one to `read_only=True` in the catalogue
# cannot pass review by accident.
WRITE_TOOLS = (
    "crm_it_support_ticket_create",
    "crm_complaint_close",
    "crm_order_cancel",
    "crm_purchase_request_approve",
    "crm_purchase_request_reject",
)

# The POST tools that only READ. Each carries `read_only=True` in the catalogue with a
# comment saying why; they are in the pool on purpose and the AI assistant's tool search
# shares that pool.
READ_ONLY_POST_TOOLS = (
    "crm_lookup_resolve",
    "crm_portal_link_get",
    "user_guides_read",
)


def _catalog_by_name() -> dict[str, Any]:
    return {spec.name: spec for spec in _load_catalog_specs()}


def _reads(spec: Any) -> bool:
    return str(getattr(spec, "method", "GET")).upper() == "GET" or bool(
        getattr(spec, "read_only", False)
    )


def test_the_catalogue_still_carries_writing_tools() -> None:
    """The guard's own precondition: if nothing in the catalogue could write, this file
    would pass for the wrong reason. Asserted rather than assumed, so a catalogue change
    that removed the write tools announces itself instead of quietly turning the exclusion
    tests below into tautologies."""
    writers = [s.name for s in _load_catalog_specs() if not _reads(s)]

    assert writers, (
        "the MCP catalogue no longer holds a single writing tool - the exclusion tests in "
        "this file now prove nothing; retire them or re-point them"
    )


def test_every_embedded_tool_is_declared_read_only() -> None:
    """AC-813: nothing that can write is retrievable by similarity."""
    catalog = _catalog_by_name()

    offenders = []
    for doc in build_capability_documents(include_planned=False):
        spec = catalog.get(doc.source_key)
        if spec is None:
            # A tool-definitions FILE entry, not a catalogue entry: it has no method and
            # no path, so it is not an HTTP tool this rule can speak about.
            continue
        if not _reads(spec):
            offenders.append(f"{doc.source_key} ({spec.method})")

    assert not offenders, (
        "these WRITING tools are in the Tool-RAG embedding pool, so a business question "
        "can select one and the chatbot will call it: " + ", ".join(sorted(offenders))
    )


@pytest.mark.parametrize("tool_name", WRITE_TOOLS)
def test_the_five_write_tools_are_named_and_excluded(tool_name: str) -> None:
    """By name, both from the allowed set and from the pool.

    A future edit that added `read_only=True` to one of these in the catalogue would be
    declaring that cancelling an order is a read, and this is where that gets caught.
    """
    catalog = _catalog_by_name()
    spec = catalog.get(tool_name)
    assert spec is not None, f"{tool_name} is no longer in the MCP catalogue - retire this case"
    assert not getattr(spec, "read_only", False), (
        f"{tool_name} is declared read_only=True in sorento_crm_mcp/catalog.py. It WRITES; "
        "the flag is for a POST whose body is transport, never for a side effect."
    )

    assert tool_name not in read_only_tool_names()
    embedded = {doc.source_key for doc in build_capability_documents(include_planned=False)}
    assert tool_name not in embedded


@pytest.mark.parametrize("tool_name", READ_ONLY_POST_TOOLS)
def test_a_post_tool_that_declares_read_only_stays_in_the_pool(tool_name: str) -> None:
    """The other half of the rule, and the reason it is not "method == GET".

    These three take a POST body because their input does not fit in a query string. They
    read; excluding them would have taken three useful tools out of the assistant's search
    for a transport detail.
    """
    catalog = _catalog_by_name()
    spec = catalog.get(tool_name)
    assert spec is not None, f"{tool_name} is no longer in the MCP catalogue - retire this case"
    assert str(spec.method).upper() != "GET", (
        f"{tool_name} is a GET now, so it proves nothing about the read_only flag - "
        "re-point this case at a POST tool that only reads"
    )
    assert spec.read_only is True

    assert tool_name in read_only_tool_names()
    embedded = {doc.source_key for doc in build_capability_documents(include_planned=False)}
    assert tool_name in embedded


def test_the_flag_and_not_the_method_is_what_admits_a_post_tool() -> None:
    """The rule stated directly on a pair of synthetic specs: same method, one flag apart.

    The two cases above prove it on the real catalogue, which is what matters; this proves
    the DERIVATION rather than today's data, so the day the catalogue happens to hold no
    read-only POST the rule is still pinned.
    """
    template = next(s for s in _load_catalog_specs() if str(s.method).upper() != "GET")
    writes = dataclasses.replace(template, name="zzt_post_writes", read_only=False)
    reads = dataclasses.replace(template, name="zzt_post_reads", read_only=True)

    assert not _reads(writes)
    assert _reads(reads)


def test_read_only_names_are_derived_from_the_catalogue_not_a_list() -> None:
    """One source of truth: the set IS the catalogue's own declaration, no more and no less.

    A hand-kept allow-list would pass every test above on the day it was written and fail
    silently on the day the next tool landed, so the derivation itself is the thing worth
    pinning.
    """
    expected = {s.name for s in _load_catalog_specs() if _reads(s)}

    assert read_only_tool_names() == expected


def test_the_field_survives_the_import_path_the_backend_actually_uses() -> None:
    """`_load_catalog_specs` prefers an IMPORTED `sorento_crm_mcp.catalog` and falls back to
    loading the file by path, so the field has to exist on whichever object comes back.

    Worth its own case because the failure is silent in the safe-looking direction: a stale
    package without the field makes `getattr(spec, "read_only", False)` answer False for
    everything, and the three read-only POST tools would drop out of the pool with no error
    anywhere. This is where that gets noticed.
    """
    specs = list(_load_catalog_specs())

    assert specs, "the catalogue loaded empty"
    assert all(hasattr(s, "read_only") for s in specs), (
        "the ToolSpec reaching the CRM has no `read_only` field - the resolved "
        "sorento_crm_mcp package is older than this backend"
    )
    assert any(s.read_only for s in specs), (
        "no spec on the resolved catalogue declares read_only=True, so the three POST "
        "reads are silently out of the Tool-RAG pool"
    )
