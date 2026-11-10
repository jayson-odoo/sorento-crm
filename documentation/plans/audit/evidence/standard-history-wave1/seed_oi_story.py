"""Scratch seed for the STANDARD-HISTORY browser pass: the OI-2611-0019 story (names masked).
Run from sorento_crm_backend with SORENTO_ENV_FILE=.env.ci-tests. Throwaway DB only."""
import os, sys
from datetime import datetime
sys.path.insert(0, os.getcwd())
from app.database import SessionLocal
from app.models.project_so import OI_RAISE_RAISED, OrderInquiryRaise
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from tests.test_order_inquiry_worklist_raised_by import (
    _adopted_order, _inquiry, _line, _product, _row, _sorento, _uid, _user,
)
db = SessionLocal()
company_id = _sorento(db)
cs = _user(db, "A*** (CS)", f"cs.{_uid()[:8]}@zzt.test")
buyer = _user(db, "J*** (Purchasing)", f"buy.{_uid()[:8]}@zzt.test")
order = _adopted_order(db, company_id, "SO428916")
raised_at = datetime(2026, 11, 2, 9, 31)
inquiry = _inquiry(db, company_id, order, raised_by=cs.id, raised_at=raised_at)
db.add(OrderInquiryRaise(id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id,
                         kind=OI_RAISE_RAISED, raised_by=cs.id, raised_at=raised_at))
codes = ["CKS1050", "CKSW015", "SRT61-CR", "SRTHD122", "SRTSH22512-N", "SRTWC286-SH-NEW",
         "SRTWT167", "SRTWT2219", "SRTSP131", "SRT320-CR", "SRT5674-N", "SRT5732", "SRTWB246"]
rows = []
for n, code in enumerate(codes, start=1):
    product = _product(db, f"{code}-{_uid()[:4]}")
    line = _line(db, company_id, order, product)
    line.line_no = n
    row = _row(db, company_id, inquiry, line, code)
    row.created_at = raised_at
    rows.append(row)
db.commit()
svc = ProjectOrderInquiryService(db)
svc.acknowledge_rows([r.id for r in rows[:8]], actor_user_id=buyer.id); db.commit()
svc.acknowledge_rows([rows[8].id], actor_user_id=buyer.id); db.commit()
svc.unacknowledge_rows([r.id for r in rows[:9]], actor_user_id=buyer.id); db.commit()
print("OI", inquiry.id, inquiry.inquiry_no)
