"""Shared harness for the PRODUCT-COSTING lane's backend tests (Phase 2, written test-FIRST).

Built on `tests/support/cost_price_env.py`: a `TestClient(app)` over `blank_session()` (a
throwaway Postgres schema made from whatever is on `Base.metadata`) with `get_db`,
`get_current_user(_or_api_key)` and `apply_company_scope` overridden so a test drives the real
routes without a real login. Users are built from real roles/permissions, never borrowed.

NOTHING under `app/models/costing.py`, `app/services/costing/*` or the costing router exists
when this is written. Every helper that touches one of those imports it INSIDE the method body,
so collection never fails on a name that is not built yet; a missing route 404s and a missing
model raises inside the specific test that needed it.

The workbook world (`workbook()`) mirrors PLAN-product-costing-10nov.md section 10:

    rates      RMB 0.617284 from 2026-09-01, RMB 0.625 from 2026-11-01, USD 4.40 from 2026-01-01
               (no EUR rate at all). SST is the default 1.10 (no settings row is written).
    rules      Ceramics ADD 8, Jacuzzi ADD 8, Taps x1.07, Showers x1.07, Accessories x1.07,
               Kitchen sinks x1.10
    WB 245     CGB9032B, list 79.00, Ceramics. Links: A (SUP-A01, primary, RMB 34.50),
               B (SUP-B07, RMB 38.00), L (SUP-L05, MYR 42.00), D (SUP-D03, EUR 7.50).
    Jacuzzi    JAC-5001, list 3998.93, RMB 2450 at SUP-A01 -> landing 1692.375 on 2026-11-11.
    Tap        T-1001, list 150.00, RMB 120.00 at SUP-A01 -> 88.275
    Sink       K-2001, list 400.00, RMB 260.00 at SUP-A01 -> 196.625
    Shower     S-3001, list 250.00, USD 20.00 at SUP-D03 (primary) -> 103.576
    Accessory  A-4001, list 30.00, a primary link with NO cost row -> "no_cost"
    Bare       N-9001, list 10.00, no links at all -> "no_primary"
    Inactive   Z-0001, list 12.00, is_active False, RMB 10 at SUP-A01
    party      304-R017 "RELATED - BATHPLUS SDN BHD", profile 8%; products WB 245 (no row
               mark-up) and the Jacuzzi (row mark-up 10)

ASSUMED MODEL API (app/models/costing.py, contract section 2; company_id is auto-stamped by the
scope layer, so the helpers never pass it): ExchangeRate(id, currency, rate_to_base, effective_from,
note), CostingSettings(id, sst_factor, default_method), CostingCategoryRule(category_id, mode, value),
CostingProductOverride(product_id, transport_mode, transport_value, cost_method,
cost_method_supplier_id), CustomerCostingProfile(customer_id, markup_pct, cost_method, is_active),
CustomerCostingProduct(id, customer_id, product_id, markup_pct). Column names are the contract's.

`AS_OF` is 2026-11-11 (RMB 0.625). `AS_OF_OLD` is 2026-10-31 (RMB 0.617284, 1.62 per MYR).
Every date is explicit: no test freezes the clock.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  (must be the first app import, see cost_price_env)
from tests._pg_fixture import blank_session
from tests.support.cost_price_env import (
    CostPriceEnv,
    _u,
    _wire_overrides,
    install_audit_action_check,
)

BASE = "/api/v1/master-data/costing"

COST_VIEW = "products.cost.view"
MANAGE = "products.party_costing.manage"
RATE_WRITE = "scm.config.manage"
RATE_READ = "scm.dashboard.view"

AS_OF = date(2026, 11, 11)
AS_OF_OLD = date(2026, 10, 31)


class CostingEnv(CostPriceEnv):
    """One test's company, users, workbook catalogue and authenticated client."""

    # ------------------------------------------------------------- principals
    def viewer(self, name: str = "Viewer") -> dict:
        return self.user(COST_VIEW, name=name)

    def manager(self, name: str = "Manager") -> dict:
        """Holds both gates a costing write needs (contract section 4)."""
        return self.user(COST_VIEW, MANAGE, name=name)

    def admin(self, name: str = "Admin") -> dict:
        """A user whose role slug is literally `admin`: the RBAC bypass, no permission rows."""
        from app.models.user import User, UserRole, UserRoleAssignment

        uid, role_id = _u(), _u()
        self.db.add(User(id=uid, email=f"zzpc-{uid[:8]}@test.com", name=name, status="ACTIVE"))
        self.db.add(
            UserRole(
                id=role_id, slug="admin", name="Admin", description="",
                is_protected=True, is_default=False,
            )
        )
        self.db.flush()
        self.db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role_id))
        self.db.commit()
        return {"id": uid, "email": f"zzpc-{uid[:8]}@test.com", "name": name}

    # ---------------------------------------------------------------- catalogue
    def category(self, name: str, *, rule: tuple[str, float] | None = None):
        """A product category, optionally with a transport rule `("add", 8)` / `("multiply", 1.07)`."""
        from app.models.product import ProductCategory

        cat = ProductCategory(
            id=_u(), category_code=f"ZZPC-{name[:20].upper().replace(' ', '')}-{_u()[:4]}",
            category_name=name,
        )
        self.db.add(cat)
        self.db.flush()
        if rule is not None:
            self.rule(cat, *rule)
        return cat

    def rule(self, category, mode: str, value) -> None:
        from app.models.costing import CostingCategoryRule

        self.db.add(CostingCategoryRule(category_id=category.id, mode=mode, value=value))
        self.db.flush()

    def brand(self, name: str = "Sorento"):
        from app.models.product import Brand

        b = Brand(id=_u(), brand_code=f"ZZPC-{_u()[:6]}", brand_name=name)
        self.db.add(b)
        self.db.flush()
        return b

    def item(self, code: str, *, category, list_price, brand=None, active: bool = True,
             name: str | None = None):
        """A product with a list price. (`CostPriceEnv.product` has no price or category.)"""
        from app.models.product import Product, UnitOfMeasure

        uom = self.db.query(UnitOfMeasure).filter_by(uom_code="ZZPC-U").one_or_none()
        if uom is None:
            uom = UnitOfMeasure(id=_u(), uom_code="ZZPC-U", uom_name="pcs")
            self.db.add(uom)
            self.db.flush()
        p = Product(
            id=_u(), product_code=code, product_name=name or f"{code} name",
            category_id=category.id, brand_id=brand.id if brand else None,
            base_uom_id=uom.id, list_price=list_price,
            is_active=active, is_discontinued=False,
        )
        self.db.add(p)
        self.db.flush()
        return p

    def source(self, code: str, name: str | None = None):
        """A supplier; the code is the plain workbook code (the scratch schema is per run)."""
        return self.supplier(name=name or f"{code} Ltd", code=code)

    def cost_link(self, product, supplier, *, cost=None, currency=None, primary: bool = False,
                  lead_time_days: int = 30, start_date=None, end_date=None,
                  packaging: str = "standard", mirror_unit_cost: bool = False):
        """A `product_suppliers` link. `cost` writes one `product_supplier_costs` row (the cost
        list the contract reads through `current_cost`). `mirror_unit_cost=True` also fills the
        link's own `unit_cost` / `currency` (the fallback for a link with NO cost rows)."""
        from app.models.cost_price import ProductSupplierCost
        from app.models.procurement import ProductSupplier

        link = ProductSupplier(
            id=_u(), product_id=product.id, supplier_id=supplier.id,
            standard_lead_time_days=lead_time_days, is_primary_supplier=primary,
            unit_cost=cost if mirror_unit_cost else None,
            currency=currency if mirror_unit_cost else None,
        )
        self.db.add(link)
        self.db.flush()
        if cost is not None and not mirror_unit_cost:
            self.cost_row(link, cost, currency, start_date=start_date, end_date=end_date,
                          packaging=packaging)
        return link

    def cost_row(self, link, cost, currency, *, start_date=None, end_date=None,
                 packaging: str = "standard"):
        from app.models.cost_price import ProductSupplierCost
        from app.services.procurement.supplier_cost_service import packaging_key

        row = ProductSupplierCost(
            id=_u(), product_supplier_id=link.id, unit_cost=cost, currency=currency,
            start_date=start_date, end_date=end_date,
            packaging_method=packaging, packaging_key=packaging_key(packaging),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def po_line(self, product, supplier, *, po_number: str, issue_date, unit_cost, currency=None,
                po_currency: str | None = None, removed: bool = False,
                created_at: datetime | None = None):
        """A purchase order (one line) for `product`. `currency` is the LINE currency (the
        contract's COALESCE(line.currency, po.currency) prefers it); `po_currency` is the header's."""
        from app.models.procurement import PurchaseOrder, PurchaseOrderLine

        po = PurchaseOrder(
            id=_u(), po_number=po_number, supplier_id=supplier.id, issue_date=issue_date,
            status="active", currency=po_currency,
        )
        self.db.add(po)
        self.db.flush()
        extra = {"created_at": created_at} if created_at else {}
        line = PurchaseOrderLine(
            id=_u(), purchase_order_id=po.id, product_id=product.id, qty_ordered=10,
            unit_cost=unit_cost, currency=currency, removed_unreferenced=removed, **extra,
        )
        self.db.add(line)
        self.db.flush()
        return line

    # ------------------------------------------------------------------- rates
    def rate(self, currency: str, rate_to_base, effective_from: date, note: str | None = None):
        from app.models.costing import ExchangeRate

        row = ExchangeRate(
            id=_u(), currency=currency, rate_to_base=rate_to_base,
            effective_from=effective_from, note=note,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def set_settings(self, *, sst_factor=None, default_method=None):
        from app.models.costing import CostingSettings

        row = self.db.query(CostingSettings).first()
        if row is None:
            row = CostingSettings(id=_u())
            self.db.add(row)
        if sst_factor is not None:
            row.sst_factor = sst_factor
        if default_method is not None:
            row.default_method = default_method
        self.db.flush()
        return row

    def override(self, product, **fields):
        """A `costing_product_overrides` row (transport_mode/value, cost_method, cost_method_supplier_id)."""
        from app.models.costing import CostingProductOverride

        row = CostingProductOverride(product_id=product.id, **fields)
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------------ parties
    def customer(self, code: str = "304-R017", name: str = "RELATED - BATHPLUS SDN BHD"):
        from app.models.order import Customer

        c = Customer(id=_u(), customer_code=code, customer_name=name)
        self.db.add(c)
        self.db.flush()
        return c

    def profile(self, customer, markup_pct=8, cost_method=None, is_active: bool = True):
        from app.models.costing import CustomerCostingProfile

        row = CustomerCostingProfile(
            customer_id=customer.id, markup_pct=markup_pct, cost_method=cost_method,
            is_active=is_active,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def party_product(self, customer, product, markup_pct=None):
        from app.models.costing import CustomerCostingProduct

        row = CustomerCostingProduct(
            id=_u(), customer_id=customer.id, product_id=product.id, markup_pct=markup_pct,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # --------------------------------------------------------------- the world
    def workbook(self) -> SimpleNamespace:
        """Seed the plan's section 10 fixtures. Returns a namespace of everything created."""
        w = SimpleNamespace()
        w.rmb_old = self.rate("RMB", "0.617284", date(2026, 9, 1))
        w.rmb_new = self.rate("RMB", "0.625", date(2026, 11, 1))
        w.usd = self.rate("USD", "4.40", date(2026, 1, 1))

        w.brand = self.brand("Sorento")
        w.cat_ceramics = self.category("Ceramics", rule=("add", 8))
        w.cat_jacuzzi = self.category("Jacuzzi", rule=("add", 8))
        w.cat_taps = self.category("Taps", rule=("multiply", "1.07"))
        w.cat_showers = self.category("Showers", rule=("multiply", "1.07"))
        w.cat_accessories = self.category("Accessories", rule=("multiply", "1.07"))
        w.cat_sinks = self.category("Kitchen sinks", rule=("multiply", "1.10"))

        w.sup_a = self.source("SUP-A01")
        w.sup_b = self.source("SUP-B07")
        w.sup_l = self.source("SUP-L05")
        w.sup_d = self.source("SUP-D03")

        w.wb = self.item("CGB9032B", category=w.cat_ceramics, list_price="79.00",
                         brand=w.brand, name="WB 245 basin")
        w.link_a = self.cost_link(w.wb, w.sup_a, cost="34.50", currency="RMB", primary=True)
        w.link_b = self.cost_link(w.wb, w.sup_b, cost="38.00", currency="RMB")
        w.link_l = self.cost_link(w.wb, w.sup_l, cost="42.00", currency="MYR")
        w.link_d = self.cost_link(w.wb, w.sup_d, cost="7.50", currency="EUR")

        w.jac = self.item("JAC-5001", category=w.cat_jacuzzi, list_price="3998.93",
                          brand=w.brand, name="Jacuzzi 5001")
        w.jac_link = self.cost_link(w.jac, w.sup_a, cost="2450.00", currency="RMB", primary=True)

        w.tap = self.item("T-1001", category=w.cat_taps, list_price="150.00", brand=w.brand)
        w.tap_link = self.cost_link(w.tap, w.sup_a, cost="120.00", currency="RMB", primary=True)

        w.sink = self.item("K-2001", category=w.cat_sinks, list_price="400.00", brand=w.brand)
        w.sink_link = self.cost_link(w.sink, w.sup_a, cost="260.00", currency="RMB", primary=True)

        w.shower = self.item("S-3001", category=w.cat_showers, list_price="250.00")
        w.shower_link = self.cost_link(w.shower, w.sup_d, cost="20.00", currency="USD", primary=True)

        w.acc = self.item("A-4001", category=w.cat_accessories, list_price="30.00")
        w.acc_link = self.cost_link(w.acc, w.sup_a, primary=True)  # a primary link, no cost at all

        w.bare = self.item("N-9001", category=w.cat_accessories, list_price="10.00")

        w.inactive = self.item("Z-0001", category=w.cat_ceramics, list_price="12.00", active=False)
        w.inactive_link = self.cost_link(w.inactive, w.sup_a, cost="10.00", currency="RMB", primary=True)

        w.customer = self.customer()
        w.profile = self.profile(w.customer, markup_pct=8)
        w.pp_wb = self.party_product(w.customer, w.wb)
        w.pp_jac = self.party_product(w.customer, w.jac, markup_pct=10)
        self.db.commit()
        return w

    # --------------------------------------------------------------------- HTTP
    def get(self, path: str, **params):
        return self.client.get(f"{BASE}{path}", params={k: v for k, v in params.items() if v is not None})

    def rows(self, **params):
        return self.get("/rows", **params)

    def patch_rows(self, body: dict):
        return self.client.patch(f"{BASE}/rows", json=body)

    def post(self, path: str, body: dict):
        return self.client.post(f"{BASE}{path}", json=body)

    def put(self, path: str, body: dict):
        return self.client.put(f"{BASE}{path}", json=body)

    def row_of(self, response, code: str) -> dict:
        """The one Row for `product_code == code` in a /rows response (asserts it is there)."""
        assert response.status_code == 200, response.text
        found = [r for r in response.json()["data"] if r["product_code"] == code]
        assert len(found) == 1, (code, [r["product_code"] for r in response.json()["data"]])
        return found[0]

    def audit_rows(self, entity_type: str, entity_id: str) -> list:
        from app.models.audit import AuditLog

        return (
            self.db.query(AuditLog)
            .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.changed_at)
            .all()
        )


@pytest.fixture
def costing_env():
    with blank_session() as db:
        install_audit_action_check(db)
        e = CostingEnv(db)
        _wire_overrides(e, db)
        e.client = TestClient(app)
        try:
            yield e
        finally:
            app.dependency_overrides.clear()


def f(value):
    """float() that keeps None. Basis values are Decimals; the API returns floats."""
    return None if value is None else float(value)
