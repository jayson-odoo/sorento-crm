# Functional Specification: Event-Driven Embedding Pipeline for pgvector

## Overview

This functional specification defines an event-driven architecture that keeps pgvector embeddings synchronized with business data changes in the Sorento platform. The target design uses the third integration pattern: the core system remains the source of truth for transactional data, emits change events when relevant records are created or updated, and a dedicated worker service consumes those events to generate embeddings and update pgvector-backed retrieval tables.[cite:51][cite:55]

The purpose of this enhancement is to support Retrieval-Augmented Generation (RAG) and semantic search without coupling embedding generation to synchronous business transactions. This approach avoids turning the main application into an embedding pipeline while still keeping vector data fresh enough for production support workflows.[cite:51][cite:87]

## Objectives

The enhanced system should meet the following objectives:

- Keep embeddings up to date automatically when relevant source data changes.[cite:51][cite:91]
- Prevent unnecessary re-embedding when text content has not materially changed.[cite:51]
- Decouple embedding generation from user-facing write operations so normal product, promotion, stock, and support flows remain responsive.[cite:51][cite:91]
- Allow n8n and other agents to query pgvector for semantic retrieval while continuing to use SQL tools for live structured facts.[cite:30][cite:65]
- Support future embedding model upgrades and versioning without destructive rewrites.[cite:51][cite:97]
- Allow horizontal scaling of workers and safe retry handling for failures.[cite:51]

## Scope

### In scope

- Detecting source-data changes for RAG-relevant entities such as products, promotions, attachments, forms, and knowledge-oriented business documents.[cite:51][cite:91]
- Publishing domain events when source records are inserted, updated, soft-deleted, activated, deactivated, or reclassified.[cite:51][cite:93]
- Processing events in an asynchronous worker service that creates text chunks, calls an embedding model, and writes embeddings into PostgreSQL with pgvector.[cite:51][cite:55][cite:94]
- Maintaining metadata, source hashes, model identifiers, and current/stale flags to support reindexing and traceability.[cite:51]
- Exposing a retrieval-ready embedding store for n8n PGVector usage.[cite:30]

### Out of scope

- Replacing the SQL sub-agent for exact structured queries against live transactional data.[cite:65]
- Building a full user-facing vector search UI.
- Re-architecting all transactional microservices.
- Performing semantic retrieval directly from source OLTP tables without an embedding layer.

## Target Architecture

The target architecture should follow this flow:

1. The Sorento application writes to normal transactional tables.
2. A change event is emitted whenever embedding-relevant text changes.
3. The event is stored in an event stream or durable queue.
4. An embedding worker consumes the event asynchronously.
5. The worker resolves the source record, builds canonical text, chunks it, and computes a content hash.[cite:51][cite:55]
6. If the hash differs from the latest embedded version, the worker generates embeddings using the configured embedding model and writes them into pgvector tables.[cite:51][cite:94]
7. Older embeddings for the same logical document/model space are marked non-current rather than immediately destroyed, enabling auditability and safer rollbacks.[cite:51]
8. n8n agents query the pgvector store for semantic context and still use SQL tooling for precise live values.[cite:30][cite:65]

## Recommended Integration Pattern

The recommended implementation pattern is **application event emission plus asynchronous worker consumption**.

Two event-source options are acceptable:

| Option | Description | Recommended use |
|---|---|---|
| Application-published domain events | The application emits events after successful writes to supported entities. | Preferred when the application already has service-layer hooks, queues, or an outbox pattern. |
| Database-triggered queueing | PostgreSQL triggers insert change records into an embedding queue table after insert/update/delete. | Good fallback when application changes are harder than database changes.[cite:51] |

For Sorento, the preferred baseline is an **outbox/event bus pattern** because it gives cleaner service boundaries, clearer payload versioning, and easier worker evolution than hardwiring all behavior into database triggers alone.[cite:51][cite:93]

## Functional Components

### Source entities

The first release should support these embedding source types:

- Product master content: product code, product name, description, brand, category, and other descriptive non-sensitive fields.
- Promotion content: promo code, promotion name, description, active date notes, and customer/dealer visibility notes.
- Attachment metadata: original filename, description, file path semantics, linked entity type, and document classification.
- Forms and business documents: form code, form name, purpose, language, and other descriptive text.
- Internal business glossary or schema documentation used by AI agents for retrieval support.

