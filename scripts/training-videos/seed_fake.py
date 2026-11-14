#!/usr/bin/env python3
"""Fake-data seeder for recording training videos. NOT for any real database.

Every row is invented: "Demo Trading Sdn Bhd", customers like "Lim Bina Hardware Sdn Bhd",
phones 012-000 0xxx, emails @example.com, bathroom/tile products priced in RM. No real names.

Run from the backend directory against the local sandbox DB only:

    cd sorento_crm_backend && SORENTO_ENV_FILE=.env.ci-tests \
        venv/bin/python ../scripts/training-videos/seed_fake.py [--part p1|p2|all]

p1: admin + salesperson logins, sales agent with own customers, products, prices, stock in
    two warehouses, tag templates, complaint master data, a chatbot-console test contact.
p2: a project with a published project sales order (4 lines), order inquiries in mixed
    states through the real decision path, a CS user, ready for an amendment. p2 drives the
    sandbox backend over HTTP, so it needs TV_API_URL (that backend's /api/v1 base) set.

Idempotent: every row is found by a natural key first and only created when missing.
Refuses to run against anything but the local throwaway database named exactly sorento_ci_tv.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "sorento_crm_backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.config import settings  # noqa: E402

from sqlalchemy.engine import make_url  # noqa: E402

_DB = make_url(str(settings.database_url))
if _DB.host not in ("localhost", "127.0.0.1") or _DB.database != "sorento_ci_tv":
    raise SystemExit(f"Refusing to seed: DATABASE_URL is not the local sorento_ci_tv sandbox ({_DB.host}/{_DB.database}).")

import bcrypt  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.base import company_scope  # noqa: E402
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners  # noqa: E402

COMPANY_ID = DEFAULT_COMPANY_ID
COMPANY_NAME = "Demo Trading Sdn Bhd"
PASSWORD = "Demo1234!"

ADMIN = {"name": "Aina Admin", "email": "admin@example.com", "phone": "012-000 0000"}
SALES = {"name": "Sam Sales", "email": "sales@example.com", "phone": "012-000 0001"}
CS = {"name": "Chloe CS", "email": "cs@example.com", "phone": "012-000 0002"}

SALES_PERMS_REMOVED = ["dealer_kit.price_tag_requests.view"]
SALES_PERMS = [
    "dealer_kit.page.view",
    "dealer_kit.price_tag_requests.create",
    # NOT `.view`: holding it makes the scope "all" (own_scope.request_access), so the staff
    # page renders marketing's detail instead of the portal PriceTagRequestForm the video shows.
    "dealer_kit.price_tag_requests.view_own",
    "user_management.contacts.edit_own",
    "complaint_management.complaints.view_own",
    "complaint_management.complaints.add",
    "master_data.complaint_root_causes.view",
    "master_data.complaint_resolutions.view",
]
# The real CS role and the grants migration dp_0001_cs_planning_access gives it
# (sorento_crm_backend/alembic/versions/dp_0001_cs_planning_access.py:26-27), so the recorded
# sidebar matches CS staff.
CS_ROLE = ("customer_service", "Customer Service")
CS_PERMS = [
    "projects.projects.view",
    "projects.projects.edit",
    "scm.dashboard.view",
]
# Acknowledging (Confirm) and rejecting an order inquiry row is purchasing's grant, never CS's:
# "CS ... must not be able to acknowledge their own instructions"
# (sorento_crm_backend/app/api/v1/projects/order_inquiries.py, ACKNOWLEDGE).
CS_PERMS_REMOVED = ("projects.order_inquiries.acknowledge",)
PURCHASING = {"name": "Pat Purchasing", "email": "purchasing@example.com", "phone": "012-000 0003"}
PURCHASING_ROLE = ("purchasing", "Purchasing")  # the existing role; only the two grants below are added
PURCHASING_PERMS = [
    "projects.projects.view",  # reading an inquiry (order_inquiries.py VIEW) and the menu entry
    "projects.order_inquiries.acknowledge",  # Confirm / Reject on a row (order_inquiries.py ACKNOWLEDGE)
]

AGENT_CODE = "SAM I"
CUSTOMERS = [
    # code, name, phone, email
    ("300-L001", "Lim Bina Hardware Sdn Bhd", "012-000 0101", "purchasing@limbina.example.com"),
    ("300-S002", "Seri Maju Tiles Enterprise", "012-000 0102", "orders@serimaju.example.com"),
    ("300-K003", "Kedai Jubin Harmoni", "012-000 0103", "kedai@jubinharmoni.example.com"),
    ("300-T004", "Tegas Renovation Supplies", "012-000 0104", "admin@tegasreno.example.com"),
]
# Dealer staff who hold portal access to Sam's accounts (Dealer access > People).
DEALER_PEOPLE = [
    ("012-000 0201", "Alan Lim", "300-L001"),
    ("012-000 0202", "Mei Chen", "300-S002"),
]
CHATBOT_CONTACT = {"phone": "012-000 0301", "name": "Ravi Kumar", "respond_io_id": "demo-respond-1301",
                   "customer": "300-K003"}

WAREHOUSES = [("MAIN", "Main Warehouse", "Jalan Demo 1, Klang"), ("SA", "Shah Alam Store", "Seksyen 15, Shah Alam")]
CATEGORIES = [("DM-BATH", "Bathroom Fittings"), ("DM-TILE", "Tiles")]
BRAND = ("DEMOLUX", "Demolux")
UOMS = [("UNIT", "Unit"), ("SET", "Set"), ("BOX", "Box")]
PRODUCTS = [
    # code, name, category, uom, list price, qty MAIN, qty SA
    ("DM-BS-1001", "Basin Mixer Chrome", "DM-BATH", "UNIT", "123.45", 48, 12),
    ("DM-BS-1002", "Basin Mixer Matte Black", "DM-BATH", "UNIT", "168.90", 30, 6),
    ("DM-WC-2002", "Wall Hung WC Set", "DM-BATH", "SET", "1288.00", 15, 4),
    ("DM-SH-3003", "Rain Shower Set Chrome", "DM-BATH", "SET", "689.50", 22, 8),
    ("DM-BA-4004", "Freestanding Bathtub 1700", "DM-BATH", "UNIT", "3450.00", 3, 1),
    ("DM-TL-6060", "Porcelain Tile 60x60 Grey", "DM-TILE", "BOX", "45.80", 900, 260),
    ("DM-TL-3060", "Ceramic Wall Tile 30x60 White", "DM-TILE", "BOX", "38.20", 640, 150),
    ("DM-TL-1212", "Mosaic Tile 30x30 Blue", "DM-TILE", "BOX", "62.75", 120, 40),
]
ROOT_CAUSES = ["Damaged in transit", "Manufacturing defect", "Wrong item delivered", "Installation error"]
RESOLUTIONS = ["Replace item", "Repair on site", "Credit note issued", "No fault found"]
# The complaint form's four dropdowns: set key -> (complaints column, set name, [(value, label)]).
# The portal form reads them by set key (SubmissionForm.tsx), the staff form by the binding.
COMPLAINT_LOOKUPS = {
    "complaints_customer_type": ("customer_type", "Complaint customer types", [
        ("dealer", "Dealer"), ("contractor", "Contractor"), ("end_user", "End user")]),
    "complaints_within_warranty": ("within_warranty", "Complaint warranty status", [
        ("yes", "Yes"), ("no", "No"), ("not_sure", "Not sure")]),
    "complaints_defects_discovered": ("defects_discovered", "Complaint defects discovered", [
        ("on_delivery", "On delivery"), ("during_installation", "During installation"),
        ("after_installation", "After installation")]),
    "complaints_complaint_type": ("complaint_type", "Complaint types", [
        ("product_defect", "Product defect"), ("delivery_issue", "Delivery issue"),
        ("wrong_item", "Wrong item"), ("missing_parts", "Missing parts")]),
}


def say(msg: str) -> None:
    print(f"  {msg}")


def msisdn(phone: str) -> str:
    from app.services.phone_utils import normalize_msisdn

    return normalize_msisdn(phone)


def legacy_phone(phone: str) -> str:
    """The number an earlier seed gave this row (012-000 1xxx), before the PII guard's fake
    shape (four zeros after 60 1x) moved them to 012-000 0xxx. Lets a re-run find and rewrite it."""
    return re.sub(r"^012-000 0", "012-000 1", phone)


def contact_phone(phone: str) -> str:
    from app.services.contact_setup_engine import normalise_phone

    return normalise_phone(phone)


def hash_pw(plain: str) -> str:
    # The app's own scheme (app/api/v1/auth.py signup + login check).
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@contextmanager
def unscoped(db):
    with company_scope(db, None):
        yield


# ============================================================================ P1


def seed_company(db):
    from app.models.company import Company

    with unscoped(db):
        company = db.query(Company).filter(Company.id == COMPANY_ID).one()
        if company.name != COMPANY_NAME:
            company.name = COMPANY_NAME
            say(f"company renamed to {COMPANY_NAME} (code {company.code})")
    return company


def seed_workspace(db):
    from app.models.respond_workspace import RespondWorkspace
    from app.utils.field_encryption import encrypt_secret

    ws = db.query(RespondWorkspace).filter(RespondWorkspace.space_id == "demo-space-0001").first()
    if ws is None:
        ws = RespondWorkspace(space_id="demo-space-0001", name="Demo Workspace",
                              api_key_ciphertext=encrypt_secret("demo-not-a-real-key"),
                              is_active=True, is_default=True)
        db.add(ws)
        db.flush()
        say("respond workspace Demo Workspace")
    # Reserved TLD: nothing sent through this workspace can reach the real Respond.io API.
    ws.base_url = "https://respond.invalid"
    return ws


def contact(db, phone: str, name: str, ws, *, respond_io_id: str | None = None, **extra):
    from app.models.access import RespondContact
    from app.models.company import RespondContactCompany

    # Stored the way Dealer access > Add people stores a number (+60...), so the People column
    # reads one format; rows from an earlier seed without the + are found and rewritten.
    number = contact_phone(phone)
    old = legacy_phone(phone)
    row = db.query(RespondContact).filter(RespondContact.phone_number.in_(
        [number, msisdn(phone), contact_phone(old), msisdn(old)])).first()
    if row is not None and row.phone_number != number:
        row.phone_number = number
    if row is None:
        row = RespondContact(phone_number=number, name=name, workspace_id=ws.id, respond_io_id=respond_io_id, **extra)
        db.add(row)
        db.flush()
        say(f"contact {name} ({phone})")
    else:
        row.name = name
        row.workspace_id = row.workspace_id or ws.id
        if respond_io_id and not row.respond_io_id:
            row.respond_io_id = respond_io_id
        for k, v in extra.items():
            setattr(row, k, v)
    if not db.query(RespondContactCompany).filter_by(respond_contact_id=row.id, company_id=COMPANY_ID).first():
        db.add(RespondContactCompany(respond_contact_id=row.id, company_id=COMPANY_ID))
    db.flush()
    return row


def role_with_perms(db, slug: str, name: str, perms: list[str], remove: tuple[str, ...] = ()):
    from app.models.user import UserPermission, UserRole, UserRolePermission

    role = db.query(UserRole).filter(UserRole.slug == slug).first()
    if role is None:
        role = UserRole(slug=slug, name=name, description="Demo role for training videos")
        db.add(role)
        db.flush()
        say(f"role {name}")
    have = {p for (p,) in db.query(UserRolePermission.permission_id).filter(UserRolePermission.role_id == role.id)}
    for slug_ in perms:
        perm = db.query(UserPermission).filter(UserPermission.slug == slug_).first()
        if perm is None:
            raise SystemExit(f"Permission {slug_} is not seeded in this database.")
        if perm.id not in have:
            db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
    for slug_ in remove:
        perm = db.query(UserPermission).filter(UserPermission.slug == slug_).first()
        if perm is not None:
            db.query(UserRolePermission).filter_by(role_id=role.id, permission_id=perm.id).delete()
    db.flush()
    return role


def user(db, spec: dict, role_slug: str, *, contact_row=None):
    from app.models.company import UserCompany
    from app.models.user import User, UserRole, UserRoleAssignment

    email = spec["email"].lower()
    row = db.query(User).filter(func.lower(User.email) == email).first()
    if row is None:
        row = User(email=email, name=spec["name"], contact_number=msisdn(spec["phone"]),
                   status="ACTIVE", password=hash_pw(PASSWORD), country="Malaysia",
                   timezone="Asia/Kuala_Lumpur", respond_synced="pending")
        db.add(row)
        db.flush()
        say(f"user {spec['name']} <{email}>")
    elif not row.password or not bcrypt.checkpw(PASSWORD.encode(), row.password.encode()):
        row.password = hash_pw(PASSWORD)
    row.contact_number = msisdn(spec["phone"])
    row.status = "ACTIVE"
    row.is_trashed = False
    row.last_active_company_id = COMPANY_ID
    if contact_row is not None:
        row.respond_contact_id = contact_row.id
    role = db.query(UserRole).filter(UserRole.slug == role_slug).one()
    if not db.query(UserRoleAssignment).filter_by(user_id=row.id, role_id=role.id).first():
        db.add(UserRoleAssignment(user_id=row.id, role_id=role.id))
    if not db.query(UserCompany).filter_by(user_id=row.id, company_id=COMPANY_ID).first():
        db.add(UserCompany(user_id=row.id, company_id=COMPANY_ID))
    db.flush()
    return row


def seed_agent_and_customers(db, sam_contact, admin):
    from app.models.order import Customer
    from app.models.sales_agent import SalesAgent

    agent = db.query(SalesAgent).filter(SalesAgent.sales_agent == AGENT_CODE).first()
    if agent is None:
        agent = SalesAgent(sales_agent=AGENT_CODE, description="Sam Sales", person_label="Sam Sales",
                           company_id=None, source="manual")
        db.add(agent)
        db.flush()
        say(f"sales agent {AGENT_CODE}")
    agent.is_active = True
    agent.contact_id = sam_contact.id

    customers = {}
    for code, name, phone, email in CUSTOMERS:
        row = db.query(Customer).filter(Customer.customer_code == code).first()
        if row is None:
            row = Customer(customer_code=code, customer_name=name, company_id=COMPANY_ID, is_active=True,
                           created_by=None, country="Malaysia")
            db.add(row)
            say(f"customer {code} {name}")
        row.customer_name = name
        row.phone_number = phone
        row.email = email
        row.sales_agent_id = agent.id
        row.account_owner_user_id = None
        row.is_active = True
        db.flush()
        customers[code] = row
    return agent, customers


def link_contact_customer(db, contact_row, customer):
    from app.models.access import RespondContactCustomer

    if not db.query(RespondContactCustomer).filter_by(contact_id=contact_row.id, customer_id=customer.id).first():
        db.add(RespondContactCustomer(contact_id=contact_row.id, customer_id=customer.id, is_primary=True,
                                      company_id=COMPANY_ID))
        db.flush()


def enable_form(db, contact_row, form_type: str):
    from app.models.price_tag import ContactPortalFormOverride

    row = db.query(ContactPortalFormOverride).filter_by(contact_id=contact_row.id, form_type=form_type).first()
    if row is None:
        db.add(ContactPortalFormOverride(contact_id=contact_row.id, form_type=form_type, is_enabled=True))
    else:
        row.is_enabled = True
    db.flush()


def seed_catalogue(db, admin):
    from app.models.inventory import Warehouse
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
    from app.services.stock_balance_ingest_service import StockBalanceIngestService

    for code, name, location in WAREHOUSES:
        if not db.query(Warehouse).filter(Warehouse.warehouse_code == code).first():
            db.add(Warehouse(warehouse_code=code, warehouse_name=name, location=location, is_active=True,
                             company_id=COMPANY_ID))
            say(f"warehouse {code} {name}")
    cats = {}
    for code, name in CATEGORIES:
        row = db.query(ProductCategory).filter(ProductCategory.category_code == code).first()
        if row is None:
            row = ProductCategory(category_code=code, category_name=name, company_id=COMPANY_ID)
            db.add(row)
        cats[code] = row
    brand = db.query(Brand).filter(Brand.brand_code == BRAND[0]).first()
    if brand is None:
        brand = Brand(brand_code=BRAND[0], brand_name=BRAND[1], company_id=COMPANY_ID)
        db.add(brand)
    uoms = {}
    for code, name in UOMS:
        row = db.query(UnitOfMeasure).filter(UnitOfMeasure.uom_code == code).first()
        if row is None:
            row = UnitOfMeasure(uom_code=code, uom_name=name, company_id=COMPANY_ID)
            db.add(row)
        uoms[code] = row
    db.flush()

    products = {}
    for code, name, cat, uom, price, _q1, _q2 in PRODUCTS:
        row = db.query(Product).filter(Product.product_code == code).first()
        if row is None:
            row = Product(product_code=code, product_name=name, category_id=cats[cat].id, brand_id=brand.id,
                          base_uom_id=uoms[uom].id, list_price=Decimal(price), is_active=True,
                          company_id=COMPANY_ID, description=name)
            db.add(row)
            say(f"product {code} {name} RM{price}")
        row.list_price = Decimal(price)
        row.product_name = name
        products[code] = row
    db.flush()

    # Stock through the AutoCount stock-balance ingest, so the ledger rows are the real ones.
    records = []
    for code, *_rest, q_main, q_sa in PRODUCTS:
        records.append({"source_ref": f"DEMO:{code}:MAIN", "item_code": code, "location_code": "MAIN", "qty": q_main})
        records.append({"source_ref": f"DEMO:{code}:SA", "item_code": code, "location_code": "SA", "qty": q_sa})
    result = StockBalanceIngestService(db, company_id=COMPANY_ID, actor_user_id=admin.id).ingest(
        "stock_balances", records
    )
    bad = [r for r in result.records if getattr(r, "outcome", None) and str(r.outcome).lower().endswith("failed")]
    if bad:
        raise SystemExit(f"stock ingest failed: {bad}")
    db.flush()
    return products


class _NoStorage:
    """The sandbox has no bucket. The tag template seed uploads its artwork; here the bytes go
    nowhere and the asset rows still get written by the real asset service."""

    def upload_file(self, file_content, file_path, content_type=None, **_):
        return file_path, f"https://demo.invalid/{file_path}"

    def delete_file(self, *_a, **_k):
        return True

    def get_cloudfront_base_url(self, key):
        return f"https://demo.invalid/{key}"

    get_cdn_base_url = get_cloudfront_base_url

    def __getattr__(self, name):
        def _noop(*_a, **_k):
            return None
        return _noop


def seed_tag_templates(db):
    from app.services import storage_router
    from scripts import seed_tag_templates as stt

    saved = dict(storage_router._backends)
    saved_env = storage_router._env_loaded
    storage_router._backends.update({"s3": _NoStorage(), "r2": _NoStorage()})
    storage_router._env_loaded = True  # never load the real .env's S3 / R2 keys into the seeder
    try:
        assets, result = stt.seed_assets(db, dry_run=False)
        stt.seed_templates(db, assets, result, dry_run=False)
    finally:
        storage_router._backends.clear()
        storage_router._backends.update(saved)
        storage_router._env_loaded = saved_env
    db.flush()
    say(f"tag templates: {result.summary()}")


# Which seeded template each product's tag is drawn on (one each, so the form never asks).
TEMPLATE_FOR_PREFIX = [("DM-BS", "Art Basin"), ("DM-WC", "Water Closet"), ("DM-SH", "Exposed Shower Set")]
TEMPLATE_DEFAULT = "Kitchen Sink - Ala Carte"


def publish_and_link_templates(db, products, admin):
    """Only a PUBLISHED template linked to the product draws in the form's Preview
    (product_tag_template_service.preview / published_items)."""
    from app.models.dealer_kit import TagTemplate
    from app.services.dealer_kit import product_tag_template_service, tag_template_service

    db.commit()  # publish() commits on its own
    by_name = {t.name: t for t in db.query(TagTemplate).all()}
    for template in by_name.values():
        if template.published_version_id is None:
            tag_template_service.publish(db, template, note="Demo seed", created_by=admin.id)
            say(f"published template {template.name}")
    for code, product in products.items():
        name = next((n for prefix, n in TEMPLATE_FOR_PREFIX if code.startswith(prefix)), TEMPLATE_DEFAULT)
        tid = by_name[name].id
        linked = [t.id for t in product_tag_template_service.linked_templates(db, product.id)]
        if linked != [tid]:
            product_tag_template_service.set_product_templates(
                db, product.id, [tid], user_id=admin.id,
                default_list_template_id=tid, default_selling_template_id=tid,
            )
            say(f"{code} tags on {name}")
    db.flush()


# Delivery orders the complaint video picks from (DO number search fills the product lines).
DELIVERY_ORDERS = [
    # number, customer code, days ago, [(product code, qty)]
    ("DO-DM-26101", "300-L001", 6, [("DM-BS-1001", 4), ("DM-WC-2002", 2)]),
    ("DO-DM-26102", "300-L001", 20, [("DM-SH-3003", 3)]),
    ("DO-DM-26103", "300-S002", 9, [("DM-TL-6060", 40)]),
]


def seed_delivery_orders(db, customers, products):
    from datetime import date, timedelta

    from app.models.inventory import Warehouse
    from app.models.order import Order, OrderLine

    main_wh = _need(db, Warehouse, warehouse_code="MAIN")
    for number, code, ago, lines in DELIVERY_ORDERS:
        if db.query(Order).filter(Order.order_number == number).first():
            continue
        cust = customers[code]
        order = Order(order_number=number, customer_id=cust.id, debtor_name=cust.customer_name,
                      order_date=date.today() - timedelta(days=ago), company_id=COMPANY_ID)
        db.add(order)
        db.flush()
        total = Decimal("0")
        for seq, (pcode, qty) in enumerate(lines, start=1):
            product = products[pcode]
            db.add(OrderLine(order_id=order.id, product_id=product.id, line_sequence=seq, quantity=Decimal(qty),
                                 warehouse_id=main_wh.id))
            total += product.list_price * qty
        order.subtotal_amount = order.total_amount = total
        db.flush()
        say(f"delivery order {number} for {cust.customer_name}")


# Rows a video creates, removed on every seed so a re-recording starts from the same screen.
VIDEO_PHONES = ["012-000 0401", "012-000 0402"]


def reset_video_rows(db):
    from app.models.access import (
        RespondContact, RespondContactCustomer, respond_contact_access_types, respond_contact_tags,
    )

    for phone in VIDEO_PHONES:
        forms = [contact_phone(phone), msisdn(phone), contact_phone(legacy_phone(phone)), msisdn(legacy_phone(phone))]
        for row in db.query(RespondContact).filter(RespondContact.phone_number.in_(forms)):
            db.query(RespondContactCustomer).filter_by(contact_id=row.id).delete()
            # Their level too (Business owner is a tag plus access types), so Add people starts from Employee.
            for table in (respond_contact_tags, respond_contact_access_types):
                db.execute(table.delete().where(table.c.contact_id == row.id))
            say(f"unlinked video contact {row.name}")
    # Complaints and price tag requests the salesperson filed in a video (child rows cascade).
    from app.models.complaints import Complaint
    from app.models.price_tag import PriceTagRequest

    old = legacy_phone(SALES["phone"])
    sam = db.query(RespondContact).filter(RespondContact.phone_number.in_(
        [contact_phone(SALES["phone"]), msisdn(SALES["phone"]), contact_phone(old), msisdn(old)])).first()
    if sam is not None:
        # A request's tag sheet (dealer_kit.page, slug tag-sheet-<doc number>) would outlive it with
        # request_id nulled, and the restarted numbering would then collide with the old slug on Approve.
        from app.models.dealer_kit import Page

        mine = db.query(PriceTagRequest.id).filter(PriceTagRequest.contact_id == sam.id)
        n = db.query(Page).filter(Page.kind == "tag_sheet", Page.request_id.in_(mine.scalar_subquery())
                                  ).delete(synchronize_session=False)
        if n:
            say(f"removed {n} video tag sheets")
        for model, what in ((Complaint, "complaints"), (PriceTagRequest, "price tag requests")):
            n = db.query(model).filter(model.contact_id == sam.id).delete(synchronize_session=False)
            if n:
                say(f"removed {n} video {what}")
    db.flush()


def seed_dealer_access_setup(db):
    """What Dealer access > Add people needs and production already holds: the Business owner
    tag (migration dap_0001, wiped by the test-DB reset), the template's stock locations and
    chatbot agents (contact_access_sheet_service.TEMPLATE)."""
    from app.models.access import AccessAgent, ContactAccessType, ContactTag
    from app.models.inventory import Warehouse
    from app.services.contact_access_sheet_service import TEMPLATE

    types = {"end_user": "End user", "dealer": "Dealer", "cabana_dealer": "Cabana dealer", "mocha_dealer": "Mocha dealer"}
    for i, (code, name) in enumerate(types.items()):
        if db.get(ContactAccessType, code) is None:
            db.add(ContactAccessType(code=code, name=name, is_active=True, sort_order=i, keywords=[]))

    if not db.query(ContactTag).filter(func.lower(ContactTag.name) == "sorento business owner").first():
        db.add(ContactTag(name="Sorento Business Owner", is_active=True, sort_order=0,
                          settings={"access_types": ["dealer", "cabana_dealer"]}))
    from app.models.access import MarketSegment

    if not db.query(MarketSegment).filter(MarketSegment.code == TEMPLATE["segment"]).first():
        db.add(MarketSegment(code=TEMPLATE["segment"], name="Retail", is_active=True, sort_order=0,
                             is_requestor_selectable=False, portal_form_types=[]))
    names = {"BRW": "Showroom Store", "MWH": "Central Warehouse"}
    for code in TEMPLATE["locations"]["SRT"]:
        if not db.query(Warehouse).filter(Warehouse.warehouse_code == code).first():
            db.add(Warehouse(warehouse_code=code, warehouse_name=names.get(code, code), is_active=True,
                             company_id=COMPANY_ID, location="Klang"))
    for code in TEMPLATE["agents"]:
        if not db.query(AccessAgent).filter(AccessAgent.code == code).first():
            db.add(AccessAgent(code=code, name=code.replace("_", " ").title(), is_active=True,
                               assign_to_new_internal_contacts=False, in_parser_prompt=False,
                               synced_to_excel=False))
    db.flush()
    say("dealer access setup: owner tag, stock locations, chatbot agents")


def seed_complaint_master(db):
    from app.models.complaint_master_data import ComplaintResolution, ComplaintRootCause
    from app.models.lookup import LookupBinding, LookupOption, LookupSet

    for model, names in ((ComplaintRootCause, ROOT_CAUSES), (ComplaintResolution, RESOLUTIONS)):
        for name in names:
            if not db.query(model).filter(model.name == name).first():
                db.add(model(name=name, is_active=True))
    # An earlier seed used the bare key "complaint_type", which the portal form never reads.
    legacy = db.query(LookupSet).filter(LookupSet.set_key == "complaint_type").first()
    if legacy is not None and not db.query(LookupSet).filter(LookupSet.set_key == "complaints_complaint_type").first():
        legacy.set_key = "complaints_complaint_type"
        db.flush()
    for set_key, (column, name, options) in COMPLAINT_LOOKUPS.items():
        lset = db.query(LookupSet).filter(LookupSet.set_key == set_key).first()
        if lset is None:
            lset = LookupSet(set_key=set_key, name=name, is_active=True)
            db.add(lset)
            db.flush()
        for i, (value, label) in enumerate(options):
            if not db.query(LookupOption).filter_by(set_id=lset.id, value=value).first():
                db.add(LookupOption(set_id=lset.id, value=value, label=label, sort_order=i, is_active=True))
        if not db.query(LookupBinding).filter_by(table_name="complaints", column_name=column).first():
            db.add(LookupBinding(set_id=lset.id, table_name="complaints", column_name=column))
    db.flush()
    say("complaint root causes, resolutions, complaint form dropdowns")


def seed_modules(db):
    """Switch every catalogue module on for the default tenant. A fresh schema has no
    tenant_modules rows, and the frontend's route guard then sends every module page home."""
    from app.models.app_modules import AppModuleCatalog
    from app.modules.runtime.installer import DEFAULT_TENANT_ID, install_modules

    keys = [r.module_key for r in db.query(AppModuleCatalog).all()]
    install_modules(db, DEFAULT_TENANT_ID, keys, None, action="install")
    say(f"modules: {len(keys)} enabled")


