"""S3 (PLAN-chatbot-media-into-turn.md): the `entities_only` lane - bare entities, no
domain, no focus, routed away from `casual`'s LLM clarifier and answered deterministically.

AC-1822 to AC-1832 (UAC section C). General fix (plan Q1): the arm serves TYPED bare
codes too, not only photo-sourced ones - most tests here type the codes directly, which
is both the cheapest way to prove the lane exists and the plan's own scope.

Every test is expected to fail today: `turn/apply.py::_lane` routes a domain-less
`business_query` straight to `"casual"` (`app/services/chatbot/turn/apply.py`, the
`message_type == "business_query" and not domains: return "casual"` line), which reaches
the stubbed LLM clarifier (`tests/chatbot/conftest.py::_stub_casual_llm`, autouse) - so
the right red reason is "the casual clarifier ran" / "lane != entities_only", never an
import error.

Reuses `test_outstanding_lane.py`'s real-engine harness (`_run_turn`, `_resolve_services`,
`_enable_business_lane`, `_session_of`) rather than a second copy of the business-lane
wiring - the same precedent `test_pass5_item2_...` and `test_pass4_item2_...` already
follow.

**Journey-runner note for the captain**: `tests/chatbot/journeys/*.json` on this branch is
NOT a pytest-collected suite - it is consumed by a separate live-console replay tool
(the file's own `"cold": true` / real `contact_respond_id` shape is a LIVE journey
recording, not a Postgres-fixture case). Per the brief's own fallback ("otherwise keep
them in `test_entities_only_arm.py` and say so"), J1-J4 (AC-1827/1828/1829/1830) are
written here as ordinary pytest tests instead of a new file under that directory.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod

from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded  # noqa: F401
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_outstanding_lane import (
    _capturing_mcp,
    _enable_business_lane,
    _resolve_services,
    _run_turn,
    _seed_contact,
    _session_of,
    _wire_business_services,
    ResolveGateServices,
)
from tests.chatbot.test_media_intake_turn import (
    IMAGE_RESULT,
    _image_envelope,
    _seed_media_limit,
    _seed_settings,
    _voice_envelope,
    media_pipeline,  # noqa: F401
)

PRODUCT_A_CODE = "SRTWT7445"
PRODUCT_A_UUID = "aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"
PRODUCT_B_CODE = "SRTWT7446"
PRODUCT_B_UUID = "aaaaaaaa-2222-2222-2222-aaaaaaaaaaaa"
UNPLACED_CODE = "MBF-9902-ZZT"

MATCHES = {
    PRODUCT_A_CODE: {"uuid": PRODUCT_A_UUID, "entity_type": "product", "canonical_code": PRODUCT_A_CODE},
    PRODUCT_B_CODE: {"uuid": PRODUCT_B_UUID, "entity_type": "product", "canonical_code": PRODUCT_B_CODE},
}


def _bare_entities_qf(*, placed: list[str], unplaced: list[str] | None = None) -> dict[str, Any]:
    """A parser verdict for "typed bare codes, no domain, no ask" - the shape the plan
    names as the gap (`_lane`'s casual fallthrough)."""
    entities = [
        {
            "raw": code,
            "hint": "product",
            "canonical_code": None,
            "current_message": True,
            "confident": True,
        }
        for code in [*placed, *(unplaced or [])]
    ]
    return _parser_output(domain_hint=None, intent_hint=None, entities=entities, asks=[])


def _focus_products(session_factory) -> list[dict[str, Any]]:
    sess = _session_of(session_factory)
    focus = sess.get("focus") or {}
    return focus.get("products") or []


class TestRoutesToEntitiesOnlyNotCasual:
    """AC-1822."""

    def test_bare_codes_do_not_reach_the_casual_clarifier(
        self, session_factory, seeded, monkeypatch, _stub_casual_llm
    ):
        qf = _bare_entities_qf(placed=[PRODUCT_A_CODE, PRODUCT_B_CODE])
        _run_turn(
            session_factory, monkeypatch, qf=qf, text_body=f"{PRODUCT_A_CODE}, {PRODUCT_B_CODE}",
            msg_id="ZZT-eo-1", matches=MATCHES,
        )
        assert not _stub_casual_llm, (
            f"the casual LLM clarifier ran {len(_stub_casual_llm)} time(s) - bare "
            "entities with no domain still fall through to the casual lane"
        )


class TestResolvesAndSettlesFocus:
    """AC-1823: placed rows land on focus.products WITH uuids; unplaced tokens do not."""

    def test_placed_tokens_carry_a_uuid_unplaced_do_not(self, session_factory, seeded, monkeypatch):
        qf = _bare_entities_qf(placed=[PRODUCT_A_CODE], unplaced=[UNPLACED_CODE])
        _run_turn(
            session_factory, monkeypatch, qf=qf, text_body=f"{PRODUCT_A_CODE}, {UNPLACED_CODE}",
            msg_id="ZZT-eo-2", matches=MATCHES,
        )
        products = _focus_products(session_factory)
        placed_row = next((p for p in products if p.get("raw") == PRODUCT_A_CODE), None)
        assert placed_row is not None, f"focus.products carries no row for {PRODUCT_A_CODE}: {products}"
        assert placed_row.get("uuid") == PRODUCT_A_UUID, (
            f"{PRODUCT_A_CODE} was not resolved onto focus.products - entities_only "
            f"never ran the resolver: {placed_row}"
        )
        unplaced_row = next((p for p in products if p.get("raw") == UNPLACED_CODE), None)
        assert unplaced_row is None or not unplaced_row.get("uuid")


class TestReplyWordingBySource:
    """AC-1824/AC-1825: the reply names the source (photo vs typed) with its own words."""

    def test_typed_source_reply_wording(self, session_factory, seeded, monkeypatch):
        qf = _bare_entities_qf(placed=[PRODUCT_A_CODE, PRODUCT_B_CODE], unplaced=[UNPLACED_CODE])
        result, _ = _run_turn(
            session_factory, monkeypatch, qf=qf,
            text_body=f"{PRODUCT_A_CODE} {PRODUCT_B_CODE} {UNPLACED_CODE}",
            msg_id="ZZT-eo-3", matches=MATCHES,
        )
        text = (result.reply or {}).get("text") or ""
        assert text.startswith(f"I have {PRODUCT_A_CODE} and {PRODUCT_B_CODE}."), text
        assert f"Couldn't find {UNPLACED_CODE}." in text, text
        assert text.rstrip().endswith("What would you like me to know?"), text

    def test_no_couldnt_find_line_when_everything_placed(self, session_factory, seeded, monkeypatch):
        qf = _bare_entities_qf(placed=[PRODUCT_A_CODE, PRODUCT_B_CODE])
        result, _ = _run_turn(
            session_factory, monkeypatch, qf=qf, text_body=f"{PRODUCT_A_CODE} {PRODUCT_B_CODE}",
            msg_id="ZZT-eo-4", matches=MATCHES,
        )
        text = (result.reply or {}).get("text") or ""
        assert "Couldn't find" not in text


class TestOpenQuestionStaysNull:
    """AC-1826.

    NOTE FOR THE CAPTAIN: the bare `open_question is None` / `domains == []` checks are
    ALSO true today (the `casual` lane the message currently falls into sets neither), so
    they are paired with a check on the reply TEXT itself - which today is literally the
    autouse `_stub_casual_llm` fixture's canned string - so the test still goes red for
    the right reason (wrong lane), not a vacuously-true session-shape assertion.
    """

    def test_open_question_and_domains_stay_empty(self, session_factory, seeded, monkeypatch):
        qf = _bare_entities_qf(placed=[PRODUCT_A_CODE, PRODUCT_B_CODE])
        result, _ = _run_turn(
            session_factory, monkeypatch, qf=qf, text_body=f"{PRODUCT_A_CODE} {PRODUCT_B_CODE}",
            msg_id="ZZT-eo-5", matches=MATCHES,
        )
        sess = _session_of(session_factory)
        assert sess.get("open_question") is None
        assert (sess.get("focus") or {}).get("domains") in (None, [])
        text = (result.reply or {}).get("text") or ""
        assert text != "ZZT stubbed casual reply.", (
            "the turn answered through the casual LLM clarifier stub, not the "
            "entities_only lane"
        )


class TestJourneyPhotoThenCheckStock:
    """AC-1827 (J1): photo-only turn, then "check stock" -> answers the placed codes,
    domains == ["inventory"], no re-ask for a product."""

    def test_photo_then_check_stock(
        self, session_factory, seeded, stub_access, media_pipeline, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(
            {**IMAGE_RESULT, "entities": [{"raw": PRODUCT_A_CODE}, {"raw": PRODUCT_B_CODE}]}
        )
        stub_access()

        # Step 1 has no preceding `_run_turn` call (unlike J2/J3/J4, whose photo step
        # rides the SAME `monkeypatch` a prior `_run_turn` call already wired) - so the
        # business-lane switches and the resolver seam are wired explicitly here,
        # exactly what `_run_turn` itself would do internally.
        _enable_business_lane(session_factory)
        call, _captured = _capturing_mcp()
        _wire_business_services(monkeypatch, resolve_services=_resolve_services(MATCHES), mcp_call=call)

        # Step 1: bare photo, no caption -> entities_only, no domain.
        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        photo_qf = _bare_entities_qf(placed=[PRODUCT_A_CODE, PRODUCT_B_CODE])
        with _patch.object(parser_mod, "parse", lambda config, user_block: photo_qf):
            with _patch.object(
                parser_mod,
                "resolve_config",
                lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
                    system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
                ),
            ):
                engine_mod.run_turn(_image_envelope(caption=None), session_factory=session_factory)

        products_after_photo = _focus_products(session_factory)
        assert any(p.get("raw") == PRODUCT_A_CODE and p.get("uuid") for p in products_after_photo), (
            "photo-only turn did not settle focus.products - J1 step 1 is not wired"
        )

        # Step 2: "check stock".
        stock_qf = _parser_output(domain_hint="master_products", intent_hint="check_product", entities=[])
        result, _ = _run_turn(
            session_factory, monkeypatch, qf=stock_qf, text_body="check stock",
            msg_id="ZZT-eo-j1-2", matches=MATCHES,
        )
        assert result.branch_kind != "clarify_menu", "the bot re-asked for a product instead of using focus"


class TestJourneyCheckStockThenPhoto:
    """AC-1828 (J2): "check stock" (needs-scope reply), then a photo -> answers directly,
    prefix "I read A and B from that photo."."""

    def test_check_stock_then_photo(
        self, session_factory, seeded, stub_access, media_pipeline, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(
            {**IMAGE_RESULT, "entities": [{"raw": PRODUCT_A_CODE}, {"raw": PRODUCT_B_CODE}]}
        )
        stub_access()

        stock_qf = _parser_output(domain_hint="master_products", intent_hint="check_product", entities=[])
        _run_turn(
            session_factory, monkeypatch, qf=stock_qf, text_body="check stock",
            msg_id="ZZT-eo-j2-1", matches=MATCHES,
        )

        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        photo_qf = _bare_entities_qf(placed=[PRODUCT_A_CODE, PRODUCT_B_CODE])
        with _patch.object(parser_mod, "parse", lambda config, user_block: photo_qf), _patch.object(
            parser_mod,
            "resolve_config",
            lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            ),
        ):
            result = engine_mod.run_turn(_image_envelope(caption=None), session_factory=session_factory)

        text = (result.reply or {}).get("text") or ""
        assert text.startswith(f"I read {PRODUCT_A_CODE} and {PRODUCT_B_CODE} from that photo."), text


class TestJourneyCaptionInOneTurn:
    """AC-1829 (J3): photo with caption "Check stock" -> one turn, stock answered."""

    def test_captioned_photo_answers_in_one_turn(
        self, session_factory, seeded, stub_access, media_pipeline, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="image")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result(
            {
                "rendered_text": f"Check stock: {PRODUCT_A_CODE}, {PRODUCT_B_CODE}",
                "entities": [{"raw": PRODUCT_A_CODE}, {"raw": PRODUCT_B_CODE}],
                "truncated": False,
                "needs_clarification": False,
            }
        )
        stub_access()

        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        stock_qf = _parser_output(
            domain_hint="master_products",
            intent_hint="check_product",
            entities=[
                {"raw": PRODUCT_A_CODE, "hint": "product", "canonical_code": None, "current_message": True, "confident": True},
                {"raw": PRODUCT_B_CODE, "hint": "product", "canonical_code": None, "current_message": True, "confident": True},
            ],
        )
        with _patch.object(parser_mod, "parse", lambda config, user_block: stock_qf), _patch.object(
            parser_mod,
            "resolve_config",
            lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            ),
        ):
            result = engine_mod.run_turn(_image_envelope(caption="Check stock"), session_factory=session_factory)

        assert result.branch_kind == "business_query", (
            f"expected the captioned photo to resolve straight to a business query, "
            f"got {result.branch_kind!r}"
        )
        text = (result.reply or {}).get("text") or ""
        assert text.startswith(f"I read {PRODUCT_A_CODE} and {PRODUCT_B_CODE} from that photo."), (
            f"the reply prefix is missing: {text!r}"
        )


