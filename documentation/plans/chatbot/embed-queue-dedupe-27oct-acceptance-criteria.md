# UAC: embedding_queue dedupe + cheap poll (EMBED-QUEUE-DEDUPE)

Plan: `PLAN-embed-queue-dedupe-27oct.md`. Backend only; each criterion names its test in
`sorento_crm_backend/tests/test_embedding_queue_dedupe.py`.

| ID | Criterion | Test |
| --- | --- | --- |
| AC-1 | A tracked row's insert queues exactly one pending row. | `test_insert_queues_one_row` |
| AC-2 | An update that changes no embedded column, or sets one to its current value, queues nothing. | `test_update_of_a_non_embedded_field_queues_nothing`, `test_setting_an_embedded_field_to_its_current_value_queues_nothing` |
| AC-3 | An update of an embedded column queues one row. Every listed field is a real column. | `test_update_of_an_embedded_field_queues_one_row`, `test_every_embedded_field_is_a_column_of_its_model` |
| AC-4 | Repeated changes keep one pending row per source. A claimed (`processing`) row or a failed (`retry_count > 0`) row does not count as pending. | `test_repeated_changes_keep_one_pending_row`, `test_a_processing_row_does_not_block_a_new_pending_row`, `test_a_failed_row_does_not_absorb_a_new_change` |
| AC-5 | Bulk and service enqueues skip pending sources. `queue_event` reuses the pending row, takes the newest payload, and gives it an RQ job if it has none. | `test_bulk_enqueue_skips_sources_already_pending`, `test_queue_event_*` |
| AC-6 | No change is lost: while an enqueue that relied on a pending row is still open, the worker cannot claim that row (it reports `busy`). An enqueue that runs after an uncommitted claim inserts its own row. | `test_worker_cannot_claim_a_row_an_open_enqueue_relied_on`, `test_an_enqueue_after_an_uncommitted_claim_queues_its_own_row` |
| AC-7 | A claim marks the source's other pending rows `skipped` ("dedup: superseded"), except for mcp_tool. A failed run is marked `skipped` instead of `pending` when a newer row is waiting. | `test_claim_supersedes_*`, `test_claiming_an_older_mcp_tool_row_*`, `test_failed_run_*` |
| AC-7b | The worker's claim, its supersede step and the backlog dedupe never wait on a row that live work holds: they skip it, and the row stays pending. A row retrying a failure never retires a fresh row. | `test_claim_and_backlog_dedupe_never_wait_on_a_held_row`, `test_claiming_a_retrying_row_keeps_the_fresh_rows`, `test_backlog_dedupe_keeps_a_fresh_row_over_a_newer_retrying_one` |
| AC-8 | The Order Tracking import queues only orders that are new or had an embedded column change. | `test_tracking_import_queues_only_orders_whose_embedded_fields_changed` |
| AC-9 | The poll takes mcp_tool first, then the oldest rows, up to `EMBEDDING_QUEUE_BATCH_SIZE` (default 10), from `ix_embedding_queue_pending_poll_cov`, with no sort and no `count(*)`. | `test_poll_*`, `test_processor_uses_the_configured_batch_size`, `test_batch_size_defaults_to_ten` |
| AC-10 | Prune deletes only `completed` and `skipped` rows older than 14 days, in batches, and stops at its per-run cap. | `test_prune_*` |
| AC-11 | Backlog dedupe keeps the newest pending row per source. A second run is a no-op, and a capped run resumes. | `test_backlog_dedupe_*` |
| AC-12 | An index build never stalls a release: it runs CONCURRENTLY with bounded waits. A failure warns, leaves no INVALID index, and does not raise. A VALID index of the same name is reused and an INVALID one is rebuilt. The prune task retries once a day. | `test_ensure_*`, `test_a_build_*`, `test_a_failed_build_*`, `test_an_invalid_index_*`, `test_prune_task_retries_*` |