Stock quantities, order totals, and other rapidly changing numeric facts should not be embedded as the authoritative answer source because they are better answered by live SQL queries.[cite:65][cite:87]

### Event producer

The producer is responsible for detecting relevant changes and emitting an event only when embedding-relevant content may have changed.[cite:51]

#### Producer responsibilities

- Detect create, update, soft delete, restore, and deactivate events.
- Build an event payload with enough metadata for downstream processing.
- Guarantee at-least-once event delivery.
- Publish events only after the source-of-truth transaction is committed successfully.
- Include entity version or updated timestamp to aid idempotency.

#### Suggested event types

- `product.created`
- `product.updated`
- `product.deactivated`
- `promotion.created`
- `promotion.updated`
- `promotion.deactivated`
- `attachment.created`
- `attachment.updated`
- `attachment.deleted`
- `form.created`
- `form.updated`
- `knowledge_document.updated`
- `embedding.rebuild_requested`

### Event transport

The transport can be a queue or stream platform such as RabbitMQ, Kafka, SQS, Redis Streams, or a PostgreSQL-backed queue table, as long as it is durable and supports retries.[cite:51][cite:93]

#### Transport requirements

- Durable persistence.
- Retry capability.
- Dead-letter handling.
- Ordering at least per entity key when feasible.
- Consumer acknowledgement semantics.
- Visibility into pending, processing, failed, and dead-lettered events.

### Embedding worker service

The embedding worker is the main asynchronous processing component.

#### Worker responsibilities

- Consume source change events.
- Load the latest source record using a trusted read model.
- Construct canonical embedding text.
- Normalize text, filter noise, and chunk content according to chunking policy.[cite:55]
- Compute a deterministic source hash and skip re-embedding if unchanged.[cite:51]
- Generate embeddings using the configured provider or model.[cite:94]
- Persist embeddings, chunk text, metadata, source hash, model name, and model version.[cite:51]
- Mark previous embeddings as stale/non-current where appropriate.[cite:51]
- Log processing outcomes and emit operational metrics.

#### Worker non-functional behavior

- Must be idempotent.
- Must support concurrent workers without double-processing the same work item.[cite:51]
- Must fail safely and retry transient errors.
- Must isolate provider/API failures from the main application.

## Functional Data Design

### Canonical document model

Every embedding source should be converted into a canonical document representation before chunking.

Recommended canonical fields:

- `source_type` - e.g. `product`, `promotion`, `attachment`, `form`, `schema_doc`
- `source_id` - source primary key or stable business key
- `source_key` - optional human-readable identifier such as product code or promo code
- `title` - short human-readable label
- `body_text` - normalized text used for embedding
- `metadata` - JSONB with searchable context
- `source_updated_at`
- `source_hash`
- `visibility_scope` - e.g. customer, dealer, internal
- `tenant_id` or `space_id` if multitenancy applies

### Suggested tables

#### 1. Embedding queue / work table

A durable queue table is recommended even when using a message broker, because it gives replay, auditing, and direct operational visibility.[cite:51]

Suggested columns:

- `id`
- `source_type`
- `source_id`
- `event_type`
- `event_version`
- `source_updated_at`
- `source_hash`
- `payload`
- `status` (`pending`, `processing`, `completed`, `failed`, `dead_letter`, `skipped`)
- `retry_count`
- `available_at`
- `last_error`
- `created_at`
- `processed_at`
- `correlation_id`

#### 2. Embedding documents table

Suggested purpose: store the latest canonical source document before chunking.

Suggested columns:

- `id`
- `source_type`
- `source_id`
- `source_key`
- `title`
- `body_text`
- `metadata` JSONB
- `visibility_scope`
- `source_hash`
- `source_updated_at`
- `is_active`
- `created_at`
- `updated_at`

#### 3. Embedding chunks / vectors table

This table stores the actual vector rows and should support versioning.[cite:51]

Suggested columns:

- `id`
- `document_id`
- `source_type`
- `source_id`
- `chunk_index`
- `chunk_text`
- `chunk_hash`
- `embedding` `vector(<dimension>)`
- `model_name`
- `model_version`
- `embedding_provider`
- `source_hash`
- `metadata` JSONB
- `is_current`
- `embedded_at`
- `superseded_at`

