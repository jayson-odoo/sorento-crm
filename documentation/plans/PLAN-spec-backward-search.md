# PLAN - spec backward search (shape B: spec FILTER ∩ domain predicate)

**Status:** In progress (S1)
**Branch:** `feat/spec-search-category-signal` (spec-search worktree)
**Contract (authoritative):** `sorento_crm_n8n/n8n-workflows-init/plans/crm-ask-spec-backward-search.md`
(CONVERGED 2026-08-11, two-session grill). This plan is the CRM build mirror; on conflict the
contract doc wins.

## Journey

A customer in WhatsApp describes products by what they are, not by code, then asks a domain
question about the described set:

> "what faucets have certs" · "any promo for wall hung basins" · "which water closets have stock"
> · "send me technical drawings for kitchen sinks"

1. Customer sends the sentence. The n8n parser detects shape B (class noun + has-X predicate) and
   emits a `require` object alongside the normal resolve payload.
2. n8n `resolve-entity` calls `POST /api/v1/system/references/resolve?contact_id=<respond_io_id>&space_id=...`
   with `require` in the body. The CRM computes the FULL company-scoped intersection
   (described set ∩ domain predicate) and returns the top-K qualifying products plus an honest
   count. The customer never sees a false "none" caused by top-K truncation.
3. n8n feeds the returned ids to existing MCP list tools unchanged (ids in, rows out) and renders:
   "40 faucets have certs, here are the 15 closest." Unrecognized words produce a clarify, never
   a silent "none".

The customer holds: an honest, scoped answer with real products. No new MCP tool, no new n8n
domain. Fail-closed scoping confirmed as policy: a contact with zero `respond_contact_companies`
rows gets zero owned rows (user decision 2026-08-11).

## Shape

- **Membership + count = SQL** over `product_specifications` ∩ `require` legs. Never a ranker
  re-walk.
- **Display ranking = the ranker restricted** to the qualifying id-set (`search_specs` gains a
  `product_ids` whitelist). Cheaper than today's full-catalogue walk.
- **v1 filter legs are CLASS-ONLY** (decided). Non-class entries (numeric/op from
  `_resolve_quantities`) are dropped from membership and still passed to stage-2 ranking as
  boosts.
- `qualifying_total` counts **distinct variant families**:
  `count(distinct coalesce(parent.product_code, product_code))`, matching the ranker's display
  collapse.
- Company scope rides the existing `CompanyScopedMixin` + `do_orm_execute` listener. Obligations:
  every leg is ORM-only (raw `text()` bypasses the listener); the certificate leg joins through
  `Certificate` (scoped), never bare `certificate_products` (no mixin).

## Work items

| # | item | where |
|---|------|-------|
| 1 | `filter_specs()` - class-only membership clause, reusing `resolve_terms_to_specs` + `resolve_classes_for_term` | `app/services/product_spec_search.py` (beside the vocabulary) |
| 2 | `product_predicate_service.py` - `REQUIRE_LEGS` registry (4 legs) + `resolve_product_set()` | `app/services/product_predicate_service.py` (new) |
| 3 | `search_specs(product_ids=...)` whitelist param | `app/services/product_spec_search.py` |
| 4 | `require` on `ResolveReferenceRequest` + veneer in resolve POST + `predicate` response block | `app/api/v1/system/references.py` (veneer only, zero SQL) |
| 5 | pytest: per-leg, two-company cross-bleed per leg, variant-family counting, unrecognized terms, byte-identical-without-require | `tests/test_product_predicate_service.py`, `tests/test_resolve_predicate.py` |

## Leg semantics (v1)

| key | payload | predicate (EXISTS on `Product.id`) |
|-----|---------|-------------------------------------|
| `attachment_type` | customer's LABEL (e.g. "technical drawing") | resolve label case-insensitively against `AttachmentType.code` OR `type_name` (mirrors `_probe_attachment_type`); miss feeds `unrecognized_terms` and the require call qualifies nothing; hit: EXISTS `product_attachments` JOIN `attachments` ON `attachment_type_id` = resolved id |
| `certificate` | `true` OR `{scheme, validity_state}` | bare: EXISTS `certificate_products` JOIN `certificates` (status='active'). Object: + `scheme` equality; `validity_state: "valid"` joins the current revision and requires `valid_until IS NULL OR valid_until >= today` (validity is derived, not stored - model docstring) |
| `promotion` | `true` | EXISTS `promotion_products` JOIN `promotions` (is_active AND start_date null-or-past AND end_date null-or-future) |
| `stock` | `true` | EXISTS `stock` with `quantity_on_hand > 0` (NOT the MCP `exclude_zero_system_adjustment` semantics) |

Multiple keys AND. Unknown key = 422 (`AppException`) - a parser emitting an unknown key is a bug
to surface, not to ignore.

## Response

```jsonc
"predicate": {
  "require": { ... },          // echo, attachment_type as-resolved
  "qualifying_total": 40,      // distinct variant families, company-scoped
  "truncated": true,
  "unrecognized_terms": []
}
```

Matches stay ordinary product matches in `resolutions[].matches` (`match_tier: "spec_search"`,
similarity from stage-2). Absent `require` = response byte-identical to today. `require` present
supersedes the `spec_fallback` fallback path (mutually exclusive by construction: predicate path
runs whenever `require` is present).

Input terms: the spec leg consumes `free_terms` (parser-supplied, same as shape A); falls back to
`[query]` when absent. `unrecognized_terms` = free terms resolving to neither a class nor any
registry spec, plus an unresolvable `attachment_type` label.
