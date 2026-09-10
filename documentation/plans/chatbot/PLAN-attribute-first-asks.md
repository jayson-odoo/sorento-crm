# PLAN: attribute-first asks, "which products have X", across every product and domain

Status: DRAFT, awaiting grill (10 Sep 2026). Lane `feat/chatbot-attribute-first-asks`.
UAC: `attribute-first-asks-acceptance-criteria.md`.
Supersedes: `documentation/plans/_archive/chatbot/PLAN-spec-backward-search.md` (its backend half
shipped as `product_predicate_service.py`; its n8n contract is obsolete, the Python lane owns
every business decision and n8n only relays the message and posts the reply).
Review surface that produced the decisions: `.lavish/reverse-asking-gap.html` (session ended by
the owner 10 Sep 2026).

## Journey

A contact asks for a SET, not a record: "which tap has cert", "which basin got stock", "any
shower set on promo", "which sink has incoming", "which item has PPS cert", "basin ada gambar".
Today every one of these is read as a record lookup with a missing product and answers "no
certificate matched these" or a product picker. The contact should get the same structured block
they get for one product, for the first five qualifying products, files attached, with a header
that says how many qualify, and "more" to page. A miss goes through today's did-you-mean flow
with the set named. An unknown word clarifies and never says "none".

## Current state, measured (prod copy restored 2026-09-10)

- `resolve_product_set()` in `app/services/product_predicate_service.py` computes described set
  ∩ predicate legs (certificate, stock, attachment_type, promotion) over the full company-scoped
  catalogue with an honest family count. It runs only when the resolve body carries `require`.
- `resolve_entity_body` in `app/services/chatbot/lanes/business/resolve_gate.py` never sends
  `require`. The parser (registry prompt, business_query) has no shape-B key. So HAS is
  unreachable from a turn.
- Direct calls on the copy: tap + certificate 1,256 families; water closet 460; wash basin +
  stock 586; scheme PPS 940; any certificate 2,704; products with open incoming lines 624 (no
  leg exists for it).
- Silent zero: "water tap", "water basin", "bidet" give `clause=None` and
  `unrecognized_terms=[]` from `filter_specs`, so the caller cannot tell "none qualify" from "not
  understood".
- The registry already binds "bidet" as `product_type=bidet`, "sorento" as `brand=SORENTO`,
  "shower set" as `product_type=shower_set` (via `derive_search_inputs`), but `filter_specs`
  membership is class-only by the old plan's decision, so those bindings are dropped.
- LOOKUP already matches "bidet" to 3 products by name (the screenshot picker). Those ids are a
  perfectly good described set and are thrown away today.
- The certificate register covers 3,002 products; the legacy Certification attachment type
  covers 2,928, all of them also in the register (2,894 both, 74 register-only, 0
  attachment-only). Register wins (owner decision D1).
- The register has 11 scheme spellings; WEPLS / WELPS / WELPLS are one scheme spelled three
  ways. No scheme is spelled "watermark".
- Lookup sets (`lookup_sets` / `lookup_options` / `lookup_option_keywords`,
  `LookupResolverService.resolve(set_key, raw)`) exist with 9 sets today and a System page to
  edit them. They are the alias mechanism (owner's suggestion, confirmed a fit: exact value,
  label, then keyword, 404 on miss).
- No "more" paging exists in the lane today. AC-1317 is the only genuinely new mechanic.

## Decisions (owner, 10 Sep 2026)

| # | Decision |
|---|----------|
| D1 | "has cert" = certificate register (`certificate` leg). The Certification attachment type is never the truth source for the predicate. |
| D2 | Dissolved: "bidet" is already an entity; LOOKUP's name matches join the described set. No name-fallback design. |
| D3 | A brand entity scopes the set (Product.brand). |
| D4 | All five predicates (certificate, stock, attachment_type, incoming, promotion) in one lane. |
| D5 | A set answer shows 5 products WITH files; header carries the full count; "more" pages by 5. |
| D6 | Default validity = any active certificate, expired rows flagged per row as today. "watermark" maps to no scheme and clarifies, listing schemes on file. |
| D7 | No parser prompt change, no registry version, no new MCP tool, no new reply format. Predicate derived mechanically from `intent_hint` + entity hints, like `derive_routing()`. |

## Shape

```
message -> parser (unchanged) -> lane derive_require() -> resolve body (+require, +predicate_words)
       -> resolver: exact code resolved?  yes -> LOOKUP, bytes identical to today
                                          no  -> HAS: described set ∩ legs -> ids into resolutions[].matches
       -> existing fetch (TYPE_TO_PARAM product -> product_ids, limit 5) -> existing MCP list tool
       -> existing render + one header line          | zero -> existing miss / DYM with the set named
```

