"""Backfill helpers to emit embedding rebuild events from existing records."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product import ProductAttachment
from app.models.marketing import Promotion, PromotionProduct, PromotionAttachment
from app.models.resources import Attachment
from app.models.forms import Form
from app.models.list_query_metadata import ListQueryResource
from app.models.procurement import InboundShipment, InboundShipmentLine, SPOAllocation, PickingHeader, PickingLine
from app.models.order import Order, OrderStatus, OrderLine, Customer, Transporter
from app.models.projects import Project
from app.models.embeddings import EmbeddingDocument
from app.services.embedding_service import DEBTOR_SEED_ID_MAX, EmbeddingEventService, debtor_seed_id
from app.services.mcp_tool_capability_service import build_capability_documents

logger = logging.getLogger(__name__)

BackfillSource = Literal[
    "product",
    "promotion",
    "promotion_product",
    "inbound_shipment",
    "inbound_shipment_line",
    "spo_allocation",
    "picking_header",
    "picking_line",
    "product_attachment",
    "promotion_attachment",
    "attachment",
    "form",
    "schema_doc",
    "order",
    "order_status",
    "order_line",
    "customer",
    "transporter",
    "project",
    "mcp_tool",
    "all",
]


@dataclass
class BackfillStats:
    source: str
    scanned: int = 0
    queued: int = 0
    failed: int = 0


class EmbeddingBackfillService:
    def __init__(self, db: Session):
        self.db = db
        self.event_service = EmbeddingEventService(db)

    def run(
        self,
        *,
        source: BackfillSource,
        batch_size: int = 500,
        max_rows: int | None = None,
        dry_run: bool = False,
        triggered_by: str | None = None,
    ) -> dict:
        sources = [
            "product",
            "promotion",
            "promotion_product",
            "inbound_shipment",
            "inbound_shipment_line",
            "spo_allocation",
            "picking_header",
            "picking_line",
            "product_attachment",
            "promotion_attachment",
            "attachment",
            "form",
            "schema_doc",
            "order",
            "order_status",
            "order_line",
            "customer",
            "transporter",
            "mcp_tool",
        ] if source == "all" else [source]
        results: list[BackfillStats] = []
        for one in sources:
            stats = self._backfill_one(
                source=one,
                batch_size=batch_size,
                max_rows=max_rows,
                dry_run=dry_run,
                triggered_by=triggered_by,
            )
            results.append(stats)
        return {
            "dry_run": dry_run,
            "batch_size": batch_size,
            "max_rows": max_rows,
            "sources": [
                {"source": r.source, "scanned": r.scanned, "queued": r.queued, "failed": r.failed}
                for r in results
            ],
        }

    def _backfill_one(
        self,
        *,
        source: str,
        batch_size: int,
        max_rows: int | None,
        dry_run: bool,
        triggered_by: str | None,
    ) -> BackfillStats:
        stats = BackfillStats(source=source)
        offset = 0
        remaining = max_rows
        while True:
            limit = min(batch_size, remaining) if remaining is not None else batch_size
            rows = self._fetch_rows(source=source, limit=limit, offset=offset)
            if not rows:
                break
            for row in rows:
                stats.scanned += 1
                if dry_run:
                    continue
                try:
                    queued_item = self.event_service.queue_event(
                        source_type=source,
                        source_id=str(row["id"]),
                        source_key=row.get("source_key"),
                        source_updated_at=row.get("source_updated_at"),
                        event_type="embedding.rebuild_requested",
                        changed_fields=["manual_backfill"],
                        payload=row.get("payload"),
                        triggered_by=triggered_by or "system",
                    )
                    if queued_item is not None:
                        stats.queued += 1
                except Exception:
                    stats.failed += 1
            if remaining is not None:
                remaining -= len(rows)
                if remaining <= 0:
                    break
            offset += len(rows)
        return stats

    def _fetch_rows(self, *, source: str, limit: int, offset: int) -> list[dict]:
        if source == "product":
            rows = (
                self.db.query(Product.id, Product.product_code, Product.updated_at, Product.created_at)
                .filter(Product.is_active.is_(True))
                .order_by(Product.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "source_key": r.product_code, "source_updated_at": r.updated_at or r.created_at}
                for r in rows
            ]
        if source == "promotion":
            rows = (
                self.db.query(Promotion.id, Promotion.updated_at, Promotion.created_at)
                .filter(Promotion.is_active.is_(True))
                .order_by(Promotion.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "source_key": str(r.id), "source_updated_at": r.updated_at or r.created_at}
                for r in rows
            ]
        if source == "attachment":
            rows = (
                self.db.query(Attachment.id, Attachment.original_filename, Attachment.created_at)
                .filter(Attachment.is_deleted.is_(False))
                .order_by(Attachment.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "source_key": r.original_filename, "source_updated_at": r.created_at}
                for r in rows
            ]
        if source == "form":
            rows = (
                self.db.query(Form.id, Form.code, Form.updated_at, Form.created_at)
                .filter(Form.is_active.is_(True))
                .order_by(Form.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "source_key": r.code, "source_updated_at": r.updated_at or r.created_at}
                for r in rows
            ]
        if source == "schema_doc":
            rows = (
                self.db.query(ListQueryResource.id, ListQueryResource.resource_key, ListQueryResource.updated_at, ListQueryResource.created_at)
                .filter(ListQueryResource.is_active.is_(True))
                .order_by(ListQueryResource.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "source_key": r.resource_key, "source_updated_at": r.updated_at or r.created_at}
                for r in rows
            ]
        if source == "promotion_product":
            rows = self.db.query(PromotionProduct.id, PromotionProduct.created_at, PromotionProduct.updated_at).order_by(PromotionProduct.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": str(r.id), "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "inbound_shipment":
            rows = self.db.query(InboundShipment.id, InboundShipment.shipment_number, InboundShipment.created_at, InboundShipment.updated_at).order_by(InboundShipment.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": r.shipment_number, "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "inbound_shipment_line":
            rows = self.db.query(InboundShipmentLine.id, InboundShipmentLine.created_at, InboundShipmentLine.updated_at).order_by(InboundShipmentLine.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": str(r.id), "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "spo_allocation":
            # R9: a hidden line is never queued for a fresh embed - a backfill
            # run must not undo the deactivation `process_embedding_queue_item`
            # gives a retired row by re-activating its document.
            from app.services.scm import spo_supply

            rows = (
                self.db.query(SPOAllocation.id, SPOAllocation.spo_number, SPOAllocation.created_at, SPOAllocation.updated_at)
                .filter(*spo_supply.visible_line_clauses())
                .order_by(SPOAllocation.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [{"id": r.id, "source_key": r.spo_number or str(r.id), "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "picking_header":
            rows = self.db.query(PickingHeader.id, PickingHeader.picking_number, PickingHeader.created_at, PickingHeader.updated_at).order_by(PickingHeader.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": r.picking_number, "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "picking_line":
            rows = self.db.query(PickingLine.id, PickingLine.created_at, PickingLine.updated_at).order_by(PickingLine.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": str(r.id), "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "product_attachment":
            rows = self.db.query(ProductAttachment.id, ProductAttachment.created_at, ProductAttachment.updated_at).order_by(ProductAttachment.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": str(r.id), "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "promotion_attachment":
            rows = self.db.query(PromotionAttachment.id, PromotionAttachment.created_at, PromotionAttachment.updated_at).order_by(PromotionAttachment.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": str(r.id), "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "order":
            rows = self.db.query(Order.id, Order.order_number, Order.created_at, Order.updated_at).order_by(Order.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": r.order_number, "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "order_status":
            rows = self.db.query(OrderStatus.id, OrderStatus.status_code, OrderStatus.created_at).order_by(OrderStatus.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": r.status_code, "source_updated_at": r.created_at} for r in rows]
        if source == "order_line":
            rows = self.db.query(OrderLine.id, OrderLine.created_at, OrderLine.updated_at).order_by(OrderLine.created_at.asc()).offset(offset).limit(limit).all()
            return [{"id": r.id, "source_key": str(r.id), "source_updated_at": r.updated_at or r.created_at} for r in rows]
        if source == "mcp_tool":
            docs = build_capability_documents(include_planned=True)
            sliced = docs[offset: offset + limit]
            return [
                {"id": d.source_id, "source_key": d.source_key, "source_updated_at": None, "payload": {"capability": {"title": d.title, "source_key": d.source_key, "body_text": d.body_text, "metadata": d.metadata}}}
                for d in sliced
            ]
        if source == "customer":
            # Master customers.
            cust_rows = (
                self.db.query(Customer.id, Customer.customer_code, Customer.created_at, Customer.updated_at)
                .order_by(Customer.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            out = [
                {
                    "id": r.id,
                    "source_key": r.customer_code,
                    "source_updated_at": r.updated_at or r.created_at,
                }
                for r in cust_rows
            ]
            # When the customer master is exhausted, also seed embeddings for each
            # company's distinct orders.debtor_code values that have no matching
            # Customer row in THAT company: one seed per (company, code), stamped with
            # the company so it resolves inside it only. The seeds page on from where
            # the master ends (offset past the customer count), so a later page never
            # repeats them and the run reaches an empty page.
            if len(cust_rows) < limit:
                from sqlalchemy import func as _sa_func

                seen = {
                    (str(c[0]), c[1])
                    for c in self.db.query(Customer.company_id, Customer.customer_code).all()
                    if c[0] and c[1]
                }
                debtor_rows = (
                    self.db.query(Order.company_id, Order.debtor_code)
                    .filter(Order.debtor_code.isnot(None))
                    .filter(Order.company_id.isnot(None))
                    .filter(Order.deleted_at.is_(None))
                    .group_by(Order.company_id, Order.debtor_code)
                    .order_by(_sa_func.min(Order.created_at).asc(), Order.company_id, Order.debtor_code)
                    .all()
                )
                seeds: list[dict] = []
                for company_id, raw_code in debtor_rows:
                    code = (raw_code or "").strip()
                    if not code or (str(company_id), code) in seen:
                        continue
                    seen.add((str(company_id), code))  # " X" and "X" are one seed
                    seed_id = debtor_seed_id(str(company_id), code)
                    if len(seed_id) > DEBTOR_SEED_ID_MAX:
                        continue  # would not fit embedding_*.source_id
                    seeds.append({"id": seed_id, "source_key": f"debtor:{code}", "source_updated_at": None})
                seed_offset = max(0, offset - self.db.query(Customer.id).count())
                out.extend(seeds[seed_offset : seed_offset + limit - len(out)])
            return out
        if source == "project":
            from app.services.project_service import approved_projects

            rows = (
                approved_projects(self.db.query(Project.id, Project.project_code, Project.created_at))
                .order_by(Project.created_at.asc(), Project.id)
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "source_key": r.project_code, "source_updated_at": r.created_at}
                for r in rows
            ]
        if source == "transporter":
            rows = (
                self.db.query(Transporter.id, Transporter.code, Transporter.created_at)
                .order_by(Transporter.created_at.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "source_key": r.code, "source_updated_at": r.created_at}
                for r in rows
            ]
        raise ValueError(f"Unsupported source: {source}")


# --------------------------------------------------------------------------- #
# LOOKUP-EMBED-CENTRAL: capped, resumable backfill of one embedding model, and the search-model guard
# --------------------------------------------------------------------------- #
MAX_EMBED_FAILURES = 3
DEFAULT_BACKFILL_RPM = 20


@dataclass
class BackfillResult:
    embedded: int
    failed: int
    remaining: int
    complete: bool


def _failures(doc_metadata, model: str) -> int:
    try:
        return int(((doc_metadata or {}).get("embed_failures") or {}).get(model) or 0)
    except (TypeError, ValueError):
        return 0


def _missing_documents(db: Session, model: str):
    """Active keep-set documents with no current chunk of `model` (failed ones included)."""
    from sqlalchemy import exists

    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.services.embedding_settings import RECORD_KEEP_SET

    has_chunk = exists().where(
        EmbeddingChunk.document_id == EmbeddingDocument.id,
        EmbeddingChunk.model_name == model,
        EmbeddingChunk.is_current.is_(True),
    )
    return db.query(EmbeddingDocument).filter(
        EmbeddingDocument.is_active.is_(True),
        EmbeddingDocument.source_type.in_(sorted(RECORD_KEEP_SET)),
        ~has_chunk,
    )


_MISSING_SQL = (
    "FROM embedding_documents d WHERE d.is_active AND d.source_type = ANY(:keep) "
    "AND NOT EXISTS (SELECT 1 FROM embedding_chunks c WHERE c.document_id = d.id AND c.model_name = :m AND c.is_current)"
)
_FAILS_SQL = "COALESCE((d.metadata->'embed_failures'->>:m)::int, 0)"


def _count_remaining(db: Session, model: str) -> int:
    """Active keep-set documents with no current chunk of `model` that are not given up on (counted in SQL)."""
    from sqlalchemy import text

    from app.services.embedding_settings import RECORD_KEEP_SET

    return int(
        db.execute(
            text(f"SELECT count(*) {_MISSING_SQL} AND {_FAILS_SQL} < :max"),
            {"keep": sorted(RECORD_KEEP_SET), "m": model, "max": MAX_EMBED_FAILURES},
        ).scalar()
        or 0
    )


def count_failed(db: Session, model: str) -> int:
    """Active keep-set documents given up on for `model` (counted in SQL)."""
    from sqlalchemy import text

    from app.services.embedding_settings import RECORD_KEEP_SET

    return int(
        db.execute(
            text(f"SELECT count(*) {_MISSING_SQL} AND {_FAILS_SQL} >= :max"),
            {"keep": sorted(RECORD_KEEP_SET), "m": model, "max": MAX_EMBED_FAILURES},
        ).scalar()
        or 0
    )


def _counts_against_documents(exc: Exception) -> bool:
    """Only an error about the documents themselves counts: a 4xx other than auth (401/403), rate limit (429), an
    unknown model (404) and the 400s that name the key or the account (API_KEY_INVALID, FAILED_PRECONDITION).
    A 5xx, a missing key and a dropped connection are not the documents' fault either: the run stops uncounted."""
    status = getattr(exc, "status_code", None)
    if not (isinstance(status, int) and 400 <= status < 500) or status in (401, 403, 404, 429):
        return False
    text = str(exc).upper()
    return not any(marker in text for marker in ("API_KEY_INVALID", "FAILED_PRECONDITION"))