def seed_p1(db) -> dict:
    print("p1:")
    seed_company(db)
    seed_modules(db)
    ws = seed_workspace(db)
    sam_contact = contact(db, SALES["phone"], SALES["name"], ws)
    role_with_perms(db, "salesperson", "Salesperson", SALES_PERMS, tuple(SALES_PERMS_REMOVED))
    admin = user(db, ADMIN, "superadmin")
    sam = user(db, SALES, "salesperson", contact_row=sam_contact)
    enable_form(db, sam_contact, "price_tag_request")
    agent, customers = seed_agent_and_customers(db, sam_contact, admin)
    for phone, name, code in DEALER_PEOPLE:
        link_contact_customer(db, contact(db, phone, name, ws), customers[code])
    bot = contact(db, CHATBOT_CONTACT["phone"], CHATBOT_CONTACT["name"], ws,
                  respond_io_id=CHATBOT_CONTACT["respond_io_id"], chatbot_allowed=True)
    link_contact_customer(db, bot, customers[CHATBOT_CONTACT["customer"]])
    products = seed_catalogue(db, admin)
    seed_tag_templates(db)
    publish_and_link_templates(db, products, admin)
    seed_complaint_master(db)
    seed_delivery_orders(db, customers, products)
    seed_dealer_access_setup(db)
    reset_video_rows(db)
    db.commit()
    return {"admin": admin.id, "sam": sam.id, "agent": agent.id}


