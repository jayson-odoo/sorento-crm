"""Migration 393 - splice page_text into a CUSTOMISED po_extractor / schedule_extractor
production version, rather than stomping it with the stock fallback.

`upgrade()` is imported by PATH and run inside `blank_session`'s rolled-back
transaction, per the project rule that a migration touching seed/prompt data is
tested against the CODE, not whatever the shared local database happens to hold
(see tests/test_migration_ed706a98ddc6_fulfilment_policy_settings.py).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import _po_extractor_fallback
from tests._pg_fixture import blank_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "393_po_schedule_extractor_page_text.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_393_po_schedule_extractor_page_text", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _seed_version(db, name: str, template: str, *, version: int = 1) -> AIPromptVersion:
    row = AIPromptVersion(
        name=name,
        version=version,
        type="text",
        template=template,
        variables=["page_no", "page_count"],
    )
    db.add(row)
    db.flush()
    return row


def _label_production(db, name: str, version: AIPromptVersion) -> AIPromptLabel:
    row = AIPromptLabel(name=name, label="production", version_id=version.id)
    db.add(row)
    db.flush()
    return row


def _production_version(db, name: str) -> AIPromptVersion:
    return (
        db.query(AIPromptVersion)
        .join(AIPromptLabel, AIPromptLabel.version_id == AIPromptVersion.id)
        .filter(AIPromptLabel.name == name, AIPromptLabel.label == "production")
        .one()
    )


def test_no_production_label_is_left_alone(db):
    """Nothing published for this key: `get_prompt` already serves the current,
    page_text-carrying hardcoded fallback, so the migration does nothing."""
    _run_upgrade(db)

    db.expire_all()
    assert db.query(AIPromptVersion).filter(AIPromptVersion.name == "po_extractor").count() == 0


def test_already_carrying_page_text_is_left_alone(db):
    version = _seed_version(db, "po_extractor", "already has {{page_text}} in it")
    _label_production(db, "po_extractor", version)

    _run_upgrade(db)

    db.expire_all()
    current = _production_version(db, "po_extractor")
    assert current.id == version.id  # untouched, no new version


def test_uncustomised_stock_fallback_is_replaced_outright(db):
    module = _migration_module()
    version = _seed_version(db, "po_extractor", module._OLD_PO_FALLBACK)
    _label_production(db, "po_extractor", version)

    _run_upgrade(db)

    db.expire_all()
    current = _production_version(db, "po_extractor")
    assert current.id != version.id
    assert current.version == 2
    assert current.template == _po_extractor_fallback()
    assert "page_text" in current.variables


def test_a_customised_template_keeps_its_edit_with_page_text_spliced_in(db):
    """The scenario the bug report is about: a captain's real customisation must
    survive, with the page_text block inserted at the same position the stock
    fallback puts it - right after the page-number intro, before the JSON shape."""
    module = _migration_module()
    custom = module._OLD_PO_FALLBACK.replace(
        "- Numbers: no thousands separators, a dot decimal.\n",
        "- Numbers: no thousands separators, a dot decimal.\n"
        "- CUSTOM: also flag any line naming an Impact Sanitaryware product.\n",
    )
    assert custom != module._OLD_PO_FALLBACK  # sanity: the fixture is actually customised
    version = _seed_version(db, "po_extractor", custom)
    _label_production(db, "po_extractor", version)

    _run_upgrade(db)

    db.expire_all()
    current = _production_version(db, "po_extractor")
    assert current.id != version.id
    assert "{{page_text}}" in current.template
    assert "- CUSTOM: also flag any line naming an Impact Sanitaryware product.\n" in current.template
    # Spliced at the same position as the stock fallback: right after the intro,
    # immediately before the JSON-shape instructions.
    assert (
        "{{page_count}}.\n\nThe page's own text layer" in current.template.replace("\n\n\n", "\n\n")
        or "{{page_count}}.\n\nThe page's own text layer" in current.template
    )
    assert current.template.index("{{page_text}}") < current.template.index(
        "Return STRICT JSON only"
    )
    assert "page_text" in current.variables


def test_schedule_extractor_customisation_also_splices(db):
    module = _migration_module()
    custom = module._OLD_SCHEDULE_FALLBACK.replace(
        "- Only the products whose columns appear on THIS page.\n",
        "- Only the products whose columns appear on THIS page.\n"
        "- CUSTOM: cross-check the column total against the PO quantity.\n",
    )
    version = _seed_version(db, "schedule_extractor", custom)
    _label_production(db, "schedule_extractor", version)

    _run_upgrade(db)

    db.expire_all()
    current = _production_version(db, "schedule_extractor")
    assert current.id != version.id
    assert "{{page_text}}" in current.template
    assert "- CUSTOM: cross-check the column total against the PO quantity.\n" in current.template
    assert current.template.index("{{page_text}}") < current.template.index("It is a MATRIX")


def test_running_the_migration_twice_is_idempotent(db):
    module = _migration_module()
    version = _seed_version(db, "po_extractor", module._OLD_PO_FALLBACK)
    _label_production(db, "po_extractor", version)

    _run_upgrade(db)
    db.expire_all()
    first = _production_version(db, "po_extractor")

    _run_upgrade(db)
    db.expire_all()
    second = _production_version(db, "po_extractor")

    assert first.id == second.id
    assert db.query(AIPromptVersion).filter(AIPromptVersion.name == "po_extractor").count() == 2


def test_a_rewritten_intro_cannot_be_safely_spliced_and_is_left_alone(db):
    """The prefix the splice anchors on (the page-number intro) is gone, so the
    migration must not guess at a position - it leaves the version untouched rather
    than corrupt a real customisation."""
    module = _migration_module()
    custom = "Completely rewritten prompt with no recognisable intro line.\n" + module._OLD_PO_FALLBACK.split(
        "Return STRICT JSON only", 1
    )[1]
    version = _seed_version(db, "po_extractor", custom)
    _label_production(db, "po_extractor", version)

    _run_upgrade(db)

    db.expire_all()
    current = _production_version(db, "po_extractor")
    assert current.id == version.id
    assert "{{page_text}}" not in current.template
