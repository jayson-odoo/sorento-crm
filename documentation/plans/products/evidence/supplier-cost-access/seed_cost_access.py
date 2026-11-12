"""Throwaway seed for the SUPPLIER-COST-ACCESS browser pass (ZZT-prefixed data).
Run from sorento_crm_backend: SORENTO_ENV_FILE=.env.ci-tests venv/bin/python <this file>
Sandbox DB only. Logins: zzt.sales@example.com / zzt.buyer@example.com, password from ZZT_SEED_PASSWORD."""
import os, sys, uuid
from decimal import Decimal
import bcrypt
sys.path.insert(0, os.getcwd())
from app.database import SessionLocal
from app.models.audit import AuditLog
from app.models.company import UserCompany
from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import (User, UserPermission, UserRole, UserRolePermission,
                             UserRoleAssignment)

COMPANY = "00000000-0000-0000-0000-000000000001"
PASSWORD = os.environ["ZZT_SEED_PASSWORD"]  # sandbox-only login, set when seeding
BASE = ["master_data.products.view", "master_data.products.edit",
        "procurement.product_suppliers.view"]
u = lambda: str(uuid.uuid4())
db = SessionLocal()
pw = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()


def role_with(slug, name, perms):
    role = UserRole(id=u(), slug=slug, name=name)
    db.add(role); db.flush()
    for p in perms:
        pid = db.query(UserPermission.id).filter(UserPermission.slug == p).scalar()
        assert pid, p
        db.add(UserRolePermission(id=u(), role_id=role.id, permission_id=pid))
    db.flush()
    return role


def user(name, email, role):
    row = User(id=u(), email=email, name=name, password=pw, status="ACTIVE",
               last_active_company_id=COMPANY, email_verified_at=None)
    db.add(row); db.flush()
    db.add(UserRoleAssignment(id=u(), user_id=row.id, role_id=role.id))
    db.add(UserCompany(id=u(), user_id=row.id, company_id=COMPANY))
    db.flush()
    return row

sales_role = role_with("zzt-sales", "ZZT Sales", BASE)
buyer_role = role_with("zzt-buyer", "ZZT Buyer", BASE + ["products.cost.view"])
sales = user("ZZT Sales", "zzt.sales@example.com", sales_role)
buyer = user("ZZT Buyer", "zzt.buyer@example.com", buyer_role)

uom = UnitOfMeasure(id=u(), company_id=COMPANY, uom_code="ZZTU", uom_name="ZZT Unit")
cat = ProductCategory(id=u(), company_id=COMPANY, category_code="ZZT-CAT", category_name="ZZT Category")
db.add_all([uom, cat]); db.flush()
prod = Product(id=u(), company_id=COMPANY, product_code="ZZT-COST-1", product_name="ZZT Cost Product",
               category_id=cat.id, base_uom_id=uom.id, list_price=Decimal("300.00"),
               cost_price=Decimal("125.00"), invoice_price=Decimal("280.00"))
sup = Supplier(id=u(), company_id=COMPANY, supplier_code="ZZT-SUP", supplier_name="ZZT Supplier Sdn Bhd")
db.add_all([prod, sup]); db.flush()
db.add(ProductSupplier(id=u(), company_id=COMPANY, product_id=prod.id, supplier_id=sup.id,
                       standard_lead_time_days=14, unit_cost=Decimal("9.99"), currency="MYR",
                       is_primary_supplier=True))
db.add(AuditLog(id=u(), entity_type="product", entity_id=prod.id, action="UPDATE", user_id=buyer.id,
                actor_type="user", company_id=COMPANY, old_values={"cost_price": "120.00"},
                new_values={"cost_price": "125.00"}))
db.commit()
print("product", prod.id, "sales", sales.id, "buyer", buyer.id)

# Sidebar items are hidden until the tenant has its modules installed (empty sandbox DB).
from app.modules.runtime.installer import DEFAULT_TENANT_ID, install_modules, load_dependency_graph
install_modules(db, DEFAULT_TENANT_ID, sorted(load_dependency_graph(db)), None, action="install")
db.commit()
