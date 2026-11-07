from datetime import date
import sqlalchemy as sa
from tests.test_sales_leaderboard import db, _world, DEFAULT_COMPANY_ID, MOCHA_ID
from app.services.reports import ask
from app.models.finance import BillingDocument, BillingDocumentLine
from app.services.sales import invoiced_sales as inv

def test_dbg(db):
    w = _world(db)
    print("POSTED", db.query(BillingDocument).filter(inv.posted()).count(), db.query(BillingDocumentLine).count())
    print("DATES", [(d.document_type, d.status, d.doc_date, d.company_id[-2:]) for d in db.query(BillingDocument).limit(3)])
    from tests._sales_unified_seed import run, grand
    r = run(db, "sales_by_debtor_type", period={"kind":"custom","from":"2026-10-01","to":"2026-10-31"}, grants=frozenset({DEFAULT_COMPANY_ID}))
    print("ENGINE", grand(r))
    b = ask.run_ask(db, basis="invoiced", measure="amount", group_by=None, date_from=date(2026,10,1), date_to=date(2026,10,31), filters={}, warehouse_codes=[], policy=None, company_grants=frozenset({DEFAULT_COMPANY_ID}))
    print("ASK", b["total"])
