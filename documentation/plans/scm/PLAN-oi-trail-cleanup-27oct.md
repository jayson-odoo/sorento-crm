# PLAN: OI trail cleanup (fake "Reconfirmed" rows from the 20 Sep sheet import)

Status: in progress (small fix track: data migration only, no UI change, no auth/RBAC change; owner OK'd the cleanup 27 Oct 2026)

Lane: OI-TRAIL-CLEANUP. UAC: `oi-trail-cleanup-27oct-acceptance-criteria.md` alongside.

## Problem

The Fulfilment Planning decision trail shows "Reconfirmed" events in the uploader's name that
nobody performed. Two causes stacked:

1. The OI sheet import of 20 Sep 2026 stamped the inquiry header `raised_at` and every row's
   acknowledged time with a Malaysia wall clock stored as if it were naive UTC (+8 h). Fixed for
   new imports in #1093 (22 Sep).
2. Migration `523_oi_monthly_no_raises.backfill_raises` then saw the header time more than a
   minute after the rows' `created_at` and wrote a `reconfirmed` raise row in the uploader's
   name at the shifted time.

## Fix

To be filled in once the code is read (sections: identification by provenance, timestamp
shift, idempotency, rollback).
