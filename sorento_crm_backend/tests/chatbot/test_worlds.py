"""World replay (AC-009, cutover gate 2): every captured turn, end to end.

Node replay proves each ported function against the bytes n8n recorded. A world proves
the WIRING: one envelope in, `run_turn` then `complete_turn`, and the reply, the quick
replies and the persisted variables must equal what that execution actually produced.
Everything the CRM cannot reproduce offline is stubbed from the capture itself
(`tests/chatbot/worlds.py` says which and why); the session read and write, the turn row,
the copy resolution, the outcome hub, the state compiler and the compose all run for real
against a blank Postgres schema.

**Multi-turn worlds are the only test that can catch a wrong CARRY.** Turn 2 reads the
session turn 1 wrote, not the session n8n wrote, so a lifecycle rule the port gets wrong
changes the reply two turns later - which is exactly the class of defect the operator
journey (D4, "so a wrong follow-up answer can be traced to the memory, not guessed") was
written about.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot import worlds as worlds_mod

WORLDS = worlds_mod.derive_worlds()
CHAINS = worlds_mod.multi_turn_worlds(WORLDS)

# The gate-0 floor the plan names for worlds: 100+ overall, 5 per branch kind and per
# shape. Asserted rather than reported, so a corpus that shrinks is a failure and not a
# quieter table.
WORLD_FLOOR = 100

# See `_graded_variables`.
_PORT_ONLY_KEYS = frozenset({"pending", "focus", "open_question"})


@pytest.fixture()
def world_db(session_factory):
    """A blank schema plus the one row a world reads: the contact and its session."""

    def _seed(world: worlds_mod.World) -> None:
        db = session_factory()
        params = worlds_mod.seed_sql_params(world)
        # Delete then insert, not upsert: `respond_contacts.respond_io_id` carries no
        # unique constraint, so there is nothing for ON CONFLICT to match.
        db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": params["cid"]})
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
            ),
            params,
        )
        db.commit()

    return _seed


@pytest.fixture()
def stub_world(monkeypatch):
    """Replace the three off-box calls with what that execution actually saw."""

    def _install(world: worlds_mod.World) -> None:
        def fake_resolve_config(db, *, current_date, override_version_id=None):
            return parser_mod.ParserConfig(
                system_prompt="stub",
                prompt_version=1,
                provider="openai",
                model="gpt-test",
                api_key="sk-test",
            )

        monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: world.parser_raw)
        monkeypatch.setattr(engine_mod, "check_access", lambda db, **kw: world.access)
        monkeypatch.setattr(engine_mod, "default_space_id", lambda db: None)

        from app.services.chatbot.tail import member_offer as member_mod

        monkeypatch.setattr(
            member_mod, "fetch_rosters", lambda db, plan, ctx: list(world.roster_responses)
        )

    return _install


def _run(world: worlds_mod.World, session_factory) -> Any:
    result = engine_mod.run_turn(Envelope(**world.envelope), session_factory=session_factory)
    assert result.status != "failed", f"{world.world_id} failed at {result.stage}: {result.error}"
    return engine_mod.complete_turn(result.turn_id, world.fragments, session_factory=session_factory), result


def _graded_variables(world: worlds_mod.World, actual: dict) -> tuple[dict, dict]:
    """Both sides, with the two allowed differences removed from each.

    `pending` is the R3 marker the JS had no equivalent of (the same field-scoped
    divergence the node replay registers), `focus` is growth r1 slice B3's dialogue state
    and `open_question` is slice B4's (both registered the same way, for the same reason:
    no capture predates the code that writes them), and `dym_offer.id` is `$execution.id`
    becoming the CRM turn id. Nothing
    else is excused: a world that differs anywhere else is either a defect or a NAMED body
    difference, and a body difference SKIPS the world rather than quietly ignoring the key.

    `entities`, `domain_hint`, `date_filter_*`, `requested_attributes`, `access_levels`
    and `query_brands` are deliberately NOT in the list. They are what the six focus rules
    decide, so grading them is the proof that slice B3 moved those decisions without
    changing any of them.
    """
    expected = worlds_mod.drop_paths(
        {k: v for k, v in world.expected_variables.items() if k not in _PORT_ONLY_KEYS}
    )
    got = worlds_mod.drop_paths({k: v for k, v in actual.items() if k not in _PORT_ONLY_KEYS})
    return expected, got


def _grade_or_skip(world: worlds_mod.World, head, session_patch: dict) -> None:
    """Skip with a NAMED reason when the capture came from a different node body."""
    parse_output = ((head.ctx or {}).get("parse") or {}).get("output") or {}
    reason = worlds_mod.body_difference(
        world,
        parse_output=parse_output,
        actual_variables=(session_patch or {}).get("variables") or {},
        captured_parse_output=world.captured_parse_output,
    )
    if reason:
        pytest.skip(f"{world.world_id}: {reason}")


def _assert_world(world: worlds_mod.World, done, session_patch: dict) -> None:
    reply = done.reply or {}
    assert reply.get("text") == world.expected_text, f"{world.world_id}: reply text"
    assert reply.get("quick_replies") == world.expected_quick_replies, (
        f"{world.world_id}: quick replies"
    )
    expected, got = _graded_variables(world, (session_patch or {}).get("variables") or {})
    assert got == expected, f"{world.world_id}: persisted variables"
    # S2 still delegates every lane, so the CRM returns no actions of its own except the
    # human-intervened clear the head raises (AC-108).
    for action in done.actions:
        assert action["kind"] == "update_contact_fields", (
            f"{world.world_id}: unexpected action {action['kind']} - S2's caller only sends"
        )
        assert action["dry_run"] is True, "a world is a test envelope; every action is dry"


class TestTheWorldCorpus:
    """The corpus itself is the gate-0 evidence, so its size is asserted, not reported."""

    def test_the_corpus_meets_the_hundred_world_floor(self) -> None:
        """The floor is on the FULL corpus, so it is graded where the full corpus is.

        The vendored subset is a few hundred kilobytes of curated fixtures - it derives a
        dozen worlds and is not meant to derive a hundred. Asserting the floor against it
        would fail in CI for a reason that has nothing to do with the corpus the gate is
        about, so the test skips there and says which corpus it needed.
        """
        from tests.chatbot import _corpus

        if _corpus.corpus_root() is None:
            pytest.skip(
                f"the world floor describes the FULL corpus ({len(WORLDS)} worlds derived "
                f"from the vendored subset alone); {_skip_reason()}"
            )
        assert len(WORLDS) >= WORLD_FLOOR, (
            f"{len(WORLDS)} worlds, floor is {WORLD_FLOOR} (plan, cutover gate 0). "
            "Derive more by capturing fresh spine executions; never by lowering this."
        )

    def test_every_world_names_the_contact_and_the_reply_it_must_produce(self) -> None:
        for world in WORLDS:
            assert world.contact_id
            assert world.shape in worlds_mod.SHAPES
            assert isinstance(world.expected_variables, dict)

    def test_multi_turn_chains_exist_for_the_memory_paths(self) -> None:
        if not WORLDS:
            pytest.skip("no worlds in this checkout")
        assert CHAINS, "no contact has 3 consecutive captured turns - the carry paths are ungraded"
        assert all(3 <= len(chain.turns) <= 5 for chain in CHAINS)


def _skip_reason() -> str:
    from tests.chatbot import _corpus

    return _corpus.corpus_skip_reason()


@pytest.mark.parametrize("world", WORLDS or [None], ids=lambda w: w.world_id if w else "no-worlds")
def test_world_replay(world, world_db, stub_world, session_factory) -> None:
    """One captured turn, end to end. `reply.text`, quick replies and the session patch."""
    if world is None:
        pytest.skip(_skip_reason())
    world_db(world)
    stub_world(world)
    done, head = _run(world, session_factory)
    _grade_or_skip(world, head, done.session_patch)
    if world.branch_kind:
        assert head.branch_kind == world.branch_kind, f"{world.world_id}: lane"
    _assert_world(world, done, done.session_patch)


@pytest.mark.parametrize(
    "chain",
    CHAINS or [None],
    ids=lambda c: f"{c.contact_id}-{len(c.turns)}turns" if c else "no-chains",
)
def test_multi_turn_world_replay(chain, world_db, stub_world, session_factory, monkeypatch) -> None:
    """3 to 5 turns of one contact, each reading the session the PREVIOUS turn wrote.

    Only the FIRST turn is seeded from its capture. After that the CRM's own memory is
    what the next turn reads, which is the property no single-turn world can check: a
    carry lifecycle the port got wrong shows up as a different reply two turns later.

    The turns run as LIVE envelopes (not dry) precisely so the session is written; the
    blank schema and the transaction rollback are what keep that contained.
    """
    if chain is None:
        pytest.skip(_skip_reason())
    world_db(chain.turns[0])
    graded = 0
    for index, world in enumerate(chain.turns):
        stub_world(world)
        live = dict(world.envelope)
        live["is_test"] = False
        result = engine_mod.run_turn(Envelope(**live), session_factory=session_factory)
        assert result.status != "failed", (
            f"{chain.contact_id} turn {index + 1} ({world.world_id}) failed at "
            f"{result.stage}: {result.error}"
        )
        done = engine_mod.complete_turn(result.turn_id, world.fragments, session_factory=session_factory)
        stored = _stored_session(session_factory, world.contact_id)
        parse_output = ((result.ctx or {}).get("parse") or {}).get("output") or {}
        reason = worlds_mod.body_difference(
            world,
            parse_output=parse_output,
            actual_variables=(stored or {}).get("variables") or {},
            captured_parse_output=world.captured_parse_output,
        )
        if reason:
            # THE CHAIN STOPS HERE, it does not skip this turn and carry on. Once one turn
            # was produced by a different node body, the session the next turn reads is no
            # longer the session production had, so grading turn N+1 against its capture
            # would be measuring the contamination. The clean PREFIX is what this chain
            # can honestly prove.
            break
        _assert_world(world, done, stored)
        graded += 1
    if graded < 2:
        pytest.skip(
            f"{chain.contact_id}: only {graded} turn(s) of this chain come from the body "
            "the export ships, so there is no multi-turn memory path to grade. A fresh "
            "capture of this contact makes the whole chain gradeable."
        )


def _stored_session(session_factory, contact_id: str) -> dict:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": contact_id},
    ).first()
    raw = row.session_vars if row is not None else {}
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


# --------------------------------------------------------------------------- #
# The grader is asserted against, not just relied on: proves `_assert_world` fails
# the instant `reply.text` differs by ONE character, so the world-replay gate is
# checking the WORDS a customer reads, never just the response's shape (keys
# present, types right, text merely non-empty).
# --------------------------------------------------------------------------- #

# Three worlds confirmed to reach `_assert_world` (not skipped by `_grade_or_skip`)
# on the vendored-plus-full corpus available at S2 time. Picked, not derived, because
# the point of this test is the GRADER's sensitivity, not corpus coverage (that is
# `test_world_replay`'s job) - a world list that changes under the corpus should not
# make this test flap.
_GRADED_SAMPLE_IDS = (
    "clone-spine-RS/rs09-t2",
    "clone-spine-RS/rs09-t3",
    "clone-spine-RS/s57-t0",
)


def _graded_sample() -> list[worlds_mod.World]:
    by_id = {w.world_id: w for w in WORLDS}
    return [by_id[world_id] for world_id in _GRADED_SAMPLE_IDS if world_id in by_id]


class _MutatedResult:
    def __init__(self, reply: dict, actions: list) -> None:
        self.reply = reply
        self.actions = actions


@pytest.mark.parametrize(
    "world",
    _graded_sample() or [None],
    ids=lambda w: w.world_id if w else "no-graded-worlds-available",
)
def test_the_grader_fails_on_a_one_character_text_change(world, world_db, stub_world, session_factory) -> None:
    if world is None:
        pytest.skip(
            f"none of {_GRADED_SAMPLE_IDS} are gradeable in this checkout; "
            f"{_skip_reason()}"
        )
    world_db(world)
    stub_world(world)
    done, head = _run(world, session_factory)
    _grade_or_skip(world, head, done.session_patch)

    # The world must ACTUALLY pass on the real reply first - a world that fails on its
    # own tells us nothing about whether the grader is sensitive to a small change.
    _assert_world(world, done, done.session_patch)

    original = done.reply.get("text") or ""
    assert original, f"{world.world_id}: no reply text to mutate"
    flipped = ("!" if original[-1] != "!" else "?")
    mutated = _MutatedResult(reply={**done.reply, "text": original[:-1] + flipped}, actions=done.actions)

    with pytest.raises(AssertionError):
        _assert_world(world, mutated, done.session_patch)


# --------------------------------------------------------------------------- #
# The OWNER worlds (growth r1 slice B5, AC-940 to AC-948)
# --------------------------------------------------------------------------- #
#
# `worlds.OWNER_WORLDS` carries the cases and the reason each one exists. This is the
# runner: one contact per world, one turn after another, each reading the session the
# previous turn wrote - the same chaining property `test_multi_turn_world_replay` has and
# for the same reason. What differs is what is graded: a derived world grades the reply an
# execution actually produced, and these grade the DIALOGUE FACTS, because the rules they
# are about have no captured execution to be graded against.


OWNER_CONTACT = "ZZT-owner-world-contact"


@pytest.fixture()
def owner_stubs(monkeypatch):
    """The parser and the access check, stubbed at the seams the derived worlds use."""
    from app.services.chatbot.head import parser as parser_mod

    def _install(emission: dict, *, emits_v3: bool = False) -> None:
        monkeypatch.setattr(
            parser_mod,
            "resolve_config",
            lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
                system_prompt="stub",
                prompt_version=3 if emits_v3 else 1,
                provider="openai",
                model="gpt-test",
                api_key="sk-test",
                emits_v3=emits_v3,
            ),
        )
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: emission)
        monkeypatch.setattr(
            engine_mod,
            "check_access",
            lambda db, **kw: {
                "allowed": True,
                "decision": "allow",
                "agent_name": "General Enquiries",
                "attributes": None,
                "all_attributes_allowed": None,
            },
        )
        monkeypatch.setattr(engine_mod, "default_space_id", lambda db: None)

    return _install


def _owner_emission(overrides: dict) -> dict:
    from tests.chatbot.test_engine import _parser_output

    emission = _parser_output()
    # A v1-shaped authored turn carries none of the three v3 keys, exactly as every capture
    # does; a v3-shaped one sets only the ones it is about.
    for key in ("answers_open_question", "anaphora", "topic_reset"):
        emission.pop(key, None)
    emission.update(overrides)
    return emission


def _owner_fragments() -> dict:
    """The `sub-output` trigger contract, minimal, so the TAIL runs and writes the session.

    `not_supported` because these worlds grade memory and scope, not the answer: any lane
    that composes a reply would drag its own copy, its own roster and its own offer
    lifecycle into a test about which product is in scope.
    """
    return {
        "item": {"branch_kind": "not_supported", "allowed": True},
        "result": None,
        "resolved": None,
        "gate": None,
        "offer_hold": None,
        "suggest_offer": None,
        "not_found": None,
        "incoming_picker": None,
        "access_choice": None,
        "crossdomain_render": None,
        "answer": None,
        "clarify": None,
    }


def _owner_envelope(message: str, index: int, quoted: str | None = None) -> dict:
    inner: dict[str, Any] = {
        "messageId": f"ZZT-owner-msg-{index}",
        "contactId": OWNER_CONTACT,
        "message": {"type": "text", "text": message},
    }
    if quoted is not None:
        inner["replyTo"] = {"id": quoted}
    return {
        "message": {"contact": {"id": OWNER_CONTACT}, "message": inner},
        "contact": {"id": OWNER_CONTACT},
        "ingress": "console",
        "is_test": False,
    }


def _owner_session(session_factory) -> dict:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": OWNER_CONTACT},
    ).first()
    raw = row.session_vars if row is not None else {}
    stored = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return stored.get("variables") or {}


def _patch_owner_session(session_factory, patch: dict, *, drop: tuple[str, ...] = ()) -> None:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": OWNER_CONTACT},
    ).first()
    raw = row.session_vars if row is not None else {}
    stored = json.loads(raw) if isinstance(raw, str) else (raw or {})
    variables = {
        k: v for k, v in (stored.get("variables") or {}).items() if k not in drop
    }
    variables.update(patch)
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :c"),
        {"c": OWNER_CONTACT, "sv": json.dumps({**stored, "variables": variables})},
    )
    db.commit()


def _codes(entities: Any) -> list[str] | None:
    if not isinstance(entities, list):
        return None
    return [e.get("canonical_code") or e.get("raw") for e in entities if isinstance(e, dict)]


def _assert_owner_expectations(
    world: worlds_mod.OwnerWorld,
    turn: worlds_mod.OwnerTurn,
    index: int,
    *,
    variables: dict,
    qf: dict,
    trace: list,
) -> None:
    where = f"{world.world_id} turn {index + 1} ({turn.message!r})"
    focus = variables.get("focus") or {}
    expect = turn.expect

    if "focus_products" in expect:
        slot = focus.get("products") or {}
        got = _codes(slot.get("value"))
        assert got == expect["focus_products"], f"{where}: focus.products"
    if "focus_domain" in expect:
        assert (focus.get("domain") or {}).get("value") == expect["focus_domain"], (
            f"{where}: focus.domain"
        )
    if "focus_customer" in expect:
        slot = (focus.get("customer") or {}).get("value") or {}
        assert slot.get("canonical_code") == expect["focus_customer"], f"{where}: focus.customer"
    if "focus_date_window" in expect:
        assert (focus.get("date_window") or {}).get("value") == expect["focus_date_window"], (
            f"{where}: focus.date_window"
        )
    if "answered" in expect:
        assert qf.get("open_question_answered") == expect["answered"], (
            f"{where}: which handler answered the open question"
        )
    if expect.get("open_question_gone"):
        assert variables.get("open_question") is None, f"{where}: the offer should be closed"
    if "decayed" in expect:
        decayed = tuple(r["slot"] for r in trace if r.get("kind") == "decay")
        assert decayed == expect["decayed"], f"{where}: what decayed at intake"
    if "decay_reason_contains" in expect:
        reasons = " | ".join(
            str(r.get("reason") or "") for r in trace if r.get("kind") == "decay"
        )
        assert expect["decay_reason_contains"] in reasons, (
            f"{where}: the decay line has to SAY why, in turns"
        )
    if "qf_entity_codes" in expect:
        # THE assertion that makes a TTL mean something. A slot cleared in the focus
        # object and an entity still in `qf.entities` is a customer being answered about a
        # product they stopped talking about four turns ago.
        codes = _codes(qf.get("entities")) or []
        assert codes == expect["qf_entity_codes"], f"{where}: the scope that reached the lane"
    for key, value in (expect.get("qf") or {}).items():
        assert qf.get(key) == value, f"{where}: qf.{key}"


@pytest.mark.parametrize(
    "world", worlds_mod.OWNER_WORLDS, ids=lambda w: w.world_id
)
def test_owner_world(world, owner_stubs, session_factory, monkeypatch) -> None:
    """One authored conversation, turn by turn, on the CRM's own memory."""
    from app.models.chatbot_turn import ChatbotTurn
    from app.models.user import SystemSetting

    db = session_factory()
    db.execute(text("DELETE FROM respond_contacts WHERE respond_io_id = :c"), {"c": OWNER_CONTACT})
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :c, :p, CAST(:sv AS jsonb))"
        ),
        {"c": OWNER_CONTACT, "p": "+60000000777", "sv": json.dumps({"variables": {}})},
    )
    settings_row = db.query(SystemSetting).first()
    if settings_row is None:
        settings_row = SystemSetting()
        db.add(settings_row)
    settings_row.chatbot_focus_ttl_turns = world.ttl_turns
    db.commit()

    for index, turn in enumerate(world.turns):
        if turn.arm:
            # The lane that would have rendered this roster, stubbed by writing what it
            # would have persisted. See `worlds.OWNER_WORLDS`' own note. `open_question` is
            # REMOVED with the same write: for this release it is a mirror derived from the
            # legacy keys, and a present-but-null one means "it aged out", which would make
            # the stub arm nothing at all.
            _patch_owner_session(session_factory, turn.arm, drop=("open_question",))
        if turn.quoted_rows is not None:
            monkeypatch.setattr(
                engine_mod,
                "_read_session_vars",
                lambda db, *, respond_io_id, reply_to_id, _rows=turn.quoted_rows: {
                    "respond_io_id": respond_io_id,
                    "session_vars": {
                        **_stored_session_vars(session_factory, respond_io_id),
                        "referenced_result_set": _rows,
                        "referenced_state": None,
                    },
                },
            )
        owner_stubs(_owner_emission(turn.emission), emits_v3=world.emits_v3)
        envelope = _owner_envelope(
            turn.message, index, quoted="ZZT-owner-quoted" if turn.quoted_rows else None
        )
        result = engine_mod.run_turn(Envelope(**envelope), session_factory=session_factory)
        assert result.status != "failed", (
            f"{world.world_id} turn {index + 1} failed at {result.stage}: {result.error}"
        )
        engine_mod.complete_turn(
            result.turn_id, _owner_fragments(), session_factory=session_factory
        )
        row = (
            session_factory()
            .query(ChatbotTurn)
            .filter(ChatbotTurn.id == result.turn_id)
            .first()
        )
        _assert_owner_expectations(
            world,
            turn,
            index,
            variables=_owner_session(session_factory),
            qf=((result.ctx or {}).get("parse") or {}).get("output") or {},
            trace=list(row.trace or []),
        )
        if turn.quoted_rows is not None:
            monkeypatch.undo()


def _stored_session_vars(session_factory, respond_io_id: str) -> dict:
    from app.services.conversation_variables_service import get_for_contact

    return get_for_contact(session_factory(), respond_io_id=respond_io_id)


class TestTheOwnerWorldsCoverWhatTheOwnerAskedFor:
    """Six cases were named on 7 Sep 2026; each has a world and each names its ACs."""

    def test_every_world_says_which_criteria_it_grades_and_why(self) -> None:
        for world in worlds_mod.OWNER_WORLDS:
            assert world.acs, f"{world.world_id} grades no stated criterion"
            assert len(world.why) > 80, f"{world.world_id} does not say why it exists"
            assert len(world.turns) >= 2, f"{world.world_id} is not multi-turn"

    def test_the_criteria_the_plan_names_are_all_covered(self) -> None:
        covered = {ac for world in worlds_mod.OWNER_WORLDS for ac in world.acs}

        assert {"AC-940", "AC-941", "AC-942", "AC-944", "AC-945", "AC-946", "AC-947"} <= covered
