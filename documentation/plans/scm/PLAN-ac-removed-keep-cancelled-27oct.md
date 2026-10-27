# PLAN: AutoCount-removed PO/SO lines stay Cancelled, never deleted

Status: in progress (small fix track, URGENT hotfix; backend only; no migration)

## Owner ruling (27 Oct 2026)

A PO/SO line removed in AutoCount stays in the CRM as a Cancelled record; only its linkage
goes. An AutoCount-era line (one carrying a DtlKey `source_ref`) is never hard-deleted.

## Defect

`DocumentIngestService._sync_lines` sweeps every leftover line. A leftover nothing points at
was deleted. After AC-REMOVED-LINES (#1878) releases a removed line's OI links/claims on
push 1, push 2 finds the line unreferenced and deletes it (PO 202607-S0081, SRTSA-SS 546,
DtlKey 45713392).

## Fix

In the sweep, a leftover row with a `source_ref` is always cancelled, whatever references
it. Only ref-less (xlsx-era) leftovers nothing points at are still deleted: that is the
pre-AutoCount duplicate-count guard the sweep was built for, and those rows carry no DtlKey.

## Recovery

`sorento_crm_backend/scripts/restore_deleted_removed_lines.py`: restores lines deleted by
the bug from a pre-27-Oct-11:45 deploy snapshot, as Cancelled with no links. Dry run by
default, `--apply` to write. Runbook in the PR body.

UAC: `ac-removed-keep-cancelled-27oct-acceptance-criteria.md`.
