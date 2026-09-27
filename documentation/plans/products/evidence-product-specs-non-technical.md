# Lane evidence - product specifications for non-technical staff (#1286)

**Companion to:** `PLAN-product-specs-non-technical-26sep.md` section 7 (evidence to gather at
S0 start) and the S1 parity gate (AC-S1.4).
**Branch base:** `origin/main` `232182ae5`.

## Where this lane was measured, and what that means

This lane ran in a Claude Code cloud environment. Its database is the empty,
`scripts.bootstrap_env`-seeded schema (reference data only, no business rows), and the
prod-copy database is never restored to a cloud VM (`documentation/agents/cloud-lanes.md`,
"The one rule"). So the dev-database figures in sections 1 to 5 below could not be read from
here. Each section carries the exact read-only query, and one script prints all of them:

```bash
cd sorento_crm_backend
venv/bin/python -m scripts.product_spec_lane_evidence   # sections 1 to 5, before the migrations
venv/bin/python -m scripts.product_spec_rule_parity     # section 6, after the migrations
```

The owner (or the orchestrator on the Mini) runs it once against the dev copy before merge and
pastes the output under each heading. The S0 and S1 migrations also log, at `WARNING`, every
value they clear and every rule they convert, so the deploy log carries the same list.

Fix round 2 (reviewer pass at ea0b804b) widened what the script and the migrations report:
section 1 now carries the Brand row's `is_active`, `rank_weight` and `value_weights` (a
non-empty `value_weights` is a house preference that stops applying: the owner rules on it
before merge); 1b lists every other rule or scope gated on brand (those rules stop reading);
1c lists every visibility policy naming brand. Section 2 counts the same hand-set sources the
migration does (`human`, `supplier`, `flyer`). `spec_0003_rules_null_brand_pol` then logs each
policy it takes brand out of, and the keys whose empty stored rule list becomes the shipped-rules
marker (NULL); after it, an empty list means "no rules".

Nothing in S0 copies a typed Brand value into `products.brand_id`. Where section 2 or 3 shows a
typed value naming a real brand on a product with no brand field, the owner decides by hand.

## 0. Every reader of the Brand specification value (static, measured on the branch base)

`grep` over `sorento_crm_backend/app`, `sorento_crm_mcp/` and the spec screens in
`sorento_crm_frontend` for `values["brand"]`, `read("brand")`, `spec_key == "brand"`,
`"brand"` inside the spec services and `field === 'brand'`:

| # | Reader | What it did | S0 change |
| --- | --- | --- | --- |
| R1 | `product_spec_search._brand_match_in_haystack` | read `excluded_values` off the `brand` registry row to decide which brand names never bind | reads `brands.is_searchable` instead |
| R2 | `product_spec_search.search_specs` | scored a bound brand against the stored `brand` spec value, weight = the registry row's `rank_weight` (1.5) | scores it against the product's own brand (`products.brand_id` joined through `brands`), same weight 1.5 |
| R3 | `product_spec_search.filter_specs` | turned a bound brand into a membership clause on the stored `brand` spec value | membership on `products.brand_id` through `brands.brand_name` |
| R4 | `product_spec_understanding._vocabulary` | offered the model the distinct stored `brand` values minus OTHERS and NO LOGO | offers the Brands master names where `is_searchable` is true |
| R5 | `product_spec_rendering.render_spec_sentence` | led the customer sentence with the stored `brand` value | leads with the product's brand field |
| R6 | `product_spec_derivation.derive_for_code` | flagged `company_copies_disagree` on `brand` | flag removed (nothing derived to disagree) |
| R7 | `product_spec_derivation._record_read` + `product_spec_registry.from_field_choices` | `from_field brand` read the brand field into the spec | removed; `brand` is refused as a rule or a spec value |
| R8 | `api/v1/master_data/product_specifications.py` (Spec Verification list) | `brand_hint` from the stored spec value, and `brand` excluded from `spec_count` | `brand_hint` reads the product's brand field |
| R9 | FE `SpecRuleEditor.tsx:72`, `lib/ruleSentence.ts:208` | "the product's brand field" as a rule choice | gone with the rule editor rewrite (S1) |
| R10 | `sorento_crm_mcp/` | no spec-key reader; `brand` there is the Brands master list tool | no change |

The Spec Verification list keeps its **Brand** column: it shows `products.brand_id`'s name (the
product's brand field, which D1 keeps as the only brand), not the removed specification.

## 1. The `brand` registry row, verbatim

```sql
SELECT user_values, value_labels, suppressed_values, user_synonyms, excluded_values,
       value_weights, derivation_rules
FROM product_spec_registry WHERE spec_key = 'brand';
```

Not measured from the cloud lane (see above). Output: _to paste_.

## 2. Products whose Brand spec was set by hand

