# PLAN: OI trail cleanup (fake "Reconfirmed" rows from the 20 Sep sheet import)

Status: built, dry run done on a throwaway copy of sorento_prod_1020 (699 fakes, 0 genuine), in review (small fix track: one data migration, no UI change, no auth/RBAC change; owner OK'd deleting these rows 27 Oct 2026)

Lane: OI-TRAIL-CLEANUP. UAC: `oi-trail-cleanup-27oct-acceptance-criteria.md` alongside.

## Problem

The Fulfilment Planning decision trail shows "Reconfirmed" events in the uploader's name that
nobody performed (SO400884 / CB4702: "Reconfirmed · OI-2609-0416 · qty 36 · 20/09/2026 7:19 pm").
Two causes stacked:

1. The OI sheet import of 20 Sep 2026 (code at baad8defc7, `now = _now()`, a naive Malaysia wall
   clock) stamped the header `raised_at`, every row's `acknowledged_at`, and `actioned_at` /
   `changed_at` where it closed or settled a row, eight hours ahead of the real instant. The
   rows' own `created_at` (server `now()`) is real UTC. 523 itself later moved the header
   `raised_at` back to the earliest row's `created_at`, so only the row stamps are still off.
2. Migration `523_oi_monthly_no_raises.backfill_raises` (shipped in #1093 together with the
   clock fix) read the header as "re-stamped more than a minute after its first row", wrote a
   `reconfirmed` raise row in the uploader's name at the shifted stamp, and blanked the `raised`
   row's `raised_by`. `decision_trail_service._raise_entries` ("later events" pass) renders it.

## Fix

One data migration, `sorento_crm_backend/alembic/versions/oitc_0001_fake_reconfirms.py`.

- **Provenance, not a timestamp list.** A `(stamp, uploader)` pair is an affected upload when a
  `reconfirmed` raise row's `raised_at` / `raised_by` equal, to the microsecond, the
  `acknowledged_at` / `acknowledged_by` of a sheet-migrated row (note prefix
  "Migrated from order inquiry sheet", the trail's own test) on the same inquiry, 7h50m-9h after
  that row's `created_at`. The import's `now` was one Python value shared by the whole upload; a
  genuine reconfirm is stamped by `_record_raise`'s `datetime.utcnow()` and cannot land on it.
- Every `reconfirmed` row at an affected pair is deleted.
- Every `order_inquiry_rows.acknowledged_at` / `actioned_at` / `changed_at` equal to an affected
  stamp moves back 8 h (microsecond equality is what ties a row to that upload). That includes
  rows born later that copied the acknowledgement forward (a split or revision,
  `project_order_inquiry_service.py:7364`; 91 such rows on the 20 Oct copy).
- The header `raised_at` needs no step: 523 already moved it to the earliest row's
  `created_at`, the real instant (all 699 headers on the 20 Oct copy).
- The `raised` row 523 left nameless gets the uploader back, only where the header's own
  `raised_by` is that uploader (the import names only headers it creates).
- Idempotent: stamps are read off the rows the same step deletes, one transaction, so a second
  run touches nothing. Counts are logged.
- Downgrade: no-op. The real rollback is restoring the pre-migrate dump.

## Out of scope

- 2 sheet rows at one other upload's stamp also sit 8 h after their birth, but that upload
  created no header, so it left no fake reconfirm and is not one of the two 20 Sep uploads the
  owner approved. Their acknowledged time stays 8 h late; a new crew ask if it should move.

## Nothing re-creates it

- 523 is a past revision; alembic does not rerun it, and its `backfill_raises` skips any header
  that already holds a raise row (the `raised` row stays).
- Current import: `project_order_inquiry_import_service.py:3044`
  `now = _now() - timedelta(hours=8)`; `_record_raise` stamps `datetime.utcnow()`
  (`project_order_inquiry_service.py:7777`).

## Verification

- `tests/test_migration_oitc_fake_reconfirms.py`: fixture built with the real 523 backfill;
  red against a no-op cleanup, green with it.
- `scripts/oitc_dry_run.py`: counts plus SO400884's trail before/after, rolled back. Run by crew
  on a throwaway copy of sorento_prod_1020.
