"""RQ worker for embedding queue processing."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.embeddings import EmbeddingQueue, EmbeddingDocument, EmbeddingChunk
from app.models.product import Product, ProductCategory, Brand
from app.models.marketing import Promotion
from app.models.marketing import PromotionProduct, PromotionAttachment
from app.models.resources import Attachment
from app.models.forms import Form
from app.models.list_query_metadata import ListQueryResource, ListQueryField
from app.models.procurement import InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine
from app.models.order import Order, OrderStatus, OrderLine
from app.models.product import ProductAttachment
from app.services.embedding_service import EmbeddingReadService

logger = logging.getLogger(__name__)


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _canonical_for_source(db: Session, source_type: str, source_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if source_type == "mcp_tool":
        capability = (payload or {}).get("capability") or {}
        body_text = str(capability.get("body_text") or "").strip()
        if not body_text:
            raise ValueError("mcp_tool payload.capability.body_text is required")
        metadata = capability.get("metadata") or {}
        return {
            "source_key": capability.get("source_key") or source_id,
            "title": capability.get("title") or source_id,
            "body_text": body_text,
            "visibility_scope": "internal",
            "source_updated_at": datetime.utcnow(),
            "metadata": metadata,
        }

    if source_type == "product":
        row = (
            db.query(Product, ProductCategory, Brand)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .filter(Product.id == source_id)
            .first()
        )
        if not row:
            raise ValueError(f"Product not found: {source_id}")
        product, category, brand = row
        body = "\n".join(
            [
                "Source Type: Product",
                f"Product Code: {product.product_code}",
                f"Product Name: {product.product_name}",
                f"Category: {category.category_name if category else ''}",
                f"Brand: {brand.brand_name if brand else ''}",
                f"Description: {product.description or ''}",
                f"Item Type: {product.item_type or ''}",
            ]
        ).strip()
        return {
            "source_key": product.product_code,
            "title": product.product_name,
            "body_text": body,
            "visibility_scope": "customer",
            "source_updated_at": product.updated_at or product.created_at,
            "metadata": {"category": category.category_name if category else None, "brand": brand.brand_name if brand else None},
        }

    if source_type == "promotion":
        promotion = db.query(Promotion).filter(Promotion.id == source_id).first()
        if not promotion:
            raise ValueError(f"Promotion not found: {source_id}")
        title = (promotion.description or f"Promotion {str(promotion.id)[:8]}").strip().splitlines()[0]
        body = "\n".join(
            [
                "Source Type: Promotion",
                f"Description: {promotion.description or ''}",
                f"Active From: {promotion.start_date}",
                f"Active Until: {promotion.end_date}",
            ]
        ).strip()
        return {
            "source_key": str(promotion.id),
            "title": title,
            "body_text": body,
            "visibility_scope": "customer",
            "source_updated_at": promotion.updated_at or promotion.created_at,
            "metadata": {"access_levels": promotion.access_levels or []},
        }

    if source_type == "attachment":
        attachment = db.query(Attachment).filter(Attachment.id == source_id).first()
        if not attachment:
            raise ValueError(f"Attachment not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Attachment",
                f"File Name: {attachment.original_filename}",
                f"Description: {attachment.description or ''}",
                f"Path: {attachment.full_directory_path or ''}",
                f"Entity Type: {attachment.entity_type or ''}",
                f"Entity ID: {attachment.entity_id or ''}",
            ]
        ).strip()
        return {
            "source_key": attachment.original_filename,
            "title": attachment.original_filename,
            "body_text": body,
            "visibility_scope": "customer",
            "source_updated_at": attachment.created_at,
            "metadata": {"entity_type": attachment.entity_type, "access_levels": attachment.access_levels or []},
        }

    if source_type == "form":
        form = db.query(Form).filter(Form.id == source_id).first()
        if not form:
            raise ValueError(f"Form not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Form",
                f"Form Code: {form.code}",
                f"Form Name: {form.name}",
                f"Form Type: {form.form_type}",
                f"Purpose: {form.purpose or ''}",
                f"Language: {form.language or ''}",
            ]
        ).strip()
        return {
            "source_key": form.code,
            "title": form.name,
            "body_text": body,
            "visibility_scope": "internal",
            "source_updated_at": form.updated_at or form.created_at,
            "metadata": {
                "language": form.language,
                "is_active": form.is_active,
                "form_type": form.form_type,
            },
        }

    if source_type == "schema_doc":
        resource = db.query(ListQueryResource).filter(ListQueryResource.id == source_id).first()
        if not resource:
            raise ValueError(f"Schema doc not found: {source_id}")
        fields = (
            db.query(ListQueryField)
            .filter(ListQueryField.resource_id == resource.id)
            .order_by(ListQueryField.sort_order.asc())
            .all()
        )
        field_lines = [f"{f.field_key}: {f.label}" for f in fields]
        body = "\n".join(
            ["Source Type: Schema Doc", f"Resource: {resource.resource_key}", f"Name: {resource.display_name}", "Fields:", *field_lines]
        ).strip()
        return {
            "source_key": resource.resource_key,
            "title": resource.display_name,
            "body_text": body,
            "visibility_scope": "internal",
            "source_updated_at": resource.updated_at or resource.created_at,
            "metadata": {"resource_key": resource.resource_key, "field_count": len(field_lines)},
        }

    if source_type == "promotion_product":
        row = db.query(PromotionProduct, Promotion, Product).join(Promotion, Promotion.id == PromotionProduct.promotion_id).join(Product, Product.id == PromotionProduct.product_id).filter(PromotionProduct.id == source_id).first()
        if not row:
            raise ValueError(f"Promotion product not found: {source_id}")
        line, promo, product = row
        promo_label = (promo.description or f"Promotion {str(promo.id)[:8]}").strip().splitlines()[0]
        body = "\n".join(
            [
                "Source Type: Promotion Product",
                f"Promotion: {promo_label}",
                f"Product Code: {product.product_code}",
                f"Product Name: {product.product_name}",
                f"Promo Selling Price: {line.promo_selling_price}",
                f"Discount Percent: {line.discount_percent}",
            ]
        ).strip()
        return {"source_key": f"{promo.id}:{product.product_code}", "title": f"{promo_label} / {product.product_name}", "body_text": body, "visibility_scope": "customer", "source_updated_at": line.updated_at or line.created_at, "metadata": {"promotion_id": line.promotion_id, "product_id": line.product_id}}

    if source_type == "inbound_shipment":
        shipment = db.query(InboundShipment).filter(InboundShipment.id == source_id).first()
        if not shipment:
            raise ValueError(f"Inbound shipment not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Inbound Shipment",
                f"Shipment Number: {shipment.shipment_number}",
                f"Shipment Status: {shipment.shipment_status}",
                f"Shipment Date: {shipment.shipment_date}",
                f"Estimated Arrival: {shipment.estimated_arrival_date}",
                f"Notes: {shipment.notes or ''}",
            ]
        ).strip()
        return {"source_key": shipment.shipment_number, "title": shipment.shipment_number, "body_text": body, "visibility_scope": "internal", "source_updated_at": shipment.updated_at or shipment.created_at, "metadata": {"supplier_id": shipment.supplier_id, "access_levels": shipment.access_levels or []}}

    if source_type == "inbound_shipment_line":
        line = db.query(InboundShipmentLine).filter(InboundShipmentLine.id == source_id).first()
        if not line:
            raise ValueError(f"Inbound shipment line not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Inbound Shipment Line",
                f"Shipment ID: {line.shipment_id}",
                f"Product ID: {line.product_id}",
                f"Quantity Shipped: {line.quantity_shipped}",
                f"Line Status: {line.line_status}",
                f"Batch Number: {line.batch_number or ''}",
            ]
        ).strip()
        return {"source_key": f"{line.shipment_id}:{line.product_id}", "title": "Inbound Shipment Line", "body_text": body, "visibility_scope": "internal", "source_updated_at": line.updated_at or line.created_at, "metadata": {"shipment_id": line.shipment_id, "product_id": line.product_id}}

    if source_type == "spo_allocation":
        row = db.query(SPOAllocation).filter(SPOAllocation.id == source_id).first()
        if not row:
            raise ValueError(f"SPO allocation not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: SPO Allocation",
                f"SPO Number: {row.spo_number or ''}",
                f"Inbound Shipment ID: {row.inbound_shipment_id}",
                f"Product ID: {row.product_id}",
                f"Allocated Quantity: {row.allocated_quantity}",
                f"Receipt Status: {row.receipt_status}",
            ]
        ).strip()
        return {"source_key": row.spo_number or str(row.id), "title": row.spo_number or "SPO Allocation", "body_text": body, "visibility_scope": "internal", "source_updated_at": row.updated_at or row.created_at, "metadata": {"warehouse_id": row.warehouse_id, "storage_zone_id": row.storage_zone_id}}

    if source_type == "picking_header":
        row = db.query(PickingHeader).filter(PickingHeader.id == source_id).first()
        if not row:
            raise ValueError(f"Picking header not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Picking Header",
                f"Picking Number: {row.picking_number}",
                f"SPO Number: {row.spo_number or ''}",
                f"Picking Status: {row.picking_status}",
                f"Inspection Status: {row.inspection_status}",
                f"Notes: {row.notes or ''}",
            ]
        ).strip()
        return {"source_key": row.picking_number, "title": row.picking_number, "body_text": body, "visibility_scope": "internal", "source_updated_at": row.updated_at or row.created_at, "metadata": {"picking_type": row.picking_type}}

    if source_type == "picking_line":
        row = db.query(PickingLine).filter(PickingLine.id == source_id).first()
        if not row:
            raise ValueError(f"Picking line not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Picking Line",
                f"Picking Header ID: {row.picking_header_id}",
                f"Product ID: {row.product_id}",
                f"Quantity Expected: {row.quantity_expected}",
                f"Quantity Picked: {row.quantity_picked}",
                f"Condition: {row.picked_condition}",
            ]
        ).strip()
        return {"source_key": f"{row.picking_header_id}:{row.product_id}", "title": "Picking Line", "body_text": body, "visibility_scope": "internal", "source_updated_at": row.updated_at or row.created_at, "metadata": {"spo_allocation_id": row.spo_allocation_id}}

    if source_type == "product_attachment":
        row = db.query(ProductAttachment).filter(ProductAttachment.id == source_id).first()
        if not row:
            raise ValueError(f"Product attachment not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Product Attachment",
                f"Product ID: {row.product_id}",
                f"Attachment ID: {row.attachment_id}",
                f"Is Primary: {row.is_primary}",
                f"Sort Order: {row.sort_order}",
            ]
        ).strip()
        return {"source_key": f"{row.product_id}:{row.attachment_id}", "title": "Product Attachment", "body_text": body, "visibility_scope": "customer", "source_updated_at": row.updated_at or row.created_at, "metadata": {"access_levels": row.access_levels or []}}

    if source_type == "promotion_attachment":
        row = db.query(PromotionAttachment).filter(PromotionAttachment.id == source_id).first()
        if not row:
            raise ValueError(f"Promotion attachment not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Promotion Attachment",
                f"Promotion ID: {row.promotion_id}",
                f"Attachment ID: {row.attachment_id}",
                f"Is Primary: {row.is_primary}",
                f"Sort Order: {row.sort_order}",
            ]
        ).strip()
        return {"source_key": f"{row.promotion_id}:{row.attachment_id}", "title": "Promotion Attachment", "body_text": body, "visibility_scope": "customer", "source_updated_at": row.updated_at or row.created_at, "metadata": {}}

    if source_type == "order":
        row = db.query(Order).filter(Order.id == source_id).first()
        if not row:
            raise ValueError(f"Order not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Order",
                f"Order Number: {row.order_number}",
                f"Debtor Name: {row.debtor_name or ''}",
                f"Salesman: {row.salesman or ''}",
                f"Order Type: {row.order_type or ''}",
                f"Remarks: {row.remarks or ''}",
            ]
        ).strip()
        return {"source_key": row.order_number, "title": row.order_number, "body_text": body, "visibility_scope": "internal", "source_updated_at": row.updated_at or row.created_at, "metadata": {"order_status_id": row.order_status_id, "is_cancelled": row.is_cancelled}}

    if source_type == "order_status":
        row = db.query(OrderStatus).filter(OrderStatus.id == source_id).first()
        if not row:
            raise ValueError(f"Order status not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Order Status",
                f"Status Code: {row.status_code}",
                f"Status Name: {row.status_name}",
                f"Description: {row.description or ''}",
                f"Sequence: {row.sequence}",
            ]
        ).strip()
        return {"source_key": row.status_code, "title": row.status_name, "body_text": body, "visibility_scope": "internal", "source_updated_at": row.created_at, "metadata": {"is_final_status": row.is_final_status}}

    if source_type == "order_line":
        row = db.query(OrderLine).filter(OrderLine.id == source_id).first()
        if not row:
            raise ValueError(f"Order line not found: {source_id}")
        body = "\n".join(
            [
                "Source Type: Order Line",
                f"Order ID: {row.order_id}",
                f"Product ID: {row.product_id}",
                f"Warehouse ID: {row.warehouse_id}",
                f"Quantity: {row.quantity}",
                f"Unit Price: {row.unit_price}",
            ]
        ).strip()
        return {"source_key": f"{row.order_id}:{row.line_sequence}", "title": "Order Line", "body_text": body, "visibility_scope": "internal", "source_updated_at": row.updated_at or row.created_at, "metadata": {"line_sequence": row.line_sequence}}

    raise ValueError(f"Unsupported source type: {source_type}")


def _embed_text_chunks(chunks: list[str]) -> list[list[float]]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for embedding worker")
    if not chunks:
        return []
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    payload = {"model": settings.embedding_model_name, "input": chunks}
    with httpx.Client(timeout=30) as client:
        response = client.post(settings.openai_embeddings_url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    vectors = [item["embedding"] for item in data.get("data", [])]
    if len(vectors) != len(chunks):
        raise ValueError("Embedding provider returned mismatched vector count")
    return vectors


def _chunks_for_source(source_type: str, source: dict[str, Any]) -> list[str]:
    if source_type == "mcp_tool":
        md = source.get("metadata") or {}
        title = str(source.get("title") or "").strip()
        body_text = str(source.get("body_text") or "").strip()
        questions = [str(q).strip() for q in (md.get("typical_user_questions") or []) if str(q).strip()]
        aliases = [str(a).strip() for a in (md.get("aliases") or []) if str(a).strip()]
        required_fields = [str(f).strip() for f in (md.get("required_fields") or []) if str(f).strip()]
        optional_fields = [str(f).strip() for f in (md.get("optional_fields") or []) if str(f).strip()]

        chunks: list[str] = []
        if body_text:
            chunks.append(body_text)
        if aliases:
            chunks.append(f"Tool aliases for {title}: " + ", ".join(aliases))
        chunks.extend(questions)
        if required_fields:
            chunks.append(f"Required fields for {title}: " + ", ".join(required_fields))
        if optional_fields:
            chunks.append(f"Optional fields for {title}: " + ", ".join(optional_fields))
        if chunks:
            return chunks
    return _chunk_text(source["body_text"], settings.embedding_chunk_size, settings.embedding_chunk_overlap)


def process_embedding_queue_item(queue_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        queue_item = db.query(EmbeddingQueue).filter(EmbeddingQueue.id == queue_id).first()
        if not queue_item:
            return {"status": "missing", "queue_id": queue_id}
        if queue_item.status in {"completed", "skipped"}:
            return {"status": queue_item.status, "queue_id": queue_id}

        queue_item.status = "processing"
        db.commit()

        payload = queue_item.payload or {}
        source_payload = payload.get("payload") if isinstance(payload, dict) else None
        source = _canonical_for_source(db, queue_item.source_type, queue_item.source_id, payload=source_payload)
        read_svc = EmbeddingReadService(db)
        source_hash = read_svc.deterministic_hash(
            {
                "source_type": queue_item.source_type,
                "source_id": queue_item.source_id,
                "title": source.get("title"),
                "body_text": source.get("body_text"),
                "metadata": source.get("metadata", {}),
            }
        )
        queue_item.source_hash = source_hash

        distinct_current = read_svc.current_chunk_hashes_distinct(
            queue_item.source_type,
            queue_item.source_id,
            settings.embedding_model_name,
            settings.embedding_model_version,
        )
        # Skip only when a single current generation exists and it already matches this payload.
        # If multiple distinct source_hash values are current (duplicate batches), re-embed so
        # mark_previous_non_current + insert can consolidate.
        if len(distinct_current) == 1 and source_hash in distinct_current:
            queue_item.status = "skipped"
            queue_item.processed_at = datetime.utcnow()
            db.commit()
            return {"status": "skipped", "queue_id": queue_id}

        doc = (
            db.query(EmbeddingDocument)
            .filter(
                EmbeddingDocument.source_type == queue_item.source_type,
                EmbeddingDocument.source_id == queue_item.source_id,
            )
            .order_by(EmbeddingDocument.created_at.desc())
            .first()
        )
        if doc is not None:
            doc.source_key = source.get("source_key")
            doc.title = source.get("title")
            doc.body_text = source["body_text"]
            doc.metadata_json = source.get("metadata", {})
            doc.visibility_scope = source.get("visibility_scope")
            doc.source_hash = source_hash
            doc.source_updated_at = source.get("source_updated_at")
            doc.is_active = True
        else:
            doc = EmbeddingDocument(
                source_type=queue_item.source_type,
                source_id=queue_item.source_id,
                source_key=source.get("source_key"),
                title=source.get("title"),
                body_text=source["body_text"],
                metadata_json=source.get("metadata", {}),
                visibility_scope=source.get("visibility_scope"),
                source_hash=source_hash,
                source_updated_at=source.get("source_updated_at"),
                is_active=True,
            )
            db.add(doc)
        db.flush()

        chunks = _chunks_for_source(queue_item.source_type, source)
        vectors = _embed_text_chunks(chunks)

        read_svc.mark_previous_non_current(
            queue_item.source_type,
            queue_item.source_id,
            settings.embedding_model_name,
            settings.embedding_model_version,
        )
        db.flush()

        for idx, (chunk_text, vector) in enumerate(zip(chunks, vectors)):
            db.add(
                EmbeddingChunk(
                    document_id=doc.id,
                    source_type=queue_item.source_type,
                    source_id=queue_item.source_id,
                    chunk_index=idx,
                    chunk_text=chunk_text,
                    chunk_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                    embedding=vector,
                    model_name=settings.embedding_model_name,
                    model_version=settings.embedding_model_version,
                    embedding_provider=settings.embedding_provider,
                    source_hash=source_hash,
                    metadata_json=source.get("metadata", {}),
                    is_current=True,
                )
            )

        queue_item.status = "completed"
        queue_item.processed_at = datetime.utcnow()
        db.commit()
        return {"status": "completed", "queue_id": queue_id, "chunks": len(chunks)}
    except Exception as exc:
        db.rollback()
        queue_item = db.query(EmbeddingQueue).filter(EmbeddingQueue.id == queue_id).first()
        if queue_item:
            queue_item.retry_count = int(queue_item.retry_count or 0) + 1
            queue_item.last_error = str(exc)
            if queue_item.retry_count >= settings.embedding_max_retries:
                queue_item.status = "dead_letter"
            else:
                queue_item.status = "pending"
                queue_item.available_at = datetime.utcnow() + timedelta(
                    seconds=settings.embedding_retry_backoff_seconds * queue_item.retry_count
                )
            db.commit()
        logger.exception("Embedding worker failed for queue item %s", queue_id)
        return {"status": "failed", "queue_id": queue_id, "error": str(exc)}
    finally:
        db.close()
