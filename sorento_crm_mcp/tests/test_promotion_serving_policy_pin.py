"""The promo-serving tools are hard-pinned to the backend's per-type policy.

`serving_policy=true` goes out on every call and is deliberately NOT a tool
parameter: the agent must not be able to switch the policy off and re-introduce
an expired special that nobody will honour.
"""
from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import TOOL_DEFAULT_QUERY_PARAMS

PROMO_SERVING_TOOLS = (
    "crm_marketing_promotions_list",
    "crm_marketing_promotion_products_list",
    "crm_marketing_promotion_attachments_list",
)


def _spec(name):
    return next(spec for spec in CATALOG if spec.name == name)


def test_every_promo_serving_tool_pins_the_policy():
    for name in PROMO_SERVING_TOOLS:
        assert TOOL_DEFAULT_QUERY_PARAMS.get(name, {}).get("serving_policy") == "true", name


def test_the_policy_is_not_an_agent_facing_parameter():
    for name in PROMO_SERVING_TOOLS:
        assert "serving_policy" not in _spec(name).query_params, name


def test_descriptions_teach_the_expired_but_usable_phrasing():
    for name in PROMO_SERVING_TOOLS:
        description = _spec(name).description
        assert "expired_but_usable" in description, name
        assert "STILL APPLIES" in description, name
