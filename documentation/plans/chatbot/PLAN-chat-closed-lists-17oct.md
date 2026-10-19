# PLAN: CHAT-CLOSED-LISTS - chatbot step 2, closed candidate lists

Status: Build, round 7 (H1 hidden keys at the entries, then F3-c, F3-a, F3-b, F3-d per crew rulings a29310107 + a29691875); round 6 pushed at 18e9760e7d (reviewer READY, security PASS). Track: full (size L, LEAD pattern).
Branch `claude/chat-closed-lists-x6ymb5` (the sandbox cannot push `crew/chat-closed-lists`), PR #1755.

Design source: CHATBOT-SCALE-DESIGN-16oct section 8 step 2 + D2 (crew-only): code only SHORTLISTS
candidates (exact code, name and spec search, near spellings); the parser CHOOSES from them or says
"none", and then we ask. Code never decides meaning. Card: `chat-closed-lists-behaviour-card.md`.

## Owner CP0 notes this lane answers

| card | owner note | root cause (discovery below) |
|---|---|---|
| c04 / c19 | "do we need to pass certification type as index like spec or attachment type" | cert kinds and schemes never reach the parser as a list; regexes read them (F3) |
| c06 | "Why we cant identify WC ya" (asked "WC (product) or WC (attachment type)?") | resolver probes every token as every kind and the kind pick reads hit counts, not the parser's kind (F4) |
| c07 / c27 | "This should be spec, why we cant find" / "We should have understood this better" | free words matched exactly downstream; re-grounding rules read the message (F1, F5) |

## Discovery (file:line, `sorento_crm_backend/app/` unless stated)

**F1 Spec vocabulary is already closed, and unbounded.** `{{specs}}` (`services/chatbot_prompt_vars.py:368-372`)
renders `chatbot_parser_prompt.specification_lines` (`services/chatbot_parser_prompt.py:1268-1328`): one line per
active registry key (skips class, brand, product_type, :1265), every choice with its synonyms, no cap (50 seed keys,
`product_spec_registry.py:472-1260`). Grounding then re-checks the parser's choice: `_bound` (`chatbot/head/grounding.py:598`,
exact key, exact phrase or lower/`_`->space value), `_validate` (:637), `_as_typed` (:655), `ground_words` (:293,
re-reads the MESSAGE for registry phrases, numbers beside key words, unknown words beside key names), the class split
(:812-865). A value off the registry becomes `spec_value=None` + `spec_known` (:650) or unknown `Grounded("", "", raw)`
(:792), sent on as `unknown_values` (`chatbot/lanes/business/resolve_gate.py:752-763`) and said back by
`answer.unknown_values_sentence` (`chatbot/lanes/business/answer.py:3065`).

**F2 Attachment types are not a closed list.** No synonyms column (`models/resources.py:40-112`; `description` is used
as one). The prompt teaches a fixed taxonomy in code (photo, video, technical drawing, 3D model, certificate:
`chatbot_parser_prompt.py:684` rows, `SPECIFICATION_ADDENDUM` :525-537). Code then maps words to rows through
`grounding.PROMPT_DOCUMENT_KINDS` (:234), `DOCUMENT_TYPE_CODES` (:417), `_listed_document_type` (:422, drop at :866-873),
the resolver's exact + prefix/substring/ILIKE-on-description probes (`services/entity_resolver.py:1984, 2665`), the
predicate's code/alias/description chain (`services/product_predicate_service.py:127, 113, 140, 238`), the reference API's
catalog/catalogue swap (`api/v1/system/references.py:84, 96-99`), then `turn_runtime.answer_parse_output` renames the
entity to the row (`services/turn_runtime.py:5036`). There is no `attachment_types` row in the parser input.

**F3 Certification types.** No table of their own: a cert kind is an `attachment_types` row with `is_certificate`
(`models/resources.py:75`). Register: `certificates` (`models/certificate.py:58`, free `scheme` String(60), body,
number), `certificate_revisions` (:193), `certificate_products` (:279). Scheme vocabulary = active
`Certificate.scheme` values (`product_predicate_service.py:278 _schemes_on_file`) + lookup set `certificate_scheme`
(migration 511 :39). The chatbot reads cert words by regex: `lanes/business/predicate.py` `_CERT_RE` :20,
`_CERTIFICATE_RE` :21, `_BARE_CERT_WORDS` :44, `_BARE_CERT_WORD_RE` :57, `_CERT_PROPERTY_WORDS` :65,
`_LEG_BY_ATTRIBUTE_WORD` :115, `_cert_scheme_from_raw` :74, `derive_require` :210; `recover_certificate_scheme`
(`product_predicate_service.py:287`); a copy of the regex at `api/v1/system/references.py:1761`.

