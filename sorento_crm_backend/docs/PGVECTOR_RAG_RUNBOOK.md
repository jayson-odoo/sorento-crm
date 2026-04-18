# PGVector RAG Runbook

## Scope
- Event-driven embedding pipeline for `product`, `promotion`, `attachment`, `form`, and `schema_doc`.
- Queue transport uses Redis RQ (`embeddings` queue).
- Vector storage uses PostgreSQL pgvector (`vector(1536)` with OpenAI `text-embedding-3-small`).

## Required environment variables
- `OPENAI_API_KEY`
- `EMBEDDING_MODEL_NAME` (default: `text-embedding-3-small`)
- `EMBEDDING_MODEL_VERSION` (default: `v1`)
- `EMBEDDING_QUEUE_NAME` (default: `embeddings`)
- `EMBEDDING_MAX_RETRIES` (default: `5`)
- `EMBEDDING_RETRY_BACKOFF_SECONDS` (default: `60`)

## Deployment checklist
1. Run Alembic migrations through:
   - `142_pgvector_embedding_pipeline`
   - `143_seed_embedding_job_processor_task`
2. Confirm extension exists:
   - `CREATE EXTENSION IF NOT EXISTS vector;`
3. Ensure Redis is reachable by backend.
4. Confirm scheduler is running and `embedding_job_processor` scheduled task is enabled.
5. Set `OPENAI_API_KEY` and restart backend.

## Operational metrics
- Queue status counts: `pending`, `processing`, `completed`, `failed`, `dead_letter`, `skipped`.
- Endpoint: `GET /api/v1/system/embeddings/metrics`

## Failure handling
- Worker retry behavior:
  - increments `retry_count`
  - requeues with exponential backoff (`retry_count * EMBEDDING_RETRY_BACKOFF_SECONDS`)
  - moves to `dead_letter` after `EMBEDDING_MAX_RETRIES`
- Dead letter inspection:
  - `GET /api/v1/system/embeddings/dead-letters`

## Replay dead letters
- Endpoint: `POST /api/v1/system/embeddings/replay-dead-letters?limit=100`
- Replays items by setting status back to `pending` and enqueueing a fresh RQ job.

## Manual rebuild
- Endpoint: `POST /api/v1/system/embeddings/rebuild/{source_type}/{source_id}`
- Emits `embedding.rebuild_requested` for targeted reindex.

## Bulk seed / backfill from existing data
- API endpoint: `POST /api/v1/system/embeddings/backfill`
  - Query params:
    - `source=all|product|promotion|attachment|form|schema_doc`
    - `batch_size` (default `500`)
    - `max_rows` (optional cap)
    - `dry_run=true|false`
- CLI script:
  - `python -m app.scripts.seed_embeddings --source all --batch-size 300`
  - `python -m app.scripts.seed_embeddings --source product --max-rows 1000 --dry-run`

## n8n retrieval endpoint
- Endpoint: `POST /api/v1/external/rag/search`
- Uses semantic search over current vectors only (`is_current=true`).
- Filters supported: `source_type`, `visibility_scope`, `tenant_id`.
- Live operational values (stock/price/order totals) must continue to use SQL/MCP tools.