# ============================================================================ P2


# The sandbox backend that reads this same sorento_ci_tv DB, e.g. http://127.0.0.1:8477/api/v1. No
# default: on a shared machine localhost:8000 can be another lane's backend on another database.
API = os.environ.get("TV_API_URL", "").rstrip("/")

PROJECT_TITLE = "Taman Demo Residences"
BUYER = ("300-B005", "Bina Jaya Builders Sdn Bhd", "012-000 0105", "procurement@binajaya.example.com")
DEVELOPER = "Demo Land Development Sdn Bhd"
CLIENT_PO_NUMBER = "BJB/PO/2026/0418"
# Two published orders: Tower A (from the client PO, partly decided, for Fulfilment Planning and
# the amendment) and Tower B (every line bought, its inquiry rows walked through each state).
ORDERS = [
    {"ref": "PS-DM-0001", "area": "TOWER A", "so_number": "SO-DM-26001", "from_po": True, "buy_lines": [1, 2]},
    {"ref": "PS-DM-0002", "area": "TOWER B", "so_number": "SO-DM-26002", "from_po": False,
     "buy_lines": [1, 2, 3, 4]},
]
SUPPLIER = ("SUP-DM-01", "Demo Sanitary Supply Co. Ltd")
SUPPLIER_PO = "PO-DM-26001"


