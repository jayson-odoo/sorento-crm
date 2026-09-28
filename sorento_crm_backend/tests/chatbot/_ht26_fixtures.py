"""Shared fixtures for the owner hand test of 26 Sep 2026 on PR #1247 (stock ask v2 S3).

Not itself a test file (no `test_` prefix - pytest never collects it).

The focus states are the ones quoted in the scout's PR comment "Owner hand test 26 Sep -
conversation findings (scout)": the SRTWC286 family the resolver placed on T1 (the
product SRTWC286-SH and nine SRTWC286-SH-* siblings), SRTGV332-DIY (T7, T8), ELP3754 and
SRTKT1631SS (T12 to T14) and the ELP3753 miss (T15, T16). Every uuid is synthetic.
"""
from __future__ import annotations

from typing import Any

#: T1: "check stock srtwc286" placed these ten, SRTWC286-SH first.
SRTWC286_FAMILY: list[str] = [
    "SRTWC286-SH",
    "SRTWC286-SH-UF",
    "SRTWC286-SH-150",
    "SRTWC286-SH-BK",
    "SRTWC286-SH-CR",
    "SRTWC286-SH-GD",
    "SRTWC286-SH-GM",
    "SRTWC286-SH-RG",
    "SRTWC286-SH-SS",
    "SRTWC286-SH-WH",
]


def uuid_of(code: str) -> str:
    return f"u-{code.lower()}"


def row(code: str, *, needs_quantity: bool = True, requested_qty: Any = None, branch=None):
    """One `stock_availability` entry, the shape `inventory_service` returns."""
    out: dict[str, Any] = {
        "product_id": uuid_of(code),
        "product_code": code,
        "product_name": f"{code} name",
        "needs_quantity": needs_quantity,
        "requested_qty": requested_qty,
    }
    if branch:
        out["branch"] = branch
    return out


def envelopes(*rows: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"stock_availability": list(rows)}]


def asked(raw: str, quantity: Any = None, **extra: Any) -> dict[str, Any]:
    """A product entity the parser read off THIS message."""
    return {
        "raw": raw,
        "hint": "product",
        "canonical_code": raw.upper(),
        "current_message": True,
        "confident": True,
        "quantity": quantity,
        **extra,
    }


def state(focus=None, *, pending=None, turn_no: int = 5, availability_only: bool = False):
    from app.services.chatbot.turn.state import Focus, Profile, State

    profile = Profile()
    if availability_only:
        profile = Profile(stock_availability_only=True)
    return State(
        focus=focus if focus is not None else Focus(),
        pending=pending,
        profile=profile,
        turn_no=turn_no,
    )


def stock_task(slots, *, status: str = "open", opened_at_turn: int = 1, touched_at_turn: int = 1):
    """`slots` is a list of (code, value)."""
    from app.services.chatbot.turn.task import Slot, Task

    return Task(
        kind="stock_qty",
        domain="inventory",
        status=status,
        opened_at_turn=opened_at_turn,
        touched_at_turn=touched_at_turn,
        slots=tuple(Slot(key=uuid_of(code), label=code, value=value) for code, value in slots),
    )


def product_rows(*codes: str) -> list[dict[str, Any]]:
    """`focus.products` rows as a resolver-placed entity reaches the focus."""
    return [
        {
            "raw": code,
            "hint": "product",
            "canonical_code": code,
            "uuid": uuid_of(code),
            "current_message": False,
            "confident": True,
        }
        for code in codes
    ]


def family_pick(quantity: Any = None, codes: list[str] | None = None, *, typed: str = "SRTWC286"):
    """The pick `turn/task.py::after_reply` mints for T1 / T3."""
    from app.services.chatbot.turn import pending as turn_pending

    codes = codes or SRTWC286_FAMILY
    return turn_pending.ask(
        "product_pick",
        [
            {
                "position": i + 1,
                "label": code,
                "code": code,
                "uuid": uuid_of(code),
                "entity_type": "product",
            }
            for i, code in enumerate(codes)
        ],
        asked_at_turn=4,
        payload={
            "domain": "inventory",
            "domains": ["inventory"],
            "stock_pick": True,
            "typed": typed,
            "count": len(codes),
            "stock_qty": quantity,
        },
    )


def inventory_specs(plan) -> list[Any]:
    return [spec for spec in plan.fetch if spec.domain == "inventory"]
