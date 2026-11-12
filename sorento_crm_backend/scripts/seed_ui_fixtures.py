"""UI v2 fixture seed (phase 0, G-2): a fixed, masked dataset for captures and walks.

Sandbox only: refuses any database that is not local and named *_ci or *_smoke.

Lays a small, realistic world on the bootstrapped schema: customers, agents, staff, products,
suppliers, a warehouse, projects with project SOs backed by core SOs, and order inquiries with
lines in mixed states. Names are masked look-alikes of dev data shapes.
Run from sorento_crm_backend/: SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m scripts.seed_ui_fixtures
Idempotent: a second run on a seeded database does nothing.
"""
import os, sys, uuid, random
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.database import engine  # noqa: E402

u = engine.url
if u.host not in ("localhost", "127.0.0.1") or not (u.database or "").endswith(("_ci", "_smoke")):
    sys.exit(f"refusing: {u.host} {u.database}")

from sqlalchemy import text  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.order import Customer, SalesOrder, SalesOrderLine  # noqa: E402
from app.models.sales_agent import SalesAgent  # noqa: E402
from app.models.product import Product, ProductCategory, UnitOfMeasure, Brand  # noqa: E402
from app.models.inventory import Warehouse  # noqa: E402
from app.models.procurement import Supplier  # noqa: E402
from app.models.project_so import (  # noqa: E402
    OrderInquiry, OrderInquiryRow, ProjectSalesOrder, ProjectSalesOrderLine,
    IV_ORDER, IV_RESERVE_AND_ORDER, IV_ALREADY_INBOUND, INQUIRY_RAISED, INQUIRY_ACTIONED,
    ACK_ACKNOWLEDGED, ACK_AWAITING, SO_STATUS_PUBLISHED,
)
from app.models.base import company_scope  # noqa: E402

random.seed(7)
U = lambda: str(uuid.uuid4())  # noqa: E731

db = SessionLocal()
cid = db.execute(text("select id from companies where code='SRT'")).scalar() or db.execute(
    text("select id from companies order by created_at limit 1")).scalar()
print("company", cid)

