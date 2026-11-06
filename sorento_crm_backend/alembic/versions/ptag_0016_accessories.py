"""Accessories included: the library, the product and combo lists, and the free-text move.

PRICETAG-ACCESSORIES (owner rulings 6 Nov ~10:00, plan
documentation/plans/dealer-kit/PLAN-pricetag-accessories-06nov.md):

1. `accessories` (company scoped; name unique per company ignoring case), `product_accessories`
   and `product_combo_accessories` (ordered lists, independent of each other).
2. The `accessory_image` attachment type, seeded by code. Pictures are stored with
   `entity_type = 'general'`, so the attachments CHECK is not rebuilt.
3. `move_free_text`: every non-blank `product_combos.free_items` and
   `price_tag_request_lines.included_accessories` is split (line breaks, commas, " + "),
   de-duplicated by name ignoring case into the library, and listed in written order: combo
   text on that combo; line text on the line's combo when it has one, else on the line's product;
   never over a list that already exists (a NOTICE names what was left). Old columns stay.

Every statement is idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, skip a list that
exists), so the same SQL is safe on a database that already holds it. Additive only.

Revision ID: ptag_0016_accessories
Revises: dkfi_0001_spec_value_icons
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ptag_0016_accessories"
down_revision = "dkfi_0001_spec_value_icons"
branch_labels = None
depends_on = None

#: Card Q-M1 (a): one item per line, per comma, and per " + " (a plus with a space either side).
SPLIT_PATTERN = r"\s*(?:\n|,|\s\+\s)\s*"

DDL = [
    """
    CREATE TABLE IF NOT EXISTS accessories (
        id UUID PRIMARY KEY,
        company_id UUID REFERENCES companies(id),
        name VARCHAR(100) NOT NULL,
        spec VARCHAR(200),
        image_attachment_id UUID REFERENCES attachments(id) ON DELETE SET NULL,
        created_by UUID,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_accessories_company_id ON accessories (company_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_accessories_company_lower_name "
    "ON accessories (company_id, lower(name))",
    """
    CREATE TABLE IF NOT EXISTS product_accessories (
        id UUID PRIMARY KEY,
        product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        accessory_id UUID NOT NULL REFERENCES accessories(id) ON DELETE RESTRICT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        CONSTRAINT uq_product_accessories_pair UNIQUE (product_id, accessory_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_product_accessories_product_id ON product_accessories (product_id)",
    "CREATE INDEX IF NOT EXISTS ix_product_accessories_accessory_id "
    "ON product_accessories (accessory_id)",
    """
    CREATE TABLE IF NOT EXISTS product_combo_accessories (
        id UUID PRIMARY KEY,
        combo_id UUID NOT NULL REFERENCES product_combos(id) ON DELETE CASCADE,
        accessory_id UUID NOT NULL REFERENCES accessories(id) ON DELETE RESTRICT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        CONSTRAINT uq_product_combo_accessories_pair UNIQUE (combo_id, accessory_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_product_combo_accessories_combo_id "
    "ON product_combo_accessories (combo_id)",
    "CREATE INDEX IF NOT EXISTS ix_product_combo_accessories_accessory_id "
    "ON product_combo_accessories (accessory_id)",
    "INSERT INTO attachment_types "
    "(id, code, type_name, allowed_extensions, max_file_size_mb, created_at) "
    "SELECT gen_random_uuid(), 'accessory_image', 'Accessory Image', "
    "'jpg,jpeg,png,webp', 10, now() AT TIME ZONE 'utc' "
    "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = 'accessory_image')",
]

MOVE_FREE_TEXT_SQL = (
    r"""
DO $accessories$
DECLARE
    r record;
    piece text;
    pos integer;
    acc uuid;
    to_combo uuid;
    to_product uuid;
BEGIN
    -- Combo "Free items" -> that combo's list, unless it already has one.
    FOR r IN
        SELECT c.id AS combo_id, p.company_id, c.free_items AS txt
        FROM product_combos c
        JOIN products p ON p.id = c.host_product_id
        WHERE coalesce(btrim(c.free_items), '') <> ''
          AND NOT EXISTS (SELECT 1 FROM product_combo_accessories x WHERE x.combo_id = c.id)
        ORDER BY c.created_at, c.id
    LOOP
        pos := 0;
        FOR piece IN
            SELECT left(btrim(t), 100) FROM regexp_split_to_table(r.txt, '"""
    + SPLIT_PATTERN
    + r"""') AS t
            WHERE btrim(t) <> ''
        LOOP
            SELECT a.id INTO acc FROM accessories a
            WHERE a.company_id IS NOT DISTINCT FROM r.company_id AND lower(a.name) = lower(piece)
            LIMIT 1;
            IF acc IS NULL THEN
                acc := gen_random_uuid();
                INSERT INTO accessories (id, company_id, name) VALUES (acc, r.company_id, piece);
            END IF;
            INSERT INTO product_combo_accessories (id, combo_id, accessory_id, sort_order)
            VALUES (gen_random_uuid(), r.combo_id, acc, pos)
            ON CONFLICT (combo_id, accessory_id) DO NOTHING;
            pos := pos + 1;
        END LOOP;
    END LOOP;

    -- Request-line text -> the line's combo list when it has a combo, else its product's list;
    -- never over a list that exists.
    FOR r IN
        SELECT l.id AS line_id, l.combo_id, l.product_id, p.company_id,
               l.included_accessories AS txt
        FROM price_tag_request_lines l
        JOIN products p ON p.id = l.product_id
        WHERE coalesce(btrim(l.included_accessories), '') <> ''
        ORDER BY l.created_at, l.id
    LOOP
        to_combo := NULL;
        to_product := NULL;
        IF r.combo_id IS NOT NULL THEN
            IF EXISTS (SELECT 1 FROM product_combo_accessories x WHERE x.combo_id = r.combo_id) THEN
                RAISE NOTICE 'accessories: line % text "%" not moved, its combo already has a list',
                    r.line_id, r.txt;
                CONTINUE;
            END IF;
            to_combo := r.combo_id;
        ELSE
            IF EXISTS (SELECT 1 FROM product_accessories x WHERE x.product_id = r.product_id) THEN
                RAISE NOTICE 'accessories: line % text "%" not moved, its product already has a list',
                    r.line_id, r.txt;
                CONTINUE;
            END IF;
            to_product := r.product_id;
        END IF;
        pos := 0;
        FOR piece IN
            SELECT left(btrim(t), 100) FROM regexp_split_to_table(r.txt, '"""
    + SPLIT_PATTERN
    + r"""') AS t
            WHERE btrim(t) <> ''
        LOOP
            SELECT a.id INTO acc FROM accessories a
            WHERE a.company_id IS NOT DISTINCT FROM r.company_id AND lower(a.name) = lower(piece)
            LIMIT 1;
            IF acc IS NULL THEN
                acc := gen_random_uuid();
                INSERT INTO accessories (id, company_id, name) VALUES (acc, r.company_id, piece);
            END IF;
            IF to_combo IS NOT NULL THEN
                INSERT INTO product_combo_accessories (id, combo_id, accessory_id, sort_order)
                VALUES (gen_random_uuid(), to_combo, acc, pos)
                ON CONFLICT (combo_id, accessory_id) DO NOTHING;
            ELSE
                INSERT INTO product_accessories (id, product_id, accessory_id, sort_order)
                VALUES (gen_random_uuid(), to_product, acc, pos)
                ON CONFLICT (product_id, accessory_id) DO NOTHING;
            END IF;
            pos := pos + 1;
        END LOOP;
    END LOOP;
END
$accessories$;
"""
)


def create_schema(bind) -> None:
    for statement in DDL:
        bind.execute(sa.text(statement))


def move_free_text(bind) -> None:
    # exec_driver_sql: the DO body holds `:` and `%` that bound-parameter parsing would mangle.
    bind.exec_driver_sql(MOVE_FREE_TEXT_SQL.replace("%", "%%"))


def upgrade() -> None:
    bind = op.get_bind()
    create_schema(bind)
    move_free_text(bind)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP TABLE IF EXISTS product_combo_accessories"))
    bind.execute(sa.text("DROP TABLE IF EXISTS product_accessories"))
    bind.execute(sa.text("DROP TABLE IF EXISTS accessories"))