class TestJourneyVoice:
    """AC-1830 (J4): voice "stock for SRTWB1455" -> stock answered, prefix "I heard: ..."."""

    def test_voice_stock_ask_answers_with_heard_prefix(
        self, session_factory, seeded, stub_access, media_pipeline, monkeypatch
    ):
        _seed_media_limit(session_factory, modality="voice")
        _seed_settings(session_factory, media_sync_wait_seconds=5)
        media_pipeline.set_result({"transcript": "stock for SRTWB1455"})
        stub_access()

        import app.services.chatbot.head.parser as parser_mod
        from unittest.mock import patch as _patch

        stock_qf = _parser_output(
            domain_hint="master_products",
            intent_hint="check_product",
            entities=[
                {"raw": "SRTWB1455", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}
            ],
        )
        with _patch.object(parser_mod, "parse", lambda config, user_block: stock_qf), _patch.object(
            parser_mod,
            "resolve_config",
            lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            ),
        ):
            result = engine_mod.run_turn(_voice_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text") or ""
        assert text.startswith("I heard: stock for SRTWB1455"), text


class TestPromotionFocusCarriesTheSameWay:
    """AC-1831: a photo with a promotion focus already set applies the codes to the
    CURRENT domain, not to stock.

    NOTE FOR THE CAPTAIN: this one is NOT independently red today with typed bare
    entities - the existing focus-carry rule (`apply.py:1440`, plan Evidence 6) already
    routes a bare-entity message to `business_query` under an EXISTING domain; the plan's
    own gap is only the empty-focus/no-domain case (AC-1822). Kept here as a regression
    guard for the media source once S2 lands, and to record the "already works" finding
    rather than silently assume it - it is a positive control, not a red test."""

    def test_existing_promotion_domain_wins(self, session_factory, seeded, monkeypatch):
        # Seed a prior turn that set focus.domains = ["promotion"].
        seed_qf = _parser_output(domain_hint="promotion", intent_hint="check_promotion", entities=[])
        _run_turn(
            session_factory, monkeypatch, qf=seed_qf, text_body="any promo running",
            msg_id="ZZT-eo-promo-1", matches=MATCHES,
        )
        sess = _session_of(session_factory)
        assert (sess.get("focus") or {}).get("domains") == ["promotion"], (
            "fixture assumption failed: the seed turn did not carry a promotion focus"
        )

        bare_qf = _bare_entities_qf(placed=[PRODUCT_A_CODE, PRODUCT_B_CODE])
        result, _ = _run_turn(
            session_factory, monkeypatch, qf=bare_qf, text_body=f"{PRODUCT_A_CODE} {PRODUCT_B_CODE}",
            msg_id="ZZT-eo-promo-2", matches=MATCHES,
        )
        assert result.branch_kind != "casual", (
            "a bare-entity message under an existing promotion focus still fell "
            "through to casual instead of carrying the focus's domain"
        )


class TestCaptionNamesANewDomain:
    """AC-1832: bare entities with a non-empty focus but a NEW domain word in the
    caption follow the caption's own domain (parser decides, unchanged) - a control
    case that should already work today via the existing carry rule, included so a
    future regression here is caught beside the new lane's tests."""

    def test_new_domain_word_overrides_the_carried_one(self, session_factory, seeded, monkeypatch):
        seed_qf = _parser_output(domain_hint="promotion", intent_hint="check_promotion", entities=[])
        _run_turn(
            session_factory, monkeypatch, qf=seed_qf, text_body="any promo running",
            msg_id="ZZT-eo-newdomain-1", matches=MATCHES,
        )
        stock_qf = _parser_output(
            domain_hint="master_products",
            intent_hint="check_product",
            entities=[
                {
                    "raw": PRODUCT_A_CODE, "hint": "product", "canonical_code": None,
                    "current_message": True, "confident": True,
                }
            ],
        )
        result, _ = _run_turn(
            session_factory, monkeypatch, qf=stock_qf, text_body=f"check stock {PRODUCT_A_CODE}",
            msg_id="ZZT-eo-newdomain-2", matches=MATCHES,
        )
        assert result.branch_kind == "business_query"
