# UAC - Attribute-first asks ("which products have X")

Plan: `PLAN-attribute-first-asks.md`. Numbering: AC-13xx. Each criterion names its evidence
(pytest / console turn on the restored prod copy). "Contact" = a Respond.io contact through
`/api/v1/external/chat/turn`. "Prod copy" = local `sorento_ai_automation` restored from the
2026-09-10 dump (outbound credentials scrubbed). Numbers quoted below were measured on it and
are the acceptance values unless the copy is refreshed, in which case re-measure and update here.

Decisions this UAC encodes (taken by the owner on the lavish review, 10 Sep 2026): "has cert"
means the certificate register; brand scopes the set; all five predicates in one lane; a set
answer shows 5 products WITH their files and a header carrying the full count, "more" pages on;
default validity is any active certificate with expired rows flagged as the render does today;
"watermark" is not mapped to a scheme and must clarify. No parser prompt change. No new MCP
tool. No new reply format.

## A. Honest zero in the described set [BE]

- AC-1301 `filter_specs(free_terms=["water tap"])` returns `clause=None` AND
  `unrecognized_terms=["water tap"]`. Today it returns `clause=None` with an empty list. Same
  for "water basin" and any term whose content words are all in the vocabulary but none names a
  class, a product_type or a brand. Evidence: pytest `tests/test_product_spec_search.py`.
- AC-1302 `resolve_product_set(require={"certificate": True}, free_terms=["water tap"])`
  returns `qualifying_total=0` and `unrecognized_terms=["water tap"]`, never a silent zero.
  Evidence: pytest `tests/test_product_predicate_service.py`.

## B. Predicate derived from what the parser already emits [BE]

- AC-1303 A pure function `derive_require(parser_output) -> dict | None` in the lane maps, with
  no message-text matching beyond the existing `_CERT_RE` on the attachment_type entity raw:
  `check_stock` → `{"stock": true}`; `check_incoming` → `{"incoming": true}`;
  `check_promotion` → `{"promotion": true}`; `check_product_attachment` with an
  `attachment_type` entity whose raw matches `_CERT_RE` → `{"certificate": true}` when the raw
  is only the cert word ("cert", "certificate", "sijil"), else `{"certificate": {"scheme":
  <raw minus the cert word>}}` ("pps cert" → scheme "pps", "watermark certificate" → scheme
  "watermark"); the function stays pure, the resolver normalises the scheme word through the
  `certificate_scheme` lookup set (AC-1313); `check_product_attachment` with any other
  attachment_type raw → `{"attachment_type": <raw>}`; every other intent → `None`.
  Evidence: pytest, one case per row, `tests/test_chatbot_lane_require.py` (new).
- AC-1304 `resolve_entity_body` includes `require` exactly when `derive_require` is not None,
  and includes `predicate_words`: the raw of every attachment_type entity plus the intent's
  own word, so the resolver can subtract them from the described set. Every other key of the
  body is byte-identical to today (existing body snapshot tests stay green). Evidence: pytest
  on the body builder, before/after dict diff.

## C. The resolver runs HAS only when LOOKUP found no exact code [BE]

- AC-1305 With `require` present and a CODE-SHAPED product token that resolved to any product
  match (the customer typed a code or a code prefix such as "srtwc286"), the response is byte-identical to the same
  request without `require`. With only WORD tokens ("bidet" → 3 name matches, "sorento" → an exact
  brand-name hit, "tap" as a `category` entity) HAS runs whatever tier they resolved at. Evidence: pytest `tests/test_resolve_predicate.py`,
  deep-equal on the head_code case, predicate block present on the substring case.
- AC-1306 With `require` present and no exact code, the resolver builds the described set from
  the union of: product ids LOOKUP matched by name or code prefix for the caller's product
  tokens; `class` bindings; `product_type` bindings; `brand` bindings derived from `query` by
  `derive_search_inputs` after removing `predicate_words`. "which sorento bidet has cert" yields
  a set of exactly the 3 BIDET products scoped to brand Sorento. Evidence: pytest on the prod
  copy seed shape (3 products named BIDET, one with brand Sorento).
- AC-1307 `filter_specs` membership accepts `product_type` and `brand` entries beside `class`
  (today class only). `resolve_product_set(require={"promotion": True},
  specs=[{"key":"product_type","value":"shower_set"}])` counts only shower sets. Evidence:
  pytest.
- AC-1308 `resolve_product_set` accepts `product_ids` (the LOOKUP matches) and intersects them
  with the legs; when both `product_ids` and class/type/brand bindings are present the set is
  the UNION of the two descriptions, then intersected with the legs. Evidence: pytest, three
  cases (ids only, bindings only, both).
