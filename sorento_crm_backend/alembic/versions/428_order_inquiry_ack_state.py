"""The order inquiry handshake: `ack_state` on the row, and `committed_v` drops a rejection

Revision ID: 428_order_inquiry_ack_state
Revises: 427_sales_agents_class_backfill
Create Date: 2026-08-27 09:00:00.000000

`PLAN-scm-oi-handshake.md` (captain, 27 Aug 2026). CS raises an instruction on the
fulfilment board; purchasing ACKNOWLEDGES it, and only then are documents linked to it.
Until somebody has acknowledged a row, CS is free to change it and purchasing has not
been asked for anything.

Two columns on the row and they are never merged: `state` (raised / partly_linked /
placed / actioned / cancelled - where the SUPPLY stands) and `ack_state` (awaiting ->
acknowledged | rejected | changed - where the HANDSHAKE stands). A row can be wholly
linked and still be one CS has amended since; a row can be rejected and still carry the
links a buyer made before refusing the rest.

Two more columns ride with them and are not part of the handshake's own state:
`previous_qty` / `previous_delivery_date`, what the row said before the last
settle-in-place restated it. The CHANGED cell prints a Was / Now table off them. They
exist because the previous value used to live only in the row's note, as prose, and a
screen that parsed the sentence back into a number read its own comma as part of the
quantity ("Was 10, no previous delivery date" -> `10,`).

NO BACKFILL, deliberately. The feature is not live: nobody has acknowledged anything, so
every existing row starts `awaiting`, which is the truth about it. That is also why the
column is `NOT NULL DEFAULT 'awaiting'` rather than nullable - a NULL here would be a
third reading of "not acknowledged" with no way to tell it from the first.

The VIEW changes with the columns, in one migration, because the second cannot be applied
before the first: `scm.committed_v` drops a REJECTED row from both project legs. A
rejection is purchasing saying the quantity is not to be bought; leaving it in the view
would have the reorder plan buy it anyway and the board show it as owed. An AWAITING row
is still counted here - it IS owed to the customer - and it is the PLAN that reads the
narrower rule (`demand.horizon_committed_select_sql`, acknowledged and changed only),
which is a SELECT rather than a view and needs no migration.

The body is FROZEN here rather than imported from `app.services.scm.demand.COMMITTED_V_SQL`,
and 426's body is frozen beside it for the downgrade
(`tests/scm/test_committed_v_migration_chain.py`).

`CREATE OR REPLACE` is legal: same columns, same order, same names, same types - every
constant leg column keeps the `0::numeric` cast 424 needed to apply at all. Only two leg
predicates change.
"""
import sqlalchemy as sa
from alembic import op

revision = "428_order_inquiry_ack_state"
down_revision = "427_sales_agents_class_backfill"
branch_labels = None
#: The revision whose view body this one replaces.
depends_on = "426_committed_v_form_leg_scope"


#: The handshake's own grant, and the one it is derived from. Written as literals: a
#: migration describes a point in history, and importing the live registry is the shape
#: that killed production's first replay of the SCM chain.
_TARGET = "projects.order_inquiries.acknowledge"
_SOURCE = "projects.order_inquiry.action"
#: The desks this grant is FOR, by role name. The derived sweep below is not enough on its
#: own: on the live copy `projects.order_inquiry.action` is held by Admin alone, so
#: deriving from it would ship the feature to one role and hide it from the two people it
#: was built for. Matched case-insensitively on the name, and a no-op where a database has
#: no such role.
_ROLE_NAMES = ("purchasing", "purchasing manager role")
_NAME = "Acknowledge Order Inquiry Rows"
_DESCRIPTION = (
    "Purchasing grant: acknowledge an order inquiry row (which is what links documents "
    "to it), reject one with a reason, run Link now and upload the purchase order and "
    "SPO books from the Order Inquiries page."
)