Recommended uniqueness pattern:

- unique on `(source_type, source_id, model_name, model_version, chunk_index, is_current=true)` or an equivalent implementation.[cite:51]

## Change Detection Rules

The system should only create a new embedding job when embedding-relevant text or visibility metadata changes.

### Re-embed triggers

A new embedding job should be queued when:

- A new source record is created and is active/visible.
- A descriptive field changes, such as product name, description, category label, promo description, attachment description, or form purpose.
- Visibility or access metadata changes in a way that affects who should retrieve the document.
- A source record is reactivated.
- A document is manually flagged for rebuild.
- The embedding model or chunking policy changes and a backfill is initiated.[cite:51][cite:97]

### No-op conditions

A new embedding should not be generated when:

- Only non-semantic operational fields change, such as sync timestamps, updated_by, or unrelated bookkeeping fields.
- The recomputed source hash is unchanged from the current embedded version.[cite:51]
- The source record is inactive and policy says inactive records should be removed from current retrieval.

## Chunking Rules

Embedding should occur on normalized chunks rather than giant free-text blobs, because chunking is a standard best practice for improving retrieval quality.[cite:55]

### Functional rules

- Build source-type-specific text templates.
- Remove duplicated boilerplate where possible.
- Chunk by semantic sections first, with token-limit fallback.
- Preserve important identifiers such as product code, promo code, form code, and document type in each chunk when useful for retrieval.
- Store chunk order and chunk text for traceability.[cite:51][cite:55]

### Example canonical text for a product

```text
Source Type: Product
Product Code: SRTWT8212
Product Name: Sorento Water Tank 8212
Category: Water Storage
Brand: Sorento
Description: ...
Visibility: Customer
Related Notes: ...
```

This improves recall for mixed natural-language and code-based searches because business identifiers remain present in the semantic payload.[cite:55]

## Versioning and Staleness Management

Embedding versioning should be a first-class capability, not an afterthought.[cite:51]

### Functional rules

- Every embedding row must record `model_name`, `model_version`, and `source_hash`.[cite:51]
- When a new version is written successfully, previous current rows for the same document/model space should be marked `is_current = false` instead of being immediately deleted.[cite:51]
- Retrieval queries should search only current rows by default.[cite:51]
- A controlled purge job may archive or delete stale rows after the retention period.
- Manual rebuilds should be possible per source type, source id, or model version.

This enables safe migration when switching embedding providers, dimensions, or chunking strategies.[cite:51][cite:97]

## Deletion and Deactivation Rules

The system must define clear behavior for records that are removed or no longer visible.

### Soft delete / deactivate

- Mark related embedding rows as non-current, or mark the document inactive so retrieval excludes them.
- Preserve historical rows for audit if required.

### Hard delete

- If the source record is physically deleted, remove or deactivate related current embeddings according to retention policy.
- Cascade delete is acceptable only if historical recovery is not required.[cite:51]

### Access-level changes

- If access-level or visibility rules change, the worker must rebuild the metadata and current rows so retrieval remains policy-compliant.

## Retrieval Contract for n8n and AI Agents

The retrieval layer should expose a clean contract for AI tools such as n8n PGVector Store.

### Retrieval expectations

- Search only `is_current = true` rows by default.[cite:51]
- Allow filtering by `source_type`, `visibility_scope`, tenant/workspace, and other metadata fields.
- Return `chunk_text`, source identifiers, and enough metadata to let the calling agent decide whether SQL follow-up is needed.
- Do not use pgvector retrieval as the authoritative source for live stock counts, prices, or order math.[cite:65][cite:87]

### Agent behavior implication

- RAG answers semantic questions such as what a field means, where data is likely stored, or which documents relate to a topic.[cite:65]
- SQL tools still answer exact structured questions such as totals, stock counts, and current order states.[cite:65]

## Event Payload Specification

A minimum event payload should contain:

