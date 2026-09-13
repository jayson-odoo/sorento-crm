"""Spec visibility reaches the chatbot: `check_access`'s `hidden_spec_keys`, the
product-spec projection drop, the "not available" miss line and the turn trace.

UAC `documentation/plans/chatbot/spec-visibility-policy-acceptance-criteria.md`
AC-14..AC-17. PLAN `documentation/plans/chatbot/PLAN-spec-visibility-policy.md`
"Chatbot seam".

`TestCheckAccessHiddenSpecKeys` runs on the blank-schema `session_factory` fixture
(`tests/chatbot/conftest.py`), the same seam `tests/chatbot/test_contact_field_reveals.py`
uses. The projection tests call `fetch.output_structurer` directly (no DB), following
`tests/chatbot/test_product_spec_projection.py` and `test_restricted_fields.py`. The
trace test exercises the real `business.run_fetch`, following `test_trace_add.py`.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from app.services.chatbot import trace as trace_mod
from app.services.chatbot.head.access import check_access
from app.services.chatbot.lanes import business
from app.services.chatbot.lanes.business import fetch
from app.services.chatbot.lanes.business.services import FetchServices

CONTACT_ID = "ZZT-spec-visibility-1"
SPACE_ID = "364817"


def _seed_contact_in_segment(session_factory, *, segment_code: str, segment_name: str) -> str:
    """A respond contact tagged to one market segment, in a workspace so
    `check_access` can resolve it by `(respond_io_id, space_id)`."""
    db = session_factory()
    workspace_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, api_key_ciphertext) "
            "VALUES (:id, :space_id, 'x')"
        ),
        {"id": workspace_id, "space_id": SPACE_ID},
    )
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, workspace_id, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, :wid, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000098", "wid": workspace_id, "sv": json.dumps({})},
    )
    db.execute(
        text(
            "INSERT INTO market_segments (id, code, name, is_active) "
            "VALUES (gen_random_uuid(), :code, :name, true)"
        ),
        {"code": segment_code, "name": segment_name},
    )
    db.commit()
    contact_id = db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": CONTACT_ID}
    ).scalar()
    db.execute(
        text(
            "INSERT INTO respond_contact_market_segments (contact_id, segment_code) "
            "VALUES (:cid, :code)"
        ),
        {"cid": contact_id, "code": segment_code},
    )
    db.commit()
    return contact_id


def _seed_registry_keys(session_factory, keys: list[tuple[str, str]]) -> None:
    db = session_factory()
    for key, label in keys:
        db.execute(
            text(
                "INSERT INTO product_spec_registry (id, spec_key, label, data_type, is_active) "
                "VALUES (gen_random_uuid(), :key, :label, 'enum', true)"
            ),
            {"key": key, "label": label},
        )
    db.commit()


def _seed_default_policy(session_factory, *, excluded_spec_keys: list[str]) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO spec_visibility_policies (id, spec_keys, excluded_spec_keys) "
            "VALUES (gen_random_uuid(), NULL, :excluded)"
        ),
        {"excluded": excluded_spec_keys},
    )
    db.commit()


class TestCheckAccessHiddenSpecKeys:
    def test_check_access_carries_hidden_spec_keys_sorted(self, session_factory):
        """AC-14: a retail-segment contact inherits the default policy (retail
        carries no row of its own); `check_access` resolves it once per turn, the
        same seam `attributes` already uses."""
        _seed_registry_keys(
            session_factory,
            [
                ("thickness", "Thickness"),
                ("board_thickness", "Drainer board / countertop thickness"),
                ("material", "Material"),
            ],
        )
        _seed_default_policy(session_factory, excluded_spec_keys=["thickness", "board_thickness"])
        _seed_contact_in_segment(session_factory, segment_code="retail", segment_name="Retail")

        access = check_access(
            session_factory(),
            agent_code="general_enquiries",
            contact_id=CONTACT_ID,
            space_id=SPACE_ID,
        )

        assert access["hidden_spec_keys"] == ["board_thickness", "thickness"]


# --------------------------------------------------------------------- projection


def _product_envelope(specs: list[dict]) -> dict:
    fields = [
        {"key": "company_name", "label": "Company", "value": "Sorento"},
        {"label": "Product Code", "value": "SRTKS8825"},
        {"label": "Product Name", "value": "Kitchen Sink"},
        {"label": "List Price", "value": "MYR 199.00"},
        {"label": "Dimensions", "value": "500 x 360 x 350 mm"},
    ]
    for spec in specs:
        fields.append({"key": f"spec:{spec['key']}", "label": spec["label"], "value": spec["value"]})
    return {
        "result_type": "products",
        "intro": "Here are the matching products.",
        "items": [{"title": "SRTKS8825", "fields": fields}],
        "spec_vocabulary": {s["key"]: s["label"] for s in specs},
        "has_result": True,
    }


_SPECS = [
    {"key": "thickness", "label": "Thickness", "value": "0.8 mm"},
    {"key": "board_thickness", "label": "Drainer board / countertop thickness", "value": "18 mm"},
    {"key": "material", "label": "Material", "value": "Stainless steel"},
]


class TestProjectionDropsHiddenKeys:
    def test_projection_no_attribute_specs_line_omits_hidden_keys(self):
        """AC-15: no attribute asked - the compact Specs line names every
        populated key EXCEPT the hidden ones."""
        envelope = _product_envelope(_SPECS)
        ctx = {"semantic_input": {}, "access": {"hidden_spec_keys": ["thickness"]}}

        out = fetch.output_structurer(envelope, ctx)

        specs_field = next(f for f in out["answers"][0]["fields"] if f["label"] == "Specs")
        assert "Thickness" not in specs_field["value"]
        assert "Material: Stainless steel" in specs_field["value"]
        assert "Drainer board / countertop thickness: 18 mm" in specs_field["value"]

    def test_projection_hidden_key_removed_from_vocabulary_so_no_hit(self):
        """AC-15: a hidden key is removed from the matching vocabulary too, so an
        ask naming it directly cannot resolve to a hit - it falls to the
        `spec_hidden:` miss path instead (AC-16), never renders the field."""
        envelope = _product_envelope(_SPECS)
        ctx = {
            "semantic_input": {"requested_attributes": ["thickness"]},
            "access": {"hidden_spec_keys": ["thickness"]},
        }

        out = fetch.output_structurer(envelope, ctx)

        fields = out["answers"][0]["fields"]
        assert not any(f.get("label") == "Thickness" for f in fields)
        assert not any((f.get("key") or "").startswith("spec:thickness") for f in fields)

    def test_projection_visible_key_unchanged_when_other_key_hidden(self):
        """A word naming a visible key behaves exactly as today, whatever else on
        the product is hidden."""
        envelope = _product_envelope(_SPECS)
        ctx = {
            "semantic_input": {"requested_attributes": ["material"]},
            "access": {"hidden_spec_keys": ["thickness"]},
        }

        out = fetch.output_structurer(envelope, ctx)

        fields = out["answers"][0]["fields"]
        assert any(f["label"] == "Material" and f["value"] == "Stainless steel" for f in fields)
        assert "not available" not in out["response"]
        assert "not recorded" not in out["response"]


class TestHiddenKeyDirectAsk:
    def test_projection_direct_ask_on_hidden_key_renders_not_available_once_without_codes(self):
        """AC-16: one `spec_hidden:<key>` miss, "<label>: not available" - never
        "not recorded", and with no product code listed (the codes-capped
        `spec_miss:` shape stays for a genuinely absent key)."""
        envelope = _product_envelope(_SPECS)
        ctx = {
            "semantic_input": {"requested_attributes": ["thickness"]},
            "access": {"hidden_spec_keys": ["thickness"]},
        }

        out = fetch.output_structurer(envelope, ctx)

        assert "*Thickness:* not available" in out["response"]
        assert "not recorded" not in out["response"]
        assert "not available for" not in out["response"]
        assert out["response"].count("not available") == 1


class TestTurnTraceSpecVisibility:
    def test_turn_trace_has_spec_visibility_hidden_and_dropped(self):
        """AC-17: the turn trace gains a `spec_visibility` event beside `reveals`,
        naming the keys hidden for this contact and the keys the envelope
        actually carried and dropped."""
        t = trace_mod.TurnTrace()
        payload = {
            "_exit_kind": "continue",
            "gate": {
                "compatible_entities": [
                    {"uuid": str(uuid.uuid4()), "entity_type": "product", "code": "SRTKS8825"}
                ]
            },
            "ctx": {
                "parse": {"output": {"domain_hint": "master_products"}},
                "access": {"hidden_spec_keys": ["thickness"]},
            },
        }
        envelope = _product_envelope(_SPECS)
        services = FetchServices(mcp_call=lambda name, args: json.dumps(envelope))

        business.run_fetch(payload, services=services, dry_run=False, trace=t)

        events = [e for e in t.events if e["kind"] == "spec_visibility"]
        assert len(events) == 1
        assert events[0]["hidden"] == ["thickness"]
        assert "thickness" in events[0]["dropped"]
