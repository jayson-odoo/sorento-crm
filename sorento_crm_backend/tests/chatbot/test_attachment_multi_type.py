"""ATTACHMENT-MULTI: several attachment types in one ask, and no snake_case in the reply.

Plan: `documentation/plans/chatbot/PLAN-attachment-multi-type-2oct.md`.
UAC: `documentation/plans/chatbot/attachment-multi-type-2oct-acceptance-criteria.md`.

Owner (2 Oct 2026): a contact cannot get a photo AND a second document type in one ask, and the
attachment picker shows the raw key `product_attachment`. Measured in the cloud sandbox before
any change, on the real resolver, gate, miss lane and composer (only the MCP client stubbed):

- exact product, "photo and technical specifications for SRTWC286-SH": the gate's
  document-class precision (`gate.py` ~1336) kept ONLY Technical Specifications, because
  the parser's "photo" does not equal the type name "Product Photos" - so the fetch would
  never ask for the photo at all;
- ambiguous product, same ask: every picker line was stamped with the LAST type alone, and
  "has" meant "has any typed file" - a photo-only product read "- has Technical Specifications";
- the miss sentence read "But no photo technical specifications matched these", and both
  the picker header and the found bullet printed raw keys (`product_attachment`,
  `attachment_type`).

Type names are the dev database's own (`attachment_types`, read-only crew query 2 Oct 2026):
"Product Photos" and "Technical Specifications" carry no `code`; product codes are the
SRTWC286 family the #750 suite already seeds. Every chain is seeded fresh on the blank schema.
"""
from __future__ import annotations

import re
from typing import Any

from app.models.base import set_company_scope
from app.services.chatbot.lanes.business import gate as gate_mod
from tests.chatbot import test_product_attachment_picker_stamp as base

PHOTOS = "Product Photos"
SPECS = "Technical Specifications"
SH = "SRTWC286-SH"
SH200 = "SRTWC286-SH-200"
SHP = "SRTWC286-SH-P"

#: A snake_case word as a customer would see it: two or more lowercase runs joined by "_".
_SNAKE_RE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")


def _parser(*, product_raw: str = base.TOKEN) -> dict[str, Any]:
    """"photo and technical specifications for <product>": the #750 parser literal with a
    second `attachment_type` entity, in the order the customer named them."""
    parser = base._parser(product_raw=product_raw)
    parser["entities"].append(
        {
            "raw": "technical specifications",
            "hint": "attachment_type",
            "canonical_code": "technical specifications",
            "confident": True,
            "current_message": True,
        }
    )
    parser["user_goal"] = f"trying to get a photo and technical specifications for {product_raw}"
    return parser


def _text(product_raw: str = base.TOKEN) -> str:
    return f"photo and technical specifications for {product_raw}"


