# UAC - AC-REMOVED-LINES: a line removed in AutoCount releases its links

Status: FINAL, 26 Oct 2026, from the owner's rulings on `ac-removed-lines-behaviour-card.md`
(Q1 a, Q2 just remove the links, Q3 no suggestion, Q4 a, Q5 no UI change, minimum change
management). Plan: `PLAN-ac-removed-lines-26oct.md`.

Superseded: `test_oi_cancelled_line_used_confirm.py` pinned that a raised row on an SO line a
push removes is flagged To confirm (ruling C1, 20 Sep); Q1 (a) now retires it (AC-RL-20). Actioned
rows keep the C1 flag.

## Journey

Purchasing deletes a PO line in AutoCount. The next AutoCount push reaches the CRM. The line
still shows Cancelled, exactly as today, but nothing is placed on it any more: the sales order
rows that were placed on it simply lose that link and show whatever state the normal rules give
them. An SPO line AutoCount drops behaves the same. A sales order line AutoCount deletes has its
order inquiry rows retired exactly as CS's Transfer to Cancel SO retires them. Lines that
AutoCount CANCELS (Cancel PO / Cancel SO documents, a cancelled header) keep their links, as
today. A one-off script applies the same release to lines removed before this shipped: a dry run
lists them, the owner approves, then it applies.

## Terms

- Removed PO/SO line: a line with an AutoCount DtlKey (`source_ref`) that a push of its document
  no longer carries (not a dropped-unresolved line), on a header the push does not cancel. In
  `DocumentIngestService._sync_lines` this is a `by_ref` leftover at the sweep
  (`document_ingest_service.py:1639`).
- Removed SPO line: a `retired_refs` row of the shipping-order sweep
  (`shipping_order_ingest_service.py:557-579`) whose `retired_at` this push sets.

## Criteria

PO line removed (Q2)
- AC-RL-01 When a push removes a PO line that OI links point at, every `order_inquiry_links` row
  with that `po_line_id` is deleted, whatever the row state (draft, placed, actioned).
- AC-RL-02 The affected rows' state is recomputed by the normal rules (placed -> raised when no
  link remains, partly linked when another link remains; actioned stays actioned), and the
  inquiry header state is refreshed.
- AC-RL-03 Nothing else changes on the row: `ack_state` unchanged (no To confirm flip), `note`
  unchanged (no "Unlinked from" text), no notification or email is queued.
- AC-RL-04 EVERY `scm.order_link_claim` row on that `po_line_id`, open AND resolved, whatever its
  source, is DELETED (crew audit after the dev apply, 26 Oct: resolved AutoCount claims kept
  reserving SO demand on removed lines, `scm/purchase_order_service.py:591-623`
  `reservations_by_target`, so Placed still read 117 / 43 / 31 / 33 / 47 / 138; owner Q2: the
  line is gone in AutoCount, the source of truth). Never stamped `resolved_at` (a resolved claim
  reads "matched to PO X" on the SO list, `scm/sales_order_service.py:1160`).
- AC-RL-05 The PO line itself is written exactly as today: `line_status = cancelled`, quantities,
  `from_so_line_ref` and received qty untouched; no new column.
- AC-RL-06 PO detail Placed for that line reads 0 after the push, counting OI links AND claim
  dedications (`scm/purchase_order_service.py` `_allocations_for` + `reservations_by_target`).
- AC-RL-07 A push of a document that is NOT cancelled but carries ZERO lines releases nothing
  and retires nothing (PO, SO and SPO): a header-only or failed-detail push must not wipe a
  document's links (security review). The lines are swept as today.

SPO line removed (Q2)
- AC-RL-10 When a push retires an SPO line (its `retired_at` newly set), every OI link with that
  `spo_allocation_id` is deleted and every claim on it (open and resolved) deleted (AC-RL-04),
  with AC-RL-02 and AC-RL-03.

SO line removed (Q1 a)
- AC-RL-20 When a push removes an SO line, its live raised / partly linked / placed rows are
  retired the way Transfer to Cancel SO retires them (`ProjectSupplyService.cancel_lines`,
  `project_supply_service.py:1405-1443`, via `retire_rows_for_cancelled_lines`): links back,
  row `cancelled`, the same audit and purchasing handover that path produces. The retired row's
  note reads "Removed in AutoCount" (not "Transferred to Cancel SO: ..."). Actioned rows are
  only flagged, as today. The core line is NOT given `cancelled_at` / `cancelled_by_id` (those
  mean the CS board).

