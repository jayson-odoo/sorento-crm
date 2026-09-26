"""Line-level promotion and manual price (PLAN-price-tag-line-promo-combo-subject.md D1, S6).

A request-level promotion breaks the moment two lines sit on two promotions
(owner ruling): `promotion_id` and `manual_sell_price` move from
`price_tag_requests` onto `price_tag_request_lines`. The header keeps only
`price_mode`.

Steps:

1. Add the two line columns.
2. Backfill every line's `promotion_id` from its request's header value
   (AC-S6-2) - no line loses its promotion.
3. Drop the header column (and its index).
4. D6/AC-S8-5: split every existing OPEN tag (a line with an unresolved
   choice group that still carries exactly one tag with `choices = {}`) into
   one tag per candidate combination, the same builder
   `PriceTagRequestService._add_line_tags` uses at submit from this revision
   onward - so no "Open" tag survives into the world where the designer never
   splits one by hand.

Downgrade restores the header column from the FIRST line (by `sort_order`)
that carries a promotion, per request, and drops the line columns. The
auto-split from step 4 is left as it is - a split tag is valid data either
way, and un-splitting it would throw away a design choice as real as the
tags it started with.

Revision ID: ptag_0011_line_promo
Revises: ptag_0010_badge_textcolor
Create Date: 2026-09-16
"""
from __future__ import annotations

import copy
import itertools
import json
import logging
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

logger = logging.getLogger("alembic.runtime.migration")

revision = "ptag_0011_line_promo"
down_revision = "ptag_0010_badge_textcolor"
branch_labels = None
depends_on = None


def _split_open_tags(conn) -> None:
    """D6/AC-S8-5: mint one tag per candidate combination for every line an
    unresolved choice group is still sitting on, straight-line style (no
    Split / Pick one) - the same builder the request service now runs at
    every save.

    Scoped to a line with EXACTLY one existing tag whose `choices` is still
    `{}` (or absent): that is what an open line looked like before this
    revision. A line already split by hand (Split / Pick one, pre-D6) has
    more than one tag or a non-empty `choices` map and is left untouched -
    it is not "open", it already answered.

    R3 (security H2 / reviewer B3): the FIRST candidate combination UPDATES
    the existing tag row rather than deleting it - a review comment
    (`price_tag_review_comments.tag_id`) or a saved draft placement anchored
    to it must not go dangling just because the migration is what answered
    the group, not a click. The N-1 siblings are freshly inserted, same as
    before, and `_copy_placements_in_draft` gives each one a copy of the
    original tile's geometry, porting the SQL of the retired hand-driven
    Split's own helper of the same name (`PriceTagRequestService`, pre-D6) -
    a migration has no ORM session to share it through, so it is ported
    rather than imported.

    R14: `groups_by_line` is built from a query ordered `line_id, sort_order`
    - the SAME convention `line.parts`' relationship `order_by` gives the
    live service builder (`_add_line_tags`), so which open group is the
    outer loop of `itertools.product` (and therefore which candidate lands
    on which tag) agrees between a request split at migration time and one
    split by a save from this revision onward.
    """
    open_parts = conn.execute(
        sa.text(
            "SELECT line_id, role, candidates FROM price_tag_request_line_parts "
            "WHERE product_id IS NULL AND jsonb_array_length(candidates) > 0 "
            "ORDER BY line_id, sort_order"
        )
    ).all()
    if not open_parts:
        return

    groups_by_line: dict[str, list[tuple[str, list[str]]]] = {}
    for row in open_parts:
        mapping = row._mapping
        groups_by_line.setdefault(str(mapping["line_id"]), []).append(
            (mapping["role"] or "", [str(c) for c in (mapping["candidates"] or [])])
        )

    split_count = 0
    for line_id, groups in groups_by_line.items():
        tags = conn.execute(
            sa.text(
                "SELECT id, sort_order, quantity, choices, marketing_price_override, "
                "marketing_override_reason FROM price_tag_request_tags "
                "WHERE line_id = :line_id ORDER BY sort_order"
            ),
            {"line_id": line_id},
        ).all()
        if len(tags) != 1:
            continue
        tag = tags[0]._mapping
        if tag["choices"]:
            continue

        roles = [role for role, _ in groups]
        combos = list(itertools.product(*[candidates for _, candidates in groups]))
        if not combos:
            continue

        original_tag_id = str(tag["id"])
        new_tag_ids: list[str] = []
        for index, combo in enumerate(combos):
            choices = dict(zip(roles, combo))
            if index == 0:
                # The tag that was already there resolves to combination 0
                # and KEEPS ITS ID - not deleted and replaced.
                conn.execute(
                    sa.text(
                        "UPDATE price_tag_request_tags "
                        "SET choices = CAST(:choices AS jsonb) WHERE id = :id"
                    ),
                    {"id": original_tag_id, "choices": json.dumps(choices)},
                )
                continue
            new_id = str(uuid.uuid4())
            new_tag_ids.append(new_id)
            conn.execute(
                sa.text(
                    "INSERT INTO price_tag_request_tags "
                    "(id, line_id, sort_order, quantity, choices, "
                    " marketing_price_override, marketing_override_reason) "
                    "VALUES (:id, :line_id, :sort_order, :quantity, CAST(:choices AS jsonb), "
                    "        :override, :reason)"
                ),
                {
                    "id": new_id,
                    "line_id": line_id,
                    "sort_order": index,
                    "quantity": tag["quantity"],
                    "choices": json.dumps(choices),
                    "override": tag["marketing_price_override"],
                    "reason": tag["marketing_override_reason"],
                },
            )
        if new_tag_ids:
            _copy_placements_in_draft(conn, line_id, original_tag_id, new_tag_ids)
        split_count += 1

    if split_count:
        logger.info("ptag_0011: auto-split %s pre-existing open line(s)", split_count)