def clear_failures(db: Session, model: str) -> None:
    """Forget the failure counts of `model` (a fresh start: the setting moved to it, or Start was pressed)."""
    from sqlalchemy import text

    db.execute(
        text(
            "UPDATE embedding_documents SET metadata = (metadata::jsonb #- ARRAY['embed_failures', :m])::json "
            "WHERE metadata->'embed_failures'->>:m IS NOT NULL"
        ),
        {"m": model},
    )


def failed_documents(db: Session, model: str) -> list[tuple[str, str, int]]:
    """(source_type, source_id, failures) of keep-set documents given up on for `model`."""
    from app.models.embeddings import EmbeddingDocument

    rows = _missing_documents(db, model).with_entities(
        EmbeddingDocument.source_type, EmbeddingDocument.source_id, EmbeddingDocument.metadata_json
    ).all()
    return [(t, i, _failures(m, model)) for t, i, m in rows if _failures(m, model) >= MAX_EMBED_FAILURES]


def _document_chunks(doc) -> list[str]:
    from app.services.embedding_worker import _chunks_for_source

    metadata = doc.metadata_json or {}
    title = doc.title
    if doc.source_type == "certificate" and not metadata.get("identity_text"):
        title = None  # no identity text: the worker would fall back to the body, so do the same
    return _chunks_for_source(
        doc.source_type, {"title": title, "body_text": doc.body_text, "source_key": doc.source_key, "metadata": metadata}
    )


