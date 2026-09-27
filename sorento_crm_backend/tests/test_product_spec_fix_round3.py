"""Fix lane round 3 on PR #1302 (#1286): the reviewer pass round 2 at 55e8c704, backend.

One test (or more) per finding, named by the finding's id: S-R1 and S-R2 (should fix),
N-R2 to N-R5 (nits). Each was run red against 55e8c704 first, for the reviewer's
scenario, and then made green. N-R3 is a pin: the reviewer's cap is not taken (see the
test), and the pin keeps the bound from being lowered below a shipped key's list.
"""
from __future__ import annotations

import inspect
import uuid

import pytest

from app.models.product_spec import ProductSpecRegistry
from app.services.error_handler import AppException
from tests.test_product_spec_fix_round2 import _product, _registry, _values, api  # noqa: F401

NO_LETTER_OR_NUMBER = "Rule 1: each word needs a letter or a number."
TEXTS = {"description": "WHITE CERAMIC BASIN ... TAP & MIXER: 1+1", "flyer": "", "class_tail": ""}


def _uid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# S-R1: a lazy commit's wait for the catalogue read never runs on the event loop
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "route", ["create_pending_action", "cancel_pending_action", "get_current_pending_action"]
)
def test_sr1_the_routes_that_commit_a_lapsed_action_are_plain_functions(route):
    """`_commit_if_due` can wait up to REMOVE_WAIT_SECONDS for another catalogue read;
    in an `async def` route that wait stalls every request on the worker."""
    from app.api.v1.system import pending_actions

    assert not inspect.iscoroutinefunction(getattr(pending_actions, route))


# --------------------------------------------------------------------------- #
# S-R2: a word to find, or a code text, needs a letter or a number
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "builder",
    [
        {"kind": "words", "words": ["&"], "value": "black"},
        {"kind": "words", "words": ["+"], "value": "black"},
        {"kind": "words", "words": ["GOLD", ","], "value": "black"},
        {"kind": "words", "words": ["( ... /"], "value": "black"},
        {"kind": "code", "code_match": "contains", "texts": ["&"], "value": "black"},
        {"kind": "code", "code_match": "contains", "texts": ["/"], "value": "black"},
    ],
)
def test_sr2_a_word_or_code_text_with_no_letter_or_number_is_refused(builder):
    from app.services.product_spec_rules import validate_rules

    with pytest.raises(AppException) as excinfo:
        validate_rules(
            [{"builder": builder}], spec_key="finish", data_type="enum", allowed_values=["black"]
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.message == NO_LETTER_OR_NUMBER


@pytest.mark.parametrize(
    "builder",
    [
        {"kind": "number", "after": ["("], "before": ["MM"]},
        {"kind": "number", "before": ["MM"], "skip_after": ["/"]},
        {"kind": "words", "words": ["BLACK"], "skip_after": ["&"], "value": "black"},
    ],
)
def test_sr2_punctuation_stays_allowed_next_to_a_number_and_in_skip_after(builder):
    from app.services.product_spec_rules import validate_rules

    data_type = "numeric" if builder["kind"] == "number" else "enum"
    assert validate_rules(
        [{"builder": builder}], spec_key="finish", data_type=data_type, allowed_values=["black"]
    )


@pytest.mark.parametrize(
    "builder",
    [
        {"kind": "words", "words": ["&"], "value": "black"},
        {"kind": "words", "words": ["+"], "value": "black"},
        {"kind": "code", "code_match": "contains", "texts": ["&"], "value": "black"},
    ],
)
def test_sr2_a_stored_punctuation_word_reads_nothing(builder):
    """The reviewer's text: a stray & or + wrote the value onto every such description."""
    from app.services.product_spec_rules import read_text

    assert read_text(builder, TEXTS, "SRT&1") is None


# --------------------------------------------------------------------------- #
# N-R2: Skip after still sees its phrase across a long run of separators
# --------------------------------------------------------------------------- #
def test_nr2_skip_after_sees_its_phrase_across_many_separators():
    from app.services.product_spec_rules import read_text

    builder = {"kind": "words", "words": ["BLACK"], "skip_after": ["NOT"], "value": "black"}
    texts = {"description": "NOT" + " -" * 150 + " BLACK", "flyer": "", "class_tail": ""}

    assert read_text(builder, texts, "") is None


# --------------------------------------------------------------------------- #
# N-R3 (pin): Try it takes a whole shipped rule list
# --------------------------------------------------------------------------- #
def test_nr3_try_it_takes_the_longest_shipped_rule_list():
    """The reviewer suggested about 20 rules per try; `product_type` ships 51, so that
    cap would refuse Try it on a shipped key. The bound stays above every shipped list."""
    from app.services.product_spec_derivation import shipped_rules
    from app.services.product_spec_rules import MAX_RULES_PER_TRY

    assert MAX_RULES_PER_TRY >= max(len(rules) for rules in shipped_rules().values())


# --------------------------------------------------------------------------- #
# N-R4: removing a staff-added choice takes the rules that set it with it
# --------------------------------------------------------------------------- #
def test_nr4_removing_a_staff_added_choice_takes_its_rules_and_rereads(api):  # noqa: F811
    from app.services.product_spec_registry import remove_value
    from app.services.product_spec_rules import validate_rules

    client, db = api
    teal = {"kind": "words", "words": ["ZZTTEAL"], "value": "teal"}
    other = {"kind": "words", "words": ["ZZTAWORD"], "value": "a"}
    row = ProductSpecRegistry(
        id=_uid(), spec_key=f"zzt_{_uid()[:8]}", label="ZZT", data_type="enum",
        allowed_values=["a"], user_values=["teal"], source="user",
        derivation_rules=[{"builder": teal}, {"builder": other}],
    )
    db.add(row)
    db.commit()
    product = _product(db, "ZZTTEAL BASIN")
    assert _values(db, product)[row.spec_key] == "teal"

    result = remove_value(db, row.spec_key, "teal")

    stored = _registry(db, row.spec_key)
    assert [r["builder"]["value"] for r in stored.derivation_rules] == ["a"]
    assert result.get("products_updated") == 1
    assert row.spec_key not in _values(db, product)
    # The next rules save does not trip over a rule setting a choice that is gone.
    validate_rules(
        stored.derivation_rules, spec_key=row.spec_key, data_type="enum",
        allowed_values=list(stored.allowed_values) + list(stored.user_values or []),
    )
    response = client.patch(
        f"/api/v1/master-data/spec-registry/{row.spec_key}",
        json={"derivation_rules": stored.derivation_rules},
    )
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- #
# N-R5: a lock that did not unlock is never handed back to the pool
# --------------------------------------------------------------------------- #
def test_nr5_a_failed_unlock_invalidates_the_connection(monkeypatch):
    from app.services import product_spec_preview

    calls: list[str] = []

    class _Connection:
        def execute(self, *a, **k):
            raise RuntimeError("unlock failed")

        def commit(self):
            calls.append("commit")

        def invalidate(self):
            calls.append("invalidate")

        def close(self):
            calls.append("close")

    with product_spec_preview._DATABASE_LOCKS_GUARD:
        product_spec_preview._DATABASE_LOCKS["zzt-token"] = (_Connection(), 1)

    product_spec_preview._release_database_lock("zzt-token")

    assert "invalidate" in calls, "a pooled connection would keep the session lock"