def _po_lines():
    """(product code, qty on PO v1, qty on the revised PO v2, delivery date)."""
    from datetime import date

    return [
        ("DM-WC-2002", 120, 100, date(2027, 1, 15)),
        ("DM-BS-1001", 240, 280, date(2027, 1, 15)),
        ("DM-SH-3003", 120, 120, date(2027, 2, 15)),
        ("DM-TL-6060", 800, 800, date(2027, 3, 1)),
    ]


def http(method: str, path: str, token: str | None = None, body=None):
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(API + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode()[:800]}") from None


def login(email: str) -> str:
    return http("POST", "/auth/login", body={"email": email, "password": PASSWORD})["token"]


def _need(db, model, **by):
    row = db.query(model).filter_by(**by).first()
    if row is None:
        raise SystemExit(f"{model.__name__} {by} missing: run --part p1 first.")
    return row


def seed_party_roles(db):
    """Reference data migration ppr_0001 writes, missing from this create_all-bootstrapped sandbox
    (tests/conftest.py seeds it the same way). Without it every party link is refused."""
    from app.models.lookup import LookupOption, LookupSet
    from app.services import project_party_roles

    lset = db.query(LookupSet).filter(LookupSet.set_key == project_party_roles.SET_KEY).first()
    if lset is None:
        lset = LookupSet(set_key=project_party_roles.SET_KEY, name=project_party_roles.SET_NAME, is_active=True)
        db.add(lset)
        db.flush()
        say("lookup set project_party_role")
    for order, (value, label, many) in enumerate(project_party_roles.SEED_ROLES, start=1):
        if not db.query(LookupOption).filter_by(set_id=lset.id, value=value).first():
            db.add(LookupOption(set_id=lset.id, value=value, label=label, sort_order=order * 10,
                                is_active=True, allows_many=many))
    db.flush()