```json
{
  "event_id": "uuid",
  "event_type": "product.updated",
  "event_version": 1,
  "occurred_at": "2026-04-17T12:00:00Z",
  "source_type": "product",
  "source_id": "123",
  "source_key": "SRTWT8212",
  "tenant_id": "default",
  "source_updated_at": "2026-04-17T11:59:59Z",
  "source_hash": "optional-precomputed-hash",
  "changed_fields": ["product_name", "description"],
  "correlation_id": "uuid",
  "triggered_by": "system|user|sync-job"
}
```

### Event payload rules

- `event_id` must be globally unique.
- `event_version` must support future schema evolution.[cite:93]
- `changed_fields` should be included when available to support selective processing.
- `correlation_id` should propagate through logs, retries, and audit trails.

## Processing Flow

### Happy path

1. Business data is committed successfully.
2. Event producer publishes a domain event.
3. Queue stores the event durably.
4. Worker claims the event.
5. Worker loads the latest source state.
6. Worker builds canonical text and computes the source hash.
7. If unchanged, worker marks the event `skipped`.
8. If changed, worker chunks text, generates embeddings, writes new current rows, and supersedes old current rows.[cite:51]
9. Worker marks the event `completed`.

### Failure path

1. Worker fails to generate embeddings due to provider/network issue.
2. Event remains retryable with exponential backoff.
3. After max retries, event is moved to dead-letter state.
4. Operations team receives an alert.
5. The event can be replayed after remediation.

## Idempotency Requirements

Idempotency is mandatory for event-driven embedding pipelines.[cite:51]

### Functional requirements

- Reprocessing the same event must not create duplicate current embeddings.
- Workers must check the latest `source_hash` before generating a new embedding.[cite:51]
- Duplicate events for the same source state should be safely skipped.
- Writes should be transactional where possible: either the new current set is fully persisted and activated, or nothing changes.

## Concurrency and Scaling

The system should support multiple workers processing different queue items concurrently.[cite:51]

### Requirements

- A work item must be claimed by only one worker at a time.[cite:51]
- Stuck processing jobs should be recoverable after timeout.
- Horizontal scaling should be possible by adding more worker instances.[cite:51]
- Throughput controls should exist to protect embedding provider quotas and database load.

## Security and Governance

### Data handling

- Only embed fields approved for semantic retrieval.
- Exclude secrets, credentials, internal-only paths not needed for retrieval, and regulated personal data unless explicitly approved.
- Respect access-level semantics in metadata so retrieval can filter correctly.

### Provider controls

- Store embedding API keys securely.
- Log provider usage and failure rates.
- Support provider/model substitution without rewriting business tables.[cite:51][cite:94]

## Monitoring and Operations

The enhancement should include operational visibility from day one.

### Metrics

- queue depth
- event processing throughput
- average processing latency
- embedding generation latency
- success rate
- retry rate
- dead-letter count
- skipped count due to unchanged hash
- current embedding count by source type/model

### Logs

Each processing run should log:

- event_id
- source_type
- source_id
- source_hash
- old hash / new hash if available
- model_name
- model_version
- chunk count
- duration
- retry_count
- final status

### Alerts

Alerts should be raised for:

- dead-letter growth
- repeated provider failures
- queue backlog beyond threshold
- stale embedding age beyond SLA

## Non-Functional Requirements

| Area | Requirement |
|---|---|
| Availability | Main transactional flows must not depend on synchronous embedding completion. |
| Performance | Event publication should add minimal write-path overhead. |
| Freshness | Embeddings should be updated within a defined SLA after source change, e.g. under 5 minutes for normal priority. |
| Scalability | Worker tier must scale independently of application writes.[cite:51] |
| Reliability | At-least-once processing with idempotent writes. |
| Auditability | Every embedding version should be traceable to source hash, source record, model, and event.[cite:51] |
| Safety | Retrieval must not bypass access controls or expose sensitive content. |

## Suggested Rollout Phases

### Phase 1: Foundation

- Enable pgvector where required.[cite:94]
- Create queue, document, and embedding tables.
- Implement one event producer path for a small source type, such as products or internal schema docs.
- Implement one worker with hash-based skip logic.

### Phase 2: Retrieval readiness

- Expose current embeddings to n8n PGVector retrieval.[cite:30]
- Add metadata filters and visibility filtering.
- Validate semantic retrieval quality.

### Phase 3: Broader coverage

