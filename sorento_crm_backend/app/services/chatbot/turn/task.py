# Task: what the conversation still OWES, as one axis on the focus
# (PLAN-chatbot-dealer-stock-verdict.md "The engine (S3)", D21 to D26).
#
# The focus holds what the conversation is ABOUT. It does not hold what is still owed,
# and neither does `pending`: a genuine new ask CLOSES a roster
# (`apply.py::new_ask_closes_stale_roster`, pinned by `handpass5-stale-roster-forms`)
# while an owed collection must PARK and come back. So a task is its own axis, with its
# own lifecycle, and the roster's one-shot rules are untouched.
#
# Two production kinds today - `stock_qty` (the dealer's per-product quantity) and
# `ideation` (a status over the `session.ideation` pointer the ideate lane already owns,
# D26). `TaskKind` is the contract a third one implements; `TASK_KINDS` is its registry
# and it has exactly two entries.
#
# Pure, like the rest of this package: no I/O, no message words, no import of `head`,
# `dialogue`, `tail` or `engine`, and no import of `turn/state.py` either (that module
# imports THIS one, for `Focus.tasks`).
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol

from app.services.chatbot.turn.plan import FetchSpec

#: The pending kind that asks WHICH open task a value belongs to (D24(b)). Not a roster:
#: it is answered once and gone, which is why `pending.PENDING_KINDS` carries it.
TASK_PICK = "task_pick"

OPEN = "open"
PARKED = "parked"


@dataclass(frozen=True)
class Slot:
    """One thing a task is still collecting. `key` is the machine identity the fetch
    sends (a product uuid); `label` is what a person calls it (the product code);
    `value` is what the contact has said, or None while it is still owed."""

    key: str
    label: str
    value: Any = None


@dataclass(frozen=True)
class Task:
    """One open collection, carried on `Focus.tasks` and persisted inside the focus
    wire (D21). At most one per kind.

    `not_checked` is what this task STOPPED asking about - the slots a "just proceed"
    dropped (D15). It rides on the task because the reply has to name them, and the
    task is the one thing that knows which ones got dropped.
    """

    kind: str
    domain: str
    status: str = OPEN
    opened_at_turn: int = 0
    touched_at_turn: int = 0
    slots: tuple[Slot, ...] = ()
    not_checked: tuple[str, ...] = ()


class TaskKind(Protocol):
    """What a kind has to answer. One implementation per kind, no per-kind arms
    anywhere else (AC-1777).

    `claims(verdict)` is the routing question of D24(a): is this turn's value MINE?
    A kind that also needs state the verdict cannot carry declares `wants_ideation`
    and takes the pointer as a keyword (`IdeationTask` is the one such kind today -
    its media menu lives on `session.ideation`, which stays where it is, with one
    writer, and is never copied onto the task).
    """

    def claims(self, verdict: dict[str, Any]) -> bool: ...

    def missing(self, task: Task) -> tuple[Slot, ...]: ...

    def fill(self, task: Task, verdict: dict[str, Any]) -> Task: ...

    def to_fetch(self, task: Task) -> FetchSpec | None: ...

    def question(self, task: Task) -> str | None: ...