def ensure_product_spec_documents(db: Session) -> int:
    """A `product_spec` document for every active product that has spec text and none yet (specs derived before the
    change listener existed were never queued). Built with the worker's own text builder. Returns the documents made."""
    import hashlib  # noqa: F401
    from sqlalchemy import text

    from app.models.embeddings import EmbeddingDocument
    from app.services.embedding_service import EmbeddingReadService
    from app.services.embedding_worker import _canonical_for_source, _company_id_for_source

    ids = [
        str(r[0])
        for r in db.execute(
            text(
                "SELECT p.id FROM products p JOIN product_specifications s ON s.product_id = p.id "
                "WHERE p.is_active AND btrim(COALESCE(s.rendered_text, '')) <> '' "
                "AND NOT EXISTS (SELECT 1 FROM embedding_documents d "
                "WHERE d.source_type = 'product_spec' AND d.source_id = p.id::text)"
            )
        )
    ]
    made = 0
    for pid in ids:
        try:
            source = _canonical_for_source(db, "product_spec", pid)
        except Exception:  # noqa: BLE001 - a product the builder refuses simply gets no document
            continue
        digest = EmbeddingReadService(db).deterministic_hash(
            {
                "source_type": "product_spec",
                "source_id": pid,
                "title": source.get("title"),
                "body_text": source.get("body_text"),
                "metadata": source.get("metadata", {}),
            }
        )
        db.add(
            EmbeddingDocument(
                source_type="product_spec", source_id=pid, source_key=source.get("source_key"), title=source.get("title"),
                body_text=source["body_text"], metadata_json=source.get("metadata", {}),
                visibility_scope=source.get("visibility_scope"), source_hash=digest,
                source_updated_at=source.get("source_updated_at"), company_id=_company_id_for_source(db, "product_spec", pid),
                is_active=True,
            )
        )
        made += 1
    if made:
        db.flush()
    return made