- Add promotions, attachments, forms, and glossary/business docs.
- Add dead-letter handling, replay tooling, and dashboards.
- Add model version migration support.[cite:51]

### Phase 4: Optimization

- Tune chunking strategies.[cite:55]
- Add ANN indexes such as HNSW/IVFFlat as scale requires.[cite:95]
- Introduce scheduled rebuilds for changed policies or upgraded prompts/models.

## Acceptance Criteria

The enhancement should be accepted when all of the following are true:

1. Creating or updating a supported source record produces a durable change event.
2. The worker consumes the event and creates or updates pgvector embeddings without blocking the source transaction.[cite:51]
3. Re-saving a record without semantic text changes does not trigger a new embedding write because hash-based skip logic prevents redundant work.[cite:51]
4. Retrieval queries return only current embeddings by default.[cite:51]
5. Old embeddings remain traceable by source hash/model version until retention cleanup occurs.[cite:51]
6. Failed embedding jobs retry automatically and dead-letter after the configured threshold.
7. n8n can retrieve relevant context from pgvector for supported entities.[cite:30]
8. Live numeric questions still rely on SQL tooling rather than embeddings.[cite:65]

## Implementation Guidance for Cursor Agent

The Cursor agent should produce the enhancement using these workstreams:

### Workstream A: Event emission

- Identify embedding-relevant source entities.
- Add application-layer event publication after successful commits.
- Introduce event schema versioning.
- Add outbox persistence if direct broker publication is not transactionally safe.

### Workstream B: Storage design

- Create queue, document, and embedding tables.
- Add required indexes for queue polling, current retrieval, and source/hash lookups.[cite:51]
- Enable pgvector extension in the target PostgreSQL database if not already enabled.[cite:94]

### Workstream C: Embedding worker

- Implement consumer loop.
- Add canonical text builders per source type.
- Add chunker and source-hash logic.
- Integrate embedding provider.
- Implement transactional write/supersede behavior.
- Add retry and dead-letter behavior.

### Workstream D: Retrieval integration

- Define metadata contract expected by n8n.
- Ensure vector rows can be filtered by source type and visibility.
- Document how agents should use RAG plus SQL together.[cite:30][cite:65]

### Workstream E: Observability

- Add structured logging.
- Add metrics and alerts.
- Add replay tooling or admin commands for failed events.

## Open Design Decisions

The implementation team should explicitly decide the following before development starts:

- Which queue technology will be used.
- Which source types are in scope for v1.
- Which fields are approved for embedding per source type.
- Which embedding model/provider will be used and what vector dimension it requires.[cite:94][cite:97]
- Whether old embedding versions are archived indefinitely or purged after retention.
- What freshness SLA applies to each source type.
- Whether event publishing will use outbox-only, broker-only, or trigger-backed fallback.

## Recommended Default Decisions

For a pragmatic v1, the following defaults are recommended:

- Use an outbox/event table plus a worker consumer.
- Start with `product`, `promotion`, `attachment`, and internal `schema_doc` sources.
- Use source-hash comparison to avoid duplicate embeddings.[cite:51]
- Store chunk-level embeddings with `is_current` versioning.[cite:51]
- Keep RAG retrieval for semantic context and retain SQL tools for exact operational answers.[cite:65]
- Set a target freshness SLA of under 5 minutes for normal events and support manual rebuild events for urgent cases.

## Appendix: Example Retrieval Metadata

```json
{
  "source_type": "product",
  "source_id": 123,
  "source_key": "SRTWT8212",
  "title": "Sorento Water Tank 8212",
  "visibility_scope": "customer",
  "category": "Water Storage",
  "brand": "Sorento",
  "is_current": true,
  "model_name": "text-embedding-3-small",
  "model_version": "v1"
}
```

## Appendix: Example Worker Decision Logic

1. Receive `product.updated` for `source_id=123`.
2. Load current product read model.
3. Build canonical text.
4. Compute source hash.
5. Compare against latest current embedding set.
6. If unchanged, mark event skipped.
7. If changed, chunk text and generate embeddings.
8. Insert new chunk rows with `is_current=true`.
9. Mark prior current rows `is_current=false` in the same logical space.
10. Commit and mark queue item completed.[cite:51]