**F4 The cross-domain menu.** `turn/reconcile.py:82 apply_reconciliation` builds "`<raw> (<kind>)`" options whenever
the resolver hits one token under two kinds (:126-148); armed as a `kind_pick` at `turn/apply.py:1804-1824`. The resolver
probes every token as every allowed kind (`resolve_gate.py:582 _allowed_entity_types`, `fallback_to_all_types` :705),
and the hint lock (`resolve_gate.py:533 HINT_LOCKED_KINDS`) strips only `_NAME_MATCHED_KINDS`
(`references.py:1943-1945`), which lacks `attachment_type`; an unconfident hint is not locked at all (:552).

**F5 Rewrites and word rules.** 26 functions rewrite or re-read parser output (grounding x14, reconcile, resolve_gate x2,
predicate, find, turn_runtime x5, engine x2); about 61 hardcoded word rules, about 20 on the spec / product /
document path (list in the discovery comment on PR #1755). The ones this lane owns: everything in F2, F3 and the
spec half of F1.

**F6 Prompt as code.** Prompt text = `chatbot_parser_prompt.py` constants + `alembic/data/*.txt` addenda; a version is
published unlabelled (`scripts/publish_parser_prompt.py`, `chatbot_prompt_vars.publish_wording_edit` :748); labels are
only `production` / `staging` (`services/ai_prompt_service.py:23`); a run pins a version with the dry-run-only
`prompt_overrides` envelope key (`chatbot/engine.py:1304-1326`). CHAT-STATE (#1747) gates its path on the raw template
carrying its section, so production never opts in; this lane uses the same gate idea with its own marker.

**F7 Bench.** `scripts/chatbot_eval/replay.py` (`run --stage grounding` / whole turn, `diff --intended`); no trace fixtures
are committed, so the lane's L1 evidence is the CI-safe synthetic replay tests plus crew's `replay-gate.sh` run on the
lane head (crew runs it; the lane posts the intended-diff file).

## Shape (card answered 17 Oct)

1. **Lists the parser picks from**, rendered by code from the tables, never written by hand:
   - `{{attachment_types}}`: one line per product-facing `attachment_types` row: code, name, description words.
   - `{{certification_types}}`: the cert kinds (`is_certificate` rows) and the schemes on file (+ the lookup set).
   - Specs: `{{specs}}` stays the full closed list (system prompt, cached). New: a per-turn **candidate block** in the
     user block, bounded (at most 5 candidates per token, 25 lines per turn), built before the parse from the message's
     tokens: exact / prefix code hits, product-name hits, spec-value and synonym hits, and near spellings
     (crew Q1 (a): similarity only adds a candidate). Each line says what the candidate is (code, class, spec value, file type), so the parser picks
     the kind too.
2. **Parser picks or says none.** Entity `canonical_code` is a listed value; `attachment_type` and a new
   `certification` hint carry the listed code; nothing listed = `canonical_code` null, and the bot asks (card R3).
3. **Code validates, never interprets.** A pick is accepted only when it is on the list the turn rendered (exact
   string); otherwise it is dropped and asked. A confident pick of a kind locks that kind: no kind menu (card R4).
4. **Then delete** the F2 / F3 / spec F1 rewrites and word rules one by one, each its own commit with the L1 replay diff.

Gate: the new path runs only when the rendered template carries the `CLOSED LISTS` section marker (same pattern as
CHAT-STATE), so the production prompt is untouched until the owner moves the label. Deletions that change behaviour
under the production prompt are held until the owner moves it (each listed in the PR).

## Slices (red first; each a commit; tests run locally on the sandbox DB)

| # | Content | Red tests first |
|---|---|---|
| S1 | `{{attachment_types}}` and `{{certification_types}}` registry variables | render shape, cap, product-facing filter, scheme union, cache invalidation tables |
| S2 | Candidate block builder (`head/candidates.py`), bounded, session-held phase only | per-token caps, kinds labelled, cost (one query per kind), empty message adds nothing |
| S3 | Prompt section `CLOSED_LISTS_SECTION` + gate + publish script (unlabelled) | gate off = parser input byte-identical to main; gate on = section + block present |
| S4 | Validation: pick must be on the rendered list; kind lock; "none" -> ask | c06 shape (WC as class, no menu), unlisted pick dropped + asked, cert pick -> cert leg |
| S5.. | Delete rewrites / word rules one per commit | L1 replay diff per commit, intended list in PR |
| S6 | TRAIN measurement (live, per-PR budget) | CP2 bars reported with CI over 3 reps |

## Rules carried from the brief

No word rules, no code fuzzy matching (owner): near spellings only ever ADD a candidate to the list, the parser
decides. Never move the production label; no prod access; held-out never to this lane. Coordinate with CHAT-STATE
(#1747): new code in new files (`head/candidates.py`, `head/closed_lists_prompt.py`), the schema change limited to
one entity hint value and no new top-level key.

## Progress (17 Oct)

| Slice | Red | Green | Notes |
|---|---|---|---|
| S1 lists as registry variables | 30ab1b98 | 4e53135c | words = description parts + `attachment_type_alias` set (3c86043c) |
| S2 candidate shortlist | 63cb35d1 | 91cf60a0 | about 20 ms per message on the 50-key seed registry |
| S3 section, gate, block, publisher | 7a492b88 | 02eabada | gate = marker in the RAW template |
| S4a kind lock (c06) | 3d686767 | 1498b51b | ungated: an intended L1 diff under production |
| S4b list-validated picks, tag-built legs (c04/c19) | d8718250, 60d1762e | 811f22fb, 3c86043c | superseded by S4b-v2 |
| S4b-v2 listed_item enum on the wire (crew dev data check) | 60097592 | 3e3dc50f | only `listed_item`, code/name, or an explicit alias link validate |
| S4c "which file?" lists the product's own types (Q3 (a)) | 25e88686 | 75cc82ff | a bare "2" fetches that type |
| S5 no word rewrites under the gate (c27) | (S5 red commit) | 811f22fb | `_category_word_under_documents` off; listed type binds; F4 kept |
| T2 scheme pick indexes the product's certificates | c6c71e8b | c6c71e8b | explicit link product > attachment > revision > scheme; none held = the cert kind |
| `{{specs}}` token in the lane version (SPEC-REGISTRY-UI #1765) | (this commit) | (this commit) | the publisher swaps the baked specification lines for `{{specs}}`; the existing `specs` variable renders them at read time |
| scheme word is never a certificate record lookup | (in fix commit) | 7b7db72b | no separate `test(red):` commit; retro red-proof posted 18 Oct (new tests on the parent's code) |
| FILTER-OVER-HELD-WIDENS (CHAT-STATE card R1) | (in fix commit) | f7412977 | numeric size / brand narrows the held family; none-match keeps the held subject; retro red-proof 18 Oct |
| SIZE-AS-CODE | (in fix commit) | fa9fd99a | number + a registry unit = `spec K = N` candidate line, never a code word; retro red-proof 18 Oct |
| D CANDIDATE-LABEL-FORGE (CHAT-CODE-LOOKUP security nit) | acf5d713 | 8f3248bb | `;()` in a product name become spaces in `_code_label`, so a name never adds a candidate item |
| A UNSURE-CODE-KEEPS-DYM (cp0-2ab2f7ccc9) | 4fa98da6 | 571e06be | an unsure (confident false) product token with resolver neighbours takes the did-you-mean; no neighbours keeps the vague clarify |
| B HELD-WITHOUT-SCHEME (crew ruling (b) 18 Oct; cp0-9010f39a3d, 9f9e15dd0c, 7a655af8fa) | 5283ef89 | 0eb31d68 | held products stay the subject, the scheme's certificates filter the fetch, reply `<codes>: no <scheme> certificate on record.`; supersedes T2's "send the certificates they have" |
| C SCHEME-NO-PRODUCT (cp0-fce51f2811) | d433a648 | 0eb31d68 | clarify policy is default here (`turn/policy_rows.py:91` narrow_by_tier, `turn/narrow.py:553`): the scheme's company-scoped certificates filter the fetch, at most 50 rows (endpoint default `api/v1/master_data/product_attachments.py:153`) |
| R2-1 BRAND-SCOPE-ATTACH (security blocker) | a9cefbee | 36fa732b | `ProductAttachmentService.list_product_attachments` filters `product_in_scope_clauses`; ungated; unscoped sessions unchanged |
| R2-2 MIXED-UNSURE (reviewer) | 6e174c98 | 23db525d | the did-you-mean only when every unsure token has neighbours; under the gate the vague clarify quotes each word on its own (accepted format) |
| R2-3 SCHEME-NONE-IN-SCOPE (reviewer) | a64d26e3 | 957269b0 | nothing held, no certificate of the scheme in scope: `No <SCHEME> certificate on record.`, nothing fetched |
| R2-4 KIND-NONE-HELD (reviewer) | 0d523a7a | a7c5bc48 | `scheme_without_product` leaves a verdict holding a product unchanged; the untested filter is gone |
| R2-5 CANDIDATE-TEXT-SCRUB (security) | 41cea408 | ae92cec3 | `candidate_text` (`chatbot_prompt_vars.py`) for code, name, spec key, value, display, class label |
| R2-6 ENGINE-KEYS-STRIPPED (security) | c92c8744 (wrong reason), a3be90b9 (corrected, after the fix) | 540bc7e6 | parser entities lose `listed` / `certificate_uuids` before grounding; ungated; red-proof by reverting the strip |
| R2-7 CERT-ID-CAP (security) | 7afed4b4 | 957269b0 | scheme certificate ids capped at 200, id order |
| R3-1 SCHEME-NAME-PUNCT (security) | 6987cb13 | e93d14c8 | a scheme name / option / keyword with `.:,;()"` never reaches the list or the enum (external ingest, like the over-long read error) |
| R3-2 KIND-NONE-HELD-ENGINE (reviewer) | f57030bb | 0e467cc0 | the engine never calls `scheme_without_product` while a focus product carries a uuid; `index_scheme` no longer returns early with no certificate kind listed (it adds none) |
| R3-3 SCRUBBED-LABEL-GROUNDS (guard) | 0aa38cc6 (guard, green) | - | a pick of a scrubbed rendered value grounds to the same registry value |

Held (crew Q4 (a)): deleting the gate-off rewrites waits for the owner to move the label; each is
listed with the replay diff it would need. Gated off under the CLOSED LISTS path today:
`_category_word_under_documents`, the class split of a listed type pick, the cert regexes and
the `user_goal` fallback in `derive_require`.

Follow-up (security, staff-written text): attachment type names and description words in the closed lists get the same punctuation rule as schemes. Note: R3-1 drops a dotted scheme name ("S.I.R.I.M") rather than scrubbing it; none exists on the dev copy (11 register schemes, no `certificate_scheme` lookup rows).

Residual (one item, reported, not fixed): cp0-7a655af8fa drops its held products for an unresolved category word ("tap fittings") before the scheme leg.

Open: c06's
"300mm" reads trap_length where the answer key says dim_length (a numeric key choice; no
candidate covers a number with a unit, trigger: a TRAIN miss family on units).

## Phase 3 (17 Oct)

Security review: no blocker. Fixed: file-ask products read through a scoped Product query;
listed items one line, at most 60 chars / 100 items, null-only when none; candidate rows one
line. Answered: the file-ask roster mirrors the fetch's own visibility (the product-attachments
route the bot calls applies no tier filter). Open for crew: the external upload schema's
`scheme` has no `max_length` (the column is varchar(60), so an over-long one fails the insert).

Reviewer: READY. Fixed S1 (first line only), S2 (one whole-code query + at most 6 per-code-word
queries), S3 (shortlist failure leaves the block out, savepoint), S4 (grounding replay derives
the gate from `listed_item` on the parse; a whole-turn replay pins the version through
`prompt_overrides` as runs do), N1, N2. Accepted: N3 (two cached prompt reads per turn; the
label and text can disagree only across a TTL expiry and a label move in the same instant), N4
(the file-ask roster lists certificate types too: the customer is asking which file of THIS
product, and its certificates are files of it).

## Round 4 (19 Oct, owner): attachments only

Held-out attachments (crew-only) sits at 63.5 against the 95 bar, flat across rounds; its first-failing classes are
files 9, asked_type 6, no_picker 3. The lane measures on TRAIN only: the 27 real attachment conversations
(`crew/state/eval/cp0/train_attachment`, the attachment slice of gate #3 `g1755c`, lane head 0665fa0d, 40.7 vs main 33.3).

Steps:
1. $0 root cause on every TRAIN attachment failure of gate #3: the stage that lost it (parser type pick, grounding,
   scheme index, resolver, apply/narrowing, fetch args, scope, composer), file:line, class (>= 2 item-runs), and
   MODEL LIMIT vs CODE per class (crew may try a stronger parser model separately).
2. Red-first fixes per CODE class, reviewer (+ security-reviewer if scope/ingest is touched).
3. Paired TRAIN x1 (lane vs main) under the owner's early-stop rule (checkpoints, stop on regression), cap 3 USD.

### Round 4 part 1 (19 Oct)

| Class | Red | Green | Notes |
|---|---|---|---|
| C2 FAMILY-BY-FAMILY-CODE (crew priority) | f49d099c | 3c8810c6 | a held product's family = same company + same non-null `family_code`, chat-searchable, plus the variant graph; dev copy: variant_of_id on 2 of 15,439 products, family_code on 13,983, largest family 16 |
| HELD-OVER-NAMED-CLASS (TRAIN 41147cbf9f, 7a655af8fa, c026f64f50) | fa67869f | f6eb1165 | a current-message category / product_type entity names its own subject: no held carry, no held_none_match, the scheme's certificates filter; fixture made real in c0c43178, 1546db61, 4df5178d, 6665f100 (parse fields, class_label, certificate_products rows); a harness-only apply rule was removed |

Root cause of the 27 real attachment conversations (gate #3): crew-note 6256793867; grader artefact G1 (trace cap)
goes to EVAL-BENCH; gold calls to the owner; MODEL classes to the gpt-5.4 parser run (CHAT-CODE-LOOKUP).
Residual (reviewer): a refine that repeats the held product's own class ("p trap wc?") would drop the held subject; not
seen in g1755c (114 held turns) or train_followups (56).

### Round 4 part 2 (19 Oct)

| Class | Red | Green | Notes |
|---|---|---|---|
| R4-2 SCHEME-NO-PRODUCT-RETYPED (cp0-fce51f2811) | 026863c6 | fd246a88 | `scheme_without_product` adds the certificate kind beside the scheme, as `index_scheme` does; the reconciler's retype can no longer empty the type slot |
| R4-3 DROPPED-TYPE-CARRIES-OLD (cp0-6240dc53f8) | 55b6d27e | 7e8b2a37 | grounding records an engine-owned `dropped_kinds` (popped from parser output); apply clears that axis so the old type never answers |
| R4-4 CERT-NUMBER-AS-SET (cp0-5b20fdfe69) | f71eaaa4 | fe9f1b92 | an exact certificate match is a typed code for the Shape B skip (`cert_number_is_code`); narrowed to a listed scheme when picked |
| R4-5 NO-FREE-REMAINDER-ON-FILE-ASK (cp0-5c93483505) | d1cc720b | ac91fd9b | on a file ask under the gate the set is described by parser entities only; spec and other domains keep their remainder (guard test) |

Shared test helper `tests/chatbot/_attach_world.py` carries the real parse fields and the real certificate link chain
(certificate_products included). Watch item (reviewer): a class word the parser hints as `product` on a file ask is no
longer scoped by the leftover remainder.

### C2b HELD-FIRST (19 Oct, CHAT-STATE correction)

| Class | Red | Green | Notes |
|---|---|---|---|
| C2b HELD-FIRST | f1628123 | 4b11b5d1 | one filter applied twice: held products first; family_code siblings (+ variant graph) only when no held product matches; none line only when both are empty. Keeps es-e9d2507a71 / es-242b332bca / es-f173186e97 within the shown set, still fixes cp0-665ba3e897; old C2 brand test re-seeded so the held product lacks the filter (9ac7e39d) |

Open (CHAT-STATE, UNVERIFIED): es-0db8cf0a48 "150" is `trap_length` on file while the parser emits `dim_width`; a
numeric-key candidate line is this lane's (candidates.py). Reviewer nits kept: the held pass has no
`chat_searchable_products()` filter (held came from a searchable resolution).

### Round 5 (19 Oct, after the paired TRAIN x1 on ad78e1e7: pooled +15.3, refine +33, spec +17, attachment +7)

| Class | Red | Green | Notes |
|---|---|---|---|
| R5-1 SIZE-KEYS-BY-DATA (cp0-caafdcebea "(1)" header, es-0db8cf0a48 false none, 7 TRAIN rows on a wrong key) | 62d59d12 | 30995a98 | a size word offers only the unit's keys that hold that number in product_specifications (exact numeric), most held first, the held family's keys first; falls back to today's list when no key holds it; one query per size word, scoped |
| R5-2 CONTAINS-IS-NOT-THE-CODE (cp0-75be0b79cf, cp0-cd3328e3f1) | 36270373 | da83acf9 | a code that only contains the word is labelled `holding "W"`; one CLOSED LISTS line: such a code is that product only when the message names it (template change) |

Not built (root cause rc5-downflips.md): cp0-362022362a TYPE-OMITTED (MODEL, both arms), cp0-6240dc53f8 confident-false
pick (MODEL, single; owner call on keeping an unsure pick). Bench notes for EVAL-BENCH: the spec grader compares values,
never keys (3 of the lane's 5 spec up flips are wrong-key passes). Reviewer nits kept: `_keys_holding` skips
string-stored values (all 17 numeric keys are JSON numbers on the dev copy); the family reader is linear in the held set.

## Round 6 (19 Oct): TRAIN classes from EVAL-BENCH-train-classes-19oct.md

combined3 held-out (crew): attachments 53.8 (bar 95), spec 73.7 (bar 90), leaks 0. Plan approved by crew:
1. SIZE-WRONG-KEY (9 items): owner rule, crew ruling (a), data only: a bare size (the customer names no dimension; the
   parser picks a `size N <unit>` candidate) matches dim_width OR dim_length; trap_length where the registry says it
   applies to the class and holds N there (WC 200 / 300); a named dimension stays strict.
2. SPEC-DROPPED-FRESH (5): piece_count / finish phrases get candidate lines from registry data.
3. HELD-OVER-NEW-CLASS (2 left): a grounded class-key spec counts as naming the class; owner rule: a class ask
   answered with only the held product is a fail.
4. TYPE-ONLY-EMPTY-SET (2): a type-only follow-up over held products fetches their files, never a described set (R4-5).
5. SIZE-AS-CODE (4): check that R5-1 / R5-2 cover it; build only a gap.
Not this lane: COUNT-ONLY-SET (CHAT-COMPOSER #1771/#1776), SIZE-AS-QTY (CHAT-STATE prompt), TYPE-WORD-DROPPED (MODEL;
owner call on unconfident picks); classes 1, 4, 14 fixed on #1755 per the report. Spend: $0 root cause and tests, one
paired TRAIN x1 by EVAL-BENCH at the end (~0.9 USD, cap 3).

### Round 6 results (19-20 Oct)

| Class | Red | Green | Notes |
|---|---|---|---|
| R6-1 BARE-SIZE-BY-DATA (SIZE-WRONG-KEY) | 09fc569b | f8f15b79, c894458f | migration spec_bare_size_0001 (`matches_bare_size`), `size N <unit> (no dimension named)` line + one CLOSED LISTS line, head/bare_size.py grounding (class key by applies_when, else OR over flagged keys; Q3 named-dimension fallback by registry phrases + counts), OR carried through resolver, predicate, paging, held_family |
| R6-2 BOOLEAN-SPEC-PHRASE (SPEC-DROPPED-FRESH) | 55d122e0 | a28c93ca | boolean registry phrases get `spec K = true (<label>)`; S2 test updated (09a883ed) |
| R6-3 NAMES-OWN-CLASS-AT-EVERY-SEAM (HELD-OVER-NEW-CLASS) | beef226c | f7915900, d7917e24, 85562511, 9277505b | task revise + grounding class_hint + class-hinted spec is gate scope; a stub-only apply rule removed |
| R6-4 TYPE-ONLY-KEEPS-HELD (TYPE-ONLY-EMPTY-SET) | 51e45ba7 | a5deac2c | a follow-up naming only a file type keeps the held product |
| R6-5 review fixes | fdb9e4f2, 550f1a9c, 4d3f6aeb, e8f53573, 16b912c8 | 13a924f1, ca707012, d56e05ae, 995f18f7 | Q3 reads label words (real seed), registry API field, hidden keys in the OR, gated class_hint, unit in the miss line, CASE cast, one unit |
| R6-6 HIDDEN-KEYS-EVERYWHERE (security) | 28ac75c3 | 658cbdfa | contact-hidden keys never filter, narrow or print (bare_size, held_family, Shape B strict + OR) |

Data (dev): crew/state/migrations/CHAT-CLOSED-LISTS-L.sql (matches_bare_size true for dim_width / dim_length;
trap_length applies_when class Water Closet); UPDATEs need owner OK. Prod (crew ruling a25130034 (a)): the owner runs the same idempotent SQL from the PR
runbook after the migration deploys; a registry UI toggle for `matches_bare_size` is a later follow-up lane. Staff cannot
edit `applies_when` in the UI today either: the update service accepts it
(sorento_crm_frontend/app/(protected)/master-data-management/product-specifications/services/productSpecService.ts:462)
but no screen component reads or writes it (code check, not a browser check), so trap_length's applies_when also goes
through the owner SQL.

## ARCHITECTURE (owner 20 Oct: layer, shared mechanism, other classes fixed, special cases removed)

1. Spec key choice (R5-1, R6-1, R6-2), layer DATA -> candidates / grounding. Shared mechanism: the key a word can mean
   is read from the registry (values held, matches_bare_size flag, applies_when.class, label words and synonyms), not
   from key-name order or key type. Also fixes SIZE-AS-CODE, the es-0db8cf0a48 refine, the cp0-caafdcebea header and
   the boolean phrases. Removes: the name-sorted cut-at-5 and the "boolean keys get no candidate line" special case.
   No class or key list in code.
2. Subject decision (R6-3, R6-4, HELD-OVER-NAMED-CLASS, FILTER-OVER-HELD), layer ROUTING. Today one rule (a message
   naming its own class or product replaces the held subject; a refine fragment on any axis keeps it) is applied at
   several seams (scheme_index, held_family, task revise, gate scope, apply kept_kinds). Crew ruling a29310107 (2): the subject decision moves to
   CHAT-STATE's Subject resolver; this lane does not extend R6-3 / R6-4 and adds no new seam guards (frozen).
3. Contact-hidden spec keys (R6-5 S2, R6-6), layer ACCESS. Today enforced per consumer (bare_size, held_family,
   Shape B); the candidate line can still show a hidden key name to the parser (security nit, no customer leak).
   Crew ruling a29310107 (3)(a): read hidden keys once before the parse and strip them at the two entries
   (candidate block, grounding output), keeping downstream drops as a safety net. Next slice.
4. No round-6 fix is a special case for one message shape.

## Round 7 (20 Oct): H1 + F3 (CHAT-ARCH-REVIEW-20oct F3 / M3; crew rulings a29310107, a29691875)

Scope ruled by crew: land round 6 as is (done, head 18e9760e7d), freeze new seam guards, then:
- **H1 HIDDEN-KEYS-AT-THE-ENTRIES** (a29310107 (3)(a)), layer ACCESS: the policy is read once before the parse;
  hidden keys are stripped from the candidate block and from the parse output; the R6-6 drops stay as a safety net.
- **F3**, layer DATA -> candidates -> grounding. Shared mechanism: the spec registry is the single value-to-key
  source; candidates.py is one generic index (value -> keys holding it, scoped, held family first, ranked by data
  count, all keys shown neutrally when 2+ hold it); the parser returns a listed candidate id; grounding validates ids
  and ASKS when a pick is unconfident or tied. Order (ruling (3)(a)): F3-c, then F3-a, F3-b, F3-d.
  - F3-c grounding validates candidate ids; unconfident or 2+ equally supported -> ask (generalises #1761 R2-4, rank
    by data not trigram). Removes the grounding scheme-word drop and the unconfident-pick drop.
  - F3-a generic value index for spec / type / cert candidates only (ruling (2)(a)); code / near / set-code rows stay
    #1761's. Removes CAP_PER_WORD name cut, `_size_candidates` / `_keys_holding` / `_bare_size_keys` / boolean branch,
    unit-regex special cases.
  - F3-b one parented closed list: attachment type / cert kind / scheme (scheme -> kind parent); the parser picks ONE
    item; scheme_index reads the parent. Removes R4-2 added_kind and R4-3 dropped_kinds patches.
  - F3-d registry fields (ruling (1)(a)): JSON columns on product_spec_registry (unit_conversions, short_forms) plus
    `is_piece_count` bool, one additive migration. Removes v63 trap_length words.
- **R5-2**: EVAL-BENCH x3-per-arm A/B (~0.035 USD); the `holding "W"` label goes if harmful.
- **Prompt freeze** (a29691875): CHAT-CODE-LOOKUP owns the parser prompt (F1 consolidated template, #1761). This lane
  does not edit head/closed_lists_prompt.py or base sections; any F3-b / F3-c wording goes to crew as exact rule text
  (rule + field). A parser.py schema field change is announced to crew before it is made.
- Spend: $0 root cause + red tests; L1 replay per slice (crew run); one paired TRAIN x1 at the end via EVAL-BENCH.

### F3-a acceptance (crew ruling a30139843 (a): candidates.py only, behaviour-preserving, all keys neutral when 2+ hold the value)

Order changed by a30139843: F3-a, F3-b, F3-d; F3-c only after a $0 TRAIN count of unconfident / tied spec and type picks
(then the id field + rule text go to crew). The cp0-6240dc53f8 call (keep a confident=false attachment pick that is
exactly a listed item) waits for the owner; neither side is built.

- A1 ONE value index. Every spec line under a message word (enum value / label / synonym, boolean phrase, number + a
  registry unit, a numeric key's own words) comes from one registry-driven index of (key, value) pairs; each pair
  carries its data support: how many chat-searchable products in the contact's scope hold it, and how many of the held
  family do. One scoped count query per message for all pairs (today: one per size word).
- A2 Rank by data. Under one word, the spec lines of different keys are ordered: a key the held family holds first,
  then by products holding it (most first), then by key name only as a stable tiebreak. This now also applies to enum
  phrases two keys share (today they keep registry name order). Exact before near and product type before spec stay.
- A3 No cut of holding keys. When 2+ keys hold the value, every holding key has its line, in the same neutral wording
  (`spec K = V (label)`); the per-word cap (`CAP_PER_WORD`) no longer cuts spec lines. Code / near-code rows keep the
  cap and are untouched (ruling a29691875 (2)(a): they are #1761's). `CAP_LINES` per message stays.
- A4 A size no key holds. Every key of the unit is offered (today: name order, cut to 5), ranked as A2 (all zero, so
  name order), uncut.
- A5 Unchanged (existing tests are the guards): the bare-size line and its flag (R6-1), boolean phrases (R6-2), size
  keys by data (R5-1), SIZE-AS-CODE spanned words, numeric key words ("4 in 1"), hidden keys (H1, R6-6), gate off.
- Removes: `_keys_holding`, `_bare_size_keys` and `_unit_keys` as separate per-key readers (folded into the index),
  the `or keys` name-order fallback, the spec-line cut in `shortlist`.

### Round 7 results

| Slice | Red | Green | Notes |
|---|---|---|---|
| H1 HIDDEN-KEYS-AT-THE-ENTRIES | f6e8c02d | 426eb3b4, 32971002 (+ stub 90bc48e9, lead sign-off) | candidate block filtered in one place (`_registry`); parse output stripped once; kill-proof 3 red; security PASS with should-fixes -> H1b |
| H1b HIDDEN-KEYS-AT-EVERY-ENTRY (security should-fixes) | f95faa7d, 9329f07b | d4272502, 1a6cc876 (B4), (B5 carried-set replay in progress) | grounding output stripped too (raw-word re-derive); Shape B reads the hidden set once before the unknown-value branch; a set breakdown never splits by a hidden key (B4); `.strip()` on spec_key; kill-proof 5 red |
| F3-a ONE VALUE INDEX | 3fffdd4b, f1f1645d | 5cd73ded, 8ff8ef7d | one registry index + one scoped count query; spec lines ranked held family / count / name; holding keys never cut; near rows keep CAP_PER_WORD; removed `_keys_holding`, `_bare_size_keys`, `_unit_keys`, `or keys`; kill-proof 5 red + 1 red |

Dev data for F3-a (sorento_cagent_stack, read-only, searchable, not company-scoped): 5 numbers held by 6+ of the 9 mm
keys (250: trap_length 329, dim_height 107, dim_length 43, dim_width 20, thickness 8, diameter 7, depth 6; the old cut
dropped diameter and depth and the bare-size line took a slot). The 3 enum phrases two keys share whose name order
differs from data order ("urinal", "mixer", "mixer tap") all pair a type line with another line, and type stays ahead,
so A2's enum ranking changes none of them today.