- AC-1309 Qualifying ids land in `resolutions[].matches` with `entity_type="product"` and
  `match_tier="spec_search"`, plus `result["predicate"]` = `{require, qualifying_total,
  truncated, unrecognized_terms}`. Evidence: pytest asserting the shape the fetch step reads.
- AC-1310 Company scope holds per leg, INSIDE the leg: with the product in the caller's company
  and the child row (stock, attachment link, shipment line, promotion link) in company B, the
  product does not qualify; with the child in the caller's company on a company-B product, it does
  not qualify either. Evidence: pytest, both directions for every leg including `incoming`; a leg
  rewritten as unscoped SQL must turn these red (reviewer kill test).
- AC-1337 `is_more_reply` accepts only the fixed paging phrases (more, next, lagi, more please,
  show more, next 5, next five, lagi 5, "more <number>"); "no more" and "next week?" are not pages.
  `set_noun_for` pluralises "Bathroom Accessory" as "bathroom accessories" and the header's
  singular is the class label itself. `answer.SET_PAGE_ID_CAP` and the resolver's copy are pinned
  equal by a test, as are the two cert regexes. Evidence: pytest.

## D. Legs and aliases [BE]

- AC-1311 New `incoming` leg: EXISTS `inbound_shipment_lines` L JOIN `inbound_shipments` S
  (scoped) WHERE L.product_id = P.id AND COALESCE(L.quantity_shipped,0) minus
  COALESCE(L.quantity_received,0) > 0 AND S.actual_arrival_date IS NULL. ORM only. On the prod
  copy `require={"incoming": true}` with no terms counts 624 distinct products (853 lines).
  Evidence: pytest with a seeded shipment (one open line, one fully received line, one arrived
  shipment) asserting exactly one product qualifies.
- AC-1312 `attachment_type` label resolution tries, in order: exact code or type_name (today),
  then the `attachment_type_alias` lookup set through `LookupResolverService.resolve`. "photo",
  "picture", "gambar" resolve to Product Photos; an unknown word still feeds
  `unrecognized_terms`. Evidence: pytest with the set seeded in the test, since CI has no data.
- AC-1313 `certificate.scheme` is normalised through the `certificate_scheme` lookup set before
  equality: "pps", "PPS", "span" resolve; "watermark" does NOT resolve (no option carries it)
  and the leg returns `qualifying_total=0` with `unrecognized_terms=["watermark"]` and
  `predicate.schemes_on_file` listing the register's distinct active schemes (company-scoped,
  sorted), so the reply can name them; `resolve_product_set` returns the same list as
  `schemes_on_file` on a scheme miss. Evidence: pytest.
- AC-1314 Data: a migration creates the two lookup sets `certificate_scheme` and
  `attachment_type_alias` with NO options (the owner enters options and keywords on System >
  Lookup Sets). With an empty or absent set, a scheme word or alias word is reported in
  `unrecognized_terms` and the request never fails. Evidence: alembic upgrade on an empty
  scratch DB creates the two sets; pytest for the empty-set and missing-set paths.
- AC-1327 (the shipped header for "which sorento bidet has cert" reads "1 tap has certificates.":
  the class label wins over the product_type binding, accepted 11 Sep) When HAS ran, `resolutions` and `intersection` carry no product matches for WORD tokens
  other than the single spec_search resolution; non-product resolutions (attachment_type, brand,
  customer) are untouched. The lane's reply never prints a "Found:" enumeration of the qualifying
  codes; the set header stands in its place. Evidence: pytest on the resolver response shape and a
  lane run with two forward substring product matches on the word token.
- AC-1328 `derive_require` returns `{"certificate": {"scheme": "PPS"}}` for intent
  check_product_attachment with a single attachment_type entity raw "PPS" when `user_goal` or the
  message text matches the certificate regex; `_leg_certificate` matches a scheme word by
  case-insensitive equality against the register's active schemes before consulting the lookup
  set. Evidence: pytest, both halves.
- AC-1329 An unrecognised attachment label clarifies as a DOCUMENT type: "I don't know 'photo' as a
  document type. Types I know: <product-facing AttachmentType names>."; an unrecognised scheme
  uses the AC-1321 sentence; only an unrecognised set word uses the product-type sentence, and its
  fallback list of common product types is never empty. Evidence: pytest, three cases.
