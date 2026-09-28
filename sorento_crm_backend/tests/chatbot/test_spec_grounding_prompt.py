"""Fix round 8 on PR #833, F1: the parser is told the specification registry.

The prompt half of the grounding fix (the deterministic half is `test_spec_grounding.py`):
the policy blocks now close with one Specification line per registry key, rendered from
the registry the way the domain and entity-kind lines are rendered from their tables; the
parser's entity object carries `spec_key` / `spec_value`; `SPECIFICATION_ADDENDUM` teaches
the kind; and migration `spk_0001_specification_kind` adds the kind row and publishes the
result as a new version with the production label left where it was.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from tests._pg_fixture import blank_session

_MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "spk_0001_specification_kind.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("spk_0001_specification_kind", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_specification_block_is_rendered_from_the_registry():
    from app.services.chatbot_parser_prompt import render_prompt_blocks
    from app.services.product_spec_registry import seed_spec_registry

    with blank_session() as db:
        seed_spec_registry(db)
        _load_migration().insert_kind(db.connection())
        blocks = render_prompt_blocks(db)
    assert "Entity kind specification: resolver product_spec_registry." in blocks, blocks
    assert (
        'Specification finish ("Finish or colour"): choices Black = black (black, matt black, matte black);'
        " Gunmetal = gunmetal (gunmetal, gun metal);"
    ) in blocks, blocks
    assert 'Specification trap_type ("Trap"): choices S trap = s_trap (s trap, s-trap, floor outlet, floor waste); P trap = p_trap' in blocks
    assert 'Specification thickness ("Thickness"): a number in mm. Words: thickness, thick, gauge.' in blocks
    assert 'Specification is_rimless ("Rimless"): yes or no. Words: rimless, rim less, no rim.' in blocks
    assert "Product types (the category entity keeps these, never a specification):" in blocks
    # What the product IS and its brand are other kinds, never a specification line.
    for skipped in ("class", "brand", "product_type"):
        assert f"Specification {skipped} (" not in blocks, skipped
    # A choice listed twice in the registry is rendered once.
    mounting = next(line for line in blocks.splitlines() if line.startswith("Specification mounting "))
    assert mounting.count("Concealed = concealed") == 1, mounting


def test_a_word_staff_add_on_product_specifications_reaches_the_block():
    from app.models.product_spec import ProductSpecRegistry
    from app.services.chatbot_parser_prompt import render_prompt_blocks
    from app.services.product_spec_registry import seed_spec_registry

    with blank_session() as db:
        seed_spec_registry(db)
        row = db.query(ProductSpecRegistry).filter_by(spec_key="finish").one()
        row.user_synonyms = {"gunmetal": ["gm grey"]}
        db.flush()
        blocks = render_prompt_blocks(db)
    assert "Gunmetal = gunmetal (gunmetal, gun metal, gm grey);" in blocks, blocks


def test_the_prompt_teaches_the_kind_and_never_files_a_property_as_a_document():
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT, SPECIFICATION_ADDENDUM

    assert SEMANTIC_PARSER_PROMPT.endswith(SPECIFICATION_ADDENDUM)
    assert "entities[].spec_key" in SPECIFICATION_ADDENDUM
    assert "is NEVER an attachment_type" in SPECIFICATION_ADDENDUM
    assert '"gunmetal basin" -> category "basin" + specification' in SPECIFICATION_ADDENDUM


def test_the_strict_schema_requires_spec_key_and_spec_value_on_every_entity():
    from app.services.chatbot.head.parser import _build_json_schema

    item = _build_json_schema()["properties"]["entities"]["items"]
    assert {"spec_key", "spec_value"} <= set(item["properties"]), item
    assert {"spec_key", "spec_value"} <= set(item["required"]), item


def test_specification_is_an_entity_kind_of_the_policy():
    from app.services.chatbot.contracts import ENTITY_HINTS
    from app.services.chatbot.turn.policy_rows import DEFAULT_KIND_ROWS

    assert "specification" in ENTITY_HINTS
    assert any(row["kind"] == "specification" for row in DEFAULT_KIND_ROWS)


def test_the_migration_chains_onto_a_committed_revision_with_a_short_id():
    module = _load_migration()
    assert module.revision == "spk_0001_specification_kind" and len(module.revision) <= 32
    parents = [
        path
        for path in _MIGRATION.parent.glob("*.py")
        if f'\nrevision = "{module.down_revision}"' in path.read_text()
    ]
    assert len(parents) == 1


def test_the_migration_publishes_unlabelled_with_the_registry_block_and_is_idempotent():
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.product_spec_registry import seed_spec_registry

    module = _load_migration()
    with blank_session() as db:
        seed_spec_registry(db)
        db.flush()
        bind = db.connection()
        assert module.insert_kind(bind) is True
        assert module.insert_kind(bind) is False
        module.publish(bind)
        rows = db.query(AIPromptVersion).filter(AIPromptVersion.name == "chatbot_semantic_parser").all()
        carrying = [r for r in rows if (r.config_json or {}).get("spk_0001_specification_kind")]
        assert len(carrying) == 1
        template = carrying[0].template
        assert "SPECIFICATIONS: WHAT A PRODUCT IS DESCRIBED BY" in template
        assert 'Specification finish ("Finish or colour")' in template
        assert "Entity kind specification" in template
        labelled = {
            row.version_id for row in db.query(AIPromptLabel).filter(AIPromptLabel.name == "chatbot_semantic_parser")
        }
        assert carrying[0].id not in labelled
        module.publish(bind)
        assert db.query(AIPromptVersion).filter(AIPromptVersion.name == "chatbot_semantic_parser").count() == len(rows)


# --------------------------------------------------------------------------- #
# Fix round 9: a colour word on its own is a finish, misspelt or not             #
# --------------------------------------------------------------------------- #

_MIGRATION_9 = _MIGRATION.parent / "spk_0002_colour_word_spec.py"


def _load_migration_9():
    spec = importlib.util.spec_from_file_location("spk_0002_colour_word_spec", _MIGRATION_9)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_round9_the_prompt_says_a_misspelt_colour_word_is_a_finish():
    from app.services.chatbot_parser_prompt import SPECIFICATION_ADDENDUM

    assert '"any pnk water closet?" -> category "water closet"' in SPECIFICATION_ADDENDUM
    assert '+ specification {raw "pink", spec_key finish, spec_value null}' in SPECIFICATION_ADDENDUM
    assert "never an unknown product type" in SPECIFICATION_ADDENDUM


def test_round9_migration_chains_onto_spk_0001_with_a_short_id():
    module = _load_migration_9()
    assert module.revision == "spk_0002_colour_word_spec" and len(module.revision) <= 32
    assert module.down_revision == "spk_0001_specification_kind"


def test_round9_migration_publishes_the_new_words_unlabelled_once():
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.product_spec_registry import seed_spec_registry

    module = _load_migration_9()
    with blank_session() as db:
        seed_spec_registry(db)
        db.flush()
        bind = db.connection()
        module.publish(bind)
        rows = db.query(AIPromptVersion).filter(AIPromptVersion.name == "chatbot_semantic_parser").all()
        newest = max(rows, key=lambda r: r.version)
        assert '"any pnk water closet?"' in newest.template
        labelled = {
            row.version_id for row in db.query(AIPromptLabel).filter(AIPromptLabel.name == "chatbot_semantic_parser")
        }
        assert newest.id not in labelled
        module.publish(bind)
        _load_migration().publish(bind)
        assert db.query(AIPromptVersion).filter(AIPromptVersion.name == "chatbot_semantic_parser").count() == len(rows)
