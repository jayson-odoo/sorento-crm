"""OI-ONE-DELIVERY-DATE AC-D2: a split part on another SO line carries that line's date."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.base import company_scope
from app.models.project_so import SOLineSplit

from ._oi_one_date_seed import Chain
from ._pg_fixture import blank_session
from .test_order_inquiry_worklist import _sorento

NEW = date(2027, 1, 7)
PLANNED = date(2026, 12, 1)


def test_splits_payload_carries_the_date_of_the_line_a_part_sits_on():
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            _c, origin = chain.add_line(core_date=date(2026, 9, 1), mirror_date=date(2026, 9, 1))
            _c, other = chain.add_line(core_date=NEW, mirror_date=date(2026, 6, 1))
            on_line = SOLineSplit(
                project_sales_order_id=chain.pso.id, so_line_id=origin.id, seq=0,
                qty=Decimal("4"), delivery_date=PLANNED, sits_on_line_id=other.id,
                base_qty=Decimal("10"), base_date=date(2026, 9, 1),
            )
            new_line = SOLineSplit(
                project_sales_order_id=chain.pso.id, so_line_id=origin.id, seq=1,
                qty=Decimal("6"), delivery_date=PLANNED, sits_on_line_id=None,
                base_qty=Decimal("10"), base_date=date(2026, 9, 1),
            )
            db.add_all([on_line, new_line])
            db.commit()

            out = ProjectOrderInquiryService(db).splits_for_lines([str(origin.id)])

            parts = {p["id"]: p for p in out[str(origin.id)]}
            assert parts[str(on_line.id)]["sits_on_line_date"] == NEW.isoformat(), "core wins"
            assert parts[str(new_line.id)]["sits_on_line_date"] is None