- AC-1330 For a word token (not code-shaped) the raw always defines the described set, whatever it
  resolved to: "sink" resolving to customers still scopes to class Kitchen Sink. The code-shaped
  gate of AC-1305 reads both `intersection` (the lane's AND mode) and `resolutions`. `shown` in the
  header counts distinct products. Evidence: pytest on the resolver in AND mode and a stock lane
  run with multi-row products.
- AC-1331 When `predicate.qualifying_total > 0`, an unresolved word token (e.g. the parser's single
  entity "Sorento bidet") is never listed under "Couldn't find"; the set answer renders. Evidence:
  lane run with a real resolver, the folded token resolving to nothing.
- AC-1332 The HAS branch derives bindings deterministically: the model phrase reader is never
  invoked while `require` is present, and predicate_words are stripped word by word ("PPS cert"
  removes both words). Evidence: pytest with the model reader patched to fail if called, plus the
  phrase-stripping case.
- AC-1333 [security] A "more" page carries the contact's recomposed `access_levels` into the tool
  args (never the parser's empty list), and the set_page carry is armed only after a set answer
  actually rendered; a tier-ask turn arms nothing. Evidence: pytest, two-turn promotion set with a
  contact holding one tier, asserting the page turn's `access_levels` equal the fresh turn's; a
  tier-ask turn followed by "more" is not paged.
- AC-1334 [security] The promotion leg respects `access_levels`: a promotion the contact's tier
  cannot see never counts toward `qualifying_total` nor names its product. Evidence: pytest, two
  promotions on two products, one tier-restricted.
- AC-1335 [security] `_common_class_labels` and the nearest-label suggestions are company-scoped:
  a class label that exists only in company B never reaches a company A reply. Evidence: pytest on
  a two-company scratch schema.
- AC-1336 The set_page carry clears on any business answer that is not a page; a fresh set answer
  re-arms it. Evidence: pytest, three turns.
- AC-1338 A bare `{"certificate": true}` require whose remainder holds a word equal
  (case-insensitive) to a register scheme spelling or a `certificate_scheme` lookup keyword is
  promoted to `{"certificate": {"scheme": <register spelling>}}`, the word never reaches
  `unrecognized_terms`, and the header names the scheme ("N products have PPS certificates.").
  Evidence: pytest on the resolver with query "which item has PPS cert", predicate_words
  ["certificate"], a register cert with scheme "PPS"; a remainder word that is neither stays a set
  word (regression on AC-1320).
- AC-1339 `filter_specs` class membership includes rows whose class provenance is `category`: a
  product filed under Bathroom Accessory by its category is a member of the described set for
  "bathroom accessory". Evidence: pytest, one product with a category-sourced class row and one
  with a derived one, both members; console "which bathroom accessory has stock" answers a count
  and five products.
- AC-1340 The zero-qualifying miss copy never reads "a a match": the subject is brand + product +
  category / product_type raws, then the predicate's class labels, else the sentence is "Couldn't
  find any product with <predicate>." Evidence: pytest on the rendered text for a category-only
  entity turn.
- AC-1341 [security] The certificate leg is company-scoped in both directions: a certificate
  stamped to company B and linked to company A's product does not count under A's scope, and a
  certificate with NULL company (shared) still counts. Evidence: pytest, both directions plus the
  shared arm, mirroring the four REV-B1 tests.
- AC-1342 [security] `_access_level_codes` accepts a `contact_access_types.code` and a bare tier
  token: `["dealer"]` selects every code that is `dealer` or ends with `_dealer`; a name still
  translates as before; an unknown value still yields the empty set. Evidence: pytest on the
  helper and on `resolve_product_set` with a tier-restricted promotion and `access_levels=["dealer"]`.
- AC-1343 The set_page carry survives only a page continuation: a same-domain non-page answer and
  a same-domain zero-qualifying clarify both clear it, so a bare "more" afterwards is NOT routed
  as a set page (`is_set_page_more_reply` is false and the turn takes the ordinary low-signal
  route, exactly as a "more" with no prior set does today); a rendered set answer re-arms it.
  Evidence: pytest, two three-turn sequences in the same domain, with the low_signal lane
  registered in the harness so turn 3 completes.
- AC-1344 No em-dash or en-dash in any file the lane adds or touches. Evidence:
  `scripts/git-hooks/pre-push` dash guard green on the lane's added lines.
- AC-1345 `derive_require` treats every inflection of the cert word as the bare leg: an
  attachment_type raw of "Certification", "certificates", "certs" or "certifications" (any case)
  yields `{"certificate": true}`, never a scheme; "PPS certification" still yields scheme "PPS".
  Evidence: pytest parametrize on `derive_require`.
- AC-1346 The stock leg counts only stock in active warehouses: a product whose only on-hand row
  is in a warehouse with `is_active = false` does not qualify; the same row in an active warehouse
  does. Evidence: pytest on `resolve_product_set` with two warehouses; console "which bathroom
  accessory has stock" shows five products for five ids.
- AC-1347 The paging words (more, next, lagi, please, show) are phrase stopwords: a HAS turn whose
  remainder is only such words scopes nothing and never reports them as unrecognized. Evidence:
  pytest on `filter_specs` with free term "more"; console "which tap has cert" -> "which water tap
  has cert" -> "more" answers a set header, not "I don't know 'more'".
- AC-1326 A resolver result carrying a `predicate` block (any `qualifying_total`, zero included)
  never enters the gate's `REQUIRE_SPECIFIC_DOMAINS` ambiguity block nor the product_attachment "subject
  product did not resolve" block: the qualifying matches pass on as entities, `gate_passed`
  is True and no "needs to be more specific" picker is built; with `qualifying_total` 0 the
  turn proceeds to the miss flow of AC-1319, never to the picker. Evidence: pytest on the gate
  with a 3-match predicate result (product raw "water tap" unresolved) asserting
  `require_specific` False, `gate_passed` True, three entities reach the fetch; the AC-1319 lane
  test covers the zero case.

## E. Reply shape: existing fetch, existing render, one header line [BE]

- AC-1315 A HAS turn feeds the qualifying ids to the SAME domain tool the forward turn uses
  (`crm_master_product_attachments_list` for cert and photo, `crm_inventory_stock_balance_list`
  for stock, `crm_incoming_stock_list` for incoming, `crm_marketing_promotion_products_list`
  for promotion) through the existing `TYPE_TO_PARAM` product → `product_ids` path. No new tool
  name appears in any trace. Evidence: pytest asserting the picked tool name per predicate.
- AC-1316 A HAS turn fetches the first 5 qualifying PRODUCTS (all their rows or files; the tool's
  row limit stays at its default); the render is the existing block (for
  cert: Product Code / Attachment Type / File Name / Certificate Number / Valid Until / Validity,
  files attached) preceded by one header line "<qualifying_total> <set noun> have <predicate
  noun>. Showing <n>." e.g. "1,256 taps have certificates. Showing 5." When
  `qualifying_total` is 5 or fewer the header omits "Showing". Evidence: pytest on the rendered
  text; console turn "which tap has cert" on the prod copy.
- AC-1317 Replying "more" to a HAS answer returns the next 5 of the same qualifying set with
  the same header and "Showing 6 to 10"; a "more" past the end says "That was all
  <qualifying_total>." Evidence: pytest on two consecutive turns through the existing
  offer-carry state; console turn.
- AC-1318 Validity: "has cert" counts any active register certificate; expired rows keep the
  existing "Validity: Expired" flag in the block. Evidence: pytest on a product whose only
  certificate is expired (counted, flagged).

## F. Miss: the existing did-you-mean flow, with the set named [BE]

- AC-1319 `qualifying_total=0` with an empty `unrecognized_terms` enters the existing miss flow
  (`DOMAIN_PROBE` for the domain) and the "Couldn't find" sentence names the described set and
  predicate: "Couldn't find a Sorento bidet with a certificate (checked ACC- BIDET, CABANA
  BIDET, SRT-BIDET)." followed by today's did-you-mean list and escalate offer. Evidence:
  pytest on the rendered text; console turn "which sorento bidet has cert".
- AC-1320 `qualifying_total=0` with a non-empty `unrecognized_terms` clarifies the term and
  never says "none": "I don't know 'water tap' as a product type. Did you mean tap, basin
  tap, shower tap?" where the suggestions come from the existing class / product_type
  vocabulary nearest-match. Evidence: pytest; console turn "which water tap has cert".
- AC-1321 A scheme miss names the schemes: "The register has no watermark certificates.
  Schemes on file: SPAN, PPS, WCM, IKRAM ..." Evidence: pytest.

## G. Invariants [BE]

- AC-1322 Every existing lane test, world replay and resolver snapshot stays green: a turn whose
  intent has no leg, or whose token resolved to an exact code, produces the same bytes as
  before this lane. Evidence: full `pytest` on the lane and resolver test files, before/after.
- AC-1323 Field-reveal gating is unchanged: a dealer without `inventory.sellable` sees the same
  stock block on a HAS turn as on a forward turn. Evidence: pytest, two contacts, same seed.
- AC-1324 Nothing in this lane changes the parser prompt file, the prompt registry, the MCP
  catalogue or `n8n-changes.md`. Evidence: `git diff --stat` on the PR shows no change under
  `chatbot_parser_prompt.py`, `ai_prompt_registry.py`, `sorento_crm_mcp/`.

## H. Verification on the prod copy [E2E]

- AC-1325 Console turns, each recorded in the test report with the trace: "which water tap has
  cert" (clarify), "which tap has cert" (1,256, 5 shown with files), "which sorento bidet has
  cert" (miss with the 3 named), "which basin got stock" (586), "which item has PPS cert"
  (940), "which basin has photo" (alias hit), "which sink has incoming" (count from the new
  leg), "any shower set on promo" (product_type binding), "more" after the tap answer (6 to
  10). Evidence: `documentation/agents/chatbot-verification.md` procedure.
