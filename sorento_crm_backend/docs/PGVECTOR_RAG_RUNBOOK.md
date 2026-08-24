# PGVector RAG Runbook

## Scope
- Event-driven embedding pipeline for business entities and Tool-RAG capabilities.
- Includes `mcp_tool` capability documents (implemented MCP tools + planned tools).
- Queue transport uses Redis RQ (`embeddings` queue).
- Vector storage uses PostgreSQL pgvector (`vector(1536)` with OpenAI `text-embedding-3-small`).

## Required environment variables
- `OPENAI_API_KEY`
- `EMBEDDING_MODEL_NAME` (default: `text-embedding-3-small`)
- `EMBEDDING_MODEL_VERSION` (default: `v1`)
- `EMBEDDING_QUEUE_NAME` (default: `embeddings`)
- `EMBEDDING_MAX_RETRIES` (default: `5`)
- `EMBEDDING_RETRY_BACKOFF_SECONDS` (default: `60`)
- `REDIS_URL` - must be the **same** Redis instance for every process that enqueues or consumes RQ jobs (API, `seed_embeddings`, scheduled task). If you enqueue on your laptop (`localhost:6379`) but the server uses a different `REDIS_URL`, the server queue will look empty.
- `EMBEDDING_QUEUE_DB_FALLBACK_ENABLED` (default: `true`) - when `false`, the scheduler only drains Redis (`embeddings` queue), no Postgres fallback; use this when you rely purely on RQ and correct `REDIS_URL`.

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
    - `source=all|product|promotion|promotion_product|inbound_shipment|inbound_shipment_line|spo_allocation|picking_header|picking_line|product_attachment|promotion_attachment|attachment|form|schema_doc|order|order_status|order_line|mcp_tool`
    - `batch_size` (default `500`)
    - `max_rows` (optional cap)
    - `dry_run=true|false`
- CLI script:
  - `python -m app.scripts.seed_embeddings --source all --batch-size 300`
  - `python -m app.scripts.seed_embeddings --source product --max-rows 1000 --dry-run`
  - `python -m app.scripts.seed_mcp_tool_capabilities` (tool capability seed only)

## n8n retrieval endpoint
- Endpoint: `POST /api/v1/external/rag/search`
- Uses semantic search over current vectors only (`is_current=true`).
- Filters supported: `source_type`, `visibility_scope`, `tenant_id`.
- Live operational values (stock/price/order totals) must continue to use SQL/MCP tools.

## Tool-RAG retrieval endpoint
- Endpoint: `POST /api/v1/external/rag/tool-search`
- Input:
  - `query` (required)
  - `top_k` (returns final 3-5 deduped tools)
  - `include_planned` (default `true`)
  - optional `category`, `implementation_status`
- Output:
  - `tool_name`, `score`, `why_selected`, `status`, `required_params`, `missing_params`
- Intended usage:
  - Main agent calls this first to shortlist tools.
  - Orchestrator then executes MCP calls with required params.

## Tool-RAG benchmark
- Run:
  - `python -m app.scripts.benchmark_tool_rag --top-k 5`
- Target acceptance:
  - Top-3 hit >= 90%
  - Top-5 hit >= 95%
