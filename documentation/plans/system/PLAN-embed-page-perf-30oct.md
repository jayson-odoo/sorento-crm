# PLAN: Embeddings page perf (EMBED-PAGE-PERF)

Status: in review, merge-ready pending CI (size M per crew 30 Oct: one additive index migration, built online)

## Problem
Owner, 30 Oct on prod: System > Configuration > Embeddings, the Records tab sits empty while
`GET /api/v1/system/embeddings/overview` loads (`sorento_crm_backend/app/api/v1/system/embeddings.py:117`).
The page refetched it every 30 s whichever tab showed.

## Cause (measured)
Every count in the overview read the whole `embedding_chunks` heap: `count(id)` defeated an
index-only scan, and the "documents missing the target model" anti-join (`_MISSING_SQL`,
`app/services/embedding_backfill_service.py`) had no index holding both model and document. The heap
keeps every superseded and old-model chunk (text + 1536-dim vector), so it grows with each re-embed.
Prod-shaped seed (screenshot's doc counts, 2 models, 3 superseded generations = 469k chunks):
cold 3.3 s, warm 0.3 s.

## Fix
- `count(*)` for the chunk counts: index-only on the existing `uq_embedding_chunks_current`.
- Partial index `ix_embedding_chunks_current_model_doc (model_name, document_id) WHERE is_current`
  (migration `epp_0001_chunk_coverage_idx`, CONCURRENTLY via `app/utils/online_index.py`, retried by
  `scripts/ensure_goods_chain_indexes.py`; also on the model so create_all builds it).
- FE: the overview polls only while the Records tab shows in a visible browser tab; mutation refreshes
  join an in-flight fetch (`cancelRefetch: false`) instead of aborting it (an abort leaves the server query running).
Result on the same seed: cold 0.32-0.40 s, warm 0.19 s.

## Not built (needs crew OK)
Project documents: `scripts/seed_project_embeddings.py` already backfills existing approved projects (run once on prod); see the PR crew-note.
