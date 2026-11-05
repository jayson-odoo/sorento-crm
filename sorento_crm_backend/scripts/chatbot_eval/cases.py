"""Case model and loader. Case data lives outside the repo; the loader refuses a data dir inside it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

OUTCOMES = ("answer", "clarify", "not_supported", "handover", "silent")
SPLITS = ("dev", "hidden")


class DataDirInRepoError(Exception):
    """The data dir sits inside the git work tree that holds this package."""


@dataclass
class Expect:
    outcome: str
    acceptable_alternates: list[str] = field(default_factory=list)
    must: list[dict] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    judge_note: str | None = None
    understood: dict = field(default_factory=dict)
    expected_resolved: list[str] = field(default_factory=list)
    tool: dict = field(default_factory=dict)


@dataclass
class Case:
    id: str
    split: str
    topic_code: str | None
    language: str | None
    contact: dict
    history: list[dict]
    message: dict
    variants: list[dict]
    expect: Expect


@dataclass
class LoadResult:
    cases: list[Case]
    invalid: list[tuple[str, str]]


def _repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return None


def parse_case(raw: object) -> Case:
    if not isinstance(raw, dict):
        raise ValueError("case is not a JSON object")
    for key in ("id", "split", "message", "expect"):
        if not raw.get(key):
            raise ValueError(f"missing {key}")
    if raw["split"] not in SPLITS:
        raise ValueError(f"unknown split {raw['split']!r}")
    message, exp = raw["message"], raw["expect"]
    if not isinstance(message, dict) or not message.get("text"):
        raise ValueError("missing message.text")
    if not isinstance(exp, dict) or not exp.get("outcome"):
        raise ValueError("missing expect.outcome")
    if exp["outcome"] not in OUTCOMES:
        raise ValueError(f"unknown outcome {exp['outcome']!r}")
    alternates = list(exp.get("acceptable_alternates") or [])
    bad = [a for a in alternates if a not in OUTCOMES]
    if bad:
        raise ValueError(f"unknown alternate {bad[0]!r}")
    return Case(
        id=str(raw["id"]),
        split=raw["split"],
        topic_code=raw.get("topic_code"),
        language=raw.get("language"),
        contact=dict(raw.get("contact") or {}),
        history=list(raw.get("history") or []),
        message=dict(message),
        variants=list(raw.get("variants") or []),
        expect=Expect(
            outcome=exp["outcome"],
            acceptable_alternates=alternates,
            must=list(exp.get("must") or []),
            options=list(exp.get("options") or []),
            must_not=list(exp.get("must_not") or []),
            judge_note=exp.get("judge_note"),
            understood=dict(exp.get("understood") or {}),
            expected_resolved=list(exp.get("expected_resolved") or []),
            tool=dict(exp.get("tool") or {}),
        ),
    )


def load_cases(data_dir: str | Path, split: str | None = None) -> LoadResult:
    root = Path(data_dir).resolve()
    repo = _repo_root()
    if repo is not None and (root == repo or repo in root.parents):
        raise DataDirInRepoError(f"{root} is inside the repo; keep case data outside git")
    cases: list[Case] = []
    invalid: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.json")):
        if "calibration" in path.relative_to(root).parts[:-1]:
            continue
        try:
            case = parse_case(json.loads(path.read_text()))
        except (ValueError, OSError) as exc:  # JSONDecodeError is a ValueError
            invalid.append((str(path), str(exc)))
            continue
        if split is None or case.split == split:
            cases.append(case)
    return LoadResult(cases=cases, invalid=invalid)


# --------------------------------------------------------------------------- assistant cases
# AI tools standard (PLAN-ai-tools-standard-5nov.md 2.5, DoD line 8): every feature adds two prompts to
# gold/assistant_<module>.jsonl, each naming the entity the agent should read (crm_query / crm_describe)
# or the action it should propose (crm_act). Synthetic and committed, like the parser gold, so the
# rows hold no real customer text. One JSON object per line:
#   {"id": "asst-scm-01", "module": "scm", "message": "which POs did we approve for Kohler in October?",
#    "expect": {"entity": "purchase_order"}}
#   {"id": "asst-scm-02", "module": "scm", "message": "approve PO-2026-0042",
#    "expect": {"action": "purchase_order.approve"}}

ASSISTANT_GOLD_DIR = Path(__file__).resolve().parent / "gold"
ASSISTANT_GOLD_GLOB = "assistant_*.jsonl"
#: The agent tools whose `entity` argument names what was read.
ASSISTANT_READ_TOOLS = ("crm_query", "crm_describe")
#: The agent tool whose `action` argument names what was proposed.
ASSISTANT_ACT_TOOL = "crm_act"


@dataclass
class AssistantCase:
    id: str
    module: str
    message: str
    entity: str | None = None
    action: str | None = None


def parse_assistant_case(raw: object) -> AssistantCase:
    """One gold row; exactly one of expect.entity / expect.action."""
    if not isinstance(raw, dict):
        raise ValueError("case is not a JSON object")
    for key in ("id", "module", "message", "expect"):
        if not raw.get(key):
            raise ValueError(f"missing {key}")
    if not isinstance(raw["message"], str):
        raise ValueError("message is not text")
    exp = raw["expect"]
    if not isinstance(exp, dict):
        raise ValueError("expect is not an object")
    entity, action = exp.get("entity"), exp.get("action")
    if bool(entity) == bool(action):
        raise ValueError("expect names exactly one of entity or action")
    if not isinstance(entity or action, str):
        raise ValueError("expect.entity / expect.action is not text")
    unknown = set(exp) - {"entity", "action"}
    if unknown:
        raise ValueError(f"unknown expect key {sorted(unknown)[0]!r}")
    if action and "." not in action:
        raise ValueError(f"action {action!r} is not <entity>.<verb>")
    return AssistantCase(
        id=str(raw["id"]), module=str(raw["module"]), message=raw["message"], entity=entity, action=action
    )


def load_assistant_gold(gold_dir: str | Path = ASSISTANT_GOLD_DIR) -> tuple[list[AssistantCase], list[tuple[str, str]]]:
    """Every assistant_*.jsonl row; returns (cases, invalid as (file:line, reason)). Ids are unique."""
    cases: list[AssistantCase] = []
    invalid: list[tuple[str, str]] = []
    seen: set[str] = set()
    for path in sorted(Path(gold_dir).glob(ASSISTANT_GOLD_GLOB)):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            where = f"{path.name}:{n}"
            try:
                case = parse_assistant_case(json.loads(line))
            except ValueError as exc:  # JSONDecodeError is a ValueError
                invalid.append((where, str(exc)))
                continue
            if case.id in seen:
                invalid.append((where, f"duplicate id {case.id!r}"))
                continue
            seen.add(case.id)
            cases.append(case)
    return cases, invalid


def grade_assistant(case: AssistantCase, tools: list[dict] | None) -> tuple[str, str]:
    """(verdict, reason) from the turn digest's tool list ({"tool", "args"} rows, trace.build_digest).

    verdict: "pass" when a read tool named the expected entity (or crm_act the expected action),
    "no_trace" when the turn ran no tool, else "fail" naming what was used instead.
    """
    if not tools:
        return "no_trace", "the turn ran no tool"
    used: list[str] = []
    for t in tools:
        name, args = t.get("tool"), t.get("args") or {}
        if case.entity and name in ASSISTANT_READ_TOOLS:
            if args.get("entity") == case.entity:
                return "pass", f"{name} read {case.entity}"
            used.append(f"{name}:{args.get('entity')}")
        elif case.action and name == ASSISTANT_ACT_TOOL:
            if args.get("action") == case.action:
                return "pass", f"crm_act proposed {case.action}"
            used.append(f"crm_act:{args.get('action')}")
        else:
            used.append(str(name))
    want = case.entity or case.action
    return "fail", f"expected {want}, used {', '.join(used)}"
