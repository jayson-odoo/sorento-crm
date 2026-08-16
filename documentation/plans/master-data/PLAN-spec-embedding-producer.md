# PLAN - feed the product_spec embedding leg (close the dead producer)

**Status:** In progress - overnight build, PR only, captain merges
**Branch:** `feat/spec-embedding-producer` (off main `d2b80b353`)
**Closes:** issue #139 (`[spec-embedding] product_spec embedding queue has a consumer but no producer`)
**Related:** `PLAN-spec-authoring-verification.md` (the `apply_spec_values` choke point this depends on, already merged), `PLAN-spec-raw-text-search.md` (the lexical leg, merged in PR #142)

## Journey

A product manager opens a product, corrects its thickness from 1.0mm to 1.2mm, and saves.

1. The save writes the authored value through `apply_spec_values`, which re-derives the
   code and rewrites every company copy's spec row and its rendered sentence.
2. Because the sentence changed, the product's semantic index entry is now stale. The
   system queues exactly one re-embed per affected product row, and it does so without
   the person waiting for it and without any chance of failing their save.
3. Within the worker's next pass, semantic spec search reflects the correction. The
   manager searching "1.2mm double bowl sink" in the assistant finds the product they
   just fixed.

Today step 2 never happens for ANY writer: `enqueue_spec_embedding` exists and has no
caller, so `embedding_queue` has never held a single `product_spec` row and
`embedding_documents` has never held a single `product_spec` document. The semantic leg
of spec search has been dead since it was built.

## Gap analysis

| # | gap | evidence |
|---|-----|----------|
| G1 | **No producer at all.** `enqueue_spec_embedding` (product_spec_change_listener.py:67) has exactly one occurrence in the monorepo: its own definition. | `grep -rn enqueue_spec_embedding app/ scripts/ tests/` |
| G2 | **Two writers, not one.** Spec rows are written by `derive_for_code` (machine, via `write_spec_row`) and by `apply_spec_values` (authored, which then calls `derive_for_code`), plus the RQ task `derive_product_specs` and the `derive_all` batch. A per-call-site fix has to be repeated four times and will be missed by the fifth writer. | product_spec_derivation.py:1198, product_spec_write.py:331 |
| G3 | **`queue_event` commits.** `EmbeddingEventService.queue_event` calls `self.db.commit()` and enqueues an RQ job inline. Calling it from inside a derivation transaction would commit that caller's half-finished work. | embedding_service.py:100-112 |
| G4 | ~~**Batch volume.**~~ WITHDRAWN after building the fix for it. The premise was the derivation twin's history, not a measurement of THIS path: every writer that produces a catalogue-sized batch here already runs on the worker, so guarding it only moved work between worker jobs. See D4. | product_spec_change_listener.py:38-42 |
| G5 | **Noise.** A spec row is rewritten on every derivation pass whose fingerprint changed, even when the rendered sentence is byte-identical (a provenance-only or status-only change). Embedding an unchanged sentence burns worker time and model calls for no index change. | write_spec_row assigns rendered_text unconditionally |

## Design decisions

- **D1 - one producer, at the ORM boundary, not at the call sites.** Register
  `after_insert` / `after_update` listeners on `ProductSpecifications` that collect
  product ids into `session.info`, and drain them in `after_commit`. This covers every
  writer that exists (authored, derived, RQ task, batch, scripts) and every writer added
  later, which is what G2 asks for. It mirrors the module's own existing pattern
  (`register_product_spec_listeners` collects Product codes the same way) rather than
  inventing a new one.
- **D2 - only a changed SENTENCE queues.** The collect step reads the attribute history
  of `rendered_text` and skips the row when it did not change. That is the only field
  the worker embeds for this source type (`embedding_worker.py` builds the body from
  `spec.rendered_text`), so an unchanged sentence cannot change the document. Closes G5.
- **D3 - post-commit, fresh session, best-effort, never raises.** The drain runs after
  the caller's commit, opens its own session, and swallows every exception with a
  warning. Reasons, in order: `queue_event` commits (G3), a post-commit side effect that
  raises 500s an operation that already succeeded, and the retry would take the
  idempotent path without backfilling the missed work. This is the standing post-commit
  rule in this repo, and this module already documents it for the re-derive twin.
- **D4 (REVISED - the split was built, then removed) - the drain is always inline.**
  The first cut mirrored derivation's `INLINE_REDERIVE_LIMIT` with a limit of its own,
  an RQ task and a fallback path. Re-examined under the captain's standing rule (build
  the simplest thing; no machinery without proof the direct path is inadequate) it does
  not survive: the reason the derivation twin needs a split is that derivation runs in
  the REQUEST path, where a catalogue-sized batch holds a user's save open. Every writer
  big enough to produce one of those HERE is already on the worker (the import's derive
  task, `derive_all`, the backfill script), so the hand-off only moved work from one
  worker job to another. G4's premise was the twin's history, not a measurement of this
  path. Removed: about 100 lines, one RQ task, and eight tests. If a request-path writer
  that touches dozens of spec rows ever appears, the split comes back with that writer
  named as its proof.
- **D5 - reuse `enqueue_spec_embedding` as-is.** It already guards the empty sentence
  (an empty embedding sits near everything and would surface the product for every
  query) and is already best-effort. The bug is that nothing calls it, not that it is
  wrong. It takes a `product_id`, which is exactly what the spec row is keyed on.
- **D6 - no backfill in this PR.** The catalogue's 11,415 existing spec rows still need
  a first embed. That is a one-shot operational run (`scripts/`), not a code path, and
  it belongs in its own change with the captain choosing when it runs against prod.
  This PR ships the producer plus the script; running it is the captain's call.

## Slices (TDD, in order)

| # | slice | tests that gate it |
|---|-------|--------------------|
| S1 | Collect + drain listeners on `ProductSpecifications`, wired into the existing `register_product_spec_listeners` registration | a derived write queues exactly one `product_spec` event per product row; a second identical derivation (unchanged sentence) queues nothing; an authored write through `apply_spec_values` queues one; a rollback queues nothing |
| S2 | REMOVED, see D4. The split was built and then taken out; the drain is always inline | an empty batch opens no session (the drain runs on every commit in the process) |
| S3 | Failure containment | `queue_event` raising does not fail the caller's commit and does not lose the other ids; an empty `rendered_text` row queues nothing |
| S4 | Backfill script (`scripts/backfill_spec_embeddings.py`), idempotent, batched, resumable, `--dry-run` first | script test over a seeded catalogue: dry-run writes nothing, real run queues one event per non-empty spec row, re-run is a no-op for rows already current |

## Acceptance criteria

1. A spec write from ANY writer (authored, derived, RQ task, batch) results in exactly
   one `product_spec` queue event per affected product row, after the writer's commit.
2. A write that does not change `rendered_text` queues nothing.
3. A failure anywhere in the enqueue path never fails, never rolls back, and never
   500s the write that triggered it.
4. There is one drain path, not two. A batch of any size is enqueued in the same way.
5. `pytest` green on an exclusive Postgres database, including the existing derivation
   and authored-write suites (no behaviour change to either).
6. Backfill script present, idempotent, dry-run by default, NOT run against prod in
   this PR.
