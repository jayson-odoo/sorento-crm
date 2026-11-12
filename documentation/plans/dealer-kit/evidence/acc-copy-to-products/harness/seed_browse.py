"""Synthetic seed for the ACC-COPY-TO-PRODUCTS browser pass. Sandbox DB (sorento_browse) only.

Run from sorento_crm_backend:
  SORENTO_ENV_FILE=.env.browse BROWSE_ADMIN_PASSWORD=... venv/bin/python <this file>

Writes (all names invented): a superadmin and a view-only user, categories ZZ Bathtub / ZZ Basin, brand
ZZ Brand, a saved accessories template "ZZ FREE box", three library accessories (PRESSURE PUMP, SOAP AND
BATH BOMB SET, FREESTANDING MIXER TAP) and five products:
  ZZBT-1001 source bathtub: list PUMP (name override + remark), SOAP, TAP; box style ZZ FREE box
  ZZBT-1002 bathtub, no list
  ZZBT-1003 bathtub, own list: SOAP (own remark) + its own TOWEL RAIL; own box style "ZZ Own box"
  ZZBT-1004 bathtub, no list
  ZZBS-2001 basin (other category), no list
Installs every module for the default tenant.
"""
from __future__ import annotations

import os
import sys
import uuid

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")
from app.main import app  # noqa: E402,F401  (import order: circular import)
from app.database import engine  # noqa: E402
from app.models.accessory import Accessory, ProductAccessory  # noqa: E402
from app.models.company import UserCompany  # noqa: E402
from app.models.dealer_kit import AccessoryBoxPreset  # noqa: E402
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure  # noqa: E402
from app.models.user import User, UserRoleAssignment  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
PASSWORD = os.environ["BROWSE_ADMIN_PASSWORD"]  # throwaway, sandbox DB only
db = sessionmaker(bind=engine)()


def u() -> str:
    return str(uuid.uuid4())


def user(email, name, role_sql):
    row = db.query(User).filter(User.email == email).one_or_none()
    if row is not None:
        return row
    row = User(id=u(), email=email, name=name, status="ACTIVE",
               password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode())
    db.add(row)
    db.flush()
    db.add(UserRoleAssignment(user_id=row.id, role_id=db.execute(text(role_sql)).scalar()))
    db.add(UserCompany(id=u(), user_id=row.id, company_id=COMPANY))
    db.flush()
    return row


admin = user("browse.admin@example.com", "Browse Admin",
             "SELECT id FROM user_roles WHERE slug IN ('superadmin','super_admin') OR name ILIKE 'super admin' LIMIT 1")

# View-only role: products view, no edit.
viewer_role = db.execute(text("SELECT id FROM user_roles WHERE slug = 'zz_viewer'")).scalar()
if viewer_role is None:
    viewer_role = u()
    db.execute(text("INSERT INTO user_roles (id, name, slug, is_trashed, is_protected, is_default) VALUES (:i, 'ZZ Viewer', 'zz_viewer', false, false, false)"),
               {"i": viewer_role})
    perm = db.execute(text("SELECT id FROM user_permissions WHERE slug = 'master_data.products.view'")).scalar()
    db.execute(text("INSERT INTO user_role_permissions (id, role_id, permission_id) VALUES (:i, :r, :p)"),
               {"i": u(), "r": viewer_role, "p": perm})
db.flush()
user("browse.viewer@example.com", "Browse Viewer", "SELECT id FROM user_roles WHERE slug = 'zz_viewer'")

tub = ProductCategory(id=u(), company_id=COMPANY, category_code="ZZ-BT", category_name="ZZ Bathtub")
basin = ProductCategory(id=u(), company_id=COMPANY, category_code="ZZ-BS", category_name="ZZ Basin")
uom = UnitOfMeasure(id=u(), company_id=COMPANY, uom_code="ZZEA", uom_name="Each ZZ")
brand = Brand(id=u(), company_id=COMPANY, brand_code="ZZB", brand_name="ZZ Brand")
db.add_all([tub, basin, uom, brand])
db.flush()


def prod(code, name, category):
    p = Product(id=u(), company_id=COMPANY, product_code=code, product_name=name, category_id=category.id,
                base_uom_id=uom.id, brand_id=brand.id, list_price=1000)
    db.add(p)
    return p


src = prod("ZZBT-1001", "ZZ Bathtub 1001", tub)
b2 = prod("ZZBT-1002", "ZZ Bathtub 1002", tub)
b3 = prod("ZZBT-1003", "ZZ Bathtub 1003", tub)
b4 = prod("ZZBT-1004", "ZZ Bathtub 1004", tub)
prod("ZZBS-2001", "ZZ Basin 2001", basin)
db.flush()

design = {"direction": "horizontal", "headerText": "FREE", "columns": 2,
          "card": {"width_mm": 30, "height_mm": 20, "elements": []}}
free_box = AccessoryBoxPreset(id=u(), company_id=COMPANY, name="ZZ FREE box", design=design)
own_box = AccessoryBoxPreset(id=u(), company_id=COMPANY, name="ZZ Own box", design=design)
db.add_all([free_box, own_box])
db.flush()

pump = Accessory(id=u(), company_id=COMPANY, name="PRESSURE PUMP", spec="<p>30PC</p>")
soap = Accessory(id=u(), company_id=COMPANY, name="SOAP AND BATH BOMB SET")
tap = Accessory(id=u(), company_id=COMPANY, name="FREESTANDING MIXER TAP")
rail = Accessory(id=u(), company_id=COMPANY, name="TOWEL RAIL")
db.add_all([pump, soap, tap, rail])
db.flush()

db.add_all([
    ProductAccessory(id=u(), product_id=src.id, accessory_id=pump.id, sort_order=0,
                     name_override="Pressure pump 30PC", remark_override="<p>Free installation</p>"),
    ProductAccessory(id=u(), product_id=src.id, accessory_id=soap.id, sort_order=1),
    ProductAccessory(id=u(), product_id=src.id, accessory_id=tap.id, sort_order=2),
    ProductAccessory(id=u(), product_id=b3.id, accessory_id=soap.id, sort_order=0,
                     remark_override="<p>ZZ own words</p>"),
    ProductAccessory(id=u(), product_id=b3.id, accessory_id=rail.id, sort_order=1),
])
src.accessory_box_preset_id = free_box.id
b3.accessory_box_preset_id = own_box.id
db.commit()

from app.modules.runtime.installer import DEFAULT_TENANT_ID, install_modules, load_dependency_graph  # noqa: E402

install_modules(db, DEFAULT_TENANT_ID, sorted(load_dependency_graph(db).keys()), actor_user_id=admin.id)
db.commit()
print("source", src.id)
