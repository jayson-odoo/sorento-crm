"""Order management models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Numeric, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class OrderStatus(Base):
    __tablename__ = "order_statuses"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    status_code = Column(String(50), unique=True, nullable=False)
    status_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sequence = Column(String, default="0", nullable=False)
    is_final_status = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    orders = relationship("Order", back_populates="order_status")
    
    __table_args__ = (
        Index("ix_order_statuses_sequence", "sequence"),
        Index("ix_order_statuses_is_final_status", "is_final_status"),
    )


class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_code = Column(String(50), unique=True, nullable=False)
    customer_name = Column(String(255), nullable=False)
    email = Column(String(150), nullable=True)
    phone_number = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    orders = relationship("Order", back_populates="customer")
    
    __table_args__ = (
        Index("ix_customers_is_active", "is_active"),
        Index("ix_customers_customer_code", "customer_code"),
    )


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_number = Column(String(100), unique=True, nullable=False)
    order_date = Column(DateTime(timezone=False), nullable=True)
    promised_delivery_date = Column(DateTime(timezone=False), nullable=True)
    actual_delivery_date = Column(DateTime(timezone=False), nullable=True)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    order_status_id = Column(UUID(as_uuid=False), ForeignKey("order_statuses.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
    billing_address_id = Column(String, nullable=True)
    shipping_address_id = Column(String, nullable=True)
    created_time = Column(DateTime(timezone=False), nullable=True)
    debtor_code = Column(String(100), nullable=True)
    debtor_name = Column(String(255), nullable=True)
    agent = Column(String(100), nullable=True)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    remarks_cs = Column(Text, nullable=True)
    order_type = Column(String(50), nullable=True)
    delivery_time = Column(String(20), nullable=True)
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
    
    __table_args__ = (
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