_AS_OF_428 = """
CREATE OR REPLACE VIEW scm.committed_v AS
WITH legs AS (
    -- The BOOK leg, and it is the RETAIL channel entire (P3). A project-class line is
    -- never demand as a book line: it becomes demand when CS raises an Order Inquiry
    -- ORDER row for it, which the confirmed and form legs below count, and it stops being
    -- demand when that row is linked. A NULL class reads as retail - the book-direct
    -- channel - because nothing is unclassified any more (P4).
    SELECT sol.product_id,
           sol.warehouse_id,
           0::numeric AS project_qty,
           0::numeric AS project_confirmed_qty,
           GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                  - COALESCE(sol.qty_delivered, 0), 0) AS retail_qty,
           0::numeric AS unclassified_qty
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    WHERE so.status = 'open'
      AND sol.line_status = 'open'
      AND sol.purchasing_status <> 'covered'
      AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                 - COALESCE(sol.qty_delivered, 0), 0) > 0
      AND so.demand_class IS DISTINCT FROM 'project'
    UNION ALL
    -- The confirmed leg: what CS decided must be bought, at the reconciled core line's
    -- product and fulfilment location, LESS whatever of it now sits on a document
    -- (PLAN-scm-cs-planning-uat.md section 3.I). Never matched on provisional_ref,
    -- autocount_doc_no or item code (plan 4).
    --
    -- Netted per ROW rather than tested per STATE. Before `order_inquiry_links` a row was
    -- all or nothing - `raised` counted the whole quantity, `placed` counted none - so a
    -- cascade that could only cover part of a row had to SPLIT the row for the arithmetic
    -- to come out, which is how nine sales-order lines became eleven instructions. A fully
    -- linked row now leaves confirmed demand exactly as `placed` did, and a half-linked
    -- one leaves half of it.
    --
    -- ORDER_BACK counts here too (PLAN-scm-purchasing-uat-journey.md section 4b): it is
    -- still demand until it is linked. At the DONOR's location, which is what the row's
    -- own `stock_location` names: the row hangs off the BORROWING line, so reading the
    -- core line's warehouse would put the hole in a warehouse that never had one.
    SELECT sol.product_id,
           CASE WHEN oir.verb = 'ORDER_BACK'
                THEN COALESCE(donor.id, sol.warehouse_id)
                ELSE sol.warehouse_id END AS warehouse_id,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.so_supply_decisions d
      ON d.id = oir.supply_decision_id
     AND d.state = 'active'
    JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
    JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
    LEFT JOIN warehouses donor ON donor.warehouse_code = oir.stock_location
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) lk ON TRUE
    WHERE oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      AND oir.qty > COALESCE(lk.linked, 0)
    UNION ALL
    -- The FORM leg: an instruction the CS Order Inquiry Form raised that no supply decision
    -- points at (`PLAN-scm-cs-planning-uat.md` section 3.I; the fixture sheet's `[NL]`
    -- rows). CS writes `ORDER BACK` where a delivery date belongs, and the form is the only
    -- writer that can raise it - the fulfilment board has nothing to decide about a line
    -- AutoCount has closed. The ROW states its own item and location, and those are what
    -- this leg reads, whether or not it also names a sales-order line. Without it the
    -- fourteen instructions on SO381895's first two forms are raised, shown to purchasing,
    -- and invisible to the plan that decides what to buy.
    --
    -- Joined on the CODE and the company together, which is exactly what
    -- `uq_products_company_product_code` / `uq_warehouses_company_warehouse_code` make
    -- unique - a code alone would multiply the row once per company holding the same SKU.
    --
    -- INNER on `products`, because a row naming an item this system does not hold is demand
    -- for nothing and there is no product to attribute it to. LEFT on `warehouses`, because
    -- a row that names no location, or one we do not hold, is still demand - it comes out
    -- with a NULL warehouse, which every reader joins on `(product, warehouse)` and so
    -- matches nowhere. Counted at no location rather than invented at one, and visible in
    -- the view rather than dropped from it.
    --
    -- `supply_decision_id IS NULL` keeps this leg disjoint from the CONFIRMED leg above:
    -- a row a CS decision points at is counted there, at the core line's product and
    -- location, and every OTHER raised row is counted here at its own. The leg used to
    -- demand `so_line_id IS NULL` as well, because a row naming a book line was already
    -- counted by the SHEET leg; P3 retired that leg, and the condition would now DELETE
    -- such a row from planning instead of de-duplicating it - the form raises ORDER BACK
    -- rows carrying an `so_line_id` (`project_order_inquiry_import_service`), and they are
    -- demand like any other.
    --
    -- The `NOT EXISTS` below keeps it disjoint from the BOOK leg, which is the other half
    -- of the same worry and the half P3 opened: the book still speaks for retail, so a
    -- decision-less row naming a RETAIL line would be counted twice, once as the line and
    -- once as the row. Stated as "the book leg does not count this line" - the same four
    -- openness conditions the book leg applies, plus its class test - rather than as "the
    -- line is project": a row whose line is unreconciled, closed or fully delivered is
    -- counted by nothing else, and a class test alone would drop it.
    SELECT fp.id AS product_id,
           fw.id AS warehouse_id,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN products fp
      ON fp.product_code = oir.item_code
     AND fp.company_id = oir.company_id
    LEFT JOIN warehouses fw
      ON fw.warehouse_code = oir.stock_location
     AND fw.company_id = oir.company_id
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) flk ON TRUE
    WHERE oir.supply_decision_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM projects.sales_order_lines fpsl
          JOIN sales_order_lines fsol ON fsol.id = fpsl.core_sales_order_line_id
          JOIN sales_orders fso ON fso.id = fsol.sales_order_id
          WHERE fpsl.id = oir.so_line_id
            AND fso.demand_class IS DISTINCT FROM 'project'
            AND fso.status = 'open'
            AND fsol.line_status = 'open'
            AND fsol.purchasing_status <> 'covered'
            AND GREATEST(COALESCE(fsol.qty_required, fsol.qty_ordered)
                       - COALESCE(fsol.qty_delivered, 0), 0) > 0)
      AND oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.ack_state <> 'rejected'
      AND oir.qty > 0
      AND oir.qty > COALESCE(flk.linked, 0)
)
SELECT product_id,
       warehouse_id,
       SUM(project_qty + retail_qty + unclassified_qty) AS committed,
       SUM(project_qty) AS project_committed,
       SUM(retail_qty) AS retail_committed,
       SUM(unclassified_qty) AS unclassified_committed,
       -- LAST on purpose: appended, so a CREATE OR REPLACE of this body over a database
       -- already carrying the four-column view is legal (Postgres lets a replacement add
       -- columns at the end and nowhere else). A SUBSET of `project_committed`, never a
       -- fourth addend of `committed` - adding it there would count confirmed Buy twice.
       SUM(project_confirmed_qty) AS project_confirmed_committed
FROM legs
GROUP BY product_id, warehouse_id;
"""


