# PLAN - Flyer spec proposals: one card speaks for its code family

**Status:** Built 31 Aug 2026 (backend + review screen, one PR). `origin/main` merged in
31 Aug (#446, #447) and the review fixes applied on top; awaiting re-review + merge. One
open captain decision: the `seat_material` measurement below (143 products, not ~1). UAC:
`flyer-family-proposals-acceptance-criteria.md`.
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
- **R4 - hand-set values conflict as today**, never overwritten silently. **R4 beats
  R2** (captain, 31 Aug): a `conflict` row is KEPT on a sibling even for a key the
  sibling's own reading answers, because a conflict is not the card speaking about the
  key - it reports that a person set the value by hand and the card disagrees, and that
  question is worth asking either way. Only `new` and `change` proposals are dropped for
  an own-read key.

## Design

### Backend (`app/services/product_spec_flyer_ingest.py`)

`_propose`:
1. After `matched = list(report.matched)`, resolve siblings in ONE statement: unnest the
   matched printed codes and join `Product` on the PREFIX COMPARISON
   `substr(product_code, 1, length(code) + 1) = code || '-'` (ordinary ORM query so the
   company predicate applies). Not a `LIKE`: `_` is a single-character wildcard there, so
   a printed `SRT_WC1` would match `SRTXWC1-P` as well as its own family, and a product
   code is data rather than a pattern to be escaped. The category row is outer-joined in
   the same statement, because the sibling's own reading needs it. Exclude any sibling
   that is itself a matched printed code (it has its own card). Result:
   `{base_code: [(Product, ProductCategory | None), ...]}`.
2. `_stored` is loaded for base + sibling ids together (still one query).
3. For each matched entry, run the existing per-product step for the base (unchanged,
   AC-A.5), then for each sibling:
   - `own = derive(sibling, sibling's category, rules_by_key, scopes_by_key, max_values)`.
     **"Own reading" means everything the sibling's own rows and rules yield under
     #447 - columns included** - not only its description and code. Since #447 a
     product-master column is a rule row like any other, so a length a merchandiser
     typed into `dimensions_length` is part of the sibling's own reading and the card
     is silent on that key: the card can never override a value the sibling's own
     product master states. The call passes the sibling's REAL category row and the
     CONFIGURED `max_values`, which is exactly what the catalogue path
     (`derive_for_code`) passes - deriving with `None` for either would be a different
     reading wearing the same name, and the card would fill a gap the catalogue does
     not have.
   - `derive` reads the product master, never the flyer: since #447 the flyer is not
     an input to `derive` at all (it arrives as `""`).
   - `proposals = _proposals_for_product(text=card text, code=sibling.product_code, stored=sibling's ...)`
     then drop any proposal whose key is in `own` **unless its kind is `unchanged` or
     `conflict`** - both of those are statements about what is ALREADY STORED rather
     than about the card's reading, and R4 beats R2. Hand-set values go through
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

### The shipped `seat_material` code rule, re-measured after #447 (31 Aug)

The rule ships, but the number behind it is NOT the one this plan first wrote down, and
the difference is the captain's call to make.

- The rule row sits **last** in `seat_material`'s list, after the text rules, matching
  what migration 450 did to every other key's code rules. #447 made rule ORDER the whole
  of priority (no source-major phase), so a code row on top would genuinely outrank the
  words - which is the defect 450 exists to fix.
- **Measured on the dev catalogue (23,063 product rows, prod copy), through `derive()`
  with the configured rules, scopes and caps: 143 products change `seat_material`, not
  the ~1 this plan predicted.** 128 gain `uf` where they held nothing, 14 already hold
  `uf` (13 from a flyer, 1 derived), and 1 (`SRTWC8088-RL-UF`) holds a human-set `pp`
  that the rule now contradicts - kept, not overwritten, and raised as one exception,
  because `merge_authored_over` puts an authored value above anything derivable.
- **Why the first measurement was wrong:** it counted `-UF` products whose DESCRIPTION
  lacks the word UF, and found 1 of 179. True, but beside the point after #447: the two
  rules that read `PP`/`UF` next to `SEAT` are scoped `source: "flyer"`, and #447 removed
  the flyer from `derive()`'s inputs entirely. So on a catalogue derivation those rules
  never fire, 178 descriptions that do say UF are never read for it, and the code row is
  not a one-product fallback - it is the only `seat_material` reader that fires at all
  for a `-UF` water closet. The scope gate (`class: Water Closet`) is what takes 179 down
  to 143.
- The values it writes are correct - a `-UF` water closet does have a UF seat - but this
  is a 143-product catalogue change, not the ~1 the UAC sanctioned, so it is called out
  here rather than shipped quietly. The alternative, NOT taken here because it is a
  bigger decision about #447's engine, is to unscope the `\bUF\b[^.]*SEAT` rule so a
  description saying "WITH UF SEAT COVER" is read on a derivation.
- The live registry row for `seat_material` carries **no** stored `derivation_rules`
  (measured 31 Aug), so `configured_rules` falls back to the shipped table and the edit
  above is live on the dev database. No data-backfill of the rule into
  `product_spec_registry` is needed, and 451 does not attempt one.

### Frontend

- `services` types: `FlyerSpecProductGroup.viaProductCode: string | null`,
  `FlyerSpecBatch.viaCount`.
- `ProductProposalGroup` header: badge `via SRTWC8152-SH` when set.
- `FlyerSpecReviewScreen` / `SpecProposalSection` summary line per AC-B.2. Ordering comes
  from the server; the FE does not re-sort.
- Phase 1 mock: extend the existing fixtures with `viaProductCode` and render; no new
  component.

### Migration order
`451_flyer_proposal_via_code`, `down_revision = "450_spec_rules_readable"` - the head on
`main` once #447 landed. The lane branched before that and first named itself 450; it was
renamed when main was merged in, and `alembic heads` reports one head.

## Slices
- **S1** - backend: family resolution, own-reading filter, `via_product_code`, counts,
  apply evidence, tests (AC-A.*). Phase 2 only (no UI change beyond the badge, which is S2).
- **S2** - review screen badge + summary, evidence run (AC-B.*).

## Tests (red first)
- `tests/test_product_spec_flyer_ingest_service.py`: AC-A.1 to A.6, A.9, A.10 (query
  count with a SQLAlchemy `before_cursor_execute` counter). AC-A.5 is a GOLDEN:
  `tests/fixtures/dealer_kit/flyer_base_rows_golden.json` pins every base row the pass
  writes for the real three-page flyer fixture (227 rows, 38 codes, 18 spec keys), taken
  with the family path active, so a change to what a printed code reads for itself cannot
  pass unnoticed. Re-bless with `REBLESS_FLYER_BASE_GOLDEN=1` and a stated reason.
  Also guarded: the underscore case on the prefix join, `_reset` zeroing `via_count`,
  group ordering when a second base sits on the same page, a sibling's hand-set conflict
  surviving on a key it reads itself, and the own reading using the real category + caps.
- `tests/test_dealer_kit_flyer_spec_proposal_routes.py`: AC-A.8, sibling apply.
- vitest: `ProductProposalGroup.test.tsx` badge; summary line test.

## Evidence run (31 Aug, after the merge)

Screens: `documentation/plans/master-data/evidence/flyer-family-proposals/` (01-10).
Lane `:3090` / `:8090`, sidebar nav from `/`, headless agent-browser, no console errors.
Re-run AFTER merging #446 + #447 and restarting the lane worker, because #447 changed
what a sibling's own reading yields.

**The real flyer** (`_SORENTO A3 FLYER 2025-2026_compressed.pdf`, 36 pages, 998 printed
codes, 32 of them not in the master). Propose again completed in **2.7 s**:

> 5221 specification values across **1243 products (285 via a family card)**: 635 new,
> 221 change what the master says, 149 conflict with a value a person set, 4215
> unchanged, 1 suppressed.

**The `SRTWC8152-SH` family** (04 at 1280, 05 + 06 at 375): the base plus all seven
siblings render as their own groups, each sibling badged `via SRTWC8152-SH`, base first.
34 rows, and they read exactly as R2 says they should:

- base: 6 rows, `via_product_code` NULL, all `unchanged`;
- `-150` / `-200` / `-300`: height, width, flush AND `seat_material pp` from the card -
  their own codes say nothing about a seat;
- `-UF` / `-UF-150` / `-UF-200` / `-UF-300`: height, width, flush and NO `seat_material`
  row at all - their own `-UF` code answers it, so the card stays silent. This is the
  PP-to-UF edit the journey exists to delete, and it is the shipped code rule earning
  its place.
- no sibling gets `trap_type` or `trap_length` from the card: their own descriptions
  state the trap.

**The applied Height row** (07-10). Applied on the three-page fixture reading
(`flyer_sample.pdf`, its own `SRTWC8354-SH` family): **130 rows applied, 0 refused**, of
which 127 were sibling rows. `SRTWC8354-SH-UF-200` - a code the paper never printed - then
holds, on its Specifications tab:

| Spec | Value | Source | Evidence |
| --- | --- | --- | --- |
| Height | 800 mm | **Flyer** | `flyer flyer_sample.pdf: H800MM (card SRTWC8354-SH)` |
| Width | 370 mm | **Flyer** | `flyer flyer_sample.pdf: W370X (card SRTWC8354-SH)` |
| Seat cover material | Uf | Description | `-UF` |
| Trap outlet length | 200 mm | Description | `S-TRAP 200MM` |

The `(card SRTWC8354-SH)` suffix is AC-A.6: provenance says where the reading came from,
because this product's own code was never on the paper.

## DoD
No backfill (new column NULL on old rows means "base"); no new permission; field asserted
in the response; sidebar verification at both widths.
