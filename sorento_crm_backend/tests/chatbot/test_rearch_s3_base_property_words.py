"""S3 - base property words come from the entity kinds row, never "not recorded"
(AC-1535, PLAN-chatbot-turn-rearch.md).

`turn/compose.py` does not exist yet, so `TestDiscontinuedAnswersFromColumn` is RED at
collection with `ModuleNotFoundError: No module named 'app.services.chatbot.turn.
compose'`.

`TestWordTableReadFromEntityKindsRow` runs against the REAL migrated database
(`tests._pg_fixture.pg_session`, this worktree's private `sorento_ai_automation_
rearch_test`) because the row it mutates is migration-seeded data
(`chatbot_entity_kinds`, AC-1502/S0) - see `test_rearch_s0_entity_kinds_seed.py`'s own
docstring for why `pg_session` rather than a blank scratch schema. It is RED today for
a THIRD reason on top of the missing module: `chatbot_entity_kinds` does not exist
until the coder's S0 migration lands on this worktree's DB (`alembic upgrade head`
re-run after that), which is the same substrate gap S0's own tests hit.

**Ambiguity flagged to the captain**: no loader function name for "Policy built from
`chatbot_entity_kinds` rows" is given anywhere in the PLAN/UAC or the S2 committed
code (`turn/policy.py::Policy.from_rows` takes plain dicts, and every S2 test seeds
those by hand per the "Testing seams" doctrine - "Policy is built from rows: tests
seed rows, never patch constants" - which does not by itself say WHERE the real loader
that reads the DB rows lives). This file assumes
`app.services.chatbot.turn.policy.load_policy(db) -> Policy`, the load path AC-1535's
own "seed changed in the DB, assert honoured" wording implies must exist somewhere. If
the coder names it differently, `_load_policy` below is the one place to update.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from tests._pg_fixture import pg_session
from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row, _kind_row


def _load_policy(db):
    from app.services.chatbot.turn.policy import load_policy

    return load_policy(db)


class TestDiscontinuedAnswersFromColumn:
    def test_discontinued_figures_carry_the_column_and_text_never_says_not_recorded(self) -> None:
        from app.services.chatbot.turn.compose import compose
        from app.services.chatbot.turn.policy import Policy
        from app.services.chatbot.turn.state import Focus, Profile, State

        row = _domain_row("master_products", narrowing={"product": "list_all"})
        row["label"] = "Product information"
        kind_row = _kind_row("product", default_narrowing="list_all", family_grouping="base_code")
        kind_row["base_property_words"] = {"discontinued": "is_discontinued"}
        policy = Policy.from_rows(domains=[row], kinds=[kind_row], tier_order=TIER_ORDER_FIXTURE)

        figures = [
            {"fields": [{"label": "Product Code", "value": "SRTWC287-A"}], "is_discontinued": True},
            {"fields": [{"label": "Product Code", "value": "SRTWC287-B"}], "is_discontinued": True},
            {"fields": [{"label": "Product Code", "value": "SRTWC287-C"}], "is_discontinued": False},
        ]
        envelopes = [
            {
                "domain": "master_products",
                "denied": False,
                "entities": ["SRTWC287-A", "SRTWC287-B", "SRTWC287-C"],
                "figures": figures,
                "files": [],
                "miss": [],
            }
        ]
        state = State(focus=Focus(), pending=None, profile=Profile(), turn_no=1)

        answer = compose(envelopes, state, policy, SimpleNamespace())

        section = answer.sections[0]
        discontinued_flags = [f.get("is_discontinued") for f in section.figures]
        assert discontinued_flags == [True, True, False], section.figures
        assert "not recorded" not in answer.text.lower(), answer.text


class TestWordTableReadFromEntityKindsRow:
    NEW_WORD = "ZZT-floor-rated"
    NEW_COLUMN = "is_floor_rated"

    def test_a_seeded_extra_word_is_honoured(self) -> None:
        original: dict[str, Any] | None = None
        try:
            with pg_session() as db:
                try:
                    row = db.execute(
                        text("SELECT base_property_words FROM chatbot_entity_kinds WHERE kind = 'product'")
                    ).first()
                except ProgrammingError as exc:
                    pytest.fail(
                        "chatbot_entity_kinds does not exist yet on this worktree's DB "
                        f"(re-run `alembic upgrade head` after the coder's S0 migration lands): {exc}",
                        pytrace=False,
                    )
                if row is None:
                    pytest.fail(
                        "no chatbot_entity_kinds row for kind='product' - S0's seed has not "
                        "landed on this worktree's DB yet",
                        pytrace=False,
                    )
                original = dict(row.base_property_words or {})
                patched = dict(original)
                patched[self.NEW_WORD] = self.NEW_COLUMN
                db.execute(
                    text(
                        "UPDATE chatbot_entity_kinds SET base_property_words = CAST(:v AS jsonb) "
                        "WHERE kind = 'product'"
                    ),
                    {"v": json.dumps(patched)},
                )
                db.commit()

                policy = _load_policy(db)
                product_kind = policy.kind("product")
                assert product_kind is not None, "no 'product' EntityKindPolicy loaded"
                assert product_kind.base_property_words.get(self.NEW_WORD) == self.NEW_COLUMN, (
                    f"the newly-seeded word {self.NEW_WORD!r} must be honoured by the "
                    f"loaded Policy: {product_kind.base_property_words!r}"
                )
        finally:
            if original is not None:
                with pg_session() as db:
                    db.execute(
                        text(
                            "UPDATE chatbot_entity_kinds SET base_property_words = CAST(:v AS jsonb) "
                            "WHERE kind = 'product'"
                        ),
                        {"v": json.dumps(original)},
                    )
                    db.commit()