Described set = UNION of (a) product ids LOOKUP matched for the caller's product tokens, and
(b) products whose spec row matches any `class` / `product_type` / `brand` binding derived from
`query` minus `predicate_words`. Then ∩ every leg in `require`. Brand from an entity or a
binding is applied as a filter on the whole set.

## Work items

| # | Item | Where | AC |
|---|------|-------|----|
| A | Honest zero: a free term whose content words are known but bind no class / product_type / brand goes to `unrecognized_terms` | `app/services/product_spec_search.py` `filter_specs` | 1301, 1302 |
| A2 | Question words join `_PHRASE_STOPWORDS` ("which", "what", "who", "where", "when", "how", "many"). Measured: `_PHRASE_STOPWORDS` (line 521) has "any / some / all / has / got" but no question words, so "which basin got stock" reports "which" as unrecognised today | `product_spec_search.py` | 1320 |
| B1 | `derive_require(parser_output)` pure map; reuse `_CERT_RE` from `head/output_exchange.py` | new `app/services/chatbot/lanes/business/predicate.py` | 1303 |
| B2 | `resolve_entity_body` adds `require` + `predicate_words` when B1 returns one; every other key untouched | `lanes/business/resolve_gate.py` | 1304 |
| C1 | `ResolveReferenceRequest` gains `predicate_words: list[str]`; the require branch runs only when NO product resolution carries an `exact` or `head_code` match (a full code typed; `exact` is the probe's default tier at `entity_resolver.py:506`, `head_code` the code-head retry). Grill finding 10 Sep: `_every_caller_token_resolved` is the WRONG gate, it is True for "bidet" (3 substring matches) and would skip HAS. Otherwise fall through to today's code path unchanged | `app/api/v1/system/references.py` resolve POST | 1305 |
| C4 | Gate bypass: when the resolver result carries `predicate` with `qualifying_total > 0`, `gate.py` skips BOTH the `REQUIRE_SPECIFIC_DOMAINS` ambiguity block (product_attachment, incoming) and the product_attachment "subject product did not resolve; refusing to scope on carried entities" block (gate.py about line 342, which fires when a product raw such as "water tap" is unresolved), and passes every qualifying match on as entities. Grill finding 10 Sep: without this the HAS ids (ambiguous=True, spec_search tier) fall into the "needs to be more specific" picker, which is the screenshot B defect in a new coat | `lanes/business/gate.py` | 1326 |
| C2 | Described-set inputs: collect LOOKUP product ids from `result["resolutions"]`; strip `predicate_words` from `query`; call `derive_search_inputs` for bindings; pass `product_ids`, `specs`, brand to the service | `references.py` (veneer, zero SQL) | 1306, 1309 |
| C3 | `filter_specs` membership accepts `product_type` and `brand` entries; `resolve_product_set` accepts `product_ids` and `brand`; union-then-intersect semantics; count still by variant family | `product_spec_search.py`, `product_predicate_service.py` | 1307, 1308, 1310 |
| D1 | `incoming` leg (ORM, joined through `inbound_shipments` for scope) + `REQUIRE_LEGS` entry | `product_predicate_service.py` | 1311 |
| D2 | `_leg_attachment_type`: exact match, then `LookupResolverService.resolve("attachment_type_alias", label)`; `_leg_certificate`: scheme through `certificate_scheme` set; unknown scheme returns `schemes_on_file` in the echo | `product_predicate_service.py` | 1312, 1313 |
| D3 | Migration creates the two lookup SETS only (`certificate_scheme`, `attachment_type_alias`, company-shared, no options). The owner enters options and keywords on System > Lookup Sets (owner decision 10 Sep: "don't need to seed for scheme, I will enter"). A leg whose set has no matching option treats the word as unrecognised; a missing set is the same, never a 500. Register spelling clean-up (WEPLS / WELPS / WELPLS) is register data, not this lane | `alembic/versions/5xx_attribute_first_lookup_sets.py` | 1314 |
| E1 | Fetch: HAS turn sets `limit=5` and passes `product_ids` through the existing `TYPE_TO_PARAM` path; no tool change | `lanes/business/fetch.py` | 1315 |
| E2 | Header line from `predicate.qualifying_total` prepended to the existing render; set noun from the class label or the product tokens, predicate noun per leg | `lanes/business/answer.py` (one helper) + `tail/compile_state.py` header | 1316, 1318 |
| E3 | "more": carry `{qualifying_ids, offset, require, header}` through the existing offer-carry state; a "more" reply re-fetches the next 5 by id, no re-resolve | `tail/compile_state.py` `_offer_carry`, `lanes/business/answer.py` | 1317 |
| F1 | Zero + empty unrecognised → existing `DOMAIN_PROBE` miss flow; "Couldn't find" sentence names set + predicate + the checked codes when the set came from LOOKUP ids (5 max) | `lanes/business/miss_suggest.py`, `answer.py` not_found copy | 1319 |
| F2 | Zero + unrecognised term → clarify with nearest class / product_type names (existing vocabulary nearest-match, no new matcher) | `answer.py` | 1320 |
| F3 | Scheme miss copy names `schemes_on_file` | `answer.py` | 1321 |
| G | Invariant tests: byte-identical body without a leg intent; byte-identical resolver response with an exact code; field-reveal unchanged | `tests/test_resolve_predicate.py`, `tests/chatbot/`, new `tests/test_chatbot_lane_require.py` | 1322 to 1324 |
| H | Console verification on the prod copy, nine utterances, traces recorded in the test report | `attribute-first-asks-test-report.md` | 1325 |

## Leg semantics

| key | payload | predicate (EXISTS on Product.id) |
|-----|---------|----------------------------------|
| `certificate` | `true` or `{scheme}` | `certificate_products` JOIN `certificates` (scoped, status active); scheme through `certificate_scheme` lookup set then equality on the normalised value; validity NOT filtered by default (D6) |
| `stock` | `true` | `stock.quantity_on_hand > 0` (unchanged) |
| `attachment_type` | customer label | exact code / type_name, else `attachment_type_alias` set; EXISTS `product_attachments` JOIN `attachments` on the resolved type |
| `promotion` | `true` | active promotion inside its window (unchanged) |
| `incoming` | `true` | `inbound_shipment_lines` L JOIN `inbound_shipments` S (scoped): shipped minus received > 0 AND S.actual_arrival_date IS NULL |

Multiple keys AND. Unknown key stays a 422.

## Phases (PRINCIPLES.md order)

- Phase 1 (frontend-first mock): none. No UI surface changes; the reply is the existing WhatsApp
  block. The lavish page stands as the journey artefact.
- Phase 2 (test-first): `tester` writes red pytest for AC-1301 to 1324 in the files named above,
  then `coder` (one instance, whole lane) makes them green in the order A, B, C, D, E, F.
  Migration D3 re-parented on main's head at PR time (`scripts/alembic-reparent.sh`).
- Phase 3: `reviewer` + `security-reviewer` (company scope on every leg, the lookup-set read
  path, no raw SQL) + console verification (AC-1325) in parallel; `guide-writer` adds "ask for a
  set" examples to the chatbot user guide; DoD gate; one PR.

## Risks and open questions

- Predicate-word subtraction relies on the parser tagging the predicate word as an
  attachment_type entity (cert, photo) or the intent carrying it (stock, incoming, promo). A
  turn where the parser tags nothing and the intent is null gets no `require` and behaves as
  today, which is the safe failure.
- `derive_search_inputs` on a whole sentence returns the sentence as one free term. "any",
  "got", "has" are already stopwords; question words are not (A2 closes that). Predicate
  words (cert, stock, photo, incoming, promo and their Malay / Chinese forms the parser
  tagged) are removed by C2 from `predicate_words`, never by a hard-coded list in the
  resolver.
- "more" carry: the qualifying id list can be 2,704 long. Carry the ids, not the query, capped
  at 200 with the true count in the header; beyond 200 the "more" says to narrow.
- Scheme options are owner-entered data, so on a fresh install "PPS" resolves only once the
  owner has typed it into the set. Until then every scheme word clarifies and lists
  `schemes_on_file` from the register, which is still a correct answer.
- The parser version label in the console reads v6 while the lane plan for broaden-domain
  names v7; irrelevant here since the prompt is untouched, noted so nobody "fixes" it in this
  lane.
- 220 cert-covered products have no spec row; they are reachable only through LOOKUP ids or a
  bare "anything with cert". Out of scope; belongs to spec derivation coverage.

## Definition of done

Every AC in the UAC passes with evidence in `attribute-first-asks-test-report.md`; AC-1325 traces
recorded; PR carries the console screenshots for the two original utterances; plan Status set
to implemented and the triple moved to `documentation/plans/_archive/chatbot/`.