def _seed(
    session_factory: Any,
    *,
    files: dict[str, list[str]],
    spec_code: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Products named in `files`, each holding one file per listed type name."""
    company_id = base._seed_company(session_factory, name="ZZT Attachment Multi Co")
    base._seed_contact_in(session_factory, [company_id])
    type_ids = {
        PHOTOS: base._seed_attachment_type(session_factory, PHOTOS),
        SPECS: base._seed_attachment_type(session_factory, SPECS),
    }
    if spec_code is not None:
        db = session_factory()
        from app.models.resources import AttachmentType

        db.query(AttachmentType).filter(AttachmentType.id == type_ids[SPECS]).update({"code": spec_code})
        db.commit()
    for code, types in files.items():
        product_id = base._seed_product(session_factory, company_id=company_id, code=code)
        for type_name in types:
            base._seed_file_for(
                session_factory,
                product_id=product_id,
                attachment_type_id=type_ids[type_name],
                company_id=company_id,
                filename=f"{code}-{type_name.split()[-1].lower()}.pdf",
            )
    return company_id, type_ids


def _lane(session_factory: Any, monkeypatch: Any, company_id: str, *, product_raw: str = base.TOKEN):
    db = session_factory()
    set_company_scope(db, frozenset({company_id}))
    calls: list[tuple[str, dict]] = []
    services = base._probe_services(db, monkeypatch, calls=calls)
    resolved, gate, offer = base._run_lane(
        db, services, parser=_parser(product_raw=product_raw), text=_text(product_raw)
    )
    return resolved, gate, offer, calls


def _type_uuids(gate: dict[str, Any]) -> set[str]:
    return {
        str(e.get("uuid"))
        for e in gate.get("compatible_entities") or []
        if e.get("entity_type") == "attachment_type"
    }


# --------------------------------------------------------------------------- #
# R1: both types stay in scope
# --------------------------------------------------------------------------- #


class TestBothTypesStayInScope:
    def test_an_exact_product_keeps_both_asked_types_in_the_gate_scope(
        self, session_factory, monkeypatch
    ) -> None:
        """The defect turn: the document-class precision dropped Product Photos because
        "photo" is not spelt "Product Photos", so the fetch could only ever send the specs."""
        company_id, type_ids = _seed(session_factory, files={SH: [PHOTOS, SPECS]})
        _resolved, gate, _offer, _calls = _lane(session_factory, monkeypatch, company_id, product_raw=SH)

        assert gate.get("gate_passed") is True, gate.get("gate_reason")
        assert _type_uuids(gate) == {type_ids[PHOTOS], type_ids[SPECS]}, (
            "both asked types must reach the fetch: "
            f"gate_reason={gate.get('gate_reason')!r}"
        )

    def test_one_word_that_matched_several_types_is_still_narrowed(self) -> None:
        """The case the precision rule exists for (container-status S1, exec 11661198): ONE
        customer word, "container status list", resolving to three document types, keeps only
        the one it named. Driven from a literal resolver payload: the rule reads nothing but
        the gate's own inputs."""
        types = [
            ("aaaaaaaa-0000-4000-8000-000000000001", "container_status", "Container Status"),
            ("aaaaaaaa-0000-4000-8000-000000000002", None, "Packing List"),
            ("aaaaaaaa-0000-4000-8000-000000000003", None, "Stock_List"),
        ]
        matches = [
            {
                "entity_type": "attachment_type",
                "canonical_code": code or name,
                "uuid": uuid,
                "match_tier": "word",
                "display": {"code": code, "type_name": name},
            }
            for uuid, code, name in types
        ]
        parser = {
            "entities": [
                {
                    "raw": "container status list",
                    "hint": "attachment_type",
                    "canonical_code": "container status",
                    "confident": True,
                    "current_message": True,
                }
            ],
            "match_mode": "or",
            "domain_hint": "resource_attachment",
            "intent_hint": "check_resource_attachment",
            "message_type": "business_query",
        }
        resolver = {
            "tokens": ["container status list"],
            "resolutions": [{"token": "container status list", "resolved": True, "matches": matches}],
        }
        gate = gate_mod.run_gate({}, parser=parser, resolver=resolver)

        assert _type_uuids(gate) == {types[0][0]}, gate.get("gate_reason")


# --------------------------------------------------------------------------- #
# R2: the picker stamps every asked type, per product
# --------------------------------------------------------------------------- #


class TestPickerStampsEveryType:
    def test_each_line_names_every_asked_type_as_has_or_no(self, session_factory, monkeypatch) -> None:
        company_id, _ = _seed(
            session_factory,
            files={SH: [PHOTOS], SH200: [SPECS], SHP: [PHOTOS, SPECS]},
        )
        _resolved, gate, offer, calls = _lane(session_factory, monkeypatch, company_id)

        assert gate.get("require_specific") is True, gate.get("gate_reason")
        assert calls and calls[0][0] == base.PROBE_TOOL, calls
        lines = base._picker_lines(offer.get("escalate_message"))
        assert lines[SH].endswith(f"- has {PHOTOS}, no {SPECS}"), lines[SH]
        assert lines[SH200].endswith(f"- no {PHOTOS}, has {SPECS}"), lines[SH200]
        assert lines[SHP].endswith(f"- has {PHOTOS}, has {SPECS}"), lines[SHP]

    def test_nothing_on_file_names_both_types_not_only_the_last(self, session_factory, monkeypatch) -> None:
        company_id, _ = _seed(session_factory, files={SH: [], SH200: []})
        _resolved, gate, offer, _calls = _lane(session_factory, monkeypatch, company_id)

        assert gate.get("require_specific") is True, gate.get("gate_reason")
        lines = base._picker_lines(offer.get("escalate_message"))
        for code in (SH, SH200):
            assert lines[code].endswith(f"- no {PHOTOS}, no {SPECS}"), lines[code]

    def test_numbering_and_order_stay_the_gates_own(self, session_factory, monkeypatch) -> None:
        company_id, _ = _seed(session_factory, files={SH: [PHOTOS], SH200: [SPECS]})
        _resolved, gate, offer, _calls = _lane(session_factory, monkeypatch, company_id)

        before = (gate.get("gate_clarification") or "").split("\n")
        after = (offer.get("escalate_message") or "").split("\n")
        assert len(after) == len(before), (before, after)
        for original, rendered in zip(before, after):
            assert rendered.startswith(original), (original, rendered)

    def test_the_stamp_noun_is_the_type_name_never_a_slug_code(self, session_factory, monkeypatch) -> None:
        """Twelve dev types carry a slug `code` (`combo_image`, `packing_list`, ...); the
        resolver's `canonical_code` is `code or type_name`, so a product type that gains one
        would otherwise stamp "- has tech_spec" at the customer."""
        company_id, _ = _seed(session_factory, files={SH: [PHOTOS, SPECS], SH200: []}, spec_code="tech_spec")
        _resolved, gate, offer, _calls = _lane(session_factory, monkeypatch, company_id)

        assert gate.get("require_specific") is True, gate.get("gate_reason")
        message = offer.get("escalate_message") or ""
        lines = base._picker_lines(message)
        assert lines[SH].endswith(f"- has {PHOTOS}, has {SPECS}"), lines[SH]
        assert "tech_spec" not in message, message


# --------------------------------------------------------------------------- #
# R4 / R5: the miss sentence and the found bullets
# --------------------------------------------------------------------------- #


class TestMissWording:
    def test_the_miss_sentence_joins_the_asked_types_with_or(self, session_factory, monkeypatch) -> None:
        company_id, _ = _seed(session_factory, files={SH: []})
        _resolved, gate, offer, _calls = _lane(session_factory, monkeypatch, company_id, product_raw=SH)

        message = offer.get("escalate_message") or ""
        assert gate.get("gate_passed") is True, gate.get("gate_reason")
        assert "But no photo or technical specifications matched these." in message, message

    def test_the_found_bullets_name_both_types_under_a_human_label(
        self, session_factory, monkeypatch
    ) -> None:
        company_id, _ = _seed(session_factory, files={SH: []})
        _resolved, _gate, offer, _calls = _lane(session_factory, monkeypatch, company_id, product_raw=SH)

        message = offer.get("escalate_message") or ""
        bullet = next((line for line in message.split("\n") if line.startswith("• attachment type: ")), "")
        names = set(bullet.removeprefix("• attachment type: ").split(", "))
        assert names == {PHOTOS, SPECS}, message


class TestNoSnakeCase:
    def test_the_attachment_picker_carries_no_snake_case_key(self, session_factory, monkeypatch) -> None:
        company_id, _ = _seed(session_factory, files={SH: [PHOTOS], SH200: []})
        _resolved, gate, offer, _calls = _lane(session_factory, monkeypatch, company_id)

        assert gate.get("require_specific") is True, gate.get("gate_reason")
        message = offer.get("escalate_message") or ""
        assert "Please choose:" in message, message
        assert not _SNAKE_RE.findall(message), message

    def test_the_exact_product_miss_carries_no_snake_case_key(self, session_factory, monkeypatch) -> None:
        company_id, _ = _seed(session_factory, files={SH: []})
        _resolved, _gate, offer, _calls = _lane(session_factory, monkeypatch, company_id, product_raw=SH)

        message = offer.get("escalate_message") or ""
        assert not _SNAKE_RE.findall(message), message


# --------------------------------------------------------------------------- #
# R3: a found product missing an asked type says so (owner Q2 (a))
# --------------------------------------------------------------------------- #


def _attachment_envelope(product_codes: list[str], rows: list[tuple[str, str]], asked: list[str]) -> dict:
    figures = [
        {
            "fields": [
                {"label": "Product Code", "value": code},
                {"label": "Attachment Type", "value": type_name},
                {"label": "File Name", "value": f"{code}.pdf"},
            ]
        }
        for code, type_name in rows
    ]
    return {
        "domain": "product_attachment",
        "denied": False,
        "entities": [*product_codes, *asked],
        "product_codes": list(product_codes),
        "attachment_types": list(asked),
        "figures": figures,
        "files": [{"url": f"https://example.test/{c}.pdf", "filename": f"{c}.pdf"} for c, _ in rows],
        "miss": [] if rows else list(product_codes),
        "has_result": bool(rows),
        "tool_has_result": bool(rows),
        "unresolved": [],
        "error": None,
        "lane_text": "I have attached the file(s) below." if rows else "No matching results found.",
    }


def _compose_text(env: dict) -> str:
    from app.services.chatbot.turn.compose import compose
    from app.services.chatbot.turn.policy import Policy
    from app.services.chatbot.turn.state import Focus, Profile, State

    from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row

    row = {**_domain_row("product_attachment", narrowing={"product": "must_narrow_one"}), "label": "product attachments"}
    policy = Policy.from_rows(domains=[row], kinds=[], tier_order=TIER_ORDER_FIXTURE)
    state = State(focus=Focus(), pending=None, profile=Profile(), turn_no=2)
    return compose([env], state, policy, ctx=None).text


class TestFoundAnswerNamesTheGap:
    def test_a_product_missing_one_asked_type_gets_the_files_it_has_and_one_line(self) -> None:
        text = _compose_text(_attachment_envelope([SH], [(SH, PHOTOS)], [PHOTOS, SPECS]))

        assert "I have attached the file(s) below." in text, text
        assert f"{SH} has no {SPECS}." in text, text
        assert "escalate" not in text.lower(), text

    def test_every_asked_type_on_file_adds_no_line(self) -> None:
        text = _compose_text(_attachment_envelope([SH], [(SH, PHOTOS), (SH, SPECS)], [PHOTOS, SPECS]))

        assert "has no" not in text, text

    def test_a_product_with_no_file_at_all_names_both_types_on_one_line(self) -> None:
        text = _compose_text(
            _attachment_envelope([SH, SH200], [(SH, PHOTOS), (SH, SPECS)], [PHOTOS, SPECS])
        )

        assert f"{SH200} has no {PHOTOS} or {SPECS}." in text, text
        assert f"{SH} has no" not in text, text

    def test_a_slug_type_is_never_named_as_a_gap(self) -> None:
        text = _compose_text(_attachment_envelope([SH], [(SH, PHOTOS)], [PHOTOS, "tech_spec"]))

        assert "tech_spec" not in text, text
