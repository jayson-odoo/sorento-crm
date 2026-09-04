# PLAN: Resolver head-code retry (leading-code fallback for product tokens)

Status: Implemented - awaiting review
Branch: fix/resolver-head-code-retry
Origin: cross-repo request from sorento_crm_n8n (decision D-9, escalation-routing plan +
help-lane brand-routing plan sections 2.7/2.8). UAC: `resolver-head-code-retry-acceptance-criteria.md`.

## Problem

WhatsApp users type "code + description" ("SRTWB8004 BASIN TAP"). The n8n parser often emits no
canonical_code, and the n8n caller folds the raw into ONE token ("SRTWB8004BASINTAP") before
calling `POST /api/v1/system/references/resolve`. The folded token exact-misses even though
SRTWB8004 exists (it surfaces only as a 0.47 trgm alternative, below the suggest floor).
Measured: n8n executions 13329480 (live), 13996940 (clone).

An n8n-side regex (pick the leading code-like word) was tried and killed in review with
catalogue data: real product codes contain spaces - `SRTWB7299-WALL HUNG`, `SRT86CR-HEAD ONLY`,
plus 9 more in the -WALL HUNG family - which the regex folds from exact-hit to miss. Only the
product table can distinguish "code + description" from "a spaced code", so the retry belongs
server-side.

## Constraint discovered

n8n strips dashes and whitespace from EVERY entity token before calling resolve (documented in
`entity_resolver._norm_prefix`). The raw pre-fold text is therefore NOT available server-side
today, and re-splitting a folded token is impossible ("SRTWB8004BASINTAP" matches the code-like
regex in full). The n8n request body gains one optional field; the fold itself is unchanged.

## Design (zero-regression by construction)

### API surface

`ResolveReferenceRequest` gains:

```
raw_tokens: list[str] | None
```

Positionally parallel to `tokens`: `raw_tokens[i]` is the pre-fold raw text that produced
`tokens[i]` (e.g. tokens=["SRTWB8004BASINTAP"], raw_tokens=["SRTWB8004 BASIN TAP"]). Ignored
unless `tokens` is provided and both lists have equal length. Absent or null = response
byte-identical to today for every existing caller.

### Retry semantics (service layer, `resolve_references`)

New keyword `raw_tokens: Optional[list[str]] = None`. Pairs are zipped BEFORE the existing
strip/empty-filter/max_candidates cap so alignment survives filtering; result is a
`raw_by_token: dict[token, raw]` map.

Hook point: after Tier 2 (prefix/substring), before cross-type expansion and Tier 3 embedding.
For each token that is still matchless, not ambiguous, and whose allowed types include
`product`:

1. Take `raw = raw_by_token.get(token)`; skip when absent or when raw has no whitespace
   (nothing to split).
2. Extract head sub-token with the parser's own prodTok pattern:
   `^[A-Za-z]{2,}[A-Za-z0-9-]*\d[A-Za-z0-9-]*`. No match (no code-like head, e.g. "MUB" alone
   has no digit) = skip.
3. Head equal to the whole raw (post-strip) = skip - that lookup already ran and missed.
4. Exact-probe the head via the existing `_probe_product` (reuses `_ws_insensitive_lower`
   normalisation, `chat_searchable_products()` gating, placeholder exclusion). Product ONLY -
   no probe of product sets, orders, etc.
5. On exact hit(s): stamp each `ResolvedEntity.match_tier = "head_code"` and assign them to the
   token. `_apply_company_scope` and the route's brand stamp run downstream as usual, so
   `company_id` and `display.brand` arrive on the match like any exact hit.

`to_prompt_block` gains a `head_code` tier note ("matched by leading code; trailing words
ignored") so the LLM caller knows the description part was dropped.

### Why the whole-token lookup still wins

Tier 1 always runs first on the full (folded) token, and both sides are `[-\s]`-stripped, so a
SPACED catalogue code ("SRTWB7299-WALL HUNG" -> srtwb7299wallhung) exact-hits Tier 1 and never
reaches the retry. The retry only fires on tokens that resolve to NOTHING today, so no token
that resolves today can change behaviour.

### Ordering vs the other fallbacks

- BEFORE Tier 3 embedding and before trgm alternatives: an exact code hit beats both.
- BEFORE spec-search (`spec_fallback` / `require`): those run at the route only when the normal
  probes produced no product match; a `head_code` hit IS a product match, so spec-search is
  skipped naturally - no route change needed for the ordering.
- AND-mode (`resolve_references_intersection`) untouched - n8n's resolve-entity calls OR-mode.

### Route plumbing

`ResolveReferenceRequest.raw_tokens` -> `_resolve_input(raw_tokens=...)` -> `_run` ->
`resolve_references(..., raw_tokens=...)`. `_strip_entity_stopwords` cleans tokens in place
(count preserved), so positional alignment holds. Fallback re-runs that pass `tokens_override`
pass no raw_tokens (retry already ran in the primary pass; the fallback pass widens TYPES, and
the token-to-raw pairing no longer aligns positionally there).

### n8n side (their repo, one-line hunk)

Send `raw_tokens` alongside `tokens`, same order and length, each entry the pre-fold raw text
for that token. Nothing else changes.

## Not built (named triggers)

- Cumulative-prefix retry (try "MUB 6201" out of "MUB 6201 BASIN MIXER" word by word): build
  when a measured miss shows a spaced code followed by description text. The single-head regex
  cannot reach those; today's evidence (exec 13329480) is a solid-head code.
- Product-SET head retry (flyer codes like SRTWC8608-RL + description): build when a measured
  flyer-code-plus-description miss appears.

## Tests (Phase 2, test-first, Postgres via tests/_pg_fixture.py)

New file `sorento_crm_backend/tests/test_resolve_head_code_retry.py` - see UAC file for the
case list.
