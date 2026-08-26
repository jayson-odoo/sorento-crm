"""A SYNTHETIC report over a scratch table, shared by every kernel test.

The sponsorship report is deliberately absent from the kernel tests: the claim under test
is that the kernel is generic, and a kernel test that leans on report #1's data proves
only that the kernel works for sponsorship forms. CI's database is empty besides, so the
dataset here is a table the test creates and fills.

The table is a Postgres TEMP table: visible to one connection only, so two xdist workers
(or two worktrees sharing the local database) cannot collide on the name, and it goes away
when the connection closes whatever the test did.
"""
from __future__ import annotations

import sqlalchemy as sa

TABLE = "zzt_report_orders"

# The scratch dataset: a sales register with two dates, two money measures (one of them
# often blank), and a delivery year that renders as a tick group.
_ROWS = [
    # order_no, agent,   region,   booked_on,    shipped_on,   amount,  fee,     year
    ("Z-001", "Alice", "North", "2026-01-10", "2026-02-03", "1000.00", "10.50", 2026),
    ("Z-002", "Alice", "North", "2026-01-25", "2026-01-28", "250.25", None, 2026),
    ("Z-003", "Alice", "South", "2026-03-04", "2026-03-09", "400.00", "20.00", 2027),
    ("Z-004", "Bob", "South", "2026-03-18", "2026-04-02", None, "5.00", 2027),
    ("Z-005", "Bob", "North", "2026-11-30", "2026-12-01", "99.99", "1.01", None),
    # Outside a 2026 period on EITHER basis.
    ("Z-006", "Carol", "North", "2025-06-01", "2025-06-05", "5000.00", "50.00", 2025),
]


def create_table(db) -> None:
    db.execute(
        sa.text(
            f"""
            CREATE TEMP TABLE {TABLE} (
                order_no      text PRIMARY KEY,
                agent         text,
                region        text,
                booked_on     date,
                shipped_on    date,
                amount        numeric(14, 2),
                fee           numeric(14, 2),
                delivery_year integer,
                company_id    text
            ) ON COMMIT PRESERVE ROWS
            """
        )
    )
    for order_no, agent, region, booked, shipped, amount, fee, year in _ROWS:
        db.execute(
            sa.text(
                f"""
                INSERT INTO {TABLE}
                    (order_no, agent, region, booked_on, shipped_on, amount, fee, delivery_year)
                VALUES (:o, :a, :r, :b, :s, :amt, :fee, :y)
                """
            ),
            {
                "o": order_no,
                "a": agent,
                "r": region,
                "b": booked,
                "s": shipped,
                "amt": amount,
                "fee": fee,
                "y": year,
            },
        )


# ONE clause object for the whole file: two `sa.table()` calls with the same name are two
# different FROM elements to SQLAlchemy, and the query comes out as a cartesian product.
_TABLE_CLAUSE = None


def table_clause():
    global _TABLE_CLAUSE
    if _TABLE_CLAUSE is None:
        _TABLE_CLAUSE = sa.table(
            TABLE,
            sa.column("order_no", sa.Text),
            sa.column("agent", sa.Text),
            sa.column("region", sa.Text),
            sa.column("booked_on", sa.Date),
            sa.column("shipped_on", sa.Date),
            sa.column("amount", sa.Numeric(14, 2)),
            sa.column("fee", sa.Numeric(14, 2)),
            sa.column("delivery_year", sa.Integer),
            sa.column("company_id", sa.Text),
        )
    return _TABLE_CLAUSE


_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _month_label(value: str) -> str:
    year, month = value.split("-")
    return f"{_MONTH_ABBR[int(month) - 1]}'{year[2:]}"


def dataset(scope: str = "none"):
    from app.services.reports import registry as reg

    t = table_clause()
    columns = (
        reg.Column("order_no", "Order no", "text", "dimension", lambda c: t.c.order_no, size=120),
        reg.Column("agent", "Agent", "text", "dimension", lambda c: t.c.agent, size=140),
        reg.Column("region", "Region", "text", "dimension", lambda c: t.c.region, size=120),
        reg.Column(
            "month",
            "Month",
            "text",
            "dimension",
            lambda c: sa.func.to_char(sa.func.date_trunc("month", c.date_basis), "YYYY-MM"),
            period_months=True,
            value_label=_month_label,
        ),
        reg.Column("amount", "Amount", "money", "measure", lambda c: t.c.amount, size=140),
        reg.Column("fee", "Fee", "money", "measure", lambda c: t.c.fee, size=120),
        reg.Column(
            "delivery_year", "Delivery year", "integer", "dimension", lambda c: t.c.delivery_year
        ),
        reg.Column("booked_on", "Booked on", "date", "date", lambda c: t.c.booked_on),
    )
    return reg.Dataset(
        key="zzt_orders",
        scope=scope,
        columns=columns,
        date_bases=(
            reg.DateBasis("booked_on", "Booked", t.c.booked_on),
            reg.DateBasis("shipped_on", "Shipped", t.c.shipped_on),
        ),
        base=lambda c: sa.select().select_from(t),
        company_column=t.c.company_id if scope == "company" else None,
    )


def definition(for_dataset=None):
    from app.services.reports import registry as reg

    t = table_clause()
    for_dataset = for_dataset or dataset()
    return reg.ReportDefinition(
        key="zzt_orders",
        title="Scratch orders",
        permission="zzt.reports.orders",
        dataset=for_dataset,
        params=(
            reg.DateBasisParam(key="date_basis", label="Date basis", default="booked_on"),
            reg.PeriodParam(key="period", label="Period", default={"kind": "year", "year": 2026}),
            reg.SelectParam(
                key="agent",
                label="Agent",
                multi=True,
                default=(),
                options=lambda db: [("Alice", "Alice"), ("Bob", "Bob"), ("Carol", "Carol")],
                condition=lambda c, values: t.c.agent.in_(values),
            ),
            reg.SelectParam(
                key="region",
                label="Region",
                multi=True,
                default=("North", "South"),
                options=lambda db: [("North", "North"), ("South", "South")],
                condition=lambda c, values: t.c.region.in_(values),
            ),
        ),
        detail=reg.DetailLayout(
            title="Orders",
            order_by=lambda c: [t.c.order_no],
            groups=(reg.TickGroup(source="delivery_year", label="Delivery year"),),
        ),
        pivot=reg.PivotLayout(title="Summary by agent"),
        default_view={
            "params": {
                "date_basis": "booked_on",
                "period": {"kind": "year", "year": 2026},
                "agent": [],
                "region": ["North", "South"],
            },
            "detail": {"columns": [], "order": []},
            "pivot": {"rows": "agent", "cols": "month", "measures": ["amount", "fee"]},
        },
        workbook=reg.WorkbookSpec(company_name="ZZT Sdn Bhd", department="Scratch"),
    )


