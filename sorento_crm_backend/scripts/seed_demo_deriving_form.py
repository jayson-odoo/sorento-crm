"""Seed a demo form whose header status is DERIVED from its lines (F1a).

Exists because F1a has no builder UI yet (that is F3), so there is otherwise no way to
see line decisions move a header. Creates one published definition with a repeater, turns
derivation on, and files one submission with three lines.

Idempotent: re-running reuses the definition by code and files a fresh submission, so it
can be used to reset the demo.

Everything it creates is prefixed `ZZTDEMO` so it is easy to find and delete. It writes to
whatever DATABASE_URL points at, which locally is a COPY of production, so the prefix is
the only thing separating this from real data.

    venv/bin/python scripts/seed_demo_deriving_form.py

The derived pair is (`draft`, `submitted`) and that choice is forced, not arbitrary:
`assert_derivation_config` requires the open key to be the graph's initial rung, and the
resolved key not to be terminal. `approved` and `rejected` are terminal, so `submitted` is
the only legal resolved rung in the default graph. It also makes the asymmetry visible: a
human cannot move the header INTO the pair, but can move it out of `submitted` to
`approved`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models.workflow_forms import WorkflowFormDefinition  # noqa: E402
from app.services.workflow_forms_service import WorkflowFormsService  # noqa: E402

CODE = "ZZTDEMO_EXCHANGE"
ACTOR = "a4b15bc3-5f65-4ff3-aed8-785575a59ce3"  # EXTERNAL_API_KEY_ACT_AS_USER_ID

OPEN_KEY = "draft"
RESOLVED_KEY = "submitted"

DOCUMENT = {
    "schemaVersion": 1,
    "pages": [
        {
            "id": "p1",
            "title": "Exchange request",
            "sections": [
                {
                    "id": "s1",
                    "title": "Dealer",
                    "fields": [
                        {
                            "id": "f_dealer",
                            "type": "text",
                            "key": "dealer_name",
                            "label": "Dealer name",
                            "required": True,
                        },
                        {
                            "id": "f_invoice",
                            "type": "text",
                            "key": "invoice_no",
                            "label": "Invoice number",
                        },
                    ],
                },
                {
                    "id": "s2",
                    "title": "Items to return",
                    "fields": [
                        {
                            "id": "f_items",
                            "type": "repeater",
                            "key": "items",
                            "label": "Items",
                            "repeater": {
                                "fields": [
                                    {"id": "sf_sku", "type": "text", "key": "sku", "label": "SKU"},
                                    {"id": "sf_qty", "type": "number", "key": "qty", "label": "Qty"},
                                    {
                                        "id": "sf_reason",
                                        "type": "text",
                                        "key": "reason",
                                        "label": "Reason",
                                    },
                                ]
                            },
                        }
                    ],
                },
            ],
        }
    ],
}

LINES = [
    {"line_group_id": "items", "sort_order": 0, "row_data": {"sku": "ZZTDEMO-A1", "qty": 2, "reason": "Cracked on arrival"}},
    {"line_group_id": "items", "sort_order": 1, "row_data": {"sku": "ZZTDEMO-B2", "qty": 1, "reason": "Wrong colour"}},
    {"line_group_id": "items", "sort_order": 2, "row_data": {"sku": "ZZTDEMO-C3", "qty": 5, "reason": "Over-ordered"}},
]


def main() -> int:
    db = SessionLocal()
    try:
        svc = WorkflowFormsService(db)

        existing = (
            db.query(WorkflowFormDefinition)
            .filter(WorkflowFormDefinition.code == CODE)
            .first()
        )
        if existing is None:
            definition = svc.create_definition(
                CODE, "ZZTDEMO Dealer exchange request", "Demo form for F1a line derivation", ACTOR
            )
            print(f"created definition {definition.id}")
        else:
            definition = existing
            print(f"reusing definition {definition.id}")

        # Draft document, then publish. Publishing runs the F0 gate, so a bad document
        # fails here rather than at submit time.
        svc.update_definition(str(definition.id), None, None, True, DOCUMENT)
        version = svc.publish_definition(str(definition.id), ACTOR)
        print(f"published version {version.id} (v{version.version_number})")

        # Derivation on. Validated at save: open must be the initial rung, resolved must
        # not be terminal.
        svc.update_definition(
            str(definition.id),
            None,
            None,
            None,
            None,
            derives_status_from_lines=True,
            derived_open_status_key=OPEN_KEY,
            derived_resolved_status_key=RESOLVED_KEY,
        )
        print(f"derivation ON: {OPEN_KEY} <-> {RESOLVED_KEY}")

        submission = svc.create_submission(
            str(definition.id),
            {"dealer_name": "ZZTDEMO Northern Traders", "invoice_no": "ZZTDEMO-INV-4471"},
            LINES,
            ACTOR,
        )
        db.commit()

        db.refresh(submission)
        print(f"\nsubmission {submission.id}")
        print(f"  header status: {submission.status_key}")
        for line in sorted(submission.lines, key=lambda ln: ln.sort_order or 0):
            print(
                f"  line {line.id}  {line.row_data.get('sku'):<14} "
                f"status={line.status_key}  disposition={line.disposition}"
            )

        print("\nDrive it (needs X-API-Key or a session):")
        print(f"  GET  /api/v1/workflow-forms/submissions/{submission.id}")
        print("  GET  /api/v1/workflow-forms/lines/{line_id}/allowed-transitions")
        print("  POST /api/v1/workflow-forms/lines/{line_id}/transition   {\"to_status_id\": \"...\"}")
        print("  PATCH /api/v1/workflow-forms/lines/{line_id}/disposition {\"disposition\": \"repair\"}")
        print("  GET  /api/v1/workflow-forms/line-dispositions")
        print(
            "\nDecide EVERY line and the header derives to "
            f"'{RESOLVED_KEY}'. Add a line back, or reopen one, and it returns to "
            f"'{OPEN_KEY}'. A manual move INTO either rung is refused; out of "
            f"'{RESOLVED_KEY}' to 'approved' is allowed."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
