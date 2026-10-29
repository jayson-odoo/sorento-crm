"""prompt synonyms: move the former PROMPT_SYNONYMS words from code into data

`lookup_lists.PROMPT_SYNONYMS` (the v63 prompt's category translations and file type words) is removed in
LOOKUP-EMBED-CENTRAL: row texts now come from data only (`product_categories.search_synonyms`, the
`attachment_type_alias` lookup set). The words must travel with the deploy and prod cannot run a script, so this
migration writes them. A category word is appended to `search_synonyms` of every ACTIVE category of that class
(class label, or the category's own name, case aside). A file type word becomes a keyword of that type's option in
the `attachment_type_alias` set (set and option created when missing); no attachment type is ever created. A word
already on the row is skipped, so a rerun adds nothing. The 10-minute `lookup_words_sync` task embeds the words.

Revision ID: lec_0004_prompt_synonyms
Revises: lec_0003_lookup_words_sync
"""
from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "lec_0004_prompt_synonyms"
down_revision = "lec_0003_lookup_words_sync"
branch_labels = None
depends_on = None

# The 11 former PROMPT_SYNONYMS entries: row label (case aside) -> extra words.
CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "water tap": ("paip air", "kepala paip", "水龙头"),
    "water closet": ("tandas", "mangkuk tandas", "马桶"),
    "kitchen sink": ("sinki dapur", "厨房水槽"),
}
FILE_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "photo": ("gambar", "foto", "image", "picture", "imej"),
    "image": ("imej", "gambar", "foto", "picture"),
    "video": ("videos",),
    "drawing": ("lukisan",),
    "technical drawing": ("lukisan teknikal", "lukisan", "cad", "blueprint"),
    "3d model": ("model 3d",),
    "installation guide": ("installation manual",),
    "certificate": ("sijil", "cert", "ikram"),
}
# A label that names a class under a shorter class label.
CLASS_ALIASES: dict[str, tuple[str, ...]] = {"water tap": ("water tap", "tap")}
ALIAS_SET_KEY = "attachment_type_alias"

log = logging.getLogger(__name__)


def _folded(value) -> str:
    return str(value or "").strip().casefold()


def _category_words(bind) -> None:
    cats = bind.execute(
        sa.text(
            "SELECT id, class_label, category_name, search_synonyms FROM product_categories "
            "WHERE is_active IS TRUE ORDER BY category_code"
        )
    ).fetchall()
    for cat in cats:
        current = cat.search_synonyms or []
        if isinstance(current, str):
            current = json.loads(current)
        merged = list(current)
        have = {_folded(w) for w in merged}
        for label, words in CATEGORY_WORDS.items():
            names = set(CLASS_ALIASES.get(label, (label,)))
            if _folded(cat.class_label) not in names and _folded(cat.category_name) != label:
                continue
            for word in words:
                if _folded(word) not in have:
                    merged.append(word)
                    have.add(_folded(word))
        if len(merged) != len(current):
            bind.execute(
                sa.text("UPDATE product_categories SET search_synonyms = CAST(:syn AS jsonb) WHERE id = :id"),
                {"syn": json.dumps(merged, ensure_ascii=False), "id": cat.id},
            )


def _file_type_words(bind) -> None:
    for label, words in FILE_TYPE_WORDS.items():
        atype = bind.execute(
            sa.text(
                "SELECT code, type_name FROM attachment_types "
                "WHERE lower(code) = :label OR lower(type_name) = :label LIMIT 1"
            ),
            {"label": label},
        ).first()
        if atype is None:
            # No such type here: nothing to attach the words to, and none is invented.
            log.info("lec_0004: no attachment type %r here; its words were skipped", label)
            continue
        option_id = bind.execute(
            sa.text(
                "SELECT o.id FROM lookup_options o JOIN lookup_sets s ON s.id = o.set_id "
                "WHERE s.set_key = :key AND lower(o.value) IN (:name, :code) LIMIT 1"
            ),
            {"key": ALIAS_SET_KEY, "name": _folded(atype.type_name), "code": _folded(atype.code)},
        ).scalar()
        if option_id is None:
            set_id = bind.execute(
                sa.text("SELECT id FROM lookup_sets WHERE set_key = :key LIMIT 1"), {"key": ALIAS_SET_KEY}
            ).scalar()
            if set_id is None:
                set_id = bind.execute(
                    sa.text(
                        "INSERT INTO lookup_sets (id, set_key, name, is_active) "
                        "VALUES (gen_random_uuid(), :key, 'Attachment type aliases', true) RETURNING id"
                    ),
                    {"key": ALIAS_SET_KEY},
                ).scalar()
            option_id = bind.execute(
                sa.text(
                    "INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active) "
                    "VALUES (gen_random_uuid(), :set_id, :name, :name, 0, true) RETURNING id"
                ),
                {"set_id": set_id, "name": atype.type_name},
            ).scalar()
        have = {
            _folded(k)
            for k in bind.execute(
                sa.text("SELECT keyword FROM lookup_option_keywords WHERE option_id = :id"), {"id": option_id}
            ).scalars()
        }
        for word in words:
            if _folded(word) in have:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO lookup_option_keywords (id, option_id, keyword) "
                    "VALUES (gen_random_uuid(), :id, :word)"
                ),
                {"id": option_id, "word": word},
            )
            have.add(_folded(word))


def upgrade() -> None:
    bind = op.get_bind()
    _category_words(bind)
    _file_type_words(bind)


def downgrade() -> None:
    # No-op: a moved word cannot be told apart from one an admin typed.
    pass