Unchanged (regression guards)
- AC-RL-30 A line cancelled by a Cancel PO / Cancel SO document, a line on a header the push
  cancels, and a CS-board cancelled SO line keep every link.
- AC-RL-31 An SPO document pushed as cancelled (`force_closed`) keeps its links, including a line
  that same cancelled push no longer carries (cancel, not removal).
- AC-RL-32 A ref-less (xlsx-era) line or a duplicate-ref row swept by the push keeps its links.
- AC-RL-33 A line that was already cancelled before this push and is again absent changes
  nothing (release runs only on the transition, never as a backlog sweep on a later push).
- AC-RL-34 A line the push still carries (matched by DtlKey) keeps its links whatever its status.

Reconciliation (Q4 a)
- AC-RL-40 `scripts/release_removed_autocount_lines.py` exposes
  `run(db, company_id, dry_run=True) -> dict` (precedent `scripts/backfill_retired_spo_lines.py`).
  Dry run writes nothing and returns counts plus a per-line list: document number, DtlKey, product
  code, line qty, linked qty, OI rows affected; no customer or contact names.
- AC-RL-41 It selects only: PO lines `cancelled`, AutoCount source with a DtlKey, header not
  cancelled, not `cancelled_by_cancel_doc`, with a live OI link or ANY claim (open or resolved; a
  line holding only a claim is selected, e.g. SRTPW0035-CR 138 on the dev copy); SO lines the same
  plus `cancelled_at IS NULL`, with rows the AC-RL-20 retire acts on (raised / partly linked /
  placed; actioned rows are only flagged, so they never select a line); SPO lines with
  `retired_at` set and a live OI link or any claim. Tests pin every SO filter: a Cancel-SO-doc
  line, a line on a cancelled SO, a ref-less line and a line whose only live row is actioned are
  never selected.
- AC-RL-42 `dry_run=False` applies exactly the ingest's release (same functions, AC-RL-01..20)
  and a second run finds nothing.
- AC-RL-43 A CLI entry (`python -m scripts.release_removed_autocount_lines --company <id>
  [--apply]`) prints the dry-run report; it writes only with `--apply`.
- AC-RL-45 SPO lines need an explicit allow-list (owner via crew, 26 Oct: the data cannot tell a
  removed SPO line from one dropped by a cancelled SPO push or a superseded DocKey, and a
  placement on a cancelled SPO stays placed, LINKAGE Q5). The dry run lists each SPO candidate:
  SPO number, DtlKey, item code, placed qty, the SO numbers / order inquiry refs of its links.
  `run(..., spo_dtl_keys=())` / CLI `--only <DtlKey>` (repeatable or comma separated): `--apply`
  releases an SPO line ONLY when its DtlKey is listed; without `--only` it releases no SPO line
  at all (PO and SO lines unaffected). A listed DtlKey that is not a candidate is reported and
  ignored. On `--apply` each SPO entry says whether it was released, and the summary's SPO line
  and affected-row counts cover only the released lines (the owner reads these numbers).
- AC-RL-46 An allow-list key names the AutoCount database as well as the DtlKey (crew audit, 26 Oct:
  SPO-2026/10-0002 has live rows from two AutoCount databases, AED_SORENTO and AED_V2_MOCHA, so a
  bare DtlKey is not unique). The dry run prints each SPO candidate's key as
  `<source DB>:<DtlKey>` (the first and last parts of its `source_ref`); `--only` /
  `spo_dtl_keys` take exactly that form. A bare DtlKey (no source DB) and a key that matches more
  than one candidate are REFUSED: reported as such, nothing released for them; other valid keys
  in the same run still apply.
- AC-RL-44 The reconciliation sends nothing: `--apply` retires SO rows (AC-RL-20) but queues no
  purchasing handover email or other notification (owner: minimum change management; these
  removals are weeks old). The ingest path keeps its AC-RL-20 handover.

No UI change (Q5)
- AC-RL-50 No frontend file changes; removed lines keep showing Cancelled.