def backfill_records(
    db: Session,
    model: str,
    *,
    rpm: int | None = None,
    batch_size: int = 100,
    sleep=None,
    should_stop=None,
) -> BackfillResult:
    """Embed every active keep-set document that has no current chunk of `model`.

    Requests carry at most `batch_size` texts and are spaced `60 / rpm` seconds apart. A request that raises adds one
    to each of its documents' failure count for `model` (`metadata["embed_failures"][model]`); at
    `MAX_EMBED_FAILURES` the document is given up on. A rerun only touches documents still missing.
    """
    import time

    from app.config import settings
    from app.models.embeddings import EmbeddingChunk
    from app.models.user import SystemSetting
    from app.services.embedding_settings import embed_for_model, provider_for_model

    sleep = sleep or time.sleep
    if rpm is None:
        row = db.query(SystemSetting.embedding_backfill_rpm).first()
        rpm = (row[0] if row else None) or DEFAULT_BACKFILL_RPM
    pause = 60.0 / max(1, int(rpm))

    ensure_product_spec_documents(db)
    embedded = failed = 0
    requests_made = 0
    stopped = False
    stop_error: list[Exception] = []

    def send(group, split: bool = True) -> None:
        nonlocal embedded, failed, requests_made, stopped
        if should_stop is not None and should_stop():
            stopped = True
            return
        if requests_made:
            sleep(pause)
        requests_made += 1
        texts = [t for _doc, chunks in group for t in chunks]
        try:
            vectors = embed_for_model(db, texts, model)
        except Exception as exc:  # noqa: BLE001
            logger.warning("records backfill request failed (%s): %s", model, exc)
            db.rollback()
            if not _counts_against_documents(exc):
                stopped = True
                stop_error.append(exc)
                return
            if split and len(group) > 1:
                # One bad document spoils a whole batch: halve it until the bad ones stand alone, and count only those.
                mid = len(group) // 2
                for half in (group[:mid], group[mid:]):
                    send(half)
                    if stopped:
                        return
                return
            for doc, _chunks in group:
                meta = dict(doc.metadata_json or {})
                counts = dict(meta.get("embed_failures") or {})
                counts[model] = _failures(meta, model) + 1
                meta["embed_failures"] = counts
                doc.metadata_json = meta
            failed += len(group)
            db.commit()
            return
        at = 0
        for doc, chunks in group:
            for idx, chunk_text in enumerate(chunks):
                db.add(
                    EmbeddingChunk(
                        document_id=doc.id,
                        source_type=doc.source_type,
                        source_id=doc.source_id,
                        chunk_index=idx,
                        chunk_text=chunk_text,
                        chunk_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                        embedding=vectors[at + idx],
                        model_name=model,
                        model_version=settings.embedding_model_version,
                        embedding_provider=provider_for_model(model),
                        source_hash=doc.source_hash,
                        metadata_json=doc.metadata_json or {},
                        company_id=doc.company_id,
                        is_current=True,
                    )
                )
            at += len(chunks)
            embedded += 1
        db.commit()

    # Documents are read once, in id order, so a document whose request fails is not retried in the same run.
    last_id = "00000000-0000-0000-0000-000000000000"
    group: list = []
    size = 0
    while not stopped:
        page = (
            _missing_documents(db, model)
            .filter(EmbeddingDocument.id > last_id)
            .order_by(EmbeddingDocument.id)
            .limit(max(batch_size, 1) * 5)
            .all()
        )
        if not page:
            break
        last_id = page[-1].id
        for doc in page:
            if _failures(doc.metadata_json, model) >= MAX_EMBED_FAILURES:
                continue
            chunks = _document_chunks(doc)
            if not chunks:
                continue
            if group and size + len(chunks) > batch_size:
                send(group)
                group, size = [], 0
                if stopped:
                    break
            group.append((doc, chunks))
            size += len(chunks)
        if stopped:
            break
    if group and not stopped:
        send(group)
    if stop_error:
        raise stop_error[0]  # auth / rate / server / key trouble: the job fails visibly, nothing was counted
    remaining = _count_remaining(db, model)
    return BackfillResult(embedded=embedded, failed=failed, remaining=remaining, complete=remaining == 0)


