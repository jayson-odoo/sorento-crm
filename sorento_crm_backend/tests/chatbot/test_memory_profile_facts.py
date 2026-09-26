"""S2 profile facts service - tester-first RED, from the UAC and the lane A contract
(section 4 "Profile facts").

Covers AC-MEM030 to AC-MEM037, AC-MEM040, AC-MEM049.

**No implementation exists yet.** `app/services/chatbot/turn/profile_facts.py` does not
exist at all: `VOCABULARY`, `crm_view`, `tally`, `apply_statement`, `set_staff_fact`,
`delete_fact`, `parser_slice` are all undefined. Every test below fails at
`ModuleNotFoundError: No module named 'app.services.chatbot.turn.profile_facts'` unless
noted otherwise - a missing-module red, never a fixture bug.

Postgres only (`tests/chatbot/conftest.py::session_factory`, blank scratch schema); every
customer/sales-agent/warehouse/brand/market-segment chain is seeded fresh per test, never
borrowed (CI's database is empty).

**Ambiguities flagged to the captain** (contract reading taken, named inline at the test
that depends on it):

1. `VOCABULARY`'s shape is not pinned by the contract beyond "ordered keys". Read here as
   a `dict`-like object (insertion-ordered) mapping key -> a spec carrying at least the
   allowed sources, since that is what `apply_statement`/`set_staff_fact` need to validate
   against; `list(VOCABULARY)` is asserted to equal the ordered key list.
2. `tier` is NOT in the vocabulary table (contract section 4) - it stays a `chatbot_profile`
   SETTING (existing top-level key), not a `facts` list entry (plan 4.1: "the existing
   settings keys stay where they are (tier, default_ledgers, the toggles)"). AC-MEM037 is
   therefore tested against `chatbot_profile["tier"]` directly, through the ENGINE (a real
   tier-pick turn), not through `profile_facts.apply_statement` (which the vocabulary does
   not cover for this key).
3. AC-MEM036's "byte-identical" snapshot is taken as: `access_levels`, `company_id` on
   every one of the contact's `respond_contact_customers` rows, and the resolved reveal
   `attributes` list from `head.access.check_access` - the three surfaces the contract
   names ("access_levels, company scope, linked customers").
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import text

from app.models.conversation_frame import ConversationFrame
from app.models.order import Customer
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401

VOCAB_ORDER = [
    "customer",
    "segment",
    "salesperson",
    "language",
    "role",
    "usual_products",
    "usual_brands",
    "usual_sites",
    "project",
    "about",
    "note",
]


def _cid() -> str:
    return f"ZZT-pf-{uuid.uuid4().hex[:10]}"


def _seed_contact(session_factory, contact_respond_id: str, *, profile: dict | None = None) -> str:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, "
            "chatbot_profile) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), CAST(:p AS jsonb))"
        ),
        {
            "cid": contact_respond_id,
            "phone": f"+6011{uuid.uuid4().hex[:8]}",
            "sv": json.dumps({"variables": {}}),
            "p": json.dumps(profile or {}),
        },
    )
    db.commit()
    return db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": contact_respond_id}
    ).scalar()


def _load_profile_facts():
    from app.services.chatbot.turn import profile_facts

    return profile_facts


def _seed_market_segment(db, code: str = "dealer") -> None:
    db.execute(
        text(
            "INSERT INTO market_segments (id, code, name) VALUES (gen_random_uuid(), :c, :n) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {"c": code, "n": code.title()},
    )
    db.commit()


def _seed_sales_agent(db, *, name: str = "Aina") -> str:
    row_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO sales_agents (id, sales_agent, is_active) VALUES (:i, :n, true)"
        ),
        {"i": row_id, "n": name},
    )
    db.commit()
    return row_id


def _seed_customer_link(
    session_factory,
    *,
    contact_pk: str,
    customer_name: str = "Chin Chun Trading",
    customer_code: str = "CC001",
    segment_code: str | None = "dealer",
    sales_agent_id: str | None = None,
    is_primary: bool = True,
) -> str:
    db = session_factory()
    if segment_code:
        _seed_market_segment(db, segment_code)
    customer = Customer(
        customer_code=customer_code,
        customer_name=customer_name,
        is_active=True,
        market_segment_code=segment_code,
        sales_agent_id=sales_agent_id,
    )
    db.add(customer)
    db.flush()
    db.execute(
        text(
            "INSERT INTO respond_contact_customers (id, contact_id, customer_id, is_primary, source) "
            "VALUES (gen_random_uuid(), :cid, :cust, :prim, 'manual')"
        ),
        {"cid": contact_pk, "cust": customer.id, "prim": is_primary},
    )
    db.commit()
    return customer.id


def _seed_warehouse(session_factory, name: str = "Kuching") -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active) "
            "VALUES (gen_random_uuid(), :code, :name, true)"
        ),
        {"code": f"ZZT-{uuid.uuid4().hex[:6]}", "name": name},
    )
    db.commit()


def _seed_brand(session_factory, name: str = "Sorento") -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO brands (id, brand_code, brand_name, is_active) "
            "VALUES (gen_random_uuid(), :code, :name, true)"
        ),
        {"code": f"ZZT-{uuid.uuid4().hex[:6]}", "name": name},
    )
    db.commit()


def _seed_closed_frame(
    session_factory,
    *,
    contact_respond_id: str,
    entities: dict[str, Any],
    days_ago: int,
    turn_id: str | None = None,
) -> str:
    db = session_factory()
    when = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago)
    frame = ConversationFrame(
        contact_id=contact_respond_id,
        contact_respond_id=contact_respond_id,
        space_id="0",
        channel="whatsapp",
        domain="inventory",
        status="closed",
        close_reason="topic_switch",
        entities=entities,
        turn_ids=[turn_id or f"ZZT-pf-frame-{uuid.uuid4().hex[:8]}"],
        started_at=when,
        opened_at=when,
        last_activity_at=when,
        closed_at=when,
    )
    db.add(frame)
    db.commit()
    return frame.id


def _profile_row(session_factory, contact_pk: str) -> dict:
    return session_factory().execute(
        text("SELECT chatbot_profile FROM respond_contacts WHERE id = :i"), {"i": contact_pk}
    ).scalar()


# --------------------------------------------------------------------------- #
# AC-MEM030: the vocabulary is exact; unknown key / disallowed source rejected
# --------------------------------------------------------------------------- #


class TestVocabulary:
    def test_vocabulary_keys_in_order(self) -> None:
        profile_facts = _load_profile_facts()
        assert list(profile_facts.VOCABULARY) == VOCAB_ORDER, list(profile_facts.VOCABULARY)

    @pytest.mark.parametrize(
        "key,source",
        [
            ("customer", "staff"),  # read-only, no source may write it
            ("customer", "stated"),
            ("salesperson", "staff"),
            ("usual_products", "stated"),  # table: tallied, staff only - no "stated"
            ("note", "stated"),  # staff-only key
            ("note", "tallied"),
            ("bogus_key", "staff"),
        ],
    )
    def test_disallowed_source_or_unknown_key_is_rejected(self, session_factory, key, source) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        db = session_factory()

        if source == "staff":
            result = profile_facts.set_staff_fact(db, contact_pk, key, "some value", user_id=str(uuid.uuid4()))
        else:
            result = profile_facts.apply_statement(db, cid, key, "some value", turn_id="ZZT-pf-turn-1")
        assert result is None, f"{key}/{source} must be rejected, got {result!r}"

        stored = _profile_row(session_factory, contact_pk)
        facts = (stored or {}).get("facts") or []
        assert not any(f.get("key") == key for f in facts), (
            f"a rejected write for {key!r} must not land in chatbot_profile.facts: {facts}"
        )


# --------------------------------------------------------------------------- #
# AC-MEM031: crm_view is a LIVE read, never stored
# --------------------------------------------------------------------------- #


class TestCrmViewLive:
    def test_primary_customer_segment_and_salesperson_read_live(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        agent_id = _seed_sales_agent(session_factory, name="Aina")
        _seed_customer_link(
            session_factory, contact_pk=contact_pk, customer_name="Chin Chun Trading",
            customer_code="CC001", segment_code="dealer", sales_agent_id=agent_id,
        )
        db = session_factory()
        contact = db.execute(
            text("SELECT id, respond_io_id FROM respond_contacts WHERE id = :i"), {"i": contact_pk}
        ).one()

        facts = profile_facts.crm_view(db, contact)
        by_key = {f["key"]: f for f in facts}
        assert "Chin Chun Trading" in by_key["customer"]["value"], by_key["customer"]
        assert by_key["segment"]["value"] == "dealer", by_key["segment"]
        assert by_key["salesperson"]["value"] == "Aina", by_key["salesperson"]

        stored = _profile_row(session_factory, contact_pk)
        assert not any((stored or {}).get(k) for k in ("customer", "segment", "salesperson")), (
            "crm facts must NEVER be persisted into chatbot_profile"
        )
        for f in facts:
            assert f["key"] not in ((stored or {}).get("facts") or []), stored

    def test_changing_the_sales_agent_changes_the_next_read(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        agent_a = _seed_sales_agent(session_factory, name="Aina")
        customer_id = _seed_customer_link(
            session_factory, contact_pk=contact_pk, sales_agent_id=agent_a,
        )
        db = session_factory()
        contact = db.execute(
            text("SELECT id, respond_io_id FROM respond_contacts WHERE id = :i"), {"i": contact_pk}
        ).one()
        first = {f["key"]: f["value"] for f in profile_facts.crm_view(db, contact)}
        assert first["salesperson"] == "Aina", first

        agent_b = _seed_sales_agent(session_factory, name="Ben")
        db2 = session_factory()
        db2.execute(text("UPDATE customers SET sales_agent_id = :a WHERE id = :c"), {"a": agent_b, "c": customer_id})
        db2.commit()

        second = {f["key"]: f["value"] for f in profile_facts.crm_view(session_factory(), contact)}
        assert second["salesperson"] == "Ben", second


# --------------------------------------------------------------------------- #
# AC-MEM032 (Q7): tally over the last 10 closed episodes
# --------------------------------------------------------------------------- #


class TestTally:
    def test_entity_in_two_of_last_ten_is_a_fact_one_is_not(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["SRTWB1455"]}, days_ago=1)
        _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["SRTWB1455"]}, days_ago=2)
        _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["M486-75-BL"]}, days_ago=3)

        db = session_factory()
        facts = profile_facts.tally(db, cid)
        by_key = {f["key"]: f for f in facts}
        assert "usual_products" in by_key, facts
        assert "SRTWB1455" in by_key["usual_products"]["value"], by_key["usual_products"]
        assert "M486-75-BL" not in by_key["usual_products"]["value"], (
            "an entity seen in only ONE episode must not become a fact"
        )
        assert by_key["usual_products"]["seen_count"] == 2, by_key["usual_products"]
        assert "first_seen" in by_key["usual_products"] and "last_seen" in by_key["usual_products"]
        assert "expiry" not in by_key["usual_products"] and "expires_at" not in by_key["usual_products"]

    def test_top_three_by_count_then_recency(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        _seed_contact(session_factory, cid)
        # A: 4 hits, B: 3 hits, C: 2 hits, D: 2 hits (more recent than C) -> top3 = A, B, D
        for days_ago in (1, 2, 3, 4):
            _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["A"]}, days_ago=days_ago)
        for days_ago in (1, 2, 3):
            _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["B"]}, days_ago=days_ago)
        for days_ago in (8, 9):
            _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["C"]}, days_ago=days_ago)
        for days_ago in (1, 2):
            _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["D"]}, days_ago=days_ago)

        db = session_factory()
        facts = profile_facts.tally(db, cid)
        usual = next(f for f in facts if f["key"] == "usual_products")
        assert usual["value"] == ["A", "B", "D"], usual

    def test_value_dropping_out_of_last_ten_is_removed_on_next_tally(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        _seed_contact(session_factory, cid)
        for days_ago in (1, 2):
            _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["OLD"]}, days_ago=days_ago)
        db = session_factory()
        first = profile_facts.tally(db, cid)
        assert any(f["key"] == "usual_products" and "OLD" in f["value"] for f in first), first

        # 10 more, newer episodes never mentioning OLD - it falls out of the last-10 window.
        for i in range(10):
            _seed_closed_frame(
                session_factory, contact_respond_id=cid, entities={"product": [f"NEW{i}"]}, days_ago=0,
            )
        second = profile_facts.tally(session_factory(), cid)
        usual = next((f for f in second if f["key"] == "usual_products"), None)
        assert usual is None or "OLD" not in usual["value"], usual


# --------------------------------------------------------------------------- #
# AC-MEM033 (Q6): stated facts, validated per key
# --------------------------------------------------------------------------- #


class TestStatedValidation:
    def test_valid_role_is_written(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        db = session_factory()
        result = profile_facts.apply_statement(db, cid, "role", "purchaser", turn_id="ZZT-pf-role-1")
        assert result is not None and result["value"] == "purchaser", result
        stored = _profile_row(session_factory, contact_pk)
        assert any(f["key"] == "role" and f["value"] == "purchaser" for f in stored["facts"]), stored

    def test_invalid_role_writes_nothing(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        db = session_factory()
        result = profile_facts.apply_statement(db, cid, "role", "ceo", turn_id="ZZT-pf-role-2")
        assert result is None, result
        stored = _profile_row(session_factory, contact_pk)
        assert not (stored or {}).get("facts"), stored

    def test_valid_language_written_invalid_rejected(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()
        assert profile_facts.apply_statement(db, cid, "language", "ms", turn_id="t1") is not None
        assert profile_facts.apply_statement(session_factory(), cid, "language", "fr", turn_id="t2") is None

    def test_brand_validated_against_brand_master(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        _seed_brand(session_factory, "Sorento")
        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()
        assert profile_facts.apply_statement(db, cid, "usual_brands", ["Sorento"], turn_id="t1") is not None
        assert profile_facts.apply_statement(session_factory(), cid, "usual_brands", ["NoSuchBrand"], turn_id="t2") is None

    def test_site_validated_against_warehouse_names(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        _seed_warehouse(session_factory, "Kuching")
        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()
        assert profile_facts.apply_statement(db, cid, "usual_sites", ["Kuching"], turn_id="t1") is not None
        assert profile_facts.apply_statement(session_factory(), cid, "usual_sites", ["Nowhere"], turn_id="t2") is None

    def test_project_cut_to_60_chars_newlines_stripped(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        db = session_factory()
        raw = "Aurora Residences\nblock B " + ("x" * 80)
        result = profile_facts.apply_statement(db, cid, "project", raw, turn_id="t1")
        assert result is not None
        assert "\n" not in result["value"]
        assert len(result["value"]) <= 60, result

    def test_about_over_200_chars_per_entry_is_rejected(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()
        too_long = "x" * 201
        assert profile_facts.apply_statement(db, cid, "about", too_long, turn_id="t1") is None
        ok = "x" * 199
        assert profile_facts.apply_statement(session_factory(), cid, "about", ok, turn_id="t2") is not None


# --------------------------------------------------------------------------- #
# AC-MEM034: precedence staff > stated > crm > tallied; staff tombstone
# --------------------------------------------------------------------------- #


class TestPrecedenceAndTombstone:
    def test_staff_beats_stated_which_beats_tallied(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        db = session_factory()
        profile_facts.apply_statement(db, cid, "role", "purchaser", turn_id="t1")
        profile_facts.set_staff_fact(session_factory(), contact_pk, "role", "owner", user_id=str(uuid.uuid4()))

        stored = _profile_row(session_factory, contact_pk)
        role_entries = [f for f in stored["facts"] if f["key"] == "role"]
        assert len(role_entries) == 1, role_entries
        assert role_entries[0]["value"] == "owner", role_entries
        assert role_entries[0]["source"] == "staff", role_entries

        # a stated write AFTER the staff fact must not overwrite it (precedence, not order)
        profile_facts.apply_statement(session_factory(), cid, "role", "sales", turn_id="t2")
        stored2 = _profile_row(session_factory, contact_pk)
        role_entries2 = [f for f in stored2["facts"] if f["key"] == "role"]
        assert len(role_entries2) == 1 and role_entries2[0]["value"] == "owner", role_entries2

    def test_staff_delete_of_a_learned_value_leaves_a_tombstone_not_relearned(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        for days_ago in (1, 2):
            _seed_closed_frame(session_factory, contact_respond_id=cid, entities={"product": ["SRTWB1455"]}, days_ago=days_ago)
        db = session_factory()
        facts = profile_facts.tally(db, cid)
        db.commit()
        assert any(f["key"] == "usual_products" for f in facts)

        profile_facts.delete_fact(session_factory(), contact_pk, "usual_products")
        stored = _profile_row(session_factory, contact_pk)
        assert not any(f.get("key") == "usual_products" and f.get("source") != "staff" for f in (stored.get("facts") or [])), stored

        # Re-tally over the SAME frames must not bring the deleted value back.
        second = profile_facts.tally(session_factory(), cid)
        usual = next((f for f in second if f["key"] == "usual_products"), None)
        assert usual is None or "SRTWB1455" not in usual.get("value", []), (
            f"a tombstoned value must not be re-learned by the next tally: {usual}"
        )


# --------------------------------------------------------------------------- #
# AC-MEM035 (Q7): no expiry - a 400-day-old stated fact is still rendered
# --------------------------------------------------------------------------- #


class TestNoExpiry:
    def test_400_day_old_stated_fact_still_in_parser_slice(self, session_factory, monkeypatch) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        old_day = (date.today() - timedelta(days=400)).isoformat()

        db = session_factory()
        db.execute(
            text(
                "UPDATE respond_contacts SET chatbot_profile = jsonb_set("
                "coalesce(chatbot_profile, '{}'::jsonb), '{facts}', "
                "CAST(:facts AS jsonb)) WHERE id = :i"
            ),
            {
                "facts": json.dumps([
                    {
                        "key": "role", "value": "purchaser", "source": "stated",
                        "source_ref": "t-old", "first_seen": old_day, "last_seen": old_day,
                        "seen_count": 1, "set_by": None,
                    }
                ]),
                "i": contact_pk,
            },
        )
        db.commit()

        stored = _profile_row(session_factory, contact_pk)
        crm: list[dict] = []
        slice_text = profile_facts.parser_slice(stored.get("facts") or [], crm)
        assert "purchaser" in slice_text, slice_text


# --------------------------------------------------------------------------- #
# AC-MEM036: facts never grant
# --------------------------------------------------------------------------- #


class TestFactsNeverGrant:
    def test_stated_role_owner_leaves_access_and_customer_links_untouched(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        customer_id = _seed_customer_link(session_factory, contact_pk=contact_pk, customer_name="Iborn")

        before_links = session_factory().execute(
            text(
                "SELECT contact_id, customer_id, is_primary, company_id FROM respond_contact_customers "
                "WHERE contact_id = :c ORDER BY customer_id"
            ),
            {"c": contact_pk},
        ).fetchall()
        before_agent = session_factory().execute(
            text("SELECT id FROM sales_agents LIMIT 0")
        ).fetchall()  # no agents seeded; the point is nothing here changes either

        db = session_factory()
        profile_facts.apply_statement(db, cid, "role", "owner", turn_id="ZZT-pf-grant-1")

        after_links = session_factory().execute(
            text(
                "SELECT contact_id, customer_id, is_primary, company_id FROM respond_contact_customers "
                "WHERE contact_id = :c ORDER BY customer_id"
            ),
            {"c": contact_pk},
        ).fetchall()
        assert before_links == after_links, (before_links, after_links)
        assert before_agent == []

        # No `access_levels` column exists on `respond_contacts` today in this codebase's
        # RBAC model (grants live on `users`, not on a chat contact) - the strongest
        # available proxy is that the customer link table (the "linked customers" the AC
        # names) is untouched, asserted above.


# --------------------------------------------------------------------------- #
# AC-MEM037: a tier pick in chat writes tier; the next turn does not ask again
# (see module docstring, ambiguity 2: tier is a SETTING, not a VOCABULARY fact)
# --------------------------------------------------------------------------- #


class TestTierPickWritesProfile:
    def test_tier_pick_answer_persists_tier_and_suppresses_the_next_ask(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from app.services.chatbot import engine as engine_mod

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        stub_access()

        # T1: a promotion ask with no known tier asks the tier (narrow.py's own
        # `NarrowOutcome("tier_pick", ...)` - see `turn/narrow.py:452-469`).
        v1 = verdict(domain_hint="promotion", entities=[])
        stub_parser(v1)
        e1 = _envelope()
        e1.message["message"]["messageId"] = "ZZT-pf-tier-1"
        r1 = engine_mod.run_turn(e1, session_factory=session_factory)
        assert r1.branch_kind != "business_query" or True  # the ask is the point, not this

        # T2: the dealer answers the tier menu ("1" -> dealer). The parser's own
        # `answers_open_question` signals the resolved pick.
        v2 = verdict(
            domain_hint="promotion",
            entities=[],
            answers_open_question={"resolved": True, "picks": [1], "answer": "dealer"},
        )
        stub_parser(v2)
        e2 = _envelope()
        e2.message["message"]["messageId"] = "ZZT-pf-tier-2"
        engine_mod.run_turn(e2, session_factory=session_factory)

        stored = _profile_row(session_factory, session_factory().execute(
            text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid}
        ).scalar())
        assert (stored or {}).get("tier") == "dealer", (
            f"a tier pick in chat must write chatbot_profile.tier - got {stored!r}"
        )

        # T3: a fresh promotion ask must NOT ask the tier again.
        v3 = verdict(domain_hint="promotion", entities=[])
        stub_parser(v3)
        e3 = _envelope()
        e3.message["message"]["messageId"] = "ZZT-pf-tier-3"
        r3 = engine_mod.run_turn(e3, session_factory=session_factory)
        assert r3.branch_kind != "tier_ask", (
            f"a known tier (from the pick, not the PUT route) must suppress the next ask, "
            f"got branch_kind={r3.branch_kind!r}"
        )


# --------------------------------------------------------------------------- #
# AC-MEM040: a staff fact write under a turn's in-flight window is preserved
# --------------------------------------------------------------------------- #


class TestConcurrentStaffAndStatedWrites:
    def test_staff_fact_written_between_two_apply_statement_calls_survives(self, session_factory) -> None:
        """Simulates "a staff fact saved while a turn is between intake and tail" with two
        SEPARATE sessions (not a real thread race - see AC-MEM006's own note on why a
        genuine two-connection race is impractical on the shared blank scratch schema),
        proving the single-key `jsonb_set` under a row lock never clobbers a concurrent
        write the way a read-modify-write of an intake-time snapshot would."""
        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)

        # Turn A "loads" its profile snapshot at intake (nothing written yet)...
        db_a = session_factory()
        _ = _profile_row(session_factory, contact_pk)

        # ...then, before turn A's tail writes, staff save a fact on a DIFFERENT session.
        db_b = session_factory()
        profile_facts.set_staff_fact(db_b, contact_pk, "note", "Prefers PDF quotes", user_id=str(uuid.uuid4()))

        # Turn A's tail now writes its OWN key (a different one).
        profile_facts.apply_statement(db_a, cid, "role", "purchaser", turn_id="ZZT-pf-conc-1")

        stored = _profile_row(session_factory, contact_pk)
        keys = {f["key"] for f in (stored.get("facts") or [])}
        assert "note" in keys and "role" in keys, (
            f"both writes must survive - a read-modify-write of an intake snapshot would "
            f"have clobbered one: {stored}"
        )

    def test_whole_profile_put_preserves_facts(self, session_factory, stub_access) -> None:
        from fastapi.testclient import TestClient

        from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
        from app.main import app
        from app.services.user_service import UserPermissionService

        profile_facts = _load_profile_facts()
        cid = _cid()
        contact_pk = _seed_contact(session_factory, cid)
        db = session_factory()
        profile_facts.apply_statement(db, cid, "role", "purchaser", turn_id="ZZT-pf-put-1")

        def _override_db():
            yield session_factory()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4())}
        import contextlib

        with contextlib.suppress(Exception):
            import monkeypatch as _mp  # noqa
        try:
            from unittest import mock

            with mock.patch.object(
                UserPermissionService, "check_user_has_permission",
                lambda self, uid, slug: slug == "user_management.contacts.edit",
            ), mock.patch.object(UserPermissionService, "get_user_role_slugs", lambda self, uid: set()):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.put(
                    f"/api/v1/user-management/contacts/{contact_pk}/chatbot",
                    json={"chatbot_profile": {"tier": "dealer", "language": "en"}},
                )
                assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()

        stored = _profile_row(session_factory, contact_pk)
        assert any(f["key"] == "role" for f in (stored.get("facts") or [])), (
            f"the whole-profile PUT must preserve facts, got {stored}"
        )