```sql
SELECT p.product_code, s.values->'brand'->>'value' AS typed, b.brand_name AS product_brand
FROM product_specifications s
JOIN products p ON p.id = s.product_id
LEFT JOIN brands b ON b.id = p.brand_id
WHERE s.provenance->'brand'->>'source' IN ('human', 'supplier', 'verified')
ORDER BY p.product_code;
```

Output: _to paste_.

## 3. Stored Brand spec different from the brand field, and Brand spec with no brand field

```sql
SELECT s.provenance->'brand'->>'source' AS source, count(*)
FROM product_specifications s
JOIN products p ON p.id = s.product_id
LEFT JOIN brands b ON b.id = p.brand_id
WHERE s.values ? 'brand'
  AND (b.brand_name IS NULL OR lower(b.brand_name) <> lower(s.values->'brand'->>'value'))
GROUP BY 1;
```

The per-product list is printed by the script. Output: _to paste_.

## 4. Company copies that disagree on brand (the removed derivation flag)

```sql
SELECT p.product_code, string_agg(DISTINCT b.brand_name, ', ') AS brands
FROM products p JOIN brands b ON b.id = p.brand_id
GROUP BY p.product_code HAVING count(DISTINCT b.brand_name) > 1;
```

Six rows catalogue wide when the derivation comment was written. Output: _to paste_.

## 5. Stored rules without a builder (what S1 converts), per specification

```sql
SELECT spec_key, count(*) AS rules,
       count(*) FILTER (WHERE r ? 'builder') AS with_builder,
       count(*) FILTER (WHERE r->>'match' IN ('regex', 'present') AND NOT (r ? '_seed')) AS typed_patterns
FROM product_spec_registry, jsonb_array_elements(derivation_rules) r
GROUP BY spec_key ORDER BY spec_key;
```

The S1 conversion migration converts every shipped rule by its identity and every other rule
by its kind. A rule it cannot convert stops the migration and is printed (AC-S1.3). The script
prints any such rule before the migration runs. Output: _to paste_.

## 6. Golden parity (AC-S1.4)

The stored values on the dev copy are the old engine's output, so parity is read-only:
`venv/bin/python -m scripts.product_spec_rule_parity`, run after `alembic upgrade head` and
before any catalogue re-read, derives every active product with the new engine and prints
every derived value that differs from the stored one, with the key, before, after and the
words the new engine read. The expected groups (plan D5):

1. Ways and Spray functions read two-digit numbers (one digit before).
2. Power needs the number to stand on its own.
3. "OVER FLOW" also matches "OVER-FLOW".
4. The flyer's L, W and H rows read the number labelled inside a size.

Anything outside those four groups is a defect to fix before merge. Output: _to paste_.

### 6.1 Measured in the cloud lane: the 2,000-product golden sample

`tests/test_product_spec_rule_engine.py` derives every row of
`tests/fixtures/spec_derivation_golden_sample.json` (2,000 real catalogue products) with the
frozen legacy rules through a frozen copy of the old matcher, and with the new engine, and fails
on any difference outside the groups below. Result after fix round 1:

| Group | Products | Codes | Change |
| --- | ---: | --- | --- |
| Plan D5 group 2, Power needs a standalone number | 6 | SRTBK7004, SRTSA300HP, SRTWC7603HP, SRTWT6900HP, SRTWT9600HP, SRTWT9609HP-RG | a code's digits (7004, 300, 7603, 6900, 9600, 9609) no longer read as horsepower; now nothing |
| Plan D5 group 3, a hyphen, a doubled space or no space between words | 32 | mounting counter top: BRBC22176W-1-ENG, BRBC22207W-1, BRBC22239W-1-ENG, BRBC2244W-8, CWB1086-CB, CWB1096-CB, SRTBRBC2244W-1-ENG, SRTWB1090-BW, SRTWB1096-NEW, SRTWB1278; under counter: AMS-CCASF513-1000410M0, BRBC22353W-ENG; wall hung: BRWTP69182BTC-ENG, CB1108ASS, CB2522SS, CB2532SS, CB2544SS, CB2546SS-BL, CB2550SS-FRG, CB6112SS, MLWT5128, MWB7620-A; floor standing: SRTWT4017, SRTWT51012-GY; bar_count: CB722-GM 2, CB766-GM 2, SRT770-GM 1; control type single lever: GRH-19577001; product type angle valve: GRH-19808001, GRH-29800000, SRTWT916SS-GM-DIY; basin tap: SRTWT5841-BL | nothing before, the value now |
| Lane fix round 1, no hose length on a bathtub or jacuzzi | 3 | BRBTB25505W, BRBTB25505W-5, BRBTB25513W | 1500 before (a tub's length read as a hose), nothing now |
| Plan D5 groups 1 and 4 | 0 | none in the sample | |

Three differences outside the plan's groups were found on the way and fixed in the shipped
rules rather than accepted: a two-decimal hose length on bathtubs (Only when class is not
Bathtub, Jacuzzi, Bathtub and Jacuzzi), "(LENGTH-200MM)" (a new Length rule, number after
LENGTH before MM; BRD314CP-2 200, BRD314CP-4 70, BRD314CP-4-ENG 54, BRD323BTC-ENG 400 still
read), and "6086 BOWL ONLY" (bowl count capped at 9, so it is flagged, not stored).

Save-time cost of the re-read on save, derive loop only over 23,000 in-memory rows: 1.0 s
(Length), 1.3 s (Finish or colour), 1.6 s (Product class), 3.0 s (Type), against 14.2 s for
every key. The paged database read comes on top.

## 7. Fix round 4, the owner's hand test (27 Sep)

Browser pass on the cloud lane's CI database (empty schema plus a seven-product seed, no
prod-copy data), frontend dev server, agent-browser at 1280 and 375. The empty tenant has no
module rows, so the catalogue's modules were installed for the default tenant first; after that
the page was reached by sidebar clicks from `/` (Products, Specifications, Product
Specifications, Finish or colour, How it is read, Edit, Add a rule).