MAX_FAILED_SHARE = 0.01


def _guard_ready(db: Session, model: str) -> bool:
    """Every active keep-set document has a current chunk of `model` or is given up on, the model really has
    current chunks, fewer than 1% of the keep set is given up on, and the setting still names `model`."""
    from sqlalchemy import text

    from app.services.embedding_settings import RECORD_KEEP_SET, resolve_embedder

    if resolve_embedder(db)[1] != model:
        return False
    if _count_remaining(db, model):
        return False
    keep = sorted(RECORD_KEEP_SET)
    has_target = db.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM embedding_chunks c WHERE c.model_name = :m AND c.is_current "
            "AND c.source_type = ANY(:keep))"
        ),
        {"m": model, "keep": keep},
    ).scalar()
    if not has_target:
        return False
    total = db.execute(
        text("SELECT count(*) FROM embedding_documents d WHERE d.is_active AND d.source_type = ANY(:keep)"),
        {"keep": keep},
    ).scalar() or 0
    return count_failed(db, model) < MAX_FAILED_SHARE * max(int(total), 1)


def apply_search_model_guard(db: Session, model: str) -> bool:
    """Make `model` the records-search model once it is safe: `_guard_ready`. Builds the model's indexes first
    (CONCURRENTLY, outside any transaction; an INVALID index left by an interrupted build is reindexed). True when
    it flipped; False and nothing changed otherwise."""
    from sqlalchemy import text

    from app.models.user import SystemSetting
    from app.services import embedding_indexes

    if not _guard_ready(db, model):
        return False
    statements = embedding_indexes.index_ddl(model)
    if statements:
        invalid = [
            r[0]
            for r in db.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
                    "WHERE NOT i.indisvalid AND c.relname = ANY(:n)"
                ),
                {"n": list(embedding_indexes.index_names(model).values())},
            )
        ]
        db.commit()  # no transaction may be open on this session's connection while another builds the index
        from app.database import engine

        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("SET maintenance_work_mem = '512MB'"))
            try:
                for name in invalid:
                    conn.execute(text(f'REINDEX INDEX CONCURRENTLY "{name}"'))
                for ddl in statements:
                    conn.execute(text(ddl))
            finally:
                conn.execute(text("RESET maintenance_work_mem"))
    db.query(SystemSetting).update({"embedding_records_search_model": model})
    db.commit()
    return True
