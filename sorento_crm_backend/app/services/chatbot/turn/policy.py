# Policy: the frozen view over chatbot_domains + chatbot_entity_kinds a turn is handed
# (PLAN-chatbot-turn-rearch.md "The policy"). Built from ROWS, never from a constant -
# tests seed rows via `Policy.from_rows`, matching the real loader's own shape.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DomainPolicy:
    name: str
    label: str
    intents: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    primary_tool: str | None = None
    escalation_team_code: str | None = None
    switch_words: tuple[str, ...] = ()
    takes_date_filter: bool = False
    reveal_key: str | None = None
    supported: bool = True
    narrowing: dict[str, str] = field(default_factory=dict)
    ladder: tuple[str, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class EntityKindPolicy:
    kind: str
    resolver_source: str = ""
    did_you_mean: bool = True
    default_narrowing: str = "optional_filter"
    family_grouping: str | None = None
    base_property_words: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Policy:
    domains: tuple[DomainPolicy, ...]
    kinds: tuple[EntityKindPolicy, ...]
    tier_order: tuple[str, ...] = ()

    def domain(self, name: str) -> DomainPolicy | None:
        for row in self.domains:
            if row.name == name:
                return row
        return None

    def kind(self, kind: str) -> EntityKindPolicy | None:
        for row in self.kinds:
            if row.kind == kind:
                return row
        return None

    @classmethod
    def from_rows(
        cls,
        *,
        domains: list[dict[str, Any]],
        kinds: list[dict[str, Any]],
        tier_order: list[str] | None = None,
    ) -> "Policy":
        domain_rows = tuple(
            DomainPolicy(
                name=row["name"],
                label=row.get("label", row["name"]),
                intents=tuple(row.get("intents") or ()),
                tools=tuple(row.get("tools") or ()),
                primary_tool=row.get("primary_tool"),
                escalation_team_code=row.get("escalation_team_code"),
                switch_words=tuple(row.get("switch_words") or ()),
                takes_date_filter=bool(row.get("takes_date_filter", False)),
                reveal_key=row.get("reveal_key"),
                supported=bool(row.get("supported", True)),
                narrowing=dict(row.get("narrowing") or {}),
                ladder=tuple(row.get("ladder") or ()),
                sort_order=int(row.get("sort_order", 0)),
            )
            for row in domains
        )
        kind_rows = tuple(
            EntityKindPolicy(
                kind=row["kind"],
                resolver_source=row.get("resolver_source", ""),
                did_you_mean=bool(row.get("did_you_mean", True)),
                default_narrowing=row.get("default_narrowing", "optional_filter"),
                family_grouping=row.get("family_grouping"),
                base_property_words=dict(row.get("base_property_words") or {}),
            )
            for row in kinds
        )
        return cls(domains=domain_rows, kinds=kind_rows, tier_order=tuple(tier_order or ()))
