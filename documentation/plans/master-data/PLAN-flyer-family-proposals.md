# PLAN - Flyer spec proposals: one card speaks for its code family

**Status:** Built 31 Aug 2026 (backend + review screen, one PR); awaiting review + merge. UAC: `flyer-family-proposals-acceptance-criteria.md`.
**Lane:** `.claude/worktrees/flyer-code-adopt` after S2 of flyer-code-adopt; branch
`feat/flyer-family-proposals` stacked on `feat/flyer-code-adopt`. Queue: flyer-code-adopt S2
-> THIS -> spec-value-labels (#423) -> readers-as-rules (#425).

## Why

1037 WC codes; 222 are `<existing base code>-<suffix>` of another (113 bases). The flyer
prints the base. The propose pass writes rows for the exact match only, so staff open each
sibling, paste the card text, delete the trap line, read, and flip PP to UF by hand: 222
times. A card describes a family; the suffixes (UF, 150/200/300, P/S, RL, SC, BL, GY) are
the only things that differ, and each sibling's own code and description already state them.

## Captain rulings (31 Aug)

- **R1 - family by prefix.** Sibling = product in the active company whose code is
  `printed code + "-" + anything`. Deterministic, explainable, no new table. An explicit
  editable link waits for a family that is not prefix-shaped.
- **R2 - the card fills gaps; the sibling's own reading wins.** Trap type, trap length,
  seat material and anything else the sibling's own description or code yields are never
  proposed from the card. Card is silent on those keys for siblings.
- **R3 - base product unchanged**, options line and all.
- **R4 - hand-set values conflict as today**, never overwritten silently.

## Design

### Backend (`app/services/product_spec_flyer_ingest.py`)

`_propose`:
1. After `matched = list(report.matched)`, resolve siblings in ONE statement: unnest the
   matched printed codes, join `Product` on `Product.product_code LIKE code || '-%'`
   (ordinary ORM query so the company predicate applies, the way `_suggestions` in
   `flyer_matching.py` does it). Exclude any sibling that is itself a matched printed code
   (it has its own card). Result: `{base_code: [Product, ...]}`.
2. `_stored` is loaded for base + sibling ids together (still one query).
3. For each matched entry, run the existing per-product step for the base (unchanged,
   AC-A.5), then for each sibling:
   - `own = derive(...)` values for the sibling from its OWN description and code only
     (the derivation entry point the catalogue uses; no flyer text). The keys it sets are
     the sibling's own reading.
   - `proposals = _proposals_for_product(text=card text, code=sibling.product_code, stored=sibling's ...)`
     then drop any proposal whose key is in `own` unless the card's value equals the
     stored value (then keep as `unchanged`, as today). Hand-set values go through
     `classify_spec_proposal` untouched, so they come back `conflict` (R4).
   - Rows carry `product_id = sibling.id`, `product_code = sibling.product_code`,
     `pages = card pages`, `via_product_code = base printed code`.
4. Counts: `product_count` includes siblings; add `via_count` to the batch summary.

Apply path (`apply_flyer_spec_proposals`): evidence string for a sibling row appends
`(card <base>)` so provenance says where the reading came from. No other change: the row
already names its own product.

Model: `ProductSpecFlyerProposal.via_product_code = Column(String(100), nullable=True)`.
Schema: `FlyerSpecProductGroupOut.via_product_code: Optional[str]`; batch summary
`via_count: int`. `grouped_proposals` sorts base before its siblings (page, base code,
`via is NULL first`, code).

Measurement task in S1 (before writing the seat rule): count `-UF` siblings whose
description lacks `UF`. If > 0, ship a `code_contains` rule for `seat_material` ahead of the
text rules; else skip (see UAC Out of scope).

### Frontend

- `services` types: `FlyerSpecProductGroup.viaProductCode: string | null`,
  `FlyerSpecBatch.viaCount`.
- `ProductProposalGroup` header: badge `via SRTWC8152-SH` when set.
- `FlyerSpecReviewScreen` / `SpecProposalSection` summary line per AC-B.2. Ordering comes
  from the server; the FE does not re-sort.
- Phase 1 mock: extend the existing fixtures with `viaProductCode` and render; no new
  component.

### Migration order
`451_flyer_proposal_via_code`, `down_revision` = the head after spec-value-labels lands
(`450_spec_registry_value_labels`) or, if this lane goes first, `449_flyer_reading_code_overrides`.
The coder checks `alembic heads` on the lane before naming it; one head, always.

## Slices
- **S1** - backend: family resolution, own-reading filter, `via_product_code`, counts,
  apply evidence, tests (AC-A.*). Phase 2 only (no UI change beyond the badge, which is S2).
- **S2** - review screen badge + summary, evidence run (AC-B.*).

## Tests (red first)
- `tests/test_product_spec_flyer_ingest_service.py`: AC-A.1 to A.6, A.9, A.10 (query
  count with a SQLAlchemy `before_cursor_execute` counter).
- `tests/test_dealer_kit_flyer_spec_proposal_routes.py`: AC-A.8, sibling apply.
- vitest: `ProductProposalGroup.test.tsx` badge; summary line test.

## DoD
No backfill (new column NULL on old rows means "base"); no new permission; field asserted
in the response; sidebar verification at both widths.