Seed: Finish or colour has two live rules (WHITE to White, SATIN CHROME to Satin chrome);
Chopping board is a yes-or-no spec read from CHOPPING BOARD. Two products carry a stored finish
that today's rules no longer read (M3049-S has nothing stored while WHITE reads White; M4808SS
stores Gunmetal, which no rule reads): the drift that used to show up as "added" and "removed".

The owner's rule: Words BLACK, value Black, Only when Chopping board is Yes.

| Step | Evidence | Seen |
| --- | --- | --- |
| Its values for Chopping board | `evidence/r4-f1-only-when-yes-no-1280.png`, `-375.png` | Yes and No, never "No results found." |
| Its values for a spec with no choices | `evidence/r4-f1-no-choices-yet-1280.png` | "Basin style has no choices yet." |
| The rule in one sentence | `evidence/r4-f3-rule-sentence-1280.png`, `-375.png` | "When the description or flyer contains the word BLACK and Chopping board is Yes, set Finish or colour to Black." |
| See what would change | `evidence/r4-f2-preview-black-only-when-board-1280.png`, `-375.png` | 0 changed, 1 now set, 0 no longer set, 6 unchanged; "2 products have a stored value that differs from today's rules; saving this rule refreshes them too."; one row, SK-BLK-CB, Black sink with board, - to Black. TP-BLK (black, no board), M3049-S and M4808SS are not listed. |

## 8. Fix round 5, the record header card and the Add a rule placement (27 Sep)

Browser pass on the cloud lane's CI database (empty schema; the shipped registry seeded, 49
specifications, plus twelve products read through the real derivation), frontend dev server,
agent-browser at 1280 and 375. The `product` module was installed for the default tenant first;
after that the page was reached by sidebar clicks from `/` (Products, Specifications, Product
Specifications, Finish or colour, How it is read, Add a rule, Cancel, Choices and words, Edit).
Finish or colour carries its 22 shipped rules, as on the owner's screen.

| Step | Evidence | Seen |
| --- | --- | --- |
| Header card, read | `evidence/r5-01-record-header-read-1280.png` | Title "Finish or colour", pill "In use", pager "10 / 49" and Edit on the right; Type List, Choices 10, Products 9, Last read 27/09/2026. |
| Rules grid, read | `evidence/r5-02-rules-toolbar-read-1280.png` | "Add a rule" at the top right, on the toolbar row above Order / Where to look / Kind; the footer reads only "22 rules.". |
| Add a rule from read | `evidence/r5-03-add-rule-from-read-opens-form-1280.png` | The page enters edit mode and "Add a rule to Finish or colour" opens. |
| Rules grid, edit | `evidence/r5-04-rules-toolbar-edit-1280.png` | Header card unchanged beside Cancel and Save; "Add a rule" at the top right; footer "22 rules.". |
| Choices and words, edit | `evidence/r5-05-choices-toolbar-edit-1280.png` | "Add a choice" at the top right, above Choice / Words customers say / Products. |
| Choices and words, read, 375 | `evidence/r5-06-choices-toolbar-read-375.png` | Header card stacks to two columns; "Add a choice" top right. |
| Header and rules, read, 375 | `evidence/r5-07-header-and-rules-read-375.png` | Every header field present; "Add a rule" top right; "22 rules." below. |
| Header and rules, edit, 375 | `evidence/r5-08-header-and-rules-edit-375.png` | Same, with Cancel and Save; page `scrollWidth` 375 at a 375 viewport (no horizontal scroll). |
