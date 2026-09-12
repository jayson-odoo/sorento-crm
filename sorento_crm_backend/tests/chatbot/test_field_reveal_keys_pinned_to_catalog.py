"""AC-964 guardrail: `FIELD_REVEAL_KEYS` stays pinned to the MCP catalogue.

`contact_field_reveal_service.FIELD_REVEAL_KEYS` is a frozen literal, not a live read of
`mcp_tools.restricted_fields`, because the deployed backend image cannot import
`sorento_crm_mcp` at runtime (compose builds the backend with
`context: ./sorento_crm_backend`, the package is not in `requirements.txt`, no volume
mounts it in) - see that module's docstring for the outage this caused (Contacts >
Access > Field reveals showed "No restricted field exists yet" even though the catalogue
declared three). The precedent for a frozen-set-plus-CI-test pair over that same gap is
`app/services/chatbot/lanes/business/fetch.py::CHATBOT_READ_ONLY_TOOLS` and its
`tests/chatbot/test_tool_pool_is_read_only.py`.

This file is where the literal and the catalogue are held together: it imports the
catalogue - which CI and a checkout both CAN do, unlike the deployed container - and
asserts the literal equals the union of every `ToolSpec.restricted_fields` pair declared
across the merged catalogue. It fails in either direction: a new `restricted=` key added
to a presenter without updating the literal, or a stale literal entry the catalogue no
longer declares.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS


def _merged_catalog_restricted_fields() -> set[tuple[str, str]]:
    """The catalogue's own answer, read the same way `mcp_tool_capability_service.
    _load_catalog_specs` does.

    A shared backend venv can carry a STALE editable install of `sorento_crm_mcp`
    pointing at a different checkout (the "lane backend imports primary MCP catalog"
    gotcha), which Python's import machinery resolves ahead of a plain `sys.path`
    entry - UNLESS a directory is appended to `sys.path` first, which lets the
    interpreter's regular path-based finder win over the stale editable one. This
    appends the `sorento_crm_mcp` that sits next to THIS checkout's own
    `sorento_crm_backend`, so the test reads the same catalogue this checkout ships.
    """
    repo_root = Path(__file__).resolve().parents[3]
    mcp_root = repo_root / "sorento_crm_mcp"
    if str(mcp_root) not in sys.path:
        sys.path.append(str(mcp_root))

    from sorento_crm_mcp.catalog import CATALOG
    from sorento_crm_mcp.module_loader import merged_catalog

    pairs: set[tuple[str, str]] = set()
    for spec in merged_catalog(CATALOG):
        pairs.update(getattr(spec, "restricted_fields", None) or ())
    return pairs


def test_field_reveal_keys_literal_matches_the_catalog() -> None:
    catalog_pairs = _merged_catalog_restricted_fields()

    missing = catalog_pairs - set(FIELD_REVEAL_KEYS)
    stale = set(FIELD_REVEAL_KEYS) - catalog_pairs

    assert not missing, (
        "the MCP catalogue declares these restricted_fields pairs but "
        "contact_field_reveal_service.FIELD_REVEAL_KEYS does not, so the Contacts > "
        f"Access checklist would never offer them: {sorted(missing)}"
    )
    assert not stale, (
        "contact_field_reveal_service.FIELD_REVEAL_KEYS lists these pairs but the MCP "
        "catalogue no longer declares them restricted - the checklist would offer a key "
        f"nothing gates any more: {sorted(stale)}"
    )