def seed_project(db, sam, chloe, agent):
    from app.models.order import Customer
    from app.models.projects import Project, ProjectParty
    from app.services import project_party_contact_service, project_service

    code, name, phone, email = BUYER
    buyer = db.query(Customer).filter(Customer.customer_code == code).first()
    if buyer is None:
        buyer = Customer(customer_code=code, customer_name=name, company_id=COMPANY_ID, is_active=True,
                         phone_number=phone, email=email, country="Malaysia", sales_agent_id=agent.id)
        db.add(buyer)
        db.flush()
        say(f"customer {code} {name}")
    buyer.phone_number = phone

    def party(party_type, party_name, customer_id=None):
        row = db.query(ProjectParty).filter_by(party_type=party_type, name=party_name).first()
        if row is None:
            row = ProjectParty(company_id=COMPANY_ID, party_type=party_type, name=party_name,
                               customer_id=customer_id, is_active=True, created_by=sam.id)
            db.add(row)
            db.flush()
        return row

    developer = party("developer", DEVELOPER)
    contractor = party("main_contractor", name, buyer.id)

    project = db.query(Project).filter(Project.title == PROJECT_TITLE).first()
    if project is None:
        project = project_service.register_project(
            db, company_id=COMPANY_ID, actor_user_id=sam.id, developer_party_id=developer.id,
            title=PROJECT_TITLE, owner_user_id=sam.id,
            details={"location": "Jalan Demo 3, Bandar Baru Bangi, 43650 Selangor"},
        )
        project_party_contact_service.set_party_links(
            db, project, [{"role": "main_contractor", "party_id": str(contractor.id)}]
        )
        db.flush()
        say(f"project {project.project_code} {PROJECT_TITLE}")
    if not project.admin_ref:
        project.admin_ref = "PS26-DEMO"
    # CS works the project's orders (Confirm, amendments): an edit right on a project is owner,
    # collaborator or manager (project_service.can_edit_project).
    project_service._add_collaborator(db, project.id, chloe.id, granted_by=sam.id)
    return project, buyer, contractor