def _number(value: Any) -> int | None:
    """A quantity the parser stated, as an int, or None. `bool` is not a number here:
    `True` is 1 in Python and a quantity of one is not what a boolean meant."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _entity_codes(entity: dict[str, Any]) -> set[str]:
    codes = set()
    for name in ("canonical_code", "code", "raw"):
        value = entity.get(name)
        if isinstance(value, str) and value.strip():
            codes.add(value.strip().casefold())
    uuid = entity.get("uuid")
    if isinstance(uuid, str) and uuid.strip():
        codes.add(uuid.strip().casefold())
    return codes


#: SEC-S2 (security review, round 1): how many slots one stock task may carry, and how
#: many of them a sentence enumerates before it counts the rest. An ask that names no
#: product at all used to open a task with one slot per CATALOGUE row (the tool's own
#: page cap is 5000) and then echo every code into the reply and into every later
#: parser block. A task is a question about what the dealer named, not about the book.
MAX_SLOTS = 20
MAX_NAMED = 10


def _named(labels: list[str]) -> str:
    """The labels a QUESTION prints ("for C and D"), at most `MAX_NAMED` of them, with
    the rest counted rather than listed (SEC-S2). The wording is the MCP presenter's
    own (`presenters._noted_and_missing_question`), so one question has one shape
    whether the tool asked it or the engine re-asked it."""
    if len(labels) <= MAX_NAMED:
        return _join(labels)
    shown = labels[:MAX_NAMED]
    return f"{', '.join(shown)} and {len(labels) - MAX_NAMED} others"


def _listed(labels: list[str]) -> str:
    """The same cap for a plain COMMA list - the parser hint's own shape (AC-1778,
    `Noted: A x 5, B x 60. Still needs a quantity for: C, D.`), which is a fact stated
    to the model rather than a sentence said to a person."""
    if len(labels) <= MAX_NAMED:
        return ", ".join(labels)
    shown = labels[:MAX_NAMED]
    return f"{', '.join(shown)} and {len(labels) - MAX_NAMED} others"


def _join(words: list[str]) -> str:
    if len(words) > 1:
        return ", ".join(words[:-1]) + " and " + words[-1]
    return words[0] if words else ""


class StockQtyTask:
    """The dealer's owed quantities, one slot per product (D13, D14, D16).

    The slots are OPENED from the stock tool's own reply (`needs_quantity` per product,
    D25): the backend owns the rule about who must state a quantity, and the engine
    never reads a policy to decide it.
    """

    label = "stock check"
    wants_ideation = False

    def claims(self, verdict: dict[str, Any]) -> bool:
        if verdict.get("proceed_anyway") is True:
            return True
        for entity in verdict.get("entities") or []:
            if isinstance(entity, dict) and _number(entity.get("quantity")) is not None:
                return True
        return _number(verdict.get("demand_qty")) is not None

    def missing(self, task: Task) -> tuple[Slot, ...]:
        return tuple(slot for slot in task.slots if slot.value is None)

    def fill(self, task: Task, verdict: dict[str, Any]) -> Task:
        slots = list(task.slots)
        by_code: dict[str, int] = {}
        for entity in verdict.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            quantity = _number(entity.get("quantity"))
            if quantity is None:
                continue
            for code in _entity_codes(entity):
                by_code[code] = quantity
        for i, slot in enumerate(slots):
            for code in (slot.key, slot.label):
                if not isinstance(code, str):
                    continue
                named = by_code.get(code.strip().casefold())
                if named is not None:
                    # D16: a restated quantity REPLACES the earlier one, and nothing is
                    # asked twice for a product already noted.
                    slots[i] = replace(slot, value=named)
                    break
        if verdict.get("proceed_anyway") is True:
            # D15: answer what is noted and drop every product still missing a
            # quantity, naming them in the reply. R-S3 (reviewer, round 1): when
            # NOTHING is noted, that leaves a task with no slots at all - there is
            # nothing to fetch and nothing to answer, so the task is finished and the
            # reply is the one line that says which products went unchecked. Left as an
            # empty task it sat on the focus forever and printed a hint line about a
            # question the dealer had already closed.
            dropped = tuple(slot.label for slot in slots if slot.value is None)
            return replace(
                task,
                slots=tuple(slot for slot in slots if slot.value is not None),
                not_checked=dropped,
            )
        still_missing = [slot for slot in slots if slot.value is None]
        if len(still_missing) == 1 and not by_code:
            # D13's deterministic fallback, for a prompt version that does not fill
            # `entities[].quantity` yet: a bare number with exactly ONE slot still
            # owed belongs to that slot. Two owed slots and it belongs to neither.
            bare = _number(verdict.get("demand_qty"))
            if bare is not None:
                index = slots.index(still_missing[0])
                slots[index] = replace(still_missing[0], value=bare)
        return replace(task, slots=tuple(slots))

    def fill_value(self, task: Task, value: Any) -> Task:
        """The value a `task_pick` tie attributed to this task (D24(b)), applied to
        the one slot still owed."""
        quantity = _number(value)
        missing = self.missing(task)
        if quantity is None or len(missing) != 1:
            return task
        slots = list(task.slots)
        slots[slots.index(missing[0])] = replace(missing[0], value=quantity)
        return replace(task, slots=tuple(slots))

    def to_fetch(self, task: Task) -> FetchSpec | None:
        if not task.slots:
            # R-S3: "just proceed" with nothing noted leaves no product to ask about.
            # There is nothing to fetch, and `question()` below says the one thing
            # left to say.
            return None
        entities = [
            {
                "raw": slot.label,
                "hint": "product",
                "canonical_code": slot.label,
                "uuid": slot.key,
                "current_message": True,
                "confident": True,
            }
            for slot in task.slots
        ]
        # SEC-N4 (security review, round 1): a slot value read back from a session row
        # written by an older build (or by hand) may be a string, a float or anything
        # else JSON can carry, and `requested_quantities` is validated at the route -
        # a bad value there is a 400 that kills the WHOLE fetch, not just that product.
        # Coerced here, once, and a value that cannot be a quantity is simply not sent
        # (the backend then answers `needs_quantity` for it, which is the truth).
        quantities = {}
        for slot in task.slots:
            quantity = _number(slot.value)
            if quantity is not None:
                quantities[slot.key] = quantity
        filters: dict[str, Any] = {"task": task.kind}
        if quantities:
            filters["requested_quantities"] = quantities
        if task.not_checked:
            filters["not_checked"] = list(task.not_checked)
        return FetchSpec(
            domain=task.domain, entities=entities, filters=filters, date_window=None
        )

    def question(self, task: Task) -> str | None:
        """The same sentence the MCP presenter says when the tool reply itself carries
        a gap (`presenters._noted_and_missing_question`) - said HERE only on the turn
        that resumes the task without fetching anything, so the dealer reads one
        wording for one question."""
        if not task.slots and task.not_checked:
            # R-S3: the dealer said to proceed and had noted nothing, so the whole ask
            # went unchecked. One line, and the task is over - never an empty task that
            # keeps printing a hint about a question nobody is answering.
            return f"Not checked: {_named(list(task.not_checked))}."
        missing = [slot.label for slot in self.missing(task)]
        if not missing:
            return None
        question = f"How many units do you need for {_named(missing)}?"
        noted = [
            f"{slot.label} x {slot.value}" for slot in task.slots if slot.value is not None
        ]
        if not noted:
            return question
        return f"Noted: {_listed(noted)}. {question}"

    def hint(self, task: Task) -> str:
        """The line the parser reads (AC-1778)."""
        parts = [f"Open task: {self.label}."]
        noted = [
            f"{slot.label} x {slot.value}" for slot in task.slots if slot.value is not None
        ]
        if noted:
            parts.append(f"Noted: {_listed(noted)}.")
        missing = [slot.label for slot in self.missing(task)]
        if missing:
            parts.append(f"Still needs a quantity for: {_listed(missing)}.")
        return " ".join(parts)


class IdeationTask:
    """The ideate lane, as a task (D26).

    Measured before it was wrapped: the lane is a passthrough to `crm_ideation_turn`,
    its state is the opaque `session.ideation` pointer the tail re-persists every turn,
    and it runs whenever the parser routes `ideate`. So the state already survives a
    detour and already resumes on routing. What was missing is the open / parked
    status, the parser hint that an idea is in progress, and the D24 tie - and that is
    all this kind adds. It owns no slots (the tool owns them) and keeps no copy of the
    pointer.
    """

    label = "idea"
    wants_ideation = True

    def claims(self, verdict: dict[str, Any], ideation: dict[str, Any] | None = None) -> bool:
        if verdict.get("domain_hint") == "ideate":
            return True
        if verdict.get("entities"):
            return False
        # The media menu is answered by POSITIONS, so a bare number while one is open
        # may be this task's (D26). The pointer is the only place that fact lives; when
        # the caller did not hand one over, an open ideation task is taken at its word.
        if isinstance(ideation, dict) and not ideation.get("pending_media"):
            return False
        positions = verdict.get("reference_positions")
        return bool(positions) or _number(verdict.get("demand_qty")) is not None

    def closes_on_tool_status(self, status: Any) -> bool:
        """AC-1786: the idea is finished when the TOOL says so, and on no other word."""
        return status == "complete"

    def missing(self, task: Task) -> tuple[Slot, ...]:
        return ()

    def fill(self, task: Task, verdict: dict[str, Any]) -> Task:
        # The lane ran; the tool owns the slots. Nothing of this task's own changes.
        return task

    def to_fetch(self, task: Task) -> FetchSpec | None:
        # The ideate lane is ROUTED, never fetched through a `FetchSpec` (route.py
        # reads `ideate` off the plan's domains), so there is no spec to build.
        return None

    def question(self, task: Task) -> str | None:
        # The tool speaks for this one (D26).
        return None

    def hint(self, task: Task) -> str:
        return f"Open task: {self.label} in progress."


#: The registry. Two entries, and a third kind pays for nothing but its own class.
TASK_KINDS: dict[str, Any] = {"stock_qty": StockQtyTask(), "ideation": IdeationTask()}


def kind_of(task: Any) -> Any:
    return TASK_KINDS.get(_value(task, "kind"))


def _value(task: Any, name: str, default: Any = None) -> Any:
    """One read for a task row that may be a `Task` or the dict it is stored as."""
    if isinstance(task, dict):
        return task.get(name, default)
    return getattr(task, name, default)


def claims(kind_impl: Any, verdict: dict[str, Any], ideation: dict[str, Any] | None) -> bool:
    """`claims(verdict)` is the protocol every kind implements (AC-1777). A kind that
    declares `wants_ideation` is handed the session's own opaque pointer as well, so
    `apply()` itself stays pure and keeps no copy of it."""
    if getattr(kind_impl, "wants_ideation", False):
        return bool(kind_impl.claims(verdict, ideation=ideation))
    return bool(kind_impl.claims(verdict))


# --------------------------------------------------------------------------- #
# The wire shape - carried INSIDE the focus (D21: no new session key)
# --------------------------------------------------------------------------- #


def task_to_wire(task: Task) -> dict[str, Any]:
    return {
        "kind": task.kind,
        "domain": task.domain,
        "status": task.status,
        "opened_at_turn": task.opened_at_turn,
        "touched_at_turn": task.touched_at_turn,
        "slots": [
            {"key": slot.key, "label": slot.label, "value": slot.value}
            for slot in task.slots
        ],
        "not_checked": list(task.not_checked),
    }


def task_from_wire(raw: Any) -> Task | None:
    """Tolerant, like every other read on this path: a task that cannot be read is a
    forgotten collection, not a failed turn."""
    if not isinstance(raw, dict) or not raw.get("kind"):
        return None
    slots = []
    for row in raw.get("slots") or []:
        if not isinstance(row, dict) or row.get("key") is None:
            continue
        slots.append(
            Slot(
                key=str(row.get("key")),
                label=str(row.get("label") or row.get("key")),
                value=row.get("value"),
            )
        )
    status = raw.get("status")
    return Task(
        kind=str(raw["kind"]),
        domain=str(raw.get("domain") or ""),
        status=status if status in (OPEN, PARKED) else OPEN,
        opened_at_turn=raw.get("opened_at_turn") or 0,
        touched_at_turn=raw.get("touched_at_turn") or 0,
        slots=tuple(slots),
        not_checked=tuple(
            str(name) for name in (raw.get("not_checked") or []) if name is not None
        ),
    )


# --------------------------------------------------------------------------- #
# The lifecycle, as one pure step `apply()` runs before decide's four outcomes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TaskOutcome:
    tasks: tuple[Task, ...] = ()
    fetch: FetchSpec | None = None
    fetch_domain: str | None = None
    question: str | None = None
    question_domain: str | None = None
    tie_options: tuple[dict[str, Any], ...] = ()
    tie_value: Any = None
    clears_pending: bool = False
    parked_kinds: tuple[str, ...] = ()
    closed_kinds: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()


def _tie_options(tasks: tuple[Task, ...]) -> tuple[dict[str, Any], ...]:
    options = []
    for position, task in enumerate(tasks, start=1):
        impl = TASK_KINDS.get(task.kind)
        options.append(
            {
                "position": position,
                "label": getattr(impl, "label", task.kind),
                "entity_type": "task",
                "payload": {"task_kind": task.kind},
            }
        )
    return tuple(options)


def _answered_tie(pending: Any, positions: list[int]) -> str | None:
    for option in getattr(pending, "options", None) or []:
        if option.get("position") in positions:
            payload = option.get("payload") or {}
            named = payload.get("task_kind")
            if named:
                return str(named)
    return None


def run(
    tasks: tuple[Task, ...],
    verdict: dict[str, Any],
    *,
    decision_kind: str,
    positions: list[int] | None = None,
    pending: Any = None,
    turn_no: int = 0,
    ideation: dict[str, Any] | None = None,
) -> TaskOutcome:
    """Every task rule, in the order the plan names: claims -> fill, complete -> fetch,
    park, resume, close, tie. One function, so the arms cannot disagree about one turn.

    `decision_kind` is `decide()`'s own reading of this message; `positions` are the
    option numbers it picked. Nothing here reads a word.
    """
    rules: list[str] = []
    tasks = tuple(tasks)

    # (1) A tie the dealer has just settled (D24(b)). Before every other rule: the
    # pick names the task, so nothing else has to guess.
    if (
        pending is not None
        and getattr(pending, "kind", None) == TASK_PICK
        and positions
    ):
        named = _answered_tie(pending, list(positions))
        carried = (getattr(pending, "payload", None) or {}).get("value")
        out: list[Task] = []
        fetch: FetchSpec | None = None
        domain: str | None = None
        question: str | None = None
        question_domain: str | None = None
        for task in tasks:
            if task.kind != named:
                out.append(task)
                continue
            impl = TASK_KINDS.get(task.kind)
            filled = task
            if impl is not None and hasattr(impl, "fill_value"):
                filled = impl.fill_value(task, carried)
            moved = filled.slots != task.slots
            filled = replace(filled, status=OPEN, touched_at_turn=turn_no)
            # R-S5 (reviewer, round 1): `fill_value` applies the carried value only to
            # a task with exactly ONE slot still owed. When it applied nothing - two
            # slots still missing, or a value that is not a number - fetching anyway
            # answered a question the dealer had not finished, with the SAME gap it had
            # before the pick. Nothing moved means nothing to fetch: the task is
            # re-asked instead, naming only what is still owed.
            spec = impl.to_fetch(filled) if (impl is not None and moved) else None
            if spec is not None:
                fetch = spec
                domain = filled.domain
            elif impl is not None and not moved and question is None:
                question = impl.question(filled)
                question_domain = filled.domain
            out.append(filled)
        rules.append("task_pick_answered")
        return TaskOutcome(
            tasks=tuple(out),
            fetch=fetch,
            fetch_domain=domain,
            question=question,
            question_domain=question_domain,
            clears_pending=True,
            rules=tuple(rules),
        )

    if not tasks:
        return TaskOutcome(tasks=(), rules=())

    named_domain = verdict.get("domain_hint")

    # (2) Close or park on a topic reset (D23). A reset aimed at a task's OWN domain
    # ends it; one aimed elsewhere parks it, and the focus keeps the task through the
    # wipe (`apply._focus_rules` empties every other axis).
    if verdict.get("topic_reset") is True:
        kept: list[Task] = []
        closed: list[str] = []
        for task in tasks:
            aimed_here = not named_domain or task.domain == named_domain
            if aimed_here:
                closed.append(task.kind)
                rules.append(f"task_closed_on_reset_{task.kind}")
                continue
            kept.append(replace(task, status=PARKED))
            rules.append(f"task_parked_{task.kind}")
        return TaskOutcome(
            tasks=tuple(kept), closed_kinds=tuple(closed), rules=tuple(rules)
        )

    claimed = [
        task
        for task in tasks
        if TASK_KINDS.get(task.kind) is not None
        and claims(TASK_KINDS[task.kind], verdict, ideation)
    ]

    # (3) The tie (D24(b)): two kinds could claim the same value and the parser named
    # neither. Nothing changes; the dealer is asked which task it is for.
    if len(claimed) > 1:
        rules.append("task_pick_tie")
        return TaskOutcome(
            tasks=tasks,
            tie_options=_tie_options(tuple(claimed)),
            tie_value=verdict.get("demand_qty"),
            rules=tuple(rules),
        )

    out = []
    parked_kinds: list[str] = []
    fetch = None
    fetch_domain = None
    question = None
    question_domain = None
    for task in tasks:
        impl = TASK_KINDS.get(task.kind)
        if impl is None:
            out.append(task)
            continue
        if claimed and task is claimed[0]:
            # (4) fill: the value goes to the kind that claims it, whatever the
            # current subject (D21). A fill that moved a slot re-runs the domain's own
            # fetch over the WHOLE task, which is what lets the backend answer or
            # re-ask per product (D14, D25); a fill that moved nothing re-asks what is
            # still owed, unless this turn asked a question of its own - a fresh stock
            # ask carries its own products and its own reply rebuilds the task (D23).
            filled = replace(
                impl.fill(task, verdict), status=OPEN, touched_at_turn=turn_no
            )
            moved = filled.slots != task.slots
            spec = impl.to_fetch(filled) if moved else None
            if spec is None and moved and not filled.slots:
                # R-S3: the fill emptied the task (a "just proceed" with nothing
                # noted). It is finished - it does not ride on as an empty task - and
                # its own last sentence names what went unchecked.
                rules.append(f"task_closed_on_proceed_{task.kind}")
                if question is None:
                    question = impl.question(filled)
                    question_domain = filled.domain
                continue
            out.append(filled)
            rules.append(f"task_filled_{task.kind}")
            if spec is not None:
                fetch = spec
                fetch_domain = filled.domain
            elif not moved and decision_kind != "new_ask" and question is None:
                question = impl.question(filled)
                question_domain = filled.domain
            continue
        if task.domain and task.domain == named_domain and not verdict.get("entities"):
            # (5) resume (D22): the task's own topic, named again with nothing new.
            # Only what is still missing is asked; nothing is asked twice.
            resumed = replace(task, status=OPEN, touched_at_turn=turn_no)
            out.append(resumed)
            rules.append(f"task_resumed_{task.kind}")
            if question is None:
                question = impl.question(resumed)
                question_domain = resumed.domain
            continue
        if decision_kind == "new_ask" and not claimed:
            # (6) park (D22): the dealer asked something ELSE. Silent - the reply says
            # nothing about the parked task. A turn that answered one of the open tasks
            # is not "something else" for the others, however much it looks like a new
            # ask to `decide()` (a quantity beside a product code names an entity, so
            # the table reads it NEW_ASK): it is the conversation continuing, and
            # parking the second task there would have parked an idea in progress
            # every time a dealer typed a quantity.
            out.append(replace(task, status=PARKED))
            parked_kinds.append(task.kind)
            rules.append(f"task_parked_{task.kind}")
            continue
        out.append(task)

    return TaskOutcome(
        tasks=tuple(out),
        fetch=fetch,
        fetch_domain=fetch_domain,
        question=question,
        question_domain=question_domain if question else None,
        parked_kinds=tuple(parked_kinds),
        rules=tuple(rules),
    )


def unpark(
    tasks: tuple[Task, ...], kinds: tuple[str, ...], before: tuple[Task, ...]
) -> tuple[Task, ...]:
    """Put back the status of a task this turn parked, when the turn turned out to ASK
    a question of its own rather than answer anything (AC-1773).

    Parking is what keeps a task silent while the OTHER question is answered (D22). A
    turn that ends in a roster has answered nothing and taken the conversation nowhere,
    so there is nothing yet to be silent about - and a task parked by it would then
    need the dealer to name it again, for a detour that never happened.
    """
    if not kinds:
        return tasks
    was = {task.kind: task.status for task in before}
    return tuple(
        replace(task, status=was.get(task.kind, task.status))
        if task.kind in kinds
        else task
        for task in tasks
    )


def opened_for_domains(
    tasks: tuple[Task, ...],
    domains: list[str],
    *,
    turn_no: int = 0,
    closed_kinds: tuple[str, ...] = (),
) -> tuple[Task, ...]:
    """The IDEATION task, opened by the turn that routes to the ideate lane (D26).

    The lane itself is a passthrough whose state already survives a detour; what the
    task adds is the open / parked status and the parser hint, so it opens exactly when
    the lane runs and nothing new has to decide when an idea is "in progress".
    """
    if "ideate" not in (domains or []):
        return tasks
    if any(task.kind == "ideation" for task in tasks):
        return tasks
    if "ideation" in closed_kinds:
        # "never mind the idea" ENDS it (D23), and a reset names the very domain the
        # lane routes on - so opening it again here would be the reset re-opening what
        # it just closed.
        return tasks
    return tasks + (
        Task(
            kind="ideation",
            domain="ideate",
            status=OPEN,
            opened_at_turn=turn_no,
            touched_at_turn=turn_no,
        ),
    )


# --------------------------------------------------------------------------- #
# What the TOOL's reply says about the task (D25: the backend owns the rule)
# --------------------------------------------------------------------------- #


def tasks_after_reply(
    tasks: tuple[Task, ...],
    envelopes: list[dict[str, Any]],
    *,
    turn_no: int = 0,
    named_products: bool = True,
) -> tuple[Task, ...]:
    """The stock task, rebuilt from the stock tool's own `stock_availability` block.

    ONE rule for open, update and close, and it is the backend's rule, not the
    engine's (D25): every entry becomes a slot, its `requested_qty` becomes the slot's
    value, and a reply where no entry still needs a quantity has no task left to carry.
    The engine never reads a policy to decide who must state a quantity - it reads what
    the reply said about it.

    `named_products` is SEC-S2 (security review, round 1): did the ask name a product at
    all? "What stock do you have?" names none, so the reply is a PAGE OF THE CATALOGUE
    and every row of it carries `needs_quantity` - which opened a task with one slot per
    product and then echoed every code into the reply and into every later parser block.
    A task is a question about what the dealer named; with nothing named there is no
    task to open, and the reply stays the presenter's own single question. An ALREADY
    OPEN task is still updated (it named its products when it opened).
    """
    block: list[dict[str, Any]] | None = None
    for envelope in envelopes or []:
        rows = envelope.get("stock_availability") if isinstance(envelope, dict) else None
        if isinstance(rows, list) and rows:
            block = [row for row in rows if isinstance(row, dict)]
    if block is None:
        return tasks

    others = tuple(task for task in tasks if task.kind != "stock_qty")
    if not any(row.get("needs_quantity") is True for row in block):
        return others

    existing = next((task for task in tasks if task.kind == "stock_qty"), None)
    if existing is None and not named_products:
        # SEC-S2: nothing was named, so there is nothing to collect FOR.
        return others
    slots: list[Slot] = []
    for row in block:
        key = row.get("product_id")
        # R-S4 / SEC-N3: a row with no `product_code` must never put the UUID in front
        # of a person - not in the reply, not in the hint line the parser reads next
        # turn (the frontend's own "no UUIDs in the UI" rule, here at the seam the text
        # is built from). The product NAME is the fallback; a row with neither is
        # dropped, because there is no way to ask about it.
        label = row.get("product_code") or row.get("product_name")
        if not key or not label:
            continue
        slots.append(
            Slot(key=str(key), label=str(label), value=_number(row.get("requested_qty")))
        )
    # SEC-S2: a cap, not a truncation of the question the dealer asked - a reply that
    # needs more than this many products has stopped being a stock check and is a
    # catalogue dump. The remaining products are simply not COLLECTED for; the reply
    # itself is the presenter's and is unchanged.
    slots = slots[:MAX_SLOTS]
    if not slots:
        return others
    opened = existing.opened_at_turn if existing is not None else turn_no
    return others + (
        Task(
            kind="stock_qty",
            domain="inventory",
            status=OPEN,
            opened_at_turn=opened,
            touched_at_turn=turn_no,
            slots=tuple(slots),
        ),
    )


def tasks_after_tool_status(
    tasks: tuple[Task, ...], *, kind: str, status: Any
) -> tuple[Task, ...]:
    """AC-1786: the one seam a kind's own `closes_on_tool_status` is read at."""
    impl = TASK_KINDS.get(kind)
    if impl is None or not hasattr(impl, "closes_on_tool_status"):
        return tasks
    if not impl.closes_on_tool_status(status):
        return tasks
    return tuple(task for task in tasks if task.kind != kind)


def hint_lines(tasks: Any, *, ideation: dict[str, Any] | None = None) -> list[str]:
    """One `Open task: ...` line per task, most recently touched first (D24(e), AC-1778).

    Reads a task ROW, which may be a `Task` or the dict it is stored as - the parser
    block is built from whichever the caller holds.
    """
    rows = list(tasks or [])
    rows.sort(key=lambda row: _value(row, "touched_at_turn", 0) or 0, reverse=True)
    lines: list[str] = []
    for row in rows:
        impl = TASK_KINDS.get(_value(row, "kind"))
        if impl is None or not hasattr(impl, "hint"):
            continue
        as_task = row if isinstance(row, Task) else task_from_wire(row)
        if as_task is None:
            continue
        line = impl.hint(as_task)
        media = _value(row, "pending_media") is True or (
            _value(row, "kind") == "ideation"
            and isinstance(ideation, dict)
            and bool(ideation.get("pending_media"))
        )
        if media:
            line = f"{line} (media menu open)"
        lines.append(line)
    return lines
