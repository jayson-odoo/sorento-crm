# PLAN - AC-REKEY-SAME-LINE: an AutoCount re-keyed SO line is not a removal

Status: Plan (behaviour card pending owner answers). Track: small fix (no migration, no auth/RBAC change expected).

Lane AC-REKEY-SAME-LINE, 6 Nov 2026. Behaviour card: `ac-rekey-same-line-behaviour-card.md` (to follow).

## Problem

SO398322, 4 Nov 2026: an AutoCount re-save gave line Seq 2552 (CB2805A-DIY 118 @ 19.35) a new
DtlKey (44806451 -> 46204553). CRM matches SO lines only by `source_ref`
(`AED_SORENTO:<DocKey>:<DtlKey>`), so ingest cancelled the old core line, created a new one, and
the removed-line sweep retired the Order Inquiry row and queued the purchasing handover email.
The demand of 118 was lost.

## Goal

A push that drops DtlKey X and adds DtlKey Y on the same SO for the same line (rule in the card)
updates the core line's `source_ref` in place: same ids, project mirror line and OI rows kept, no
cancel, no OI retire, no email, no new project line. Genuine removals unchanged.
