from sorento_crm_mcp.catalog import CATALOG


def test_catalog_includes_lookup_tools():
    names = {t.name for t in CATALOG}
    assert "crm_lookup_resolve" in names
