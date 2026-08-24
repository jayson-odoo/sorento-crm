"""Collapse duplicate *current* embedding rows so each (source, model, chunk_index) wins once.

Fixes two failure modes:
  1) Multiple *batches* (different source_hash) all left is_current=true - picks the newest
     batch by max(embedded_at) per hash, marks others non-current, syncs embedding_documents.
  2) Multiple rows for the same chunk_index still current (e.g. partial unique index missing) - 
     keeps the newest row per (source_type, source_id, model_name, model_version, chunk_index).

RAG reads only is_current=true; this script does not change vectors, only flags (unless --delete-superseded).

Usage:
  cd sorento_crm_backend && .venv/bin/python -m app.scripts.dedupe_embedding_chunks_current
  .venv/bin/python -m app.scripts.dedupe_embedding_chunks_current --source-type mcp_tool --dry-run
  .venv/bin/python -m app.scripts.dedupe_embedding_chunks_current --source-type mcp_tool --delete-superseded
"""
from __future__ import annotations

import argparse
from datetime import datetime

from sqlalchemy import func, text

from app.database import SessionLocal
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument


def main() -> None:
    parser = argparse.ArgumentParser(description="Dedupe embedding_chunks is_current per source partition")
    parser.add_argument("--source-type", default=None, help="Only this source_type (default: all types)")
    parser.add_argument("--dry-run", action="store_true", help="Print summary only (no writes)")
    parser.add_argument(
        "--delete-superseded",
        action="store_true",
        help="After fixes, DELETE rows with is_current=false (optional space reclaim)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    now = datetime.utcnow()
    try:
        part_q = db.query(
            EmbeddingChunk.source_type,
            EmbeddingChunk.source_id,
            EmbeddingChunk.model_name,
            EmbeddingChunk.model_version,
        ).distinct()
        if args.source_type:
            part_q = part_q.filter(EmbeddingChunk.source_type == args.source_type)
        partitions = part_q.all()

        hash_collapses = 0
        rows_marked_false_hash = 0
        rows_marked_true_hash = 0

        for st, sid, mn, mv in partitions:
            distinct_current = (
                db.query(EmbeddingChunk.source_hash)
                .filter(
                    EmbeddingChunk.source_type == st,
                    EmbeddingChunk.source_id == sid,
                    EmbeddingChunk.model_name == mn,
                    EmbeddingChunk.model_version == mv,
                    EmbeddingChunk.is_current.is_(True),
                )
                .distinct()
                .count()
            )
            if distinct_current <= 1:
                continue

            batch_rows = (
                db.query(EmbeddingChunk.source_hash, func.max(EmbeddingChunk.embedded_at).label("t"))
                .filter(
                    EmbeddingChunk.source_type == st,
                    EmbeddingChunk.source_id == sid,
                    EmbeddingChunk.model_name == mn,
                    EmbeddingChunk.model_version == mv,
                )
                .group_by(EmbeddingChunk.source_hash)
                .all()
            )
            if not batch_rows:
                continue
            winner_hash, _winner_t = max(batch_rows, key=lambda r: r[1])

            hash_collapses += 1
            if args.dry_run:
                print(f"[dry-run] collapse hashes {st} {sid}: {distinct_current} -> keep {winner_hash[:16]}…")
                continue

            u1 = (
                db.query(EmbeddingChunk)
                .filter(
                    EmbeddingChunk.source_type == st,
                    EmbeddingChunk.source_id == sid,
                    EmbeddingChunk.model_name == mn,
                    EmbeddingChunk.model_version == mv,
                    EmbeddingChunk.source_hash != winner_hash,
                )
                .update(
                    {EmbeddingChunk.is_current: False, EmbeddingChunk.superseded_at: now},
                    synchronize_session=False,
                )
            )
            rows_marked_false_hash += int(u1 or 0)

            u2 = (
                db.query(EmbeddingChunk)
                .filter(
                    EmbeddingChunk.source_type == st,
                    EmbeddingChunk.source_id == sid,
                    EmbeddingChunk.model_name == mn,
                    EmbeddingChunk.model_version == mv,
                    EmbeddingChunk.source_hash == winner_hash,
                )
                .update(
                    {EmbeddingChunk.is_current: True, EmbeddingChunk.superseded_at: None},
                    synchronize_session=False,
                )
            )
            rows_marked_true_hash += int(u2 or 0)

            doc = (
                db.query(EmbeddingDocument)
                .filter(EmbeddingDocument.source_type == st, EmbeddingDocument.source_id == sid)
                .first()
            )
            if doc:
                doc.source_hash = winner_hash
                doc.is_active = True

            db.commit()

        # Per chunk_index: at most one current row (newest embedded_at wins).
        st_filter = ""
        params: dict = {"now": now}
        if args.source_type:
            st_filter = "AND source_type = :st"
            params["st"] = args.source_type

        dup_sql = text(
            f"""
            UPDATE embedding_chunks AS ec
            SET is_current = false, superseded_at = :now
            WHERE ec.id IN (
                SELECT id FROM (
                    SELECT id,
                        ROW_NUMBER() OVER (
                            PARTITION BY source_type, source_id, model_name, model_version, chunk_index
                            ORDER BY embedded_at DESC NULLS LAST, id DESC
                        ) AS rn
                    FROM embedding_chunks
                    WHERE is_current = true
                    {st_filter}
                ) sub
                WHERE sub.rn > 1
            )
            """
        )
        if args.dry_run:
            count_sql = text(
                f"""
                SELECT count(*) FROM (
                    SELECT id,
                        ROW_NUMBER() OVER (
                            PARTITION BY source_type, source_id, model_name, model_version, chunk_index
                            ORDER BY embedded_at DESC NULLS LAST, id DESC
                        ) AS rn
                    FROM embedding_chunks
                    WHERE is_current = true
                    {st_filter}
                ) sub
                WHERE sub.rn > 1
                """
            )
            chunk_dupes = db.execute(count_sql, params).scalar() or 0
        else:
            r = db.execute(dup_sql, params)
            chunk_dupes = r.rowcount if r else 0
            db.commit()

        deleted = 0
        if args.delete_superseded and not args.dry_run:
            del_q = db.query(EmbeddingChunk).filter(EmbeddingChunk.is_current.is_(False))
            if args.source_type:
                del_q = del_q.filter(EmbeddingChunk.source_type == args.source_type)
            deleted = int(del_q.delete(synchronize_session=False) or 0)
            db.commit()

        print(
            {
                "partitions_scanned": len(partitions),
                "hash_collapses": hash_collapses,
                "rows_marked_non_current_hash_pass": rows_marked_false_hash,
                "rows_refreshed_winner_hash_pass": rows_marked_true_hash,
                "extra_current_rows_cleared_chunk_index_pass": int(chunk_dupes) if not args.dry_run else None,
                "chunk_index_dupes_would_clear": int(chunk_dupes) if args.dry_run else None,
                "superseded_rows_deleted": deleted,
                "dry_run": args.dry_run,
                "source_type_filter": args.source_type,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