def _dealer_kit_schema(conn) -> str:
    """Where `page` actually is: literally `dealer_kit` outside a test, the
    scratch schema's own `..._dealer_kit` sibling under `blank_session`'s
    naming convention (`tests/_pg_fixture.py`) when testing.

    Read at runtime rather than hardcoded, the same reasoning
    `354_projects_schema_move.py`'s own `_source_schema()` gives for
    `current_schema()`: `app.models.dealer_kit.Page` carries
    `{"schema": "dealer_kit"}`, never `public` where every price_tag_* table
    this migration otherwise touches lives, and a Core construct built with
    a HARDCODED `schema="dealer_kit"` compiles to that literal name
    regardless of the connection's `schema_translate_map` (measured: the
    docs describe Core constructs as translated automatically, but that
    substitution did not fire through `Operations.context`'s connection in
    this alembic/SQLAlchemy combination, and the query silently read the
    REAL production `dealer_kit.page` from inside the test's own scratch
    session - the one bug this whole function exists to rule out). Resolved
    by asking Postgres directly instead: `current_schema()` is the SAME
    per-test default schema `354`'s own helper reads (`{name}` under test,
    `public` for real), and blank_session's naming convention suffixes that
    default with `_dealer_kit` for the module schema - if that suffixed name
    exists, we are under test and it is the right one; otherwise the literal
    `dealer_kit` is.
    """
    default_schema = conn.execute(sa.text("SELECT current_schema()")).scalar()
    candidate = f"{default_schema}_dealer_kit" if default_schema else None
    exists = (
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"
            ),
            {"s": candidate},
        ).scalar()
        if candidate
        else None
    )
    return candidate if exists else "dealer_kit"


def _copy_placements_in_draft(
    conn, line_id: str, source_tag_id: str, new_tag_ids: list[str]
) -> None:
    """Give every new sibling the split tag's own geometry (R3/H2).

    Ported from the retired `PriceTagRequestService._copy_placements_in_draft`
    (pre-D6 hand-driven Split): the copies keep their own `-cN` suffix, which
    is how `tagsFromDoc` tells copy 0 (the master, whose layers are the
    design) from the rest.
    """
    page = sa.table(
        "page",
        sa.column("id"),
        sa.column("request_id"),
        sa.column("kind"),
        sa.column("draft_doc", postgresql.JSONB),
        schema=_dealer_kit_schema(conn),
    )
    lines = sa.table("price_tag_request_lines", sa.column("id"), sa.column("request_id"))

    row = conn.execute(
        sa.select(page.c.id, page.c.draft_doc)
        .select_from(page.join(lines, lines.c.request_id == page.c.request_id))
        .where(lines.c.id == line_id, page.c.kind == "tag_sheet")
    ).first()
    if row is None or not row.draft_doc:
        return
    raw = row.draft_doc
    doc = json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw)
    changed = False
    for sheet in doc.get("sheets") or []:
        placed = sheet.get("tags") or []
        sources = [p for p in placed if p.get("request_tag_id") == source_tag_id]
        for source in sources:
            suffix = str(source.get("id") or "")
            copy_index = suffix.rsplit("-c", 1)[-1] if "-c" in suffix else "0"
            for new_tag_id in new_tag_ids:
                clone = copy.deepcopy(source)
                clone["request_tag_id"] = new_tag_id
                clone["id"] = f"{new_tag_id}-c{copy_index}"
                placed.append(clone)
                changed = True
        sheet["tags"] = placed
    if changed:
        conn.execute(sa.update(page).where(page.c.id == row.id).values(draft_doc=doc))


def upgrade() -> None:
    op.add_column(
        "price_tag_request_lines",
        sa.Column(
            "promotion_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("promotions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "price_tag_request_lines",
        sa.Column("manual_sell_price", sa.Numeric(12, 2), nullable=True),
    )
    op.create_index(
        "ix_price_tag_request_lines_promotion_id",
        "price_tag_request_lines",
        ["promotion_id"],
    )

    conn = op.get_bind()

    # AC-S6-2: every line inherits its request's header promotion. No line
    # loses it - a request with 3 lines backfills all 3, not just one.
    conn.execute(
        sa.text(
            "UPDATE price_tag_request_lines "
            "SET promotion_id = price_tag_requests.promotion_id "
            "FROM price_tag_requests "
            "WHERE price_tag_requests.id = price_tag_request_lines.request_id "
            "AND price_tag_requests.promotion_id IS NOT NULL"
        )
    )

    op.drop_index("ix_price_tag_requests_promotion_id", table_name="price_tag_requests")
    op.drop_column("price_tag_requests", "promotion_id")

    _split_open_tags(conn)


def downgrade() -> None:
    op.add_column(
        "price_tag_requests",
        sa.Column(
            "promotion_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("promotions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_price_tag_requests_promotion_id", "price_tag_requests", ["promotion_id"]
    )

    conn = op.get_bind()
    # Restored from the FIRST line (by sort_order) that carries one - the
    # header can only hold ONE promotion, so this is a best-effort answer for
    # whatever the header column meant before D1 retired it.
    conn.execute(
        sa.text(
            "UPDATE price_tag_requests SET promotion_id = ("
            "  SELECT l.promotion_id FROM price_tag_request_lines l"
            "  WHERE l.request_id = price_tag_requests.id AND l.promotion_id IS NOT NULL"
            "  ORDER BY l.sort_order, l.id LIMIT 1"
            ")"
        )
    )

    op.drop_index(
        "ix_price_tag_request_lines_promotion_id", table_name="price_tag_request_lines"
    )
    op.drop_column("price_tag_request_lines", "manual_sell_price")
    op.drop_column("price_tag_request_lines", "promotion_id")
