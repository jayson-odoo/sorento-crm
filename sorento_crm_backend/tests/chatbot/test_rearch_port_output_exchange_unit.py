"""Port of `test_output_exchange_unit.py` (AC-1592) onto the new seams.

`head/output_exchange.py` (the module the original file imported `output_exchange`/
`suggest_follow_up` from) no longer exists in this worktree. Two properties it proved
are re-targeted here against the module that owns each one now:

1. **Unicode-dash normalisation** (contract line 55, "dash fold") - the original file's
   `TestUnicodeDashNormalisation`. The exact mechanism moved: the old code normalised a
   MINUS SIGN (U+2212) / EN DASH (U+2013) in an entity's `raw`/`canonical_code` to an
   ASCII hyphen before the resolver ever saw it (fixing a real production incident, exec
   12053189: "SRT332-GM" typed with a U+2212 missed the resolver's exact match). The new
   resolver instead FOLDS the token - `lanes/business/resolve_gate._PRODUCT_FOLD =
   re.compile(r"[-\\s]+")`, `_token_of()` - which strips ASCII hyphen and whitespace
   entirely before matching. Grepped this worktree (`app/services/chatbot/`, `turn/`,
   `head/`, `lanes/business/`) for `0x2212`/`MINUS`/`0x2213`/`EN_DASH`/a dash-normaliser
   comment: nothing found outside this test file and the deleted module. Probed
   `_token_of` directly (confirmed empirically this session, 16 Sep 2026):
   `_token_of({"raw": "SRT332\\u2212GM", "hint": "product"})` returns
   `"SRT332\\u2212GM"` unchanged (the MINUS SIGN survives the fold, `[-\\s]+` matches
   only ASCII `-`), where the ASCII-hyphen sibling folds clean to `"SRT332GM"`. **This
   reproduces exec 12053189's original defect in the new architecture** - RED for a real
   reason, not a fixture bug. Reported to the captain; not the tester's fix to make
   (LESSONS: "do not chase further as tester").

2. **Domain-hint enum guard** (F3, `contracts.coerce_domain_hint`) - the original file's
   `TestDomainHintEnumGuard`. `coerce_domain_hint` still exists in `contracts.py` but is
   called from NOWHERE in this worktree (`grep -rn coerce_domain_hint app/services/
   chatbot/` finds only its own definition and one comment in `fetch.py` naming it, no
   real call site). `turn/apply.py` reads `verdict.get("domain_hint")` raw wherever it
   builds `Plan.domains` (lines ~175, ~220, ~252, ~459 as of this session) - no coercion
   against any known-domain set. Probed `apply()` directly (confirmed empirically):
   `verdict(domain_hint="purchasing", ...)` (a team name, not a domain - the exact F3
   incident's own value) survives straight through to `plan.domains == ["purchasing"]`.
   **This reproduces the F3 defect in the new architecture** - RED for a real reason.
   Reported to the captain; not the tester's fix to make.

Neither finding is a fixture bug: both are probed directly against the real function
with no monkeypatching, no mocked DB, no network.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict

MINUS_SIGN = chr(0x2212)  # MINUS SIGN, what Excel and Sheets emit
EN_DASH = chr(0x2013)  # EN DASH, what Word autocorrect emits


class TestUnicodeDashFoldSurvivesIntoTheResolverToken:
    """`lanes/business/resolve_gate._token_of` is the new seam a dash-bearing product
    code reaches before the resolver's SQL match (`_PRODUCT_FOLD`)."""

    def test_a_minus_sign_survives_the_fold_reproducing_exec_12053189(self) -> None:
        from app.services.chatbot.lanes.business.resolve_gate import _token_of

        token = _token_of({"raw": f"SRT332{MINUS_SIGN}GM", "hint": "product"})
        assert token == "SRT332GM", (
            f"a MINUS SIGN in the raw product code must fold to the same clean token an "
            f"ASCII hyphen does (SRT332GM) so the resolver's exact match still finds the "
            f"code; got {token!r}. This is exec 12053189's own production incident "
            "(`SRT332-GM` typed with a Unicode minus sign missed the resolver) "
            "reproduced against the new resolve_gate seam - the dash normaliser that "
            "used to run before resolve-entity (`head/output_exchange.py`, deleted in "
            "the S3 rewrite) has no equivalent here."
        )

    def test_an_en_dash_in_canonical_code_also_survives_the_fold(self) -> None:
        from app.services.chatbot.lanes.business.resolve_gate import _token_of

        token = _token_of(
            {
                "raw": f"SRT332{EN_DASH}GM",
                "hint": "product",
                "canonical_code": f"SRT332{EN_DASH}GM",
            }
        )
        assert token == "SRT332GM", f"expected SRT332GM, got {token!r}"

    def test_an_ascii_hyphen_still_folds_clean_control(self) -> None:
        """Guard, green today: the ASCII case this file is contrasting against."""
        from app.services.chatbot.lanes.business.resolve_gate import _token_of

        assert _token_of({"raw": "SRT332-GM", "hint": "product"}) == "SRT332GM"


class TestDomainHintEnumGuardIsWiredIntoApply:
    """`contracts.coerce_domain_hint` (F3) exists but has no call site in this
    worktree - `turn/apply.py` must coerce an unknown `domain_hint` before it reaches
    `Plan.domains`, the same way `head/output_exchange.py`'s deleted `_post_process`
    used to at the parser-emission entry point."""

    def test_a_team_name_outside_the_domain_enum_does_not_reach_plan_domains(self) -> None:
        from app.services.chatbot.turn.apply import apply
        from app.services.chatbot.turn.state import Focus, Profile, State

        state = State(focus=Focus(), pending=None, profile=Profile())
        v = verdict(domain_hint="purchasing", entities=[entity("SRTWC8517")])

        _state2, plan = apply(state, v, build_policy())

        assert "purchasing" not in plan.domains, (
            f"'purchasing' is a TEAM name (SUGGESTED_TEAMS), not a domain the policy "
            f"knows about (POLICY_DOMAIN_ROWS names inventory/incoming/purchase_cost/"
            f"order/product_attachment/promotion) - F3's own incident "
            "(b5b19cec-dccc-4eda-b766-1aeb1362957b) is exactly this value emitted as "
            f"domain_hint; got plan.domains == {plan.domains!r}. contracts."
            "coerce_domain_hint exists but is called from nowhere in turn/apply.py."
        )

    def test_a_declared_domain_is_unchanged(self) -> None:
        """Guard, green today: a real domain must still reach Plan.domains."""
        from app.services.chatbot.turn.apply import apply
        from app.services.chatbot.turn.state import Focus, Profile, State

        state = State(focus=Focus(), pending=None, profile=Profile())
        v = verdict(domain_hint="incoming", entities=[entity("SRTWC8517")])

        _state2, plan = apply(state, v, build_policy())

        assert "incoming" in plan.domains, plan.domains
