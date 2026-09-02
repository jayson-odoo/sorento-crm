# PLAN - Spec registry: a display label per value

**Status:** SUPERSEDED 2 Sep 2026 - folded into `PLAN-spec-workbench-redesign.md` / `spec-workbench-redesign-acceptance-criteria.md` (Groups D and E). Kept for the record; do not build from this file.
**Lane:** `.claude/worktrees/flyer-code-adopt`, branch `feat/spec-value-labels` stacked on
`feat/flyer-code-adopt` (see Migration order). Queued behind flyer-code-adopt S1/S2 because
the machine has one agent slot and one dev port (:3090).

## Why

Values are stored as lowercase slugs on purpose: `SpecKeyEditor` normalises input
(`raw.trim().toLowerCase().replace(/\s+/g,'_')`) and derivation, the ranker and the n8n
parser all compare on the slug. The screen then shows the slug through
`lib/spec-readable.ts` `readableValue`, which capitalises the first letter: `pp` -> "Pp",
`uf` -> "Uf". Abbreviations read wrong and staff cannot change it. The slug must stay; the
wording needs an owner.

## Design

**One column.** `product_spec_registry.value_labels JSONB NOT NULL DEFAULT '{}'`,
`{ "pp": "PP" }`. Staff-owned like `user_synonyms`: editable on seed rows, never
seed-repaired. No new table, no per-language layer (trigger: a second language).

**Backend** (`app/api/v1/master_data/spec_registry.py`, `app/models/product_spec.py`):
- Model column with `server_default=text("'{}'::jsonb")`, `default=dict`.
- `_serialise` adds `"value_labels": dict(row.value_labels or {})`.
- PUT payload `value_labels: Optional[dict[str, str]]`; validation per AC-A.3; reassign the
  dict on write (JSONB in-place mutation is not tracked).
- Confirm the seed repair path (`source == seed` refresh) does not touch the column; test AC-A.4.

**Frontend:**
- `SpecKeyDefinition.value_labels: Record<string, string>` (wherever the type lives; grep
  `interface SpecKeyDefinition`).
- `lib/spec-readable.ts`: `readableValue(value, unit?, labels?)`, `readableEntry(entry, labels?)`.
  String value with a label -> label (+ unit). Everything else unchanged.
- `components/spec-table/SpecTable.tsx` builds `labelsByKey` from `registry` next to the
  existing `synonymsByKey`, passes `valueLabels` into `SpecValueCell`; the cell uses it for
  the read-only text, the `title`, and the enum `options` labels.
- `SpecKeyEditor.tsx` "Words customers say": left cell becomes an `Input` (AC-B.2); state
  `valueLabels` seeded from `specKey.value_labels`; included in the save payload.
- `ProductProposalGroup`, `FlyerSpecReviewScreen`, `SpecVerificationList`,
  `SpecProposalReview`: pass labels from the registry each already holds; if one does not
  load the registry, use the existing registry query hook rather than a new fetch.

**Migration order.** `450_spec_registry_value_labels`, `down_revision` = the lane head at the time
(`449_flyer_reading_code_overrides`, then `451_flyer_proposal_via_code` if family lands first). Two lanes chaining on one parent would leave main with two
heads (memory: alembic dual-head). This branch stacks on `feat/flyer-code-adopt` and its PR
merges after that one.

## Slices
- **S1** - everything above. Phase 1: editor input + product tab label from a mocked
  `value_labels` on the registry response. Phase 2: migration, model, serialise, PUT
  validation, tests; swap the mock.

## Tests (Phase 2, red first)
- `tests/test_spec_registry_pr2_routes.py` (or the file that owns the PUT): AC-A.2, A.3
  (accept, trim, drop empty, reject unknown key 422, cap), A.4, A.5.
- vitest: `spec-readable.test.ts` (AC-B.1), `SpecKeyEditor.test.tsx` (input present,
  payload carries labels), `SpecValueCell`/`SpecTable` test (label rendered, option label).
- E2E evidence run AC-B.4.

## DoD
Mock swapped; no backfill (`{}`); no new permission; field asserted in the response;
sidebar verification at both widths.
