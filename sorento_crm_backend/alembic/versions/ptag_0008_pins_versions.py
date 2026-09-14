"""r9 S5: the product data pin, its ack, and the pins a version carries.

Master data resolved live on every render (ADR 0008) meant a price edited on
Tuesday silently rewrote the proof approved on Monday. The data is pinned when
designing starts, and this revision adds the three columns that hold it plus
the version-side snapshot Restore needs.

``backfill_pins`` is a NAMED function called from ``upgrade()`` for the same
reason S3's two steps are: ``blank_session`` builds the schema from the models,
so a data step is only testable by importing the revision and calling it.

Revision ID: ptag_0008_pins_versions
Revises: ptag_0007_print_collection
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ptag_0008_pins_versions"
down_revision = "ptag_0007_print_collection"
branch_labels = None
depends_on = None

#: Where a pin means something. A `new` request has not been claimed and
#: nobody is drawing anything, so pinning it freezes master data against a
#: design that does not exist; a finished one can decide nothing. The pin
#: belongs to the statuses in between.
_BACKFILL_STATUSES = ("designing", "changes_requested", "proof_ready", "approved")


def backfill_pins(bind) -> int:
    """Pin every line of every request somebody is still drawing (D16).

    Without this, an existing request in mid-design has no pin, so the gate has
    nothing to compare against and the first product edit walks onto the tag
    exactly as it did before. Pinning what the resolver answers TODAY means
    nothing changes visually on day one, which is the point.

    Through the REAL resolver, not a hand-rolled SELECT: every read path
    answers the pin once one exists, so a pin holding only the code, the name
    and the list price blanks the dimensions, the spec lines, the specs and the
    photo on every tag mid-design at upgrade - and the diff then reports each of
    those as a change. A set line has no `products` row at all, so a LEFT JOIN
    pin leaves it empty and the tag goes blank. The resolver knows both.

    Returns how many lines were pinned.
    """
    from sqlalchemy.orm import Session

    from app.models.base import set_company_scope
    from app.models.price_tag import PriceTagRequest
    from app.services.dealer_kit import tag_data_service

    session = Session(bind=bind)
    # A migration is not a request: it touches every company's rows, so the
    # scope is "no predicate" rather than the fail-closed default (0 rows).
    set_company_scope(session, None)
    pinned = 0
    try:
        requests = (
            session.query(PriceTagRequest)
            .filter(PriceTagRequest.status.in_(_BACKFILL_STATUSES))
            .all()
        )
        for request in requests:
            pinned += tag_data_service.pin_lines(
                session, request, only_unpinned=True
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return pinned


def upgrade() -> None:
    op.add_column(
        "price_tag_request_lines",
        sa.Column("pinned_tag_data", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "price_tag_request_lines",
        sa.Column("pinned_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "price_tag_request_lines",
        sa.Column("data_change_ack_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "page_version",
        sa.Column("pinned_line_data", postgresql.JSONB(), nullable=True),
        schema="dealer_kit",
    )

    backfill_pins(op.get_bind())


def downgrade() -> None:
    op.drop_column("page_version", "pinned_line_data", schema="dealer_kit")
    op.drop_column("price_tag_request_lines", "data_change_ack_hash")
    op.drop_column("price_tag_request_lines", "pinned_at")
    op.drop_column("price_tag_request_lines", "pinned_tag_data")