_AS_OF_426 = """CREATE OR REPLACE VIEW scm.committed_v AS
WITH legs AS (
    -- The BOOK leg, and it is the RETAIL channel entire (P3). A project-class line is
    -- never demand as a book line: it becomes demand when CS raises an Order Inquiry
    -- ORDER row for it, which the confirmed and form legs below count, and it stops being
    -- demand when that row is linked. A NULL class reads as retail - the book-direct
    -- channel - because nothing is unclassified any more (P4).
    SELECT sol.product_id,
           sol.warehouse_id,
           0::numeric AS project_qty,
           0::numeric AS project_confirmed_qty,
           GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                  - COALESCE(sol.qty_delivered, 0), 0) AS retail_qty,
           0::numeric AS unclassified_qty
    FROM sales_order_lines sol
    JOIN sales_orders so ON so.id = sol.sales_order_id
    WHERE so.status = 'open'
      AND sol.line_status = 'open'
      AND sol.purchasing_status <> 'covered'
      AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                 - COALESCE(sol.qty_delivered, 0), 0) > 0
      AND so.demand_class IS DISTINCT FROM 'project'
    UNION ALL
    -- The confirmed leg: what CS decided must be bought, at the reconciled core line's
    -- product and fulfilment location, LESS whatever of it now sits on a document
    -- (PLAN-scm-cs-planning-uat.md section 3.I). Never matched on provisional_ref,
    -- autocount_doc_no or item code (plan 4).
    --
    -- Netted per ROW rather than tested per STATE. Before `order_inquiry_links` a row was
    -- all or nothing - `raised` counted the whole quantity, `placed` counted none - so a
    -- cascade that could only cover part of a row had to SPLIT the row for the arithmetic
    -- to come out, which is how nine sales-order lines became eleven instructions. A fully
    -- linked row now leaves confirmed demand exactly as `placed` did, and a half-linked
    -- one leaves half of it.
    --
    -- ORDER_BACK counts here too (PLAN-scm-purchasing-uat-journey.md section 4b): it is
    -- still demand until it is linked. At the DONOR's location, which is what the row's
    -- own `stock_location` names: the row hangs off the BORROWING line, so reading the
    -- core line's warehouse would put the hole in a warehouse that never had one.
    SELECT sol.product_id,
           CASE WHEN oir.verb = 'ORDER_BACK'
                THEN COALESCE(donor.id, sol.warehouse_id)
                ELSE sol.warehouse_id END AS warehouse_id,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(lk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN projects.so_supply_decisions d
      ON d.id = oir.supply_decision_id
     AND d.state = 'active'
    JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
    JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
    LEFT JOIN warehouses donor ON donor.warehouse_code = oir.stock_location
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) lk ON TRUE
    WHERE oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(lk.linked, 0)
    UNION ALL
    -- The FORM leg: an instruction the CS Order Inquiry Form raised that no supply decision
    -- points at (`PLAN-scm-cs-planning-uat.md` section 3.I; the fixture sheet's `[NL]`
    -- rows). CS writes `ORDER BACK` where a delivery date belongs, and the form is the only
    -- writer that can raise it - the fulfilment board has nothing to decide about a line
    -- AutoCount has closed. The ROW states its own item and location, and those are what
    -- this leg reads, whether or not it also names a sales-order line. Without it the
    -- fourteen instructions on SO381895's first two forms are raised, shown to purchasing,
    -- and invisible to the plan that decides what to buy.
    --
    -- Joined on the CODE and the company together, which is exactly what
    -- `uq_products_company_product_code` / `uq_warehouses_company_warehouse_code` make
    -- unique - a code alone would multiply the row once per company holding the same SKU.
    --
    -- INNER on `products`, because a row naming an item this system does not hold is demand
    -- for nothing and there is no product to attribute it to. LEFT on `warehouses`, because
    -- a row that names no location, or one we do not hold, is still demand - it comes out
    -- with a NULL warehouse, which every reader joins on `(product, warehouse)` and so
    -- matches nowhere. Counted at no location rather than invented at one, and visible in
    -- the view rather than dropped from it.
    --
    -- `supply_decision_id IS NULL` keeps this leg disjoint from the CONFIRMED leg above:
    -- a row a CS decision points at is counted there, at the core line's product and
    -- location, and every OTHER raised row is counted here at its own. The leg used to
    -- demand `so_line_id IS NULL` as well, because a row naming a book line was already
    -- counted by the SHEET leg; P3 retired that leg, and the condition would now DELETE
    -- such a row from planning instead of de-duplicating it - the form raises ORDER BACK
    -- rows carrying an `so_line_id` (`project_order_inquiry_import_service`), and they are
    -- demand like any other.
    --
    -- The `NOT EXISTS` below keeps it disjoint from the BOOK leg, which is the other half
    -- of the same worry and the half P3 opened: the book still speaks for retail, so a
    -- decision-less row naming a RETAIL line would be counted twice, once as the line and
    -- once as the row. Stated as "the book leg does not count this line" - the same four
    -- openness conditions the book leg applies, plus its class test - rather than as "the
    -- line is project": a row whose line is unreconciled, closed or fully delivered is
    -- counted by nothing else, and a class test alone would drop it.
    SELECT fp.id AS product_id,
           fw.id AS warehouse_id,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_qty,
           GREATEST(oir.qty - COALESCE(flk.linked, 0), 0) AS project_confirmed_qty,
           0::numeric AS retail_qty,
           0::numeric AS unclassified_qty
    FROM projects.order_inquiry_rows oir
    JOIN products fp
      ON fp.product_code = oir.item_code
     AND fp.company_id = oir.company_id
    LEFT JOIN warehouses fw
      ON fw.warehouse_code = oir.stock_location
     AND fw.company_id = oir.company_id
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS linked
        FROM projects.order_inquiry_links l
        WHERE l.row_id = oir.id
    ) flk ON TRUE
    WHERE oir.supply_decision_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM projects.sales_order_lines fpsl
          JOIN sales_order_lines fsol ON fsol.id = fpsl.core_sales_order_line_id
          JOIN sales_orders fso ON fso.id = fsol.sales_order_id
          WHERE fpsl.id = oir.so_line_id
            AND fso.demand_class IS DISTINCT FROM 'project'
            AND fso.status = 'open'
            AND fsol.line_status = 'open'
            AND fsol.purchasing_status <> 'covered'
            AND GREATEST(COALESCE(fsol.qty_required, fsol.qty_ordered)
                       - COALESCE(fsol.qty_delivered, 0), 0) > 0)
      AND oir.verb IN ('ORDER', 'ORDER_BACK')
      AND oir.state IN ('raised', 'partly_linked')
      AND oir.qty > 0
      AND oir.qty > COALESCE(flk.linked, 0)
)
SELECT product_id,
       warehouse_id,
       SUM(project_qty + retail_qty + unclassified_qty) AS committed,
       SUM(project_qty) AS project_committed,
       SUM(retail_qty) AS retail_committed,
       SUM(unclassified_qty) AS unclassified_committed,
       -- LAST on purpose: appended, so a CREATE OR REPLACE of this body over a database
       -- already carrying the four-column view is legal (Postgres lets a replacement add
       -- columns at the end and nowhere else). A SUBSET of `project_committed`, never a
       -- fourth addend of `committed` - adding it there would count confirmed Buy twice.
       SUM(project_confirmed_qty) AS project_confirmed_committed
FROM legs
GROUP BY product_id, warehouse_id;
"""


