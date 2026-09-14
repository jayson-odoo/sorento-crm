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
from tests._pg_fixture import unique_code

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


def _seed_spec_key(session_factory, key: str, label: str, *, is_active: bool = True) -> None:
    from app.models.product_spec import ProductSpecRegistry

    db = session_factory()
    db.add(
        ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key=key, label=label, data_type="enum", is_active=is_active
        )
    )
    db.commit()


def _set_spec_key_active(session_factory, key: str, is_active: bool) -> None:
    from app.models.product_spec import ProductSpecRegistry

    db = session_factory()
    db.query(ProductSpecRegistry).filter(ProductSpecRegistry.spec_key == key).update(
        {"is_active": is_active}
    )
    db.commit()


def _seed_contact(session_factory) -> str:
    from app.models.access import RespondContact

    db = session_factory()
    row = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
    )
    db.add(row)
    db.commit()
    return row.id


def _seed_policy_row(
    session_factory,
    *,
    contact_id: str | None = None,
    spec_keys: list[str] | None = None,
    excluded_spec_keys: list[str] | None = None,
) -> None:
    from app.models.access import SpecVisibilityPolicy

    db = session_factory()
    db.add(
        SpecVisibilityPolicy(
            id=str(uuid.uuid4()),
            contact_id=contact_id,
            segment_code=None,
            spec_keys=spec_keys,
            excluded_spec_keys=excluded_spec_keys,
        )
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

    def test_hidden_keys_keeps_a_key_that_was_deactivated_after_the_policy_was_stored(
        self, session_factory
    ):
        """Security finding B1 (moved from `tests/test_spec_visibility_policy.py`,
        AC-002 `tests/chatbot/test_import_boundary.py`: only files under
        `tests/chatbot/` and the module's own doorways may import
        `app.services.chatbot`).

        Deactivating a spec key AFTER a policy already named it must not
        un-hide it - `is_active` is a merchandising decision (should the
        parser still offer/derive this key), not "does this key still exist"
        for a stored policy's read.

        Exercises `check_access`'s real seam (`_hidden_spec_keys`, private but
        it IS the unit under test: the exact call that resolves
        `resolve_policy` and feeds its result into `hidden_keys` with
        whichever registry list it obtains) rather than reimplementing the
        registry read here, so this stays correct whatever helper backs it."""
        from app.services.chatbot.head.access import _hidden_spec_keys

        _seed_spec_key(session_factory, "thickness", "Thickness", is_active=True)
        _seed_spec_key(session_factory, "material", "Material", is_active=True)
        _seed_policy_row(session_factory, spec_keys=None, excluded_spec_keys=["thickness"])
        _set_spec_key_active(session_factory, "thickness", False)

        # Hide-these shape: the default row named `thickness` explicitly; an
        # unresolvable contact falls back to it (fail-closed).
        hidden = _hidden_spec_keys(
            session_factory(), contact_id="ZZT-NO-SUCH-CONTACT", space_id=None
        )
        assert "thickness" in hidden

        # Show-only shape: a contact override naming ONLY `material` must
        # still hide `thickness` - it was never in the show list, active or
        # not.
        contact_id = _seed_contact(session_factory)
        _seed_policy_row(
            session_factory, contact_id=contact_id, spec_keys=["material"], excluded_spec_keys=None
        )

        hidden_show_only = _hidden_spec_keys(
            session_factory(), contact_id=contact_id, space_id=None
        )
        assert "thickness" in hidden_show_only


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

    def test_projection_asked_word_shared_with_hidden_key_still_renders_the_visible_key(self):
        """Code review: "thickness" token-contains BOTH the hidden `thickness`
        key (exact match) and the visible `board_thickness` key's label
        ("Drainer board / countertop thickness" - "thickness" is one of its
        tokens), the same containment rule an ordinary hit uses. The hidden
        match must not short-circuit the visible one - the reply needs the
        board thickness VALUE and the "Thickness: not available" miss, not one
        instead of the other."""
        envelope = _product_envelope(_SPECS)
        ctx = {
            "semantic_input": {"requested_attributes": ["thickness"]},
            "access": {"hidden_spec_keys": ["thickness"]},
        }

        out = fetch.output_structurer(envelope, ctx)

        fields = out["answers"][0]["fields"]
        assert any(
            f["label"] == "Drainer board / countertop thickness" and f["value"] == "18 mm"
            for f in fields
        )
        assert "*Thickness:* not available" in out["response"]
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

    def test_turn_trace_dropped_lists_only_keys_actually_removed(self):
        """Code review: `dropped` must name keys the ENVELOPE actually carried
        and removed, not merely keys the vocabulary knows about - a product
        with no `spec:thickness` field (never populated on this product) has
        nothing to drop even though `thickness` sits in `spec_vocabulary` (the
        registry-wide map) and in the contact's hidden set."""
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
        # `material` is populated on this product; `thickness` is known to the
        # vocabulary (the registry carries it) but this particular product has
        # no `spec:thickness` field at all.
        envelope = _product_envelope(
            [{"key": "material", "label": "Material", "value": "Stainless steel"}]
        )
        envelope["spec_vocabulary"]["thickness"] = "Thickness"
        services = FetchServices(mcp_call=lambda name, args: json.dumps(envelope))

        business.run_fetch(payload, services=services, dry_run=False, trace=t)

        events = [e for e in t.events if e["kind"] == "spec_visibility"]
        assert len(events) == 1
        assert events[0]["hidden"] == ["thickness"]
        assert events[0]["dropped"] == []
