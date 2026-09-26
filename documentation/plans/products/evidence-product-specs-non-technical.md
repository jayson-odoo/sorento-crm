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

What the cloud lane could measure: the parity test in `tests/test_product_spec_rule_engine.py`
runs every real catalogue phrase the existing golden and derivation suites carry through both
the old matcher and the new one. Its result is in the PR body.
