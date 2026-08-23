# PLAN - spec search on raw customer text (accurate, honest, renderable)

**Status:** S1-S5 done - awaiting review/PR
**Branch:** `feat/spec-raw-text-search` (new, off main)
**Supersedes / absorbs:** peer asks C-1, C-2, C-3 (n8n session, 2026-08-12/13)
**Related:** `PLAN-spec-backward-search.md` (shape B, shipped in PR #124), the shape-A gate fix (ae3393810)

## Journey

A customer types a sentence in WhatsApp: "sorento double bowl kitchen sink with 1.2mm thickness".

1. n8n forwards the RAW TEXT to `POST /api/v1/system/references/resolve` (`spec_fallback: true`).
   No parser-side spec extraction: the CRM owns reading the sentence, so a qualifier the
   parser never modelled ("thickness 1.0mm") can no longer be silently dropped before it
   reaches us.
2. The CRM answers with, in one response:
   - ranked products that actually answer the description (never SORENTOBAG / "NOT USE
     THIS CODE" as the headline answer),
   - per-row spec VALUES ("this one is 1.2mm, that one 1.0mm") so the reply can show WHY
     each product is offered,
   - honest verdicts: `spec_unmet` (known key, products lack the value: "thickness isn't
     recorded for these"), `unrecognized_terms` (word bound to nothing: "I don't know
     what X means") - two different sentences n8n renders differently,
   - no false "Couldn't find: double bowl kitchen sink" footer when spec rows DID answer
     that description.
3. The customer holds a shortlist with visible reasons, or an honest explanation of what
   could not be honoured. Never junk presented as an answer, never a silent drop.

## Gap analysis (current endpoint vs objective)

| # | gap | evidence |
|---|-----|----------|
| G1 | **The resolve endpoint never feeds raw text to the machinery that already reads it.** The Product Specifications page's search DOES handle a raw sentence (user-verified): `preview_spec_search` calls `understand_phrase(db, phrase, allow_model=...)` - whose word-level mode needs no LLM - then ranks. The resolve endpoint only calls `understand_phrase` behind the opt-in LLM flag and passes `payload.free_terms` straight through, so `query` alone leaves the ranker blind. Fix = mirror the preview's wiring. n8n's parser-built free_terms dropped "thickness 1.0mm" in live turn 12303548. | `product_specifications.py:474` vs `references.py` veneer |
| G2 | **Spec search unreachable on the OR-degraded path.** "sorento double bowl kitchen sink": AND matches nothing, degrades to OR, "Sorento" prefix-matches 4 junk rows, so `_result_has_zero_matches` is false and the descriptive token can NEVER reach the ranker. Live turn 12303509. | gate = zero-matches OR AND-partial-coverage only |
| G7 | **Brand words bind to nothing and headline as code junk.** (User decision: a brand must resolve AS a brand - Sorento / Cabana / Mocha are brands, and SORENTOBAG / SORENTO188 are stale codes.) The registry `brand` row exists with EMPTY synonyms (`{}`), so "sorento" cannot bind as a spec entry; meanwhile the code probes prefix-match it into junk rows. | `product_spec_registry` row `brand` = `{}`; `brands` table has 24 rows to source from |
| G3 | **No `unrecognized_terms` on shape A.** A qualifier that binds to no registry key reads as success. Shape B has the field; shape A does not. | `spec_unmet` covers only keys successfully asked for |
| G4 | **Stale "couldn't find" footer.** `_emit_spec_matches` strips an unresolved token only when it equals the whole query, so a per-token miss survives even after spec rows answered it. | `references.py` `_emit_spec_matches` tail |
| G5 | **No spec values on result rows.** Resolve matches carry `matched_specs` (key NAMES only); `crm_master_products_list` exposes nothing from `product_specifications`. "What thickness is it" is unanswerable from the rows. | `ProductResponse` has no specifications field |
| G6 | **Accuracy is not pinned at the endpoint for raw sentences.** `spec_findability` evaluates ranker angles, but nothing exercises the full raw-text POST path with paraphrases. | findability harness stops at `search_specs` |

Explicitly NOT a gap to fix here: **data coverage**. Measured 2026-08-13: thickness exists on
11% of kitchen sinks and is NOT derivable (137 sink descriptions state it, 138 derived -
extractor exhausted; 0 THK/GAUGE tokens, 0 in names, no column, 0 flyer-sourced).
bowl_count / has_drainer have a ZERO extraction gap. The endpoint's job is to be honest
about absence (`spec_unmet`), not to invent coverage. One small exception rides along:
~30 sinks state material in text without a derived value - deriver gap worth a look, S1
stretch goal only.

## Design decisions

- **D1 - raw text in, CRM derives, by MIRRORING the preview endpoint.** When the spec
  path runs, call `understand_phrase(db, query, allow_model=payload.understand_phrase)`
  unconditionally - its word-level mode (no LLM, fast) already extracts specs +
  free_terms from a raw sentence, which is exactly why the Product Specifications page
  "just works" on the same text. The LLM read stays behind the existing flag. Extract a
  shared helper so preview and resolve cannot drift. Caller-supplied `free_terms` /
  `extracted_specs` keep working unchanged (explicit wins over derived).
- **D7 - brands resolve as brands (user decision).** Two halves: (a) BIND - source the
  registry `brand` synonyms from the `brands` table automatically (24 rows; auto-sync,
  never hand-seeded) so "sorento"/"cabana"/"mocha" become a `brand` spec entry the
  ranker scores against the 99.8%-covered `brand` value; (b) ROUTE - a token that
  case-insensitively equals a known brand name is answered by its brand binding, and its
  code-PREFIX junk (SORENTOBAG, SORENTO188 "NOT USE") is suppressed from headlining.
  Exact full-code matches still win (a real code containing a brand word is still a
  code). Misstated-brand honesty unchanged: a Cabana ask over a Sorento-only shortlist
  reports brand in `spec_unmet`, never silently substitutes.
- **D2 - the gate fires on any unanswered description.** Trigger set becomes: zero
  matches anywhere, OR any resolution with zero matches (`unresolved_tokens` non-empty -
  the OR-shape per-token signal), OR AND-shape partial product coverage (shipped). The
  relevance floor remains the counterweight against nonsense.
- **D3 - one honesty vocabulary across shapes.** Shape A gains `unrecognized_terms`,
  identical name and semantics to shape B (a term binding to neither a class nor any
  registry spec). Distinction preserved: `spec_unmet` = known key, absent value;
  `unrecognized_terms` = unknown word.
- **D4 - spec rows clear the misses they answer.** When spec candidates land, strip every
  unresolved token that case-insensitively matches a free term (or the query when
  free_terms was defaulted). Junk brand-prefix rows stay in their own resolutions,
  distinguishable by `match_tier` - n8n decides their rendering.
- **D5 - rows carry their spec values.** (a) Resolve matches: `display.specifications` =
  compact `{key: value}` (values only, no evidence/provenance blobs - wire-lean).
  (b) `GET /master-data/products` (the `crm_master_products_list` path) gains
  `include_specifications=true|false` (default false, response byte-identical when
  absent): per row `specifications: {values, rendered_text}`. One extra IN-query per
  page. MCP tool description updated. CRM emits everything available; n8n selects what
  to show (container-status pattern).
- **D6 - accuracy is pinned by paraphrase tables at the ENDPOINT, not the service.**
  Per the standing no-overfit rule: test tables are paraphrases, not keyword echoes.
  A pinned pytest table drives `POST /resolve` with raw sentences over a seeded catalog
  and asserts the expected code ranks in the window, plus the honesty fields. The
  live-shaped cases from turns 12303509/12303548 are rows in that table.

## Slices (TDD, in order)

| # | slice | tests that gate it |
|---|-------|--------------------|
| S1 | Raw-text derivation (D1): shared helper mirroring `preview_spec_search`'s wiring; word-level `understand_phrase` always, LLM behind the flag | endpoint paraphrase table v1: "double bowl kitchen sink with thickness 1.2mm" ranks a 1.2mm double-bowl sink first with `matched_specs` including `thickness`; same sentence value-first order; parity test: resolve raw-text answer == preview answer for the same phrase |
| S2 | Gate extension (D2) + footer strip (D4) + brand routing (D7) | 12303509 replica: "sorento double bowl kitchen sink" -> spec rows arrive, miss cleared, NO code-prefix junk headlining for the brand token, brand scored in the ranking; registry brand synonyms auto-synced from `brands`; counterweight: fully-resolved code query stays suppressed, an exact full code containing a brand word still resolves as a code |
| S3 | `unrecognized_terms` on shape A (D3) | "double bowl kitchen sink with flurbish": `unrecognized_terms=["flurbish"]`, `spec_unmet` untouched; "thickness 9.9mm" over thickness-less catalog -> `spec_unmet` names thickness, `unrecognized_terms` empty |
| S4 | Spec values on rows (D5): resolve `display.specifications` + products endpoint param + MCP description | row for the 1.2mm sink carries `{"thickness": 1.2, ...}`; products list with flag on/off byte-comparison; pytest for the new param incl auth + validation |
| S5 | Endpoint-level accuracy eval: extend findability angles through the raw-text POST path; run over kitchen-sink class on the prod-copy DB; record numbers in this plan | eval report: findable-by-sentence rate before/after S1-S2 on the same angle set |
| S6 | Deploy + handoff: merge (single alembic head - no migrations expected), CI green auto-deploys; write the n8n consumption contract (query-only call shape, field semantics, the two honesty sentences) into the ask-doc family | prod smoke: the two live turns re-sent verbatim return correct shapes |

No migrations anticipated (S4 is serializer + query work). No FE work (consumer is n8n).
Worker untouched.

## Acceptance criteria (roll-up)

1. `POST /resolve` with ONLY `{query: <raw sentence>, spec_fallback: true}` returns ranked
   spec candidates for a describable product - no parser-side extraction required.
2. "sorento double bowl kitchen sink" never answers with junk-only: spec rows present,
   descriptive miss cleared, brand rows retain their tier.
3. Every unhonourable qualifier is NAMED in exactly one of `spec_unmet` (known key) or
   `unrecognized_terms` (unknown word). Nothing silently dropped.
4. Rows carry renderable spec values at both the resolve and products-list surfaces;
   both surfaces byte-identical for callers that don't opt in.
5. Paraphrase table green in CI; findability-by-sentence rate reported pre/post.
6. Deployed; both live incident turns replayed against prod return the new shapes.

## Hardening tests (S1-S4, added post-implementation)

`sorento_crm_backend/tests/test_spec_raw_text_hardening.py` - 14 tests over a fresh
blank Postgres schema, no bugs found (every case confirmed intended behaviour):

- `GET /master-data/products?include_specifications=banana` -> 422; the same route with
  no principal -> 401.
- `include_specifications=true` at a page boundary (5 seeded rows, limit=2 page=2):
  every row on the page carries the `specifications` block, and attaching it costs
  exactly one extra query (`before_cursor_execute` statement count on
  `product_specifications`, mirroring the existing pattern in
  `test_product_attachment_certificate_validity.py`).
- `_emit_spec_matches`'s code-exemption boundary: a real seeded code that resolves never
  reaches `unresolved_tokens`; a made-up code with a digit stays; `1.2mm` / `2mm`
  measurement tokens and an `L750`-style label are all cleared once the sentence around
  them is answered - **note:** a made-up code with NO digit at all (e.g. `ZZTKSGHOST`) is
  also read as not-code-shaped and gets cleared, same as a real description word. This is
  the existing heuristic's designed behaviour, not a gap opened by S1-S4. (Since F5 below,
  code-shape is `entity_resolver._CODE_RE` itself with a measurement exemption, so `L750`
  clears as a labelled dimension rather than as a one-letter word.)
- Two `CLASS_SYNONYMS` bilingual words (`sinki`, `tandas`) and a mixed sentence of both
  never reach `unrecognized_words`.
- Both live incident turns, replayed end to end: 12303509 ("sorento double bowl kitchen
  sink") returns junk-free resolutions with `display.specifications` populated and
  `matched_specs ∩ preferred_specs = ∅` on every spec-tier match, plus `spec_asked`
  present; 12303548 ("double bowl kitchen sink with thickness 1.0mm") ranks the 1.0mm
  sink first with `spec_unmet == []` and `unrecognized_terms == []`.

Full new-feature regression (`test_spec_values_on_rows.py`,
`test_resolve_unrecognized_terms.py`, `test_resolve_brand_routing.py`,
`test_resolve_raw_text.py`, `test_resolve_spec_fallback.py`, `test_resolve_predicate.py`,
`test_product_predicate_service.py`, `test_product_spec_search.py`,
`test_product_spec_understanding.py`, `test_product_spec_registry.py`,
`test_spec_findability.py`, `test_spec_raw_text_hardening.py`): **221 passed, 1 skipped,
0 failed.**

## Eval results (S5)

Date: 2026-08-14. Read-only, throwaway script against the prod-copy dev DB (never
committed - `pg_session()`-scoped, rolled back; no writes). Endpoint-equivalent path
exercised directly: `understand_phrase(db, sentence, allow_model=False)` then
`search_specs(db, specs=..., free_terms=..., limit=25)`, the same wiring `POST /resolve`
uses on the raw-text spec-fallback branch.

**Sample.** 1,222 active `Kitchen Sink`-class rows in `product_specifications`; 150
sampled (`random.seed(20260814)`, reproducible). 1-2 paraphrase sentences per product from
6 templates built off the product's own derived values (never an echo of `rendered_text`):
`material_length`, `bowl_thickness`, `brand_bowl`, `dims_material`, `drainer_material`,
and a `brand_class` fallback (always available - brand 99.8%-covered, class total
coverage). 208 sentences generated in total. "Findable" = the product's variant FAMILY
(family-collapsed exactly as `search_specs` collapses internally - parent `product_code`
where `variant_of_id` is set, else own code) appears anywhere in the top-25 candidates.

**Findability.**

| metric | value |
|---|---|
| overall | 70 / 208 = **33.7%** |
| mean rank of hits | 8.19 |

Per template:

| template | n | rate | mean rank of hits |
|---|---|---|---|
| brand_bowl | 12 | 100.0% | 4.58 |
| material_length | 47 | 55.3% | 4.04 |
| brand_class | 101 | 21.8% | 13.18 |
| dims_material | 46 | 21.7% | 12.30 |
| drainer_material | 2 | 0.0% | n/a |

Findability tracks how DISCRIMINATING the sentence's bound specs are, not just how many
words it has:

- `brand_bowl` (bowl_count is rare - 9% catalog coverage - but decisive when stated)
  and `material_length` (material + a `dim_length` bound via the registry's own
  `"long"` self-synonym) both bind real structured specs and rank well.
- `brand_class` and `dims_material` sit near 22% for two different, both pre-existing
  (not S1-S4-introduced) reasons: (a) brand+class alone matches every same-brand row in
  a 1,222-row class, and the tie-break (score DESC, `product_code` ASC) can only ever
  surface the alphabetically-earliest ~25 of a much larger tied set; (b) a compact
  `"780x500mm"` dimension PAIR has no adjacent registry `_self` word (`"length"` /
  `"width"`) for `_resolve_quantities`'s proximity binder (`product_spec_search.py`) to
  bind on, so both numbers land only in the free-text bag and the sentence is scored on
  generic word overlap instead of the actual dimensions. Verified directly: for a
  `dims_material` miss (`SRTKS7850-3`, "kitchen sink 780x500mm stainless steel"), the
  product scores a real positive match (rank 80 of ~2,000 unranked) - it is a ranking
  / vocabulary-binding gap, not a correctness bug, and not something S1-S4 touched
  (`_resolve_quantities` predates this feature). Flagged here as a candidate follow-up
  slice, in the same spirit as the plan's existing thickness-coverage carve-out.
- `drainer_material` (n=2) is too small a sample to read (`has_drainer` measured on 18
  rows catalog-wide) - noted, not weighted into the interpretation above.

**Worst 10 misses** (sentence, seeded values):

1. `SRTKS6054` (dims_material) "kitchen sink 540x440mm stainless steel"
2. `SRTKS6547-BL` (brand_class) "SORENTO kitchen sink" - matte black finish variant
3. `KSBT005` (brand_class) "NO LOGO kitchen sink" - `product_type=bottle_trap`, no other spec
4. `SRTKS7547-NEW` (brand_class) "SORENTO kitchen sink"
5. `KS8041-NL` (material_length) "nanograin kitchen sink 800mm long"
6. `KS8041-NL` (dims_material) "kitchen sink 800x450mm nanograin"
7. `CKS6303-A` (brand_class) "CABANA kitchen sink"
8. `CKS6406-BL` (material_length) "stainless steel kitchen sink 750mm long"
9. `CKS6406-BL` (dims_material) "kitchen sink 750x450mm stainless steel"
10. `SRTKS7850-3` (dims_material) "kitchen sink 780x500mm stainless steel"

**Precision.** `unrecognized_words` run over all 208 generated sentences: **0 flagged.**
Sentences built purely from catalogue vocabulary are never mistaken for gibberish - the
honesty channel (AC-3) holds under a broad paraphrase load, not just the two pinned live
turns.

**Vocabulary-build timing.** 20 timed calls to `unrecognized_words` against the full
prod-copy catalogue: **mean 10.2ms, max 14.5ms** - well under the 150ms budget, so it is
safe to call on every raw-text resolve turn unconditionally.

## Review findings (F1-F10), closed

Code review of 90f922af8..5357442d7 raised ten gaps. All ten are fixed test-first;
`tests/test_spec_review_findings.py` (32 tests) is the pinned behaviour.

| # | gap | fix |
|---|-----|-----|
| F1 | "kitchen sink, not glass" ranked glass first - only the LLM read could hear a refusal | `resolve_terms_to_specs_with_spans` reports WHERE each value was said; `understand_phrase`'s deterministic path moves any binding preceded within 15 chars by a negator (not/no/without/non/bukan/tanpa) into `exclusions`. Spans consumed by a brand phrase are not negators, so "no logo" stays an ask |
| F2 | the footer strip cleared EVERY descriptive token once any spec row landed | a token clears only when all its content words either earned a binding a SHOWN row matched, or appear in a shown row's own text (values + rendered sentence + class). "bathroom mirror" beside sinks now survives |
| F3 | `extracted_specs: [{"value": 1.2}]` -> KeyError -> 500 | key-guarded set comprehension |
| F4 | shape B reported nothing for "sorento grommet": the term bound a brand, so its alien word was never named | `filter_specs` checks every term word-level against the shared vocabulary; an all-alien term is still reported verbatim |
| F5 | `_is_code_shaped` demanded two letters, so "B2155" / "S7850" were never reported as missing codes | reuse `entity_resolver._CODE_RE`, with a measurement exemption (unit-suffixed numerics, and the flyer's `L750` dimension notation) so a measurement is never reported as a missing code. "10KG" reads as a measurement, not a code: a unit-suffixed number is the reading that cannot invent a failure |
| F6 | "quotation for Encik Baharudin" answered with `unrecognized_terms: [quotation, encik, baharudin]` | the field speaks only for a product-descriptive turn (candidates found, or something bound); otherwise `[]`, present and empty |
| F7 | a caller free term that was only PARTLY alien reported nothing | word-level for every caller term; verbatim only when all its content words are alien |
| F8 | a customer naming an excluded-value brand IN FULL was answered with silence | `NO LOGO` binds on a full-phrase word-boundary match; `OTHERS` stays unbindable (one generic word is never an ask) |
| F9 | require-only rows carried no spec block at all | one IN-query over `product_specifications` for the shown ids; `specifications` (values only) or **null** when nothing was recorded, plus `preferred_specs: []`. `_emit_spec_matches` copies `None` faithfully rather than defaulting to `{}` |
| F10 | resolve and preview each carried their own copy of the read-and-merge, and resolve never named the caller | `derive_search_inputs(db, phrase, *, specs, free_terms, allow_model, user_id, registry_rows)` in `product_spec_understanding`, called by both; resolve passes `user_id`. One `active_registry` + one brand read threaded through the spec path per request |

Regression at the time of the fix (the twelve feature files plus the new one):
**253 passed, 1 skipped, 0 failed.**
