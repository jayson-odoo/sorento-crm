# UAC: stop embedding line-level source types (EMBED-DROP-LINE-TYPES)

Plan: `PLAN-embed-drop-line-types-27oct.md`. Tests: `sorento_crm_backend/tests/test_embedding_dropped_line_types.py`.

| ID | Criterion | Test |
| --- | --- | --- |
| AC-1 | `order_line`, `picking_line` and `inbound_shipment_line` are the dropped types, and none of them has an embedded-field list. | `test_the_three_line_types_are_dropped` |
| AC-2 | Writing a line row queues nothing. | `test_writing_an_order_line_queues_nothing` |
| AC-3 | Backfill `all` does not cover them, and the backfill API refuses them. | `test_backfill_all_no_longer_covers_the_line_types`, `test_backfill_api_refuses_a_line_type` |
| AC-4 | The worker skips a queued row of a dropped type, never rebuilds its text, and deactivates its document. | `test_worker_skips_a_queued_line_row_and_deactivates_its_document` |
| AC-5 | The retire step deactivates every document of the dropped types and skips their pending rows. It leaves other types and terminal rows alone, is resumable after a capped run, and is then a no-op. | `test_retire_*` |
| AC-6 | The hourly prune task runs the retire step until a run reports it done, then stops calling it. | `test_prune_task_runs_the_retire_step_until_it_is_done` |
