"""Order management models."""
from sqlalchemy import (
    CheckConstraint,
    Column,
    String,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
    Numeric,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.base import CompanyScopedMixin
import uuid


def _uuid_str():
    return str(uuid.uuid4())


class OrderStatus(Base):
    __tablename__ = "order_statuses"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    status_code = Column(String(50), unique=True, nullable=False)
    status_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sequence = Column(Integer, default=0, nullable=False)
    is_final_status = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    orders = relationship("Order", back_populates="order_status")
    
    __table_args__ = (
        Index("ix_order_statuses_sequence", "sequence"),
        Index("ix_order_statuses_is_final_status", "is_final_status"),
    )


class Customer(Base, CompanyScopedMixin):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Not column-unique. Real customers can share a single code across
    # multiple debtor names (e.g. "300-D093" maps to both "Deluxe Home Center
    # (KTN)" and "Deluxe Home Center AC (I)"). Uniqueness enforced via the
    # composite functional index in __table_args__ below: lower(customer_code)
    # + lower(customer_name) must be distinct.
    customer_code = Column(String(50), nullable=False)
    customer_name = Column(String(255), nullable=False)
    email = Column(String(150), nullable=True)
    phone_number = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    # Extended profile (added by commercial_core to support lead/customer flows)
    registered_name = Column(String(255), nullable=True)
    trading_name = Column(String(255), nullable=True)
    registration_number = Column(String(100), nullable=True)
    industry = Column(String(120), nullable=True)
    website = Column(String(500), nullable=True)
    billing_address = Column(JSONB, nullable=True)
    country = Column(String(100), nullable=True)
    tax_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    account_owner_user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_type = Column(String(20), nullable=False, server_default="company")
    salutation = Column(String(32), nullable=True)
    first_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    mobile_number = Column(String(50), nullable=True)
    # SCM (M2): demand-nature channel routing via the customer's market segment.
    market_segment_code = Column(String(50), ForeignKey("market_segments.code", ondelete="SET NULL"), nullable=True)

    orders = relationship("Order", back_populates="customer")
    customer_contacts = relationship(
        "CustomerContact",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_customers_is_active", "is_active"),
        Index("ix_customers_customer_code", "customer_code"),
        Index("ix_customers_account_owner_user_id", "account_owner_user_id"),
        # Composite uniqueness — see column docstring. Created as a functional
        # UNIQUE INDEX by migration 220 so case + whitespace differences don't
        # produce silent duplicates, then re-created WITH company_id by migration
        # 305: the same code+name legally exists once per company (884 pairs are
        # held by both Sorento and Mocha today), so the pre-305 global shape would
        # reject a real row. `products` was updated to its composite at the time
        # and this one was not, which mattered because a test building its schema
        # from `Base.metadata.create_all` got the GLOBAL index and failed on data
        # production accepts. Keep this in step with the live index.
        Index(
            "uq_customers_company_code_name_lower",
            "company_id",
            func.lower(func.btrim(customer_code)),
            func.lower(func.btrim(customer_name)),
            unique=True,
        ),
    )


class CustomerContact(Base, CompanyScopedMixin):
    """Main or stakeholder person linked to a business customer profile."""

    __tablename__ = "customer_contacts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(255), nullable=False)
    job_title = Column(String(120), nullable=True)
    email = Column(String(150), nullable=True)
    phone = Column(String(50), nullable=True)
    mobile = Column(String(50), nullable=True)
    sync_source = Column(String(32), nullable=False, default="manual")
    contact_role = Column(String(20), nullable=False, default="stakeholder")
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    customer = relationship("Customer", back_populates="customer_contacts")

    __table_args__ = (
        CheckConstraint(
            "contact_role IN ('main', 'stakeholder')",
            name="ck_customer_contacts_contact_role",
        ),
        Index("ix_customer_contacts_customer_id", "customer_id"),
        Index(
            "uq_customer_contacts_one_main_per_customer",
            "customer_id",
            unique=True,
            postgresql_where=text("contact_role = 'main'"),
        ),
    )


class Transporter(Base, CompanyScopedMixin):
    """Lookup table for distinct transporter names referenced by orders.transporter.

    Seeded by migration 200_transporters_table from existing orders. `orders.transporter`
    (free-text) is retained for legacy compat; `orders.transporter_id` is the canonical FK.
    """
    __tablename__ = "transporters"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(100), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)


