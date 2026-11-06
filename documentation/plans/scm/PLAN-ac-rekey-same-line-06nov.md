# PLAN - AC-REKEY-SAME-LINE: an AutoCount re-keyed SO line is not a removal

Status: built, in review (6 Nov 2026), on the card's recommended answers (strict key, crew census). Track: small fix (no migration, no auth/RBAC change).

Lane AC-REKEY-SAME-LINE, 6 Nov 2026. Behaviour card: `ac-rekey-same-line-behaviour-card.md`.

## Problem

4 Nov 2026: an AutoCount re-save gave one SO line (qty 118) a new DtlKey, nothing else changed. CRM matches SO lines only by `source_ref`
(`AED_SORENTO:<DocKey>:<DtlKey>`), so ingest cancelled the old core line, created a new one, and
the removed-line sweep retired the Order Inquiry row and queued the purchasing handover email.
The demand of 118 was lost.

## Goal

A push that drops DtlKey X and adds DtlKey Y on the same SO for the same line (rule in the card)
updates the core line's `source_ref` in place: same ids, project mirror line and OI rows kept, no
cancel, no OI retire, no email, no new project line. Genuine removals unchanged.

## Build

- `DocumentIngestService._pair_rekeyed_lines` (`sorento_crm_backend/app/services/document_ingest_service.py`),
  called from `_sync_lines` for sales orders before the matched loop: renames the old row's `by_ref`
  key to the new `source_ref` for a unique (Seq, product, qty, unit price) pair, location equal when
  sent; a removed line (cancelled, not by CS or a Cancel SO document) is never a candidate.
- No email, notification or OI code is called from the re-key path; `retire_rows_for_removed_so_lines`
  is untouched (email gating is lane FP-EMAIL-ONE-TRIGGER).
- Tests: `sorento_crm_backend/tests/test_ac_rekey_same_line.py` (15).
- Out of scope: repair of already-affected lines (staff fix by hand), PO lines, Seq renumbering.
