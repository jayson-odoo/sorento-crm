# Composers return data first, text second (PLAN-chatbot-turn-rearch.md "Fetch and
# compose", AC-1531): `compose(envelopes, state, policy, ctx) -> Answer`, `Answer =
# {sections, question, offer, canned, files, actions, text}`. The #930 grammar
# (contract 102 to 105) renders `text` FROM the sections here - `figures` keeps
# today's per-row shape (`{"fields": [{"label", "value"}], ...}`, the same shape
# `lanes/business/fetch.py::output_structurer` already produces), so a domain's own
# composer (kept, unchanged per the plan) has somewhere familiar to write into.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.chatbot.turn.pending import ask as pending_ask
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.state import State

_ATTACHED_SENTENCE = "I have attached the file(s) below."


@dataclass
class Section:
    domain: str
    entities: list[Any] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    miss: list[Any] = field(default_factory=list)


@dataclass
class Offer:
    teams: list[str] = field(default_factory=list)


@dataclass
class Answer:
    sections: list[Section] = field(default_factory=list)
    question: Any = None
    offer: Offer | None = None
    canned: list[Any] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""


def _row_key(fig: dict[str, Any]) -> tuple:
    return tuple((f.get("label"), f.get("value")) for f in fig.get("fields") or [])


def _render_row(n: int, fig: dict[str, Any]) -> str:
    lines: list[str] = []
    for i, f in enumerate(fig.get("fields") or []):
        prefix = f"{n}. " if i == 0 else ""
        lines.append(f"{prefix}*{f.get('label')}:* {f.get('value')}")
    return "\n".join(lines)


def _file_key(f: dict[str, Any]) -> Any:
    return f.get("url") or f.get("id") or f.get("filename")


def _team_pick_question(missed_domains: list[str], policy: Policy):
    """Team pick over the missed domains (contract 106-113, 127; AC-1533). A single
    missed team is yes/no over that one team; two or more become a numbered pick plus
    a "No it's okay" hold option (contract 43).

    `Pending.team` stays a single `str | None` (S2): set when there is exactly one
    team, else None until the pick resolves - each option carries ITS OWN team under
    `payload.team` (captain ruling, 16 Sep 2026).
    """
    teams: list[tuple[str, str]] = []
    seen: set[str] = set()
    for domain in missed_domains:
        row = policy.domain(domain) if policy else None
        team = row.escalation_team_code if row else None
        if not team or team in seen:
            continue
        seen.add(team)
        teams.append((team, row.label if row else domain))

    if not teams:
        return None

    if len(teams) == 1:
        team, label = teams[0]
        options = [{"position": 1, "label": label, "entity_type": "team", "payload": {"team": team}}]
        return pending_ask("team_pick", options, team=team, expects="yes_no")

    options = [
        {"position": i + 1, "label": label, "entity_type": "team", "payload": {"team": team}}
        for i, (team, label) in enumerate(teams)
    ]
    options.append(
        {
            "position": len(options) + 1,
            "label": "No it's okay",
            "entity_type": "team",
            "payload": {"team": None},
        }
    )
    return pending_ask("team_pick", options, team=None, expects="pick")


def compose(envelopes: list[dict[str, Any]], state: State, policy: Policy, ctx: Any) -> Answer:
    sections: list[Section] = []
    seen_rows: set[tuple] = set()
    text_parts: list[str] = []
    missed_domains: list[str] = []
    files: list[dict[str, Any]] = []
    seen_file_keys: set[Any] = set()

    for env in envelopes:
        domain = env.get("domain")
        row = policy.domain(domain) if policy else None
        entities = env.get("entities") or []
        figures = env.get("figures") or []
        miss = env.get("miss") or []
        env_files = env.get("files") or []

        sections.append(Section(domain=domain, entities=entities, figures=figures, files=env_files, miss=miss))

        rows_text: list[str] = []
        n = 0
        for fig in figures:
            key = _row_key(fig)
            if key in seen_rows:
                continue
            seen_rows.add(key)
            n += 1
            rows_text.append(_render_row(n, fig))

        if entities and miss and set(entities) <= set(miss) and not figures:
            missed_domains.append(domain)

        label = row.label if row else domain
        codes = ", ".join(str(e) for e in entities)
        block = f"*{label}* for {codes}:"
        if rows_text:
            block += "\n" + "\n\n".join(rows_text)
        text_parts.append(block)

        for f in env_files:
            key = _file_key(f)
            if key in seen_file_keys:
                continue
            seen_file_keys.add(key)
            files.append(f)

    text = "\n\n".join(text_parts)

    offer = None
    question = None
    if envelopes and missed_domains and len(missed_domains) == len(envelopes):
        teams: list[str] = []
        for domain in missed_domains:
            row = policy.domain(domain) if policy else None
            team = row.escalation_team_code if row else None
            if team and team not in teams:
                teams.append(team)
        if teams:
            offer = Offer(teams=teams)
            text += "\n\nWould you like me to escalate?"
            question = _team_pick_question(missed_domains, policy)

    actions: list[dict[str, Any]] = []
    if files:
        actions = [
            {"kind": "send_file", "url": f.get("url"), "filename": f.get("filename")} for f in files
        ]
        text += "\n\n" + _ATTACHED_SENTENCE

    return Answer(
        sections=sections, question=question, offer=offer, canned=[], files=files, actions=actions, text=text
    )
