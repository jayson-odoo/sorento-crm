# UAC - Flyer spec proposals: one card speaks for its code family

**Companion to:** `PLAN-flyer-family-proposals.md`
**Status:** Built 31 Aug 2026; `origin/main` (#446, #447) merged in and the review fixes
applied 31 Aug. Awaiting re-review + merge (rulings R1-R4 in the plan; R4 beats R2).
**Legend:** `[BE]` pytest · `[FE]` vitest · `[E2E]` agent-browser · `[MIG]` migration · `[T]` CI guard.

## Journey

**Actor:** master-data staff with `master_data.products.edit`, on a flyer reading's
Product specifications section.

1. They press **Propose specs from this flyer**. The pass runs as today.
2. The review list now shows, under the card `SRTWC8152-SH`, the base product AND its
   seven siblings `SRTWC8152-SH-150 ... SRTWC8152-SH-UF-300`, each as its own group, each
   sibling badged `via SRTWC8152-SH`.
3. A sibling's group carries the card's dimensions, flush type, rimless and the rest. It
   does NOT carry the card's `PP seat cover` when the sibling's own code or description
   says UF, nor the card's `S-Trap 200, 250` when the sibling's description says
   `S-TRAP 300MM`: for those keys the sibling's own reading stands and the card is silent.
4. A sibling that already holds a hand-set value the card disagrees with shows a conflict
   row, exactly as the base does today. Nothing is overwritten silently.
5. They tick rows and press Apply once. Done for the family. No pasting, no per-product
   visit, no PP-to-UF edit.

Decisions the reviewer makes: which rows to apply. Same as today, eight times fewer times.

## Group A - The family (S1)

### AC-A.1 [BE] Family = printed code plus dash-suffix codes
Given a reading whose card prints `X` and products `X`, `X-UF`, `X-UF-300` exist in the
active company, and `XY-1` (no dash after `X`) also exists,
When a proposal pass runs,
Then rows exist for `X`, `X-UF` and `X-UF-300` and none for `XY-1`. Rows for `X` have
`via_product_code IS NULL`; rows for the siblings have `via_product_code == "X"`.
`pages` on a sibling's rows are the card's pages.

### AC-A.2 [BE] Siblings resolve inside the company scope
A sibling code that exists only under another company yields no rows.

### AC-A.3 [BE] The card fills gaps; the sibling's own reading wins
Given sibling `X-UF-300` whose description reads `(S-TRAP 300MM) ... (WITH UF SEAT COVER)`
and a card stating `S-Trap: 200, 250mm`, `P-Trap 180mm`, `*PP Seat Cover`,
`D: L700xW370xH735mm`, `Twister Flushing`,
When the pass runs,
Then the sibling's rows include `dim_length 700`, `dim_width 370`, `dim_height 735`,
`flush_type twister`; there is NO row for `seat_material` or `trap_length` from the card
(the sibling's own reading holds `uf` and `300`); if the sibling's stored value for a key
equals the card's, the row is `unchanged` as today.

**R4 beats R2:** only `new` and `change` proposals are dropped for a key the sibling reads
itself. A `conflict` row - a value a person set by hand that the card disagrees with - is
KEPT even on such a key, because it reports what is already stored rather than what the
card says. "The sibling's own reading" means everything its own rows and rules yield under
#447, product-master COLUMNS included, so a length typed into `dimensions_length` silences
the card on `dim_length` exactly as its description does.

### AC-A.4 [BE] Hand-set values conflict, never silently change
Given sibling `X-150` with `dim_height` set by hand to 740 and the card saying 735,
Then its row is `conflict` with `stored_source == human`, same classification the base
gets (R4).

### AC-A.5 [BE] The base is unchanged
Rows for `X` itself are byte-for-byte what the pass produced before this feature. Pinned
by a golden on the real three-page flyer fixture
(`tests/fixtures/dealer_kit/flyer_base_rows_golden.json`): every base row's
`(product_code, spec_key, value, unit, kind, pages, via_product_code)`, taken with the
family path active, so the test fails if any base row changes.

### AC-A.6 [BE] Apply, edit, dismiss work on sibling rows
The existing apply / edit / dismiss routes accept sibling rows; applying one writes the
sibling's `product_specifications` with the same source/evidence a base row gets, and
`via_product_code` is recorded in the provenance evidence string (`"L700xW370xH735mm (card SRTWC8152-SH)"`).

### AC-A.7 [MIG] Column
`product_spec_flyer_proposal.via_product_code VARCHAR(100) NULL`.
`451_flyer_proposal_via_code`, chained on `450_spec_rules_readable`; `alembic heads` is one.

### AC-A.8 [T] Response carries the field
`FlyerSpecProductGroupOut.via_product_code` present in the serialised JSON (null on the base).

### AC-A.9 [BE] Counts
`product_count` on the batch counts siblings; the summary line on the reading page reads
"N products (M via a family card)".

### AC-A.10 [BE] Ceiling
The existing per-apply ceiling still holds; the pass on the real flyer (998 codes, 222
family siblings across WC alone) completes within the worker's job timeout. A test pins
the query count for family resolution at ONE statement per pass, not one per code.

## Group B - Review screen (S2)

### AC-B.1 [FE] Sibling groups follow their base
Groups order: by card page, then base code, then the base first, then its siblings by
code. A sibling group header shows the badge `via <base code>`.

### AC-B.2 [FE] Summary line
"N products (M via a family card)" above the groups when M > 0.

### AC-B.3 [E2E] Family round trip
Sidebar from `/` to a done reading with `SRTWC8152-SH` on it. Propose. Eight groups for the
family appear; the `-UF-300` group has no seat/trap rows from the card; apply the family's
dimension rows; `SRTWC8152-SH-UF-300`'s Specifications tab shows Length 700 badged Flyer.
375px and 1280px.

## Out of scope
- An explicit, editable family link. Trigger: a family that is not prefix-shaped (the 16
  `...-289UF` codes look like one; measure before building).
- The base product's own trap keys when the card prints an options line: unchanged today
  (first number). Captain: not concerned.
- Shipped code rules for `seat_material` (`-UF`): SHIPPED, at the END of the key's list
  (order is priority since #447). The condition this bullet named does not decide it any
  more: after #447's engine change the `UF ... SEAT` word rules are flyer-scoped and the
  flyer is not an input to `derive()`, so a description saying UF is never read on a
  catalogue derivation. Re-measured 31 Aug on the dev catalogue: **143 water closets gain
  `seat_material = uf`**, not the ~1 first predicted; 1 (`SRTWC8088-RL-UF`) holds a
  human-set `pp` that is kept and flagged rather than overwritten. See PLAN "The shipped
  `seat_material` code rule, re-measured after #447" - this is a captain decision, not a
  settled one.