def seed_client_po(db, project, contractor, products, chloe):
    """The contractor's PO as two read versions: v1 confirmed (what Tower A is built from) and the
    revised v2 (two quantities moved), which is what the amendment compares against."""
    from datetime import date

    from app.models.project_so import ProjectPOLine, ProjectPOVersion
    from app.models.projects import ProjectPurchaseOrder
    from app.services.project_po_extraction_service import ProjectPOExtractionService

    po = db.query(ProjectPurchaseOrder).filter_by(project_id=project.id, po_number=CLIENT_PO_NUMBER).first()
    if po is None:
        po = ProjectPurchaseOrder(company_id=COMPANY_ID, project_id=project.id, po_number=CLIENT_PO_NUMBER,
                                  po_date=date(2026, 10, 20), issuing_party_id=contractor.id)
        db.add(po)
        db.flush()
        say(f"client PO {CLIENT_PO_NUMBER}")

    versions = {}
    for version_no, qty_index in ((1, 1), (2, 2)):
        version = db.query(ProjectPOVersion).filter_by(purchase_order_id=po.id, version_no=version_no).first()
        if version is None:
            version = ProjectPOVersion(
                company_id=COMPANY_ID, purchase_order_id=po.id, version_no=version_no,
                source_filename=f"BJB-PO-0418{'-rev1' if version_no == 2 else ''}.pdf", page_count=1,
                extraction_state="done",
                extracted_json={"header": {"po_number": CLIENT_PO_NUMBER, "po_date": "2026-10-20"}},
            )
            db.add(version)
            db.flush()
            for i, line in enumerate(_po_lines(), start=1):
                product = products[line[0]]
                qty = Decimal(line[qty_index])
                db.add(ProjectPOLine(
                    company_id=COMPANY_ID, po_version_id=version.id, line_no=i, stock_code_raw=line[0],
                    description_raw=product.product_name, qty=qty, uom_raw="UNIT",
                    unit_price=product.list_price, amount=(qty * product.list_price).quantize(Decimal("0.01")),
                    resolved_product_id=product.id, resolution_source="code", arithmetic_ok=True,
                ))
            db.flush()
            say(f"client PO version {version_no}")
        versions[version_no] = version
    if versions[1].confirmed_at is None:
        ProjectPOExtractionService(db).confirm_version(version=versions[1], actor_user_id=chloe.id)
        db.flush()
        say("client PO version 1 confirmed")
    return po, versions


