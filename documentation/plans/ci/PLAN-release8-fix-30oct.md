# PLAN: RELEASE8-FIX (release #8 full suite red: 4 DO backfill embedding tests)

Status: PR open, waiting CI (small fix track: tests only, no migration, no auth change)

## Symptom

Release #8 run 40936735639 on main 37f0466152, shard 6 (job 123669203909), 4 failures, all
`assert 0 >= N` on the embedding queue rows a plain DO push writes:

- `tests/test_do_history_backfill_flag.py::test_plain_push_still_audits_and_enqueues_embeddings`
- `tests/test_do_history_backfill_flag.py::test_suppression_ends_with_the_backfill_request`
- `tests/test_do_history_backfill_flag.py::test_backfill_false_is_a_plain_push`
- `tests/test_do_backfill_quiet_hooks.py::test_plain_batch_still_queues_embeddings`

Green in release #7 (232b392f25). PR CI runs only changed test files, so #1967 never ran them.

## Cause

#1967 LOOKUP-EMBED-CENTRAL (e86b459281) added the keep-set filter in `enqueue_pending`
(`app/services/embedding_change_listener.py:156-158`): every queue row whose `source_type` is not in
`RECORD_KEEP_SET` (`app/services/embedding_settings.py:38`: attachment, promotion, certificate, form,
product_spec, project) is dropped. `order` and `order_line` are outside it, so a DO push queues nothing.
Proof: with the filter disabled locally the 2 files go 17/17 green; with it, the same 4 fail.

## Decision: intended behaviour change, fix the tests

The owner chose the keep set on 29 Oct (`documentation/plans/chatbot/PLAN-lookup-embed-central-29oct.md:140`,
S1 (a); order 74,902 docs and order_line 40,289 marked DROP at `:382-383`; the slice 2 contract `:484` names
`order` among the sources whose producers stop). DO numbers are answered by exact SQL lookup, not vectors.
Prod needs nothing: DO and DO line embeddings stop by design; existing 3-small rows stay (owner N4 (c)).

## Change (tests only)

- One fixture `orders_embedded` puts `order` / `order_line` back into `RECORD_KEEP_SET` for the tests
  that measure the backfill flag's embedding suppression (`app/api/v1/external/ingest.py:868`), so AC-DH40/41/46
  can still fail if the suppression breaks.
- One new test pins today's behaviour with the real keep set: a plain DO push queues no embedding event
  for the DO or its lines.
- Module docstrings say why.

## Also red in release #8 (same run, not in the brief)

- Shard 5 (job 123669204078): `tests/test_company_scope.py::test_every_company_id_table_is_registered`
  expected 172 owned tables, found 173. `item_classes` (`app/models/product.py:189`, #1972 ITEM-CLASS) is
  CompanyScopedMixin by design, exactly as `item_types`. Count -> 173 with its line in the running tally.
- Vitest 2 (job 123669203545): `components/ui/data-grid.nested.inventory.test.ts` census pin
  `ProductsList.tsx:1115` -> `:1185` (BarcodeImportDialog; #1972 added 70 lines above it).

## Proof

- Red: the 4 tests fail on main 37f0466152 (CI run 40936735639, reproduced locally).
- Kill: dropping the suppression in `_quiet_backfill` fails the backfill tests; dropping the keep-set
  filter fails the new pin.
- Local run: the 2 files + `tests/test_lookup_embed_central_slice2.py` on throwaway `sorento_r8f_throwaway`.
