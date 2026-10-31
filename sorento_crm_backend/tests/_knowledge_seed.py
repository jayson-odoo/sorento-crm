"""Seed helpers for the AGENTIC-KNOWLEDGE P1 tests (not a test module).

Every row is created on the blank Postgres schema, because CI's database is empty. The
vectors are hand built so the cosine similarity of a chunk to the query is exactly the number
a test asks for: no model, no network.
"""
from __future__ import annotations

import hashlib
import math
import uuid

from app.models.company import Company
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.models.resources import Attachment, AttachmentType
from tests._pg_fixture import unique_code

DIM = 1536
SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
KNOWLEDGE_MODEL = "gemini-embedding-001"


def one_hot(i: int) -> list[float]:
    v = [0.0] * DIM
    v[i % DIM] = 1.0
    return v


#: The query vector every search test embeds to.
QUERY_VEC = one_hot(0)
#: A chunk vector identical to the query (cosine similarity 1.0).
EXACT_VEC = QUERY_VEC


def vec_with_similarity(sim: float) -> list[float]:
    """A unit vector whose cosine similarity to QUERY_VEC is `sim`."""
    v = [0.0] * DIM
    v[0] = sim
    v[1] = math.sqrt(max(0.0, 1.0 - sim * sim))
    return v


def query_embed(_texts):
    """The `embed=` seam for search(): always the query vector."""
    return [QUERY_VEC]


def seed_company(db, name: str = "Other Co") -> str:
    suffix = uuid.uuid4().hex[:8]
    row = Company(id=str(uuid.uuid4()), name=f"ZZTK {name} {suffix}", code=f"K{suffix}")
    db.add(row)
    db.flush()
    return str(row.id)


def seed_team(db, name: str) -> str:
    from app.models.access import Team

    row = Team(id=str(uuid.uuid4()), name=name)
    db.add(row)
    db.flush()
    return str(row.id)


def seed_type(
    db,
    name: str = "Employee Handbook",
    *,
    audience: str = "staff",
    team_id: str | None = None,
    extensions: str = "pdf,docx,xlsx",
) -> AttachmentType:
    row = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=unique_code(name),
        allowed_extensions=extensions,
        ai_audience=audience,
        ai_escalate_team_id=team_id,
    )
    db.add(row)
    db.flush()
    return row


def seed_attachment(
    db,
    att_type: AttachmentType | None,
    filename: str = "Employee Handbook 2026.pdf",
    *,
    company_id: str | None = None,
) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"https://cdn.test/{uuid.uuid4().hex}/{filename}",
        attachment_type_id=str(att_type.id) if att_type is not None else None,
        is_deleted=False,
    )
    if company_id is not None:
        row.company_id = company_id
    db.add(row)
    db.flush()
    return row


def seed_chunk(
    db,
    attachment: Attachment,
    vec: list[float],
    *,
    text: str = "Annual leave is 14 days after three years of service.",
    page: int = 14,
    heading: str | None = "Leave",
    index: int = 0,
    company_id: str | None = ...,  # type: ignore[assignment]
    source_type: str = "knowledge",
    model_name: str = KNOWLEDGE_MODEL,
) -> EmbeddingChunk:
    """One chunk. `company_id` defaults to the attachment's own company.

    `source_type` / `model_name` let a test plant a keep-set control row, or a knowledge row
    under the records-search model, so an exclusion cannot pass on a model mismatch alone.
    """
    cid = attachment.company_id if company_id is ... else company_id
    source_id = str(attachment.id)
    h = hashlib.sha256(f"{source_type}:{source_id}".encode()).hexdigest()
    doc = (
        db.query(EmbeddingDocument)
        .filter(EmbeddingDocument.source_type == source_type, EmbeddingDocument.source_id == source_id)
        .first()
    )
    if doc is None:
        doc = EmbeddingDocument(
            source_type=source_type,
            source_id=source_id,
            title=attachment.stored_filename,
            body_text=text,
            metadata_json={},
            source_hash=h,
            company_id=cid,
            is_active=True,
        )
        db.add(doc)
        db.flush()
    chunk = EmbeddingChunk(
        document_id=doc.id,
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        chunk_hash=hashlib.sha256(f"{source_id}:{index}:{text}".encode()).hexdigest(),
        embedding=vec,
        model_name=model_name,
        model_version="1",
        embedding_provider="gemini",
        source_hash=h,
        metadata_json={"attachment_id": source_id, "page": page, "heading": heading},
        company_id=cid,
        is_current=True,
    )
    db.add(chunk)
    db.flush()
    return chunk


def seed_reader(db, *, slugs=("resource.attachments.view",)) -> str:
    """A user (no linked contact) holding exactly `slugs`."""
    from tests.chatbot.agent._seed import seed_user

    return seed_user(db, contact_pk=None, slugs=slugs)