with company_scope(db, frozenset({cid})):
    if db.execute(text("select count(*) from customers where customer_code like 'UIV2-%'")).scalar():
        print("already seeded"); sys.exit(0)

    staff = {}
    for n in ["E**** T.", "J**** W.", "K** L.", "W** Y.", "N**** R.", "A***** M.", "S*** L."]:
        uid = U(); db.add(User(id=uid, email=f"uiv2-{uid[:6]}@example.com", name=n)); staff[n] = uid
    db.flush()

    custs = []
    for code, name in [("UIV2-300-R001", "R***** Kitchen Sdn Bhd"), ("UIV2-300-B014", "B****** Sdn Bhd (Project)"),
                       ("UIV2-300-M002", "M*** Debtor Enterprise"), ("UIV2-300-A090", "A*** Hartanah Sdn Bhd"),
                       ("UIV2-300-T033", "T*** Residences Sdn Bhd"), ("UIV2-300-S117", "S***** Interior Works"),
                       ("UIV2-300-O004", "O**** Trading"), ("UIV2-300-K210", "K******* Interior Sdn Bhd")]:
        c = Customer(id=U(), company_id=cid, customer_code=code, customer_name=name); db.add(c); custs.append(c)
    agents = []
    for a in ["JASON", "KOKLEONG", "AISYAH", "BENNY"]:
        s = SalesAgent(id=U(), company_id=cid, sales_agent=a); db.add(s); agents.append(s)
    db.flush()

    uom = UnitOfMeasure(id=U(), company_id=cid, uom_code="UNIT", uom_name="Unit")
    cat = ProductCategory(id=U(), company_id=cid, category_code="UIV2-SAN", category_name="Sanitaryware")
    db.add_all([uom, cat]); db.flush()
    prods = []
    for code, name in [("SRT382-6", "Ceramic Wash Basin 450mm, white"), ("SRTWC8613-RL", "Wall-hung WC, soft-close seat"),
                       ("CB6633", "Concealed cistern, dual flush"), ("SRT-WC-01", "Close-coupled WC"),
                       ("SRT-BT-1700", "Acrylic bathtub 1700mm"), ("SRT-MX-210", "Basin mixer, chrome"),
                       ("SRT-SH-88", "Rain shower set 8in"), ("TILE-600-GR", "Porcelain tile 600x600 grey")]:
        p = Product(id=U(), company_id=cid, product_code=code, product_name=name, category_id=cat.id,
                    base_uom_id=uom.id, list_price=Decimal(random.choice(["120.00", "385.00", "1120.00", "86.50"])))
        db.add(p); prods.append(p)
    wh = Warehouse(id=U(), company_id=cid, warehouse_code="HQ", warehouse_name="HQ Shah Alam", location="Shah Alam")
    db.add(wh)
    for sc, sn in [("UIV2-FW", "FOSHAN WORKS"), ("UIV2-DF", "DAFUYUAN"), ("UIV2-CS", "CHAOSHENG")]:
        db.add(Supplier(id=U(), company_id=cid, supplier_code=sc, supplier_name=sn))
    db.flush()

    from app.services.project_service import register_project
    from app.services import project_seed_service
    project_seed_service.run(db, company_id=cid)
    projects = []
    for t in ["T*** Residences Blk B", "Menara S*** Fit-out", "Taman C**** Phase 3", "S***** Velocity 2", "K******* Show Units"]:
        projects.append(register_project(db, company_id=cid, actor_user_id=staff["J**** W."], developer_party_id=None, title=t))
    db.flush()

    now = datetime(2026, 11, 10, 9, 42)
    raisers = ["E**** T.", "E**** T.", "W** Y.", "N**** R.", "E**** T.", "S*** L."]
    n = 0
    for i in range(34):
        proj = projects[i % len(projects)] if i % 4 else None
        cust = custs[i % len(custs)]
        so_date = (now - timedelta(days=1 + i // 3)).date()
        so = SalesOrder(id=U(), company_id=cid, so_number=f"SO{414285 - i * 37}", customer_id=cust.id,
                        sales_agent_id=agents[i % len(agents)].id, order_date=so_date, status="open",
                        demand_class="project")
        db.add(so); db.flush()
        pso = ProjectSalesOrder(id=U(), company_id=cid, project_id=(proj or projects[0]).id,
                                provisional_ref=f"PSO-UIV2-{i:03d}", area_group="TOWER",
                                status=SO_STATUS_PUBLISHED, so_id=so.id)
        db.add(pso); db.flush()
        oi = OrderInquiry(id=U(), company_id=cid, project_sales_order_id=pso.id, state=INQUIRY_RAISED,
                          raised_by=staff[raisers[i % len(raisers)]], raised_at=now - timedelta(hours=5 * i + (i % 3) * 0.4))
        db.add(oi); db.flush()
        nlines = 12 if i == 0 else 1 + (i % 4)
        for ln in range(nlines):
            prod = prods[(i + ln) % len(prods)]
            qty = Decimal(random.choice([4, 6, 12, 18, 24, 32, 48, 220]))
            core = SalesOrderLine(id=U(), company_id=cid, sales_order_id=so.id, product_id=prod.id,
                                  warehouse_id=wh.id, qty_ordered=qty, qty_delivered=Decimal("0"),
                                  required_date=so_date + timedelta(days=18 + ln * 7), line_status="open")
            db.add(core); db.flush()
            pl = ProjectSalesOrderLine(id=U(), company_id=cid, project_sales_order_id=pso.id,
                                       core_sales_order_line_id=core.id, line_no=ln + 1, product_id=prod.id,
                                       description=prod.product_name, qty=qty, uom="UNIT",
                                       unit_price=prod.list_price, amount=qty * prod.list_price,
                                       delivery_date=core.required_date)
            db.add(pl); db.flush()
            done = (i % 5 == 3)
            db.add(OrderInquiryRow(id=U(), company_id=cid, order_inquiry_id=oi.id, so_line_id=pl.id,
                                   item_code=prod.product_code, qty=qty, delivery_date=core.required_date,
                                   stock_location="HQ" if ln % 2 == 0 else None,
                                   verb=[IV_ORDER, IV_RESERVE_AND_ORDER, IV_ALREADY_INBOUND][(i + ln) % 3],
                                   state=INQUIRY_ACTIONED if done else INQUIRY_RAISED,
                                   ack_state=ACK_ACKNOWLEDGED if (done or ln % 2) else ACK_AWAITING,
                                   note="Deliver to site after 2pm" if ln == 0 and i % 6 == 0 else None))
            n += 1
        db.flush()
    db.commit()
    print("seeded OIs: 34, rows:", n)