def seed_orders(db, project, buyer, agent, products, po, versions, chloe):
    from app.models.inventory import Warehouse
    from app.models.order import SalesOrder, SalesOrderLine
    from app.models.project_so import (
        SO_STATUS_DRAFT, ProjectPOLine, ProjectSalesOrder, ProjectSalesOrderLine,
    )
    from app.services.project_so_draft_service import ProjectSODraftService
    from app.services.project_so_reconciliation_service import ProjectSOReconciliationService

    main_wh = _need(db, Warehouse, warehouse_code="MAIN")
    po_lines = {
        r.line_no: r for r in db.query(ProjectPOLine).filter_by(po_version_id=versions[1].id)
    }
    out = []
    for spec in ORDERS:
        order = db.query(ProjectSalesOrder).filter_by(provisional_ref=spec["ref"]).first()
        if order is None:
            order = ProjectSalesOrder(
                company_id=COMPANY_ID, project_id=project.id, area_group=spec["area"],
                provisional_ref=spec["ref"], status=SO_STATUS_DRAFT, grouping_origin="area",
                purchase_order_id=po.id if spec["from_po"] else None,
            )
            db.add(order)
            db.flush()
            for i, (code, qty, _qty2, when) in enumerate(_po_lines(), start=1):
                product = products[code]
                db.add(ProjectSalesOrderLine(
                    company_id=COMPANY_ID, project_sales_order_id=order.id, line_no=i,
                    product_id=product.id, description=product.product_name, qty=Decimal(qty), uom="UNIT",
                    unit_price=product.list_price, amount=(Decimal(qty) * product.list_price),
                    delivery_date=when, explosion_source="direct",
                    source_po_line_id=po_lines[i].id if spec["from_po"] else None,
                ))
            db.flush()
            order.total_amount = sum(
                (l.amount for l in db.query(ProjectSalesOrderLine).filter_by(project_sales_order_id=order.id)),
                Decimal("0"),
            )
            ProjectSODraftService(db).publish(order, actor_user_id=chloe.id)
            db.flush()
            say(f"project SO {spec['ref']} ({spec['area']}) published")

        # What AutoCount sends back for it: the real-numbered sales order on the outstanding book.
        core = db.query(SalesOrder).filter(SalesOrder.so_number == spec["so_number"]).first()
        if core is None:
            core = SalesOrder(company_id=COMPANY_ID, so_number=spec["so_number"], customer_id=buyer.id,
                              debtor_code=buyer.customer_code, debtor_name=buyer.customer_name,
                              sales_agent_id=agent.id, order_date=_today(),
                              status="open", demand_class="project", project_label=PROJECT_TITLE)
            db.add(core)
            db.flush()
            for line in db.query(ProjectSalesOrderLine).filter_by(project_sales_order_id=order.id).order_by(
                ProjectSalesOrderLine.line_no
            ):
                db.add(SalesOrderLine(company_id=COMPANY_ID, sales_order_id=core.id, product_id=line.product_id,
                                      warehouse_id=main_wh.id, qty_ordered=line.qty, qty_delivered=Decimal("0"),
                                      required_date=line.delivery_date, line_status="open"))
            db.flush()
            say(f"core sales order {spec['so_number']}")
        if not order.autocount_doc_no:
            order.autocount_doc_no = spec["so_number"]
        ProjectSOReconciliationService(db).reconcile(order)
        db.flush()
        out.append((spec, order))
    return out


def _today():
    from datetime import date

    return date.today()


def seed_supplier_po(db, products):
    from app.models.inventory import Warehouse
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier

    supplier = db.query(Supplier).filter_by(supplier_code=SUPPLIER[0]).first()
    if supplier is None:
        supplier = Supplier(company_id=COMPANY_ID, supplier_code=SUPPLIER[0], supplier_name=SUPPLIER[1],
                            is_active=True)
        db.add(supplier)
        db.flush()
    po = db.query(PurchaseOrder).filter_by(po_number=SUPPLIER_PO).first()
    if po is None:
        po = PurchaseOrder(company_id=COMPANY_ID, po_number=SUPPLIER_PO, supplier_id=supplier.id, status="open")
        db.add(po)
        db.flush()
        main_wh = _need(db, Warehouse, warehouse_code="MAIN")
        for code, qty in (("DM-BS-1001", 300), ("DM-SH-3003", 150)):
            db.add(PurchaseOrderLine(company_id=COMPANY_ID, purchase_order_id=po.id, product_id=products[code].id,
                                     warehouse_id=main_wh.id, qty_ordered=Decimal(qty), qty_received=Decimal("0"),
                                     line_status="open"))
        db.flush()
        say(f"supplier PO {SUPPLIER_PO}")
    return po


def reset_p2_video_rows(db):
    """The split delivery video saves splits on Tower A's lines; remove them so it starts unsplit."""
    from app.models.project_so import ProjectSalesOrder, SOLineSplit

    refs = [spec["ref"] for spec in ORDERS]
    ids = [o.id for o in db.query(ProjectSalesOrder).filter(ProjectSalesOrder.provisional_ref.in_(refs))]
    if ids:
        n = db.query(SOLineSplit).filter(SOLineSplit.project_sales_order_id.in_(ids)).delete(synchronize_session=False)
        if n:
            say(f"removed {n} video line splits")
        # The order inquiry video confirms a Tower A row: put it back to awaiting purchasing.
        from app.models.project_so import ACK_ACKNOWLEDGED, ACK_AWAITING, OrderInquiry, OrderInquiryRow

        tower_a = db.query(ProjectSalesOrder.id).filter(ProjectSalesOrder.provisional_ref == ORDERS[0]["ref"])
        inquiry_ids = db.query(OrderInquiry.id).filter(
            OrderInquiry.project_sales_order_id.in_(tower_a.scalar_subquery()))
        n = db.query(OrderInquiryRow).filter(
            OrderInquiryRow.order_inquiry_id.in_(inquiry_ids.scalar_subquery()),
            OrderInquiryRow.ack_state == ACK_ACKNOWLEDGED,
        ).update({
            OrderInquiryRow.ack_state: ACK_AWAITING, OrderInquiryRow.acknowledged_by: None,
            OrderInquiryRow.acknowledged_at: None, OrderInquiryRow.ack_override: None,
            OrderInquiryRow.ack_override_by: None, OrderInquiryRow.ack_override_at: None,
        }, synchronize_session=False)
        if n:
            say(f"reset {n} confirmed video inquiry rows")
    db.flush()


REJECT_REASON = "Supplier has stopped this model."


def _check_api_serves_this_db(order) -> str:
    """Before any write over HTTP: TV_API_URL must be the backend on THIS database. No anonymous
    route answers from the DB, so this signs CS in (that session row is the only write) and reads
    the Tower A order this run just wrote by its id; a backend on any other DB answers 404."""
    import urllib.error
    import urllib.request

    token = login(CS["email"])
    req = urllib.request.Request(f"{API}/project-sales/sales-orders/{order.id}/line-splits",
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"TV_API_URL {API} cannot read order {order.provisional_ref} ({exc.code}): "
                         "it is not the backend on this database.") from None
    return token


def _has_open_rejection(db, order_id) -> bool:
    """A line of this order whose current inquiry row purchasing rejected (not yet re-decided)."""
    from app.models.project_so import ACK_REJECTED, INQUIRY_CANCELLED, OrderInquiry, OrderInquiryRow

    return db.query(OrderInquiryRow).join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id).filter(
        OrderInquiry.project_sales_order_id == order_id,
        OrderInquiryRow.ack_state == ACK_REJECTED,
        OrderInquiryRow.state != INQUIRY_CANCELLED,
    ).first() is not None


