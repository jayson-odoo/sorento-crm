# PLAN: OI-LEGACY-DUP-REPAIR - legacy sheet rows squatting another SO line

Status: Review (small fix track: data-repair script + tests, no migration, no UI, no auth). Owner
approved a repair script 30 Oct ~09:30. Rehearsed 30 Oct on `sorento_prod_1028` in one rolled-back
transaction (crew ruling: no full copy): 12 restated, re-run 0. Prod apply waits for the owner's go
and his ruling on the 6 held rows.

UAC: `oi-legacy-dup-repair-acceptance-criteria.md` beside this file.

## 1. The defect, from the data

Read-only, local prod copy `sorento_prod_1028` (28 Oct 19:00), code `origin/main` b07e71d5bf.

The 20 Sep order inquiry sheet uploads (`import_jobs` of type `order_inquiry_import`, 2026 book
03:18, 2027 book 03:22) ran the five-pass line pick that predates `_pick_lines_by_date_order`
(2280975f97, 22 Sep). Rule R5 (6c90649669, 19 Sep) counts identical rows on one tab as separate
instructions (`_plan`, `project_order_inquiry_import_service.py:1763-1797`). Where a tab stated the
same SO + item + qty + date twice but the sales order has only one line for it, the first copy
took the matching line and the second fell through to the fallback pass, which put it on the
earliest open line with room: a line with a different quantity AND a different date.

When the next book's row for THAT line arrived, the line already carried a row, so it was skipped
with `already_raised` ("Left alone: this line already carries an order inquiry"). The line's own
instruction was never raised; the duplicate sits in its place.

Proof for OI-2609-0676 / M9713SS, from `import_job_rows` (`app/models/job.py:95`, identity JSON
`{doc_no, item_code, delivery_date, sheet, qty}`, `entity_id` = the OI row):

| job | tab | sheet row | qty | date | code | OI row |
|---|---|---|---|---|---|---|
| 2026 book | OCT 26 | 630 | 2 | 2026-10-07 | created | `a9d806ca`, line 10 (2, 2026-10-07) |
| 2026 book | OCT 26 | 662 | 2 | 2026-10-07 | created | `1367d281`, line 38 (26, 2027-04-07) |
| 2027 book | APR 27 | 166 | 26 | 2027-04-07 | already_raised | none |

## 2. Detector (read-only)

A row C is a squatter when ALL hold:

1. C was `created` by an `order_inquiry_import` job row J_c (its `import_job_rows.entity_id`).
2. Another row S was `created` by the SAME job from a DIFFERENT sheet row with the identical
   identity (tab, SO, item, qty, delivery date), and S sits on a sales order line whose qty and
   date equal that identity.
3. C's line date is not the sheet date AND C's line qty is not the sheet qty.
4. An `order_inquiry_import` job at or after J_c skipped a row `already_raised` whose identity names
   C's line exactly: same SO and item, date = C's line date, qty = C's line qty.

On `sorento_prod_1028`: 18 rows on 3 OIs (OI-2609-0676 x16, OI-2609-0327 x1, OI-2609-0352 x1).

### Against crew's first count (95 rows, 52 open, 12 OIs)

Crew's rule (row qty/date differ from its line AND an identical sibling on the same OI sits on a
matching line) gives 99 rows here: 2 non-legacy (cancelled, OI-2609-0764, not a sheet import),
60 where the row's qty EQUALS its line's qty (a tab listing an item once per SO line, e.g. MAR 26
stating 372 for each of six 372 lines, all dated 2026-03-01; only the date drifts, each carries its
own placement), 20 where qty differs but nothing proves a wrong line (splits whose rows sum to the
line, lines AutoCount reduced to 0, a PO AutoCount itself names for that line), and 17 of the 18
squatters. The 18th (OI-2609-0676 M3155) escapes crew's rule because its qty was later restated to
78 (its sibling stays 6). The "52 open" figure is UNVERIFIED: no state filter on the 99 gives 52.

## 3. Repair rule (per row, from evidence)

- **Restate in place** when C is `raised`, has no `order_inquiry_links`, no reserve request rows,
  is not a bundle anchor, and still carries the sheet's qty and date (untouched since import):
  set `qty` / `delivery_date` to the skipped row's qty / date (which equal the line's). This is
  exactly the row the skipped instruction would have raised, on the line it names. Write
  `previous_qty` / `previous_delivery_date` (the Was / Now pair), append a note naming both sheet
  rows, and if purchasing had acknowledged it set `ack_state = changed`, `changed_at = now`
  (purchasing must re-acknowledge 26, not 2). One `log_audit` EVENT per row.
- **Hold, report only** (no write): cancelled rows, placed/partly-linked rows with links, and an
  actioned row. Each is printed with the reason. Delete was rejected: it would leave the line with
  no instruction at all, while the skipped row proves what the line should carry.

On `sorento_prod_1028`: 12 restated (all OI-2609-0676), 6 held.

## 4. Shape

`sorento_crm_backend/scripts/repair_oi_legacy_dup_rows.py`, mirroring
`scripts/repair_oi_stale_link_state.py` / `scripts/rollback_oi_sheet_upload.py`:

- `find_squatters(db)` - the detector, read-only, returns one record per squatter with its evidence
  (both sheet rows, the skipped row, line, links) and its verdict (`restate` / hold reason).
- dry run is the default and prints every row. `--apply --expect N` writes, and refuses unless the
  restate count found at apply time equals N (the dry run's count). Idempotent: a restated row no
  longer carries the sheet values, so a second run reports it "already restated", never re-written.

## 5. Tests (red first)

`sorento_crm_backend/tests/test_repair_oi_legacy_dup_rows.py`, Postgres fixture, every chain seeded.
One test per UAC item.

## 6. Rehearsal

Crew ruling (30 Oct): no full scratch copy (disk), so apply inside ONE transaction on
`sorento_prod_1028`, read through the real routes, then ROLLBACK. Result (PR #1996 crew-note): found 18,
restated 12, second apply 0; OI-2609-0676 rows off their line 15 -> 3, ack `changed` 0 -> 10; Lines tab
shows M9713SS 26 on 2027-04-07 with Was 2 on 2026-10-07; the Stock Debt drill's live remaining for the
2027-04-07 line goes 2 -> 26 (its frozen "OI row" figure stays 2 until the next snapshot). Nothing
persisted. Crew asks the owner before anything touches prod.

## 7. Detector speed

The first detector was one statement self-joining `import_job_rows` on JSONB expressions; it ran past
ten minutes on the 27 GB copy. It is now staged: a window count over one scan of the created job rows,
an IN-list load of their inquiry rows, one scan of the `already_raised` rows for the SOs involved.
3 s on the same copy.
