"""Every tool schema the agent can send must be one Gemini accepts (AI-QUERY-CORE crew pass, 5 Nov).

Gemini answers a schema outside its OpenAPI subset with a 400, and the whole agent turn then fails ("the model
provider failed"). `llm_provider._convert_tools_to_gemini` translates what it can (type unions, nullable,
unknown keys), but it cannot invent what a schema leaves out: an array with no `items` schema, an object with no
`properties`. This walks the converted declarations of every schema the agent offers and checks those rules.
No network: the check is on the declarations as they would be sent.
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.services import llm_provider
from app.services.chatbot.agent import loop, portal_writes, tools, writes

_ONE_TYPE = {"string", "number", "integer", "boolean", "array", "object"}


def _agent_schemas() -> list[dict]:
    """Every function schema the agent loop can put in a request (`loop.run_agent_turn`)."""
    out = [r.schema for r in writes.USER_READS.values()]
    out += [w.schema for w in writes.WRITES.values()]
    out += [r.schema for r in portal_writes.PORTAL_READS.values()]
    out += [w.schema for w in portal_writes.PORTAL_WRITES.values()]
    out += [tools.RESOLVE_SCHEMA, tools.FIND_SCHEMA, tools.KNOWLEDGE_SCHEMA, tools.HANDOFF_SCHEMA]
    out += [tools.PLAN_SCHEMA, tools.ANSWER_SCHEMA]
    out += loop.decision_schemas("00000000-0000-0000-0000-000000000001")
    return out


def _problems(node, where: str) -> list[str]:
    """What Gemini would refuse in one converted schema node (and every node under it)."""
    if not isinstance(node, dict):
        return [f"{where}: not an object"]
    found = []
    unknown = sorted(set(node) - llm_provider._GEMINI_SCHEMA_KEYS)
    if unknown:
        found.append(f"{where}: keys Gemini does not take: {unknown}")
    if "anyOf" in node:
        branches = node["anyOf"]
        if not isinstance(branches, list) or not branches:
            found.append(f"{where}: anyOf must be a non-empty list")
        else:
            for i, branch in enumerate(branches):
                found += _problems(branch, f"{where}.anyOf[{i}]")
        return found
    kind = node.get("type")
    if kind not in _ONE_TYPE:
        found.append(f"{where}: type must be one of {sorted(_ONE_TYPE)}, got {kind!r}")
    if kind == "array":
        if not isinstance(node.get("items"), dict):
            found.append(f"{where}: an array needs an items schema")
        else:
            found += _problems(node["items"], f"{where}.items")
    if kind == "object":
        props = node.get("properties")
        if not isinstance(props, dict) or not props:
            found.append(f"{where}: an object needs non-empty properties")
        else:
            for name, prop in props.items():
                found += _problems(prop, f"{where}.{name}")
        missing = [r for r in node.get("required") or [] if r not in (props or {})]
        if missing:
            found.append(f"{where}: required names fields it does not declare: {missing}")
    return found


def _declarations() -> list[dict]:
    converted = llm_provider._convert_tools_to_gemini(_agent_schemas())
    assert converted and converted[0]["functionDeclarations"]
    return converted[0]["functionDeclarations"]


def test_every_agent_tool_is_offered_to_gemini():
    names = {d["name"] for d in _declarations()}
    expected = {s["function"]["name"] for s in _agent_schemas()}
    assert names == expected


@pytest.mark.parametrize("declaration", _declarations(), ids=lambda d: d["name"])
def test_every_agent_tool_schema_is_one_gemini_accepts(declaration):
    if "parameters" not in declaration:
        return  # a tool without parameters is sent with none, which Gemini takes
    problems = _problems(declaration["parameters"], declaration["name"])
    assert not problems, "\n".join(problems)


def test_the_check_catches_an_array_without_items():
    """The rule this file exists for: `{"type": "array"}` alone is refused."""
    bad = {"type": "function", "function": {"name": "zzt_bad", "parameters": {
        "type": "object", "properties": {"group_by": {"type": "array"}},
    }}}
    declaration = llm_provider._convert_tools_to_gemini([bad])[0]["functionDeclarations"][0]
    assert _problems(declaration["parameters"], "zzt_bad") == ["zzt_bad.group_by: an array needs an items schema"]