def upgrade() -> None:
    # The handshake's own columns. `acknowledged_by` / `rejected_by` are real FKs to
    # `users.id` (a VARCHAR there, not a UUID) with ON DELETE SET NULL: a person leaving
    # must not take the instruction's history with them, and the time and the reason stay
    # readable without them.
    op.add_column(
        "order_inquiry_rows",
        sa.Column(
            "ack_state",
            sa.String(length=16),
            nullable=False,
            server_default="awaiting",
        ),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("acknowledged_by", sa.String(length=100), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("acknowledged_at", sa.DateTime(timezone=False), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("rejected_by", sa.String(length=100), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("rejected_at", sa.DateTime(timezone=False), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        schema="projects",
    )
    # When CS last amended a row purchasing had already acknowledged. Its own column
    # rather than a reading of `updated_at`: every other write to the row would move that
    # one, and "what has changed since I looked at it" is the whole question this answers.
    op.add_column(
        "order_inquiry_rows",
        sa.Column("changed_at", sa.DateTime(timezone=False), nullable=True),
        schema="projects",
    )
    # What the row said before the last settle-in-place restated it. The Was / Now table
    # the CHANGED cell prints reads these two columns; the note beside them keeps the same
    # sentence for a person, and is never parsed back into a number.
    op.add_column(
        "order_inquiry_rows",
        sa.Column("previous_qty", sa.Numeric(15, 4), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("previous_delivery_date", sa.Date(), nullable=True),
        schema="projects",
    )
    op.create_foreign_key(
        "fk_order_inquiry_rows_acknowledged_by",
        "order_inquiry_rows",
        "users",
        ["acknowledged_by"],
        ["id"],
        source_schema="projects",
        referent_schema="public",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_order_inquiry_rows_rejected_by",
        "order_inquiry_rows",
        "users",
        ["rejected_by"],
        ["id"],
        source_schema="projects",
        referent_schema="public",
        ondelete="SET NULL",
    )
    # The worklist filters on it and the facet counts by it, over every row in the
    # company: purchasing's own list is "what have I not acknowledged yet".
    op.create_index(
        "ix_project_order_inquiry_rows_ack_state",
        "order_inquiry_rows",
        ["ack_state"],
        schema="projects",
    )
    op.execute(_AS_OF_428)
    _grant_acknowledge(op.get_bind())


def _grant_acknowledge(bind) -> None:
    """The new permission reaches every role that already ACTS on an order inquiry row.

    A permission granted to nobody is indistinguishable from a broken feature. Two sweeps,
    because neither is enough alone:

    * DERIVED from `projects.order_inquiry.action` - whoever may mark a row today is
      purchasing, and acknowledging is the same desk's work. Derived rather than
      hand-listed so it stays correct on a database whose roles were customised after
      provisioning;
    * NAMED (`_ROLE_NAMES`) - because on the live copy that source is held by Admin and
      nobody else, so the derivation alone would ship the feature to one role and hide it
      from Joey, who is the person it was built for.

    Idempotent both ways: the permission row is created only when absent (a fresh deploy
    runs migrations before the app's registry sync, so it may genuinely not be there yet),
    and the grants are `ON CONFLICT DO NOTHING`. CI's database has no roles at all, which
    makes every statement here a clean no-op rather than a failure.
    """
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": _TARGET, "name": _NAME, "descr": _DESCRIPTION},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :source
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"source": _SOURCE, "target": _TARGET},
    )
    # And the desks by NAME. Same statement shape, same idempotency; it simply names the
    # roles rather than deriving them, because the derivation reaches Admin only.
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, tgt.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
              AND lower(btrim(r.name)) = ANY(:role_names)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"target": _TARGET, "role_names": list(_ROLE_NAMES)},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM user_role_permissions grant_row
            USING user_permissions tgt
            WHERE grant_row.permission_id = tgt.id AND tgt.slug = :target
            """
        ),
        {"target": _TARGET},
    )
    op.execute(_AS_OF_426)
    op.drop_index(
        "ix_project_order_inquiry_rows_ack_state",
        table_name="order_inquiry_rows",
        schema="projects",
    )
    op.drop_constraint(
        "fk_order_inquiry_rows_rejected_by",
        "order_inquiry_rows",
        schema="projects",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_order_inquiry_rows_acknowledged_by",
        "order_inquiry_rows",
        schema="projects",
        type_="foreignkey",
    )
    for column in (
        "previous_delivery_date",
        "previous_qty",
        "changed_at",
        "rejected_reason",
        "rejected_at",
        "rejected_by",
        "acknowledged_at",
        "acknowledged_by",
        "ack_state",
    ):
        op.drop_column("order_inquiry_rows", column, schema="projects")