class Order(Base, CompanyScopedMixin):
    __tablename__ = "orders"
    __audit_track__ = True  # who changed what (Sub-plan D Tier-2)

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Unique PER COMPANY, not globally (migration 305): composite unique index in
    # __table_args__ below. A bare unique=True would rebuild the old global
    # orders_order_number_key under create_all and reject the same number in a
    # second company.
    order_number = Column(String(100), nullable=False)
    order_date = Column(Date, nullable=True)
    estimated_delivery_date = Column(Date, nullable=True)
    actual_delivery_date = Column(Date, nullable=True)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    order_status_id = Column(UUID(as_uuid=False), ForeignKey("order_statuses.id", ondelete="SET NULL"), nullable=True)
    transporter_id = Column(UUID(as_uuid=False), ForeignKey("transporters.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    updated_by = Column(UUID(as_uuid=False), nullable=True)
    billing_address_id = Column(UUID(as_uuid=False), nullable=True)
    shipping_address_id = Column(UUID(as_uuid=False), nullable=True)
    created_time = Column(DateTime(timezone=False), nullable=True)
    debtor_code = Column(String(100), nullable=True)
    debtor_name = Column(String(255), nullable=True)
    agent = Column(String(100), nullable=True)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    remarks_cs = Column(Text, nullable=True)
    order_type = Column(String(50), nullable=True)
    pickup_time = Column(String(20), nullable=True)
    checker = Column(String(100), nullable=True)
    transporter = Column(String(100), nullable=True)
    driver_name = Column(String(100), nullable=True)
    lorry_plate = Column(String(50), nullable=True)
    customer_ref = Column(String(255), nullable=True)
    delivery_remarks_cs = Column(Text, nullable=True)
    delivery_remarks = Column(Text, nullable=True)
    salesman = Column(String(100), nullable=True)
    trips = Column(Integer, nullable=True)
    warehouse = Column(String(50), nullable=True)
    delivery_days = Column(Integer, nullable=True)
    kpi_warning = Column(Boolean, default=False, nullable=False)
    subtotal_amount = Column(Numeric(15, 2), default=0, nullable=False)
    discount_amount = Column(Numeric(15, 2), default=0, nullable=False)
    tax_amount = Column(Numeric(15, 2), default=0, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0, nullable=False)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=False), nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    
    customer = relationship("Customer", back_populates="orders")
    order_status = relationship("OrderStatus", back_populates="orders")
    lines = relationship(
        "OrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLine.line_sequence",
    )

    __table_args__ = (
        Index("uq_orders_company_order_number", "company_id", "order_number", unique=True),
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_order_status_id", "order_status_id"),
        Index("ix_orders_order_date", "order_date"),
        Index("ix_orders_order_number", "order_number"),
        Index("ix_orders_created_by", "created_by"),
        Index("ix_orders_deleted_at", "deleted_at"),
        Index("ix_orders_debtor_code", "debtor_code"),
        Index("ix_orders_kpi_warning", "kpi_warning"),
        Index("ix_orders_is_cancelled", "is_cancelled"),
    )


class OrderLine(Base, CompanyScopedMixin):
    """Delivery order detail line: product + warehouse + qty + pricing."""
    __tablename__ = "order_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    line_sequence = Column(Integer, nullable=False, default=1)
    order_id = Column(
        UUID(as_uuid=False),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_id = Column(
        UUID(as_uuid=False),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity = Column(Numeric(15, 4), default=0, nullable=False)
    unit_price = Column(Numeric(15, 4), nullable=True)
    discount = Column(Numeric(15, 4), default=0, nullable=True)
    total = Column(Numeric(15, 4), nullable=True)
    tax = Column(Numeric(15, 4), nullable=True)
    total_excluding_tax = Column(Numeric(15, 4), nullable=True)
    total_including_tax = Column(Numeric(15, 4), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    order = relationship("Order", back_populates="lines")
    product = relationship("Product", backref="order_lines")
    warehouse = relationship("Warehouse", backref="order_lines")

    __table_args__ = (
        Index("ix_order_lines_order_id", "order_id"),
        Index("ix_order_lines_product_id", "product_id"),
        Index("ix_order_lines_warehouse_id", "warehouse_id"),
        Index(
            "ix_order_lines_order_product_warehouse",
            "order_id",
            "product_id",
            "warehouse_id",
            unique=False,
        ),
        UniqueConstraint("order_id", "line_sequence", name="uq_order_lines_order_id_line_sequence"),
    )


class SalesOrder(Base, CompanyScopedMixin):
    """SCM sales order (demand / committed source). Public core record — survives
    module uninstall. Sits with Order/DO in the order domain."""
    __tablename__ = "sales_orders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    so_number = Column(String(100), unique=True, nullable=False)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    # Who sold it, as the salesperson master (`sales_agents`), resolved from the agent code
    # the extract states. Nullable because most orders predate the column and no export is
    # required to carry an agent; `SET NULL` because deleting a salesperson must not delete
    # their orders. It is also the fourth and last source the demand class is read from.
    sales_agent_id = Column(UUID(as_uuid=False), ForeignKey("sales_agents.id", ondelete="SET NULL"), nullable=True)
    order_date = Column(Date, nullable=True)
    # Customer-requested delivery / ship-by date (M1-D14). Distinct from order_date
    # (when the SO was raised); drives the FE "requested_delivery_date" column.
    requested_delivery_date = Column(Date, nullable=True)
    order_type = Column(String(50), nullable=True)  # lookup code (continuous / spike vocab)
    # project | retail, resolved from the customer's market segment at import. Belongs to
    # the DEMAND, not the buyer: the same customer can place both kinds, and fulfilment
    # priority is decided by this. Nullable because a row whose class cannot be resolved is
    # rejected at import rather than silently defaulted to retail.
    demand_class = Column(String(32), nullable=True)
    # Which feed ORIGINATED this order - 'scm_order_inquiry' when the Order Inquiry sheet
    # created it. Its own column, never source_system: adoption by the outstanding extract
    # overwrites source_system to take ownership, and project demand is keyed on origin
    # (S13b), so reading origin off source_system would delete demand as a side effect of
    # the handover. Stamped at creation, never rewritten.
    demand_origin = Column(String(32), nullable=True)
    priority = Column(String(20), nullable=True)
    status = Column(String(50), default="open", nullable=False)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    # The document number in the system this order came from, and free text carried with it.
    # Both columns already existed on the table and were simply not mapped, so every read
    # through the ORM silently dropped them - the Order Inquiry feed needs `internal_note` to
    # keep a project name it cannot resolve to a customer.
    source_doc_no = Column(String, nullable=True)
    internal_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    customer = relationship("Customer")
    lines = relationship(
        "SalesOrderLine",
        back_populates="sales_order",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_sales_orders_customer_id", "customer_id"),
        Index("ix_sales_orders_so_number", "so_number"),
        Index("ix_sales_orders_status", "status"),
        Index("ix_sales_orders_sales_agent_id", "sales_agent_id"),
    )


class SalesOrderLine(Base, CompanyScopedMixin):
    """Open SO line — feeds committed / net-position views by product×warehouse."""
    __tablename__ = "sales_order_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    sales_order_id = Column(UUID(as_uuid=False), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True)
    qty_ordered = Column(Numeric(15, 4), default=0, nullable=False)
    qty_delivered = Column(Numeric(15, 4), default=0, nullable=False)
    priority = Column(String(20), nullable=True)  # inherit from header / override
    # When this line's quantity must be on hand. PER LINE, not per header: the order
    # inquiry the business works from states a delivery date per line and one SO routinely
    # carries several, so the header's requested_delivery_date cannot drive netting.
    # Without this the Coverage Timeline has no time axis at all (ADR-0011).
    required_date = Column(Date, nullable=True)
    # What purchasing should plan for, when that is not simply what is still owed to the
    # customer. NULL means nobody has said otherwise, so the netting falls back to
    # `qty_ordered - qty_delivered`. Set by the Order Inquiry feed, which is CS stating the
    # quantity they want covered; kept apart from `qty_ordered` so a sales-order amendment
    # and a purchasing decision cannot overwrite one another.
    qty_required = Column(Numeric(15, 4), nullable=True)
    # Where this line stands in purchasing. `not_reviewed` (nobody has looked at it yet, and
    # it still counts as demand), `needs_purchase` (CS says buy it, nothing placed),
    # `ordered` (a purchase order covers it), `covered` (CS ruled it out).
    purchasing_status = Column(
        String(24), default="not_reviewed", server_default="not_reviewed", nullable=False
    )
    line_status = Column(String(50), default="open", nullable=False)
    source_system = Column(String, nullable=True)
    source_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    sales_order = relationship("SalesOrder", back_populates="lines")
    product = relationship("Product")
    warehouse = relationship("Warehouse")

    __table_args__ = (
        Index("ix_sales_order_lines_sales_order_id", "sales_order_id"),
        Index("ix_sales_order_lines_product_id", "product_id"),
        Index("ix_sales_order_lines_warehouse_id", "warehouse_id"),
        Index("ix_sales_order_lines_product_warehouse_status", "product_id", "warehouse_id", "line_status"),
    )
