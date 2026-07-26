"""S1 gate — the status engine slice is provably ADDITIVE (AC-B6).

The original acceptance criterion asked for "a regression pass proving no existing
status vocabulary changed", which is proving a negative and unbounded. It was
rewritten into the two mechanical assertions below, which are the parts that can
actually fail:

1. Nothing reads the dropped ``workflow_stages`` table. Migration 308 drops it, so
   a reader reappearing would be a runtime error in production, not a test failure.
2. The engine does not touch any pre-existing hardcoded status column. Complaints,
   PR/SF, stock inquiries and orders keep their own vocabularies until they are
   migrated deliberately, entity by entity (ADR-0001).
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

# Files the engine owns. These may legitimately mention `statuses`, but must not
# reach into any domain table's own status column.
ENGINE_FILES = [
    APP / "models" / "status.py",
    APP / "status_engine" / "registry.py",
    APP / "status_engine" / "derived.py",
    APP / "services" / "status_service.py",
    APP / "api" / "v1" / "system" / "statuses.py",
    APP / "schemas" / "status.py",
]


def _python_sources():
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_nothing_reads_the_dropped_workflow_stages_table():
    """Migration 308 drops it. It held zero rows and its only references were its
    own model file and that file's export -- both removed in this slice."""
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8")
        # Skip the migration that drops (and whose downgrade recreates) it.
        if path.name == "308_status_engine.py":
            continue
        if re.search(r"\bworkflow_stages\b|\bWorkflowStage\b|\bWORKFLOW_DOMAIN_", text):
            offenders.append(str(path.relative_to(APP.parent)))
    assert not offenders, (
        "workflow_stages was dropped by migration 308, but these files still "
        f"reference it: {offenders}"
    )


def test_workflow_stage_model_file_is_gone():
    assert not (APP / "models" / "workflow_stage.py").exists()


def test_workflow_stage_is_not_exported_from_models():
    text = (APP / "models" / "__init__.py").read_text(encoding="utf-8")
    assert "WorkflowStage" not in text
    # ...and the engine's own models are exported in its place.
    assert "Status" in text and "StatusTransition" in text


def test_engine_does_not_touch_pre_existing_status_columns():
    """The engine must not read or write any domain table's own status column.

    Those vocabularies are hardcoded strings today and stay that way until each
    entity is migrated on purpose. An engine that quietly started writing
    ``complaints.status`` would change live behaviour in a slice that claims to be
    additive.
    """
    forbidden = [
        # (pattern, what it would mean)
        (r"\bComplaint\b", "complaints"),
        (r"\bPurchaseRequestHeader\b", "PR/SF"),
        (r"\bStockInquiry\b", "stock inquiries"),
        (r"\bOrderStatus\b", "order statuses"),
        (r"\bWorkflowSubmission\b", "workflow forms"),
        (r"\bConversationSLATracking\b", "SLA tracking"),
    ]
    offenders = []
    for path in ENGINE_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern, label in forbidden:
            if re.search(pattern, text):
                offenders.append(f"{path.name} references {label}")
    assert not offenders, (
        "The status engine must stay ignorant of domain tables; entities join it "
        f"via the registry only. Found: {offenders}"
    )


def test_engine_imports_no_domain_model():
    """Structural version of the check above: the engine's import graph must not
    pull in a domain model. The registry takes callables precisely so it never
    needs to."""
    offenders = []
    for path in ENGINE_FILES:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "app.models." in stripped and "app.models.status" not in stripped:
                offenders.append(f"{path.name}: {stripped}")
    assert not offenders, f"engine imports a domain model: {offenders}"


def test_new_tables_are_the_only_schema_additions_in_this_slice():
    """Migration 308 creates exactly the two engine tables and drops exactly the
    one dead table. A CREATE or ALTER on anything else here would mean the slice
    is not additive."""
    migration = (
        APP.parent / "alembic" / "versions" / "308_status_engine.py"
    ).read_text(encoding="utf-8")

    created = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", migration))
    dropped = set(re.findall(r"DROP TABLE IF EXISTS (\w+)", migration))

    # workflow_stages is recreated by downgrade(); statuses/status_transitions are
    # dropped by downgrade(). Both directions appear in the file.
    assert created == {"statuses", "status_transitions", "workflow_stages"}
    assert dropped == {"statuses", "status_transitions", "workflow_stages"}

    assert "ALTER TABLE" not in migration.upper(), (
        "an ALTER here would mean this slice modifies an existing table"
    )
