"""Synthetic seed for the PRICETAG-ACC-LABELS browser pass. Sandbox DB (sorento_browse) only.

Run from sorento_crm_backend:
  SORENTO_ENV_FILE=.env.browse BROWSE_ADMIN_PASSWORD=... venv/bin/python <this file>

Writes (all names invented): a superadmin user, five products (SRTKS7846 with a 3-item own list,
SRTWB7065 host, SRTWT7202 part, SRTW5000 and COLANDER as accessory products), a library accessory
DRAINER, a combo on SRTWB7065 (part SRTWT7202, combo list SRTW5000 + COLANDER) and a published
tag template with an Accessories box (40 x 40 mm: one 3-line card fits, two do not), linked to
the combo as its default LP and SP template. Installs every module for the default tenant.
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
from app.models.accessory import Accessory, ProductAccessory, ProductComboAccessory  # noqa: E402
from app.models.company import UserCompany  # noqa: E402
from app.models.dealer_kit import ComboTagTemplate, TagTemplate, TagTemplateVersion  # noqa: E402
from app.models.product import Product, ProductCategory, UnitOfMeasure  # noqa: E402
from app.models.product_combo import ProductCombo, ProductComboPart  # noqa: E402
from app.models.user import User, UserRoleAssignment  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
PASSWORD = os.environ["BROWSE_ADMIN_PASSWORD"]  # throwaway, sandbox DB only
BOX_H = float(os.environ.get("BOX_H", "40"))

db = sessionmaker(bind=engine)()


def u() -> str:
    return str(uuid.uuid4())


admin = db.query(User).filter(User.email == "browse.admin@example.com").one_or_none()
if admin is None:
    admin = User(id=u(), email="browse.admin@example.com", name="Browse Admin", status="ACTIVE",
                 password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode())
    db.add(admin)
    db.flush()
    role = db.execute(text("SELECT id FROM user_roles WHERE slug IN ('superadmin','super_admin') "
                           "OR name ILIKE 'super admin' LIMIT 1")).scalar()
    db.add(UserRoleAssignment(user_id=admin.id, role_id=role))
    db.add(UserCompany(id=u(), user_id=admin.id, company_id=COMPANY))
    db.commit()

cat = ProductCategory(id=u(), company_id=COMPANY, category_code="ZZ-BROWSE", category_name="ZZ-BROWSE")
uom = UnitOfMeasure(id=u(), company_id=COMPANY, uom_code="ZZEA", uom_name="Each ZZ")
db.add_all([cat, uom])
db.flush()


def prod(code: str, name: str, price: float) -> Product:
    p = Product(id=u(), company_id=COMPANY, product_code=code, product_name=name,
                category_id=cat.id, base_uom_id=uom.id, list_price=price)
    db.add(p)
    return p


ks = prod("SRTKS7846", "Kitchen sink 7846", 1200)
wb = prod("SRTWB7065", "Basin cabinet 7065", 900)
wt = prod("SRTWT7202", "Basin top 7202", 300)
w5 = prod("SRTW5000", "Popup waste 5000", 68)
col = prod("COLANDER", "Colander", 25)
drn = prod("ZZDRAINER", "Drainer item", 15)
db.flush()

board = Accessory(id=u(), company_id=COMPANY, name="CHOPPING BOARD", spec="Solid wood")
rack = Accessory(id=u(), company_id=COMPANY, name="DRAINER", spec="Stainless")
db.add_all([board, rack])
db.flush()

# SRTKS7846's own list: 3 entries (two library accessories + one product).
db.add_all([
    ProductAccessory(id=u(), product_id=ks.id, accessory_id=board.id, sort_order=0),
    ProductAccessory(id=u(), product_id=ks.id, accessory_id=rack.id, sort_order=1),
    ProductAccessory(id=u(), product_id=ks.id, item_product_id=drn.id, sort_order=2),
])

combo = ProductCombo(id=u(), host_product_id=wb.id, name="3 in 1", sort_order=0)
db.add(combo)
db.flush()
db.add(ProductComboPart(id=u(), combo_id=combo.id, part_product_id=wt.id, sort_order=0))
db.add_all([
    ProductComboAccessory(id=u(), combo_id=combo.id, item_product_id=w5.id, sort_order=0),
    ProductComboAccessory(id=u(), combo_id=combo.id, item_product_id=col.id, sort_order=1),
])

# Tag template with an Accessories box sized so 2 product cards do not fit.
acc_props = {
    "kind": "accessories", "direction": "vertical", "itemLayout": "stacked", "showHeader": True,
    "showFrame": True, "headerOnBorder": True, "headerBackground": "#ffffff",
    "nameStyle": {"fontWeight": 700}, "specStyle": {"fontWeight": 400},
    "headerText": "ACCESSORIES INCLUDED", "headerFontSize": 9, "headerColor": "#1f4d36",
    "showBadge": False, "badgeColor": "#c2410c", "fill": "#f3f7f4", "stroke": "#1f4d36",
    "strokeWidth_mm": 0.4, "cornerRadius_mm": 3, "cardFill": "#ffffff", "textColor": "#111827",
    "imageSize_mm": 10, "nameFontSize": 8, "specFontSize": 6.5, "gap_mm": 1.5, "cardWidth_mm": 26,
}
doc = {
    "width_mm": 148, "height_mm": 105,
    "layers": [{
        "id": "acc-1", "type": "accessories", "x_mm": 10, "y_mm": 10, "width_mm": 40,
        "height_mm": BOX_H, "rotation_deg": 0, "z_index": 1, "locked": False, "visible": True,
        "slot_binding": None, "text_override": None, "props": acc_props,
    }],
}
tpl = TagTemplate(id=u(), company_id=COMPANY, name="ZZ Basin accessories tag", family="art_basin",
                  doc=doc, print_size={"width_mm": 148, "height_mm": 105}, created_by=admin.id)
db.add(tpl)
db.flush()
ver = TagTemplateVersion(id=u(), template_id=tpl.id, version_no=1, doc=doc,
                         print_size={"width_mm": 148, "height_mm": 105}, note="seed",
                         created_by=admin.id)
db.add(ver)
db.flush()
tpl.published_version_id = ver.id
db.add(ComboTagTemplate(id=u(), combo_id=combo.id, template_id=tpl.id,
                        default_list=True, default_selling=True, created_by=admin.id))
db.commit()

from app.modules.runtime.installer import DEFAULT_TENANT_ID, install_modules  # noqa: E402

from app.modules.runtime.installer import load_dependency_graph  # noqa: E402

graph = load_dependency_graph(db)
all_keys = sorted(graph.keys())
install_modules(db, DEFAULT_TENANT_ID, all_keys, actor_user_id=admin.id)
db.commit()
print("combo", combo.id, "template", tpl.id, "modules", all_keys)
