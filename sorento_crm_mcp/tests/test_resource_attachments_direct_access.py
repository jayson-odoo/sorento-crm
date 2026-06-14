"""crm_resource_attachments_list is hard-pinned to direct-access types.

The tool must always send direct_access_only=true to the backend so it only
surfaces dealer-downloadable (is_direct_access) documents.
"""
from sorento_crm_mcp.server import TOOL_DEFAULT_QUERY_PARAMS


def test_resource_attachments_list_pins_direct_access_only():
    defaults = TOOL_DEFAULT_QUERY_PARAMS.get("crm_resource_attachments_list", {})
    assert defaults.get("direct_access_only") == "true"