def seed_p2(db) -> dict:
    from app.models.inventory import Warehouse
    from app.models.product import Product
    from app.models.project_so import (
        ACK_AWAITING, INQUIRY_ACTIONED, INQUIRY_CANCELLED, INQUIRY_RAISED, OrderInquiry, OrderInquiryRow,
        ProjectSalesOrderLine, SOSupplyDecision,
    )
    from app.models.procurement import PurchaseOrderLine
    from app.models.sales_agent import SalesAgent
    from app.models.user import User

    print("p2:")
    sam = _need(db, User, email=SALES["email"])
    agent = _need(db, SalesAgent, sales_agent=AGENT_CODE)
    products = {code: _need(db, Product, product_code=code) for code, *_ in PRODUCTS}
    for wh in db.query(Warehouse).filter(Warehouse.warehouse_code.in_([w[0] for w in WAREHOUSES])):
        wh.fulfilment_planning = True

    from app.models.user import UserRole

    # An earlier seed made the role as customer_service_demo; give it the real slug.
    legacy = db.query(UserRole).filter(UserRole.slug == "customer_service_demo").first()
    if legacy is not None and not db.query(UserRole).filter(UserRole.slug == CS_ROLE[0]).first():
        legacy.slug = CS_ROLE[0]
        db.flush()
    role_with_perms(db, CS_ROLE[0], CS_ROLE[1], CS_PERMS, remove=CS_PERMS_REMOVED)
    chloe = user(db, CS, CS_ROLE[0])
    role_with_perms(db, PURCHASING_ROLE[0], PURCHASING_ROLE[1], PURCHASING_PERMS)
    user(db, PURCHASING, PURCHASING_ROLE[0])

    seed_party_roles(db)
    reset_p2_video_rows(db)
    project, buyer, contractor = seed_project(db, sam, chloe, agent)
    po, versions = seed_client_po(db, project, contractor, products, chloe)
    orders = seed_orders(db, project, buyer, agent, products, po, versions, chloe)
    supplier_po = seed_supplier_po(db, products)
    db.commit()

    # The Buy decision through the real CS confirmation route; refresh_for_decision runs inside it.
    cs_token = _check_api_serves_this_db(orders[0][1])
    for spec, order in orders:
        decided = db.query(SOSupplyDecision).filter_by(project_sales_order_id=order.id).first()
        # A take of the purchasing flow may have rejected a Tower A line; CS deciding it again
        # (the same confirm) raises a fresh row, which is how the screen itself recovers.
        if decided and not (spec is ORDERS[0] and _has_open_rejection(db, order.id)):
            continue
        cs_token = cs_token or login(CS["email"])
        lines = (db.query(ProjectSalesOrderLine).filter_by(project_sales_order_id=order.id)
                 .order_by(ProjectSalesOrderLine.line_no).all())
        body = {"lines": [
            {"project_line_id": str(l.id), "timely_spo_qty": "0", "reserve": [], "borrow": [],
             "buy_qty": str(l.qty)}
            for l in lines if l.line_no in spec["buy_lines"]
        ]}
        result = http("POST", f"/project-sales/sales-orders/{order.id}/confirm", cs_token, body)
        held = result.get("lines_held_back") if isinstance(result, dict) else None
        say(f"{spec['ref']}: Buy confirmed on lines {spec['buy_lines']}" + (f" (held back: {held})" if held else ""))
    db.expire_all()

    # Tower B's rows: one left raised, one actioned, one placed on the supplier PO, one cancelled.
    tower_b = orders[1][1]
    inquiry = db.query(OrderInquiry).filter_by(project_sales_order_id=tower_b.id).first()
    if inquiry is None:
        raise SystemExit("Tower B confirmation raised no order inquiry.")
    def current_rows():
        """{line_no: row}; a cancelled history row never hides the line's current one."""
        out = {}
        for row, line_no in (db.query(OrderInquiryRow, ProjectSalesOrderLine.line_no)
                             .join(ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id)
                             .filter(OrderInquiryRow.order_inquiry_id == inquiry.id)
                             .order_by(ProjectSalesOrderLine.line_no)):
            if line_no not in out or out[line_no].state == INQUIRY_CANCELLED:
                out[line_no] = row
        return out

    by_line = current_rows()
    # Line 1 is refused by purchasing with a reason, through the real reject route, so the
    # order inquiry video can show a Rejected line. First: a reject rewrites the order's plan.
    first = by_line.get(1)
    if first is not None and first.state == INQUIRY_RAISED and first.ack_state == ACK_AWAITING:
        http("POST", f"/project-sales/order-inquiries/{first.id}/reject", login(PURCHASING["email"]),
             {"reason": REJECT_REASON})
        say(f"{inquiry.inquiry_no} line 1: rejected by purchasing")
        db.expire_all()
        by_line = current_rows()
    admin_token = None
    plan = {2: INQUIRY_ACTIONED, 3: "placed", 4: INQUIRY_CANCELLED}
    for line_no, target in plan.items():
        row = by_line.get(line_no)
        if row is None or row.state != INQUIRY_RAISED:
            continue
        admin_token = admin_token or login(ADMIN["email"])
        if target == "placed":
            product = db.query(Product).filter(Product.product_code == row.item_code).one()
            po_line = db.query(PurchaseOrderLine).filter_by(
                purchase_order_id=supplier_po.id, product_id=product.id).first()
            http("POST", f"/project-sales/order-inquiry-rows/{row.id}/place-on-po", admin_token,
                 {"po_line_id": str(po_line.id)})
        else:
            http("POST", "/project-sales/order-inquiry-rows/mark", admin_token,
                 {"row_ids": [str(row.id)], "state": target})
        say(f"{inquiry.inquiry_no} line {line_no}: {target}")
    db.expire_all()
    return {"project": project.id, "orders": [o.id for _s, o in orders], "inquiry": inquiry.inquiry_no}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--part", choices=["p1", "p2", "all"], default="all")
    args = parser.parse_args()
    if args.part in ("p2", "all") and not API:
        raise SystemExit("Part p2 calls the sandbox backend: set TV_API_URL (e.g. http://127.0.0.1:8477/api/v1).")

    register_company_scope_listeners()
    db = SessionLocal()
    try:
        with company_scope(db, frozenset({COMPANY_ID})):
            if args.part in ("p1", "all"):
                seed_p1(db)
            if args.part in ("p2", "all"):
                seed_p2(db)
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
    print("done.")


if __name__ == "__main__":
    main()
