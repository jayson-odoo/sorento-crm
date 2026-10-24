# PLAN: PARSER-TEMPLATE (F1, one consolidated parser prompt)

Status: Review READY (code) on e61181663e after the F1-E round; merge gate items waiting for dev-key credits (crew
a38627742): conflict gold N=3 on v82 01c2e25b, TRAIN x1 attachment + spec paired; no label before #1772 merges.
Track L. Owner:
CHAT-CODE-LOOKUP (crew architecture review, 20 Oct, crew/state/reports/CHAT-ARCH-REVIEW-20oct.md M1 + F1 + section 3).
Track: L, LEAD pattern. Owner 20 Oct: keep the bars, fix at the architecture layer.

## Problem (M1)

The parser prompt is a stack of absolute rules with no precedence. Each lane appended an "overrides" section:
CLOSED LISTS (#1755, 6.2 KB), CODE LOOKUP (#1761, 3.2 KB) and STATE (#1772, 6.1 KB, which aliases base sections).
v178 is 137 KB (v63 141 KB); with STATE about 143 KB. "How this message relates to what is held" lives in 7+ base
sections plus STATE and CODE LOOKUP, over 4 schema channels (open_question_answer.mode, state_changes, entity_op,
reference_positions). One decision has opposite rules: #1761 "a count beside a code is a stock ask whatever the previous
domain" vs #1772 r2-D "a message naming only another item asks the last answer's fact"; the same decision is also a regex
in engine.py `_as_a_stock_ask_by_its_own_words`.

## Design

- One template module (rule-id blocks) and one publisher; versions published unlabelled; the gate markers stay so the
  code paths that read them switch on unchanged.
- An ordered procedure: P1 the relation of this message to the State (state_changes is the only continuation channel
  under the state gate); P2 the entities named in THIS message, picked from the candidate block or none; P3 domain and
  the remaining fields.
- Rule ids; an exception only as "see R-x"; one rule per decision.
- R-DOM-QTY (replaces both count rules and the regex): a stated quantity continues the last answer's domain when that
  domain takes a quantity (stock, incoming, order); otherwise the domain is stock. Derived from the schema, no word list.
- Word lists become meaning rules (the "when deliver" list becomes: asking when goods reach a customer is an
  outstanding order status ask).

## Deletes

- The three appended sections (folded into the base as edits).
- The 7 overlapping continuation sections, and the continuation semantics of open_question_answer / entity_op /
  reference_positions under the state gate.
- Base ATTACHMENT TYPE EXTRACTION canonical rule and the cert-scheme EXCEPTION; the REQUESTED ATTRIBUTES closed
  vocabulary; CODE LOOKUP override paragraphs.
- The R2-5 when-deliver insertion and its publisher anchor code; `_as_a_stock_ask_by_its_own_words` under the gate.

## Gate

- $0 lint (pytest): every rule has an id; fails on two absolute rules over one schema field without a "see R-x" link,
  on any overrides / alias section, on a word list longer than 8 items.
- Size: <= 90 KB (stretch 75 KB).
- Parser gold N=3 on fresh conflict-pair shapes, old (v178 + STATE) vs new; when-deliver gold must stay >= 31/42.
- L1 replay; TRAIN x1 paired (code, follow-ups, attachment, spec) on a combined build. Spend <= USD 4.

## Decisions and progress

- 20 Oct: rule map 4d0f87d602 (176 blocks -> 50 rules). F1-A template 128aeb1716 (66,143 chars, lint clean), F1-B
  parser-gold context rows 1bf98f34f8, dash-pattern fix b56b01fc7e. Nothing published yet.
- Read-only risk check: ranking_drill must be explained (not null); a value-only narrowing reply keeps domain_hint
  null (decide.py R24); no hint_confident-false instruction (dealer word drop). Fixed red-first as F1-C.
- Crew a33610208: R-DOM-QTY applies to dealers (stock_availability_only) too, no code backstop. Dealer C1 shapes and
  the old no-state "code x qty" misread join the conflict gold; the gate fails if gpt-5.4-mini misreads >= 1/3 at N=3.
  Behaviour shift for the owner: a dealer's "CODE x 10" right after an ETA answer continues the incoming question.
- Open with CHAT-STATE (B1): an op to drop one item; whether an own ask closes a hand-over offer; the op `value` field.
- 20 Oct: first gate run on sorento_cagent_stack invalid (schema behind: UndefinedColumn matches_bare_size, USD 0).
  Crew a34333719: no shared-DB writes there; gate moves to sorento_eval_base (EVAL-BENCH upgraded it to
  spec_bare_size_0001, no row writes). Published there, unlabelled: OLD v77 448ebc81 (v74, same text as cagent v63,
  through the closed-lists, code-lookup and state publishers; = cagent v179 plus #1755's R6-1a bare-size line, which
  NEW carries too) and NEW v78 65cb02d4 (same md5 as cagent v180).
- 20 Oct: conflict gold defect: every row named a synthetic ZZ code, but the grader needs a canonical_code
  (parser_gold.py:90-93) that the parser can only take from DB candidates (:171-175), so each product check failed on
  both arms. c92b993a3a swaps in real catalog codes (each an exact single candidate on eval_base, active on both DBs),
  as the when-deliver and code-picks gold already do.
- 20 Oct gate run 1 (eval_base, gpt-5.4-mini, USD 2.5): conflict gold N=3 OLD 95/126, NEW 87/126: FAIL, early stop.
  NEW better on c1 (27 vs 24/30) and dq (33 vs 30/36; dealer no-context "code x qty" dq-01..06 all 3/3, so the
  a33610208 bar holds). NEW worse on c2 attachments (0 vs 8/12: no attachment_type entity for a plain file-type word;
  a cert scheme gets canonical PPS, not certificate) and c3 attributes (8 vs 15/15: free-form requested_attributes).
  Both come from deleting the closed vocabularies. When-deliver positives OLD 31/42, NEW 29/42, negatives 30/30 both;
  code picks 9/27 on both, row for row.

## F1-D (gate run 1 fixes)

Diagnosis on the rendered v78 (eval_base, $0): `{{attachment_types}}` renders (13 File type lines, 11 certificate
lines). The defects are precedence and priming, not missing data:
- D1 file word: R-P2-02 says file types are closed lists that "carry no word of their own" (name an item exactly
  as listed, or nothing), R-P2-06 says a file word in any language names the item that holds that kind. The DB
  Words lines are sparse (product_videos: "Product Videos by Marketing", no "video"), so the absolute rule wins and
  "gambar X" / "video X" get no attachment_type entity. Two absolute rules over one field, no "see R-x".
- D2 certificate: R-P2-06 asks for the kind entity plus one more entity per listed scheme; the model emits the
  scheme alone ("pps cert X" -> listed_item PPS only).
- D3 attribute phrase: R-P3-05's example "list price" primes the model to add a word the user never typed
  ("P-trap set price" -> "list price"); "is X still sold" is not tied to "discontinued" (old v249-252 said it;
  `_asks_discontinued` needs exactly "discontinued", lanes/business/fetch.py:1912-1916).

ARCHITECTURE: layer = prompt design (rule precedence). Shared mechanism: the closed-list rule in R-P2-02 scopes to
the values it owns (specification values, certificate schemes) and defers file types to R-P2-06 by "see R-P2-06",
so one rule decides each field. Other classes it should fix (UNVERIFIED until measured): every file word missing
from a DB Words line (drawing, manual, video in other languages). Removes: the conflicting absolute sentence. No
word list returns; meaning rules only, within the lint (MAX_LIST_ITEMS 8).
Gate rerun: conflict gold N=3 on NEW only (OLD v77 stands), USD <= 0.7.

Progress (20 Oct): dac39a4605 moves the c2 gold to the item downstream grounds (grounding.py:717-736 reads
listed_item then canonical_code against closed_list_items; on eval_base the keys are product_photos /
product_videos / certification / schemes, never photo / video / certificate); OLD v77 re-graded 98/126.
Round 1 (red a4f4621a67, fix 6b2d878289, v79 8a244142): 99/126. Round 2 adds D4 (the R-X-01 procedure line said
every P2 entity comes from the candidates block, which never holds file types) and D3b (bare "spec" worked
example and reason from the old text): red e5920a71fe, fix a6d4009aab, v80 cfabaac9, 68,564 chars: 106/126.
Only regressing pair: c2-01 "gambar X" (3 -> 0); a USD 0.06 probe shows a word quirk ("photo X", "foto X" 0/2,
"picture X", "X 图片" 2/2), not a language or rule gap, so no one-shape text. L1 (base chat-state-r2 d29ad44928,
head combined fbc49b0b3d): unintended 0 on grounding (5,584) and turn (1,095 of 1,480). TRAIN x1 attempt 1 invalid
(no MCP stack listening; USD 1.12); waiting on crew for a stack and cap. Spend USD 4.96.

## F1-E (review round 1 fixes)

Reviewer on 3a039cd00d: NOT READY. B1: #1755's H1 hidden keys under CODE LOOKUP (engine.py:1145) have no test.
B2: the dealer stand-down call site (engine.py ~5274, `template=`) has no engine-seam test. Both are guard tests
(kill proof, not red proof). Template: S1, D2 contradicted #1755 F3-b B-5 (PLAN-chat-closed-lists-17oct.md:345-346):
a listed scheme alone is the whole certificate ask, one entity, and code adds the parent kind
(scheme_index._with_parent_kind); a kind entity only when no listed scheme is named. The scheme line does not name its
kind: with B-2/B-3 the model never needs it, so no rendering change. S6, R-X-03 claims a quantity-only message repeats
the held domain; it defers to R-P1-03 instead. N2/N3 "see" links (show me; R-P1-04 file types; requested_attributes
restated in R-P3-01/-06/-12). Grader S3: attachment_types ignores an entity downstream drops (confident false,
NOT_LISTED; grounding.py:723-725). N6 publisher commit message, N4 fetch.py docstring.

Gate correction (S2): the $0 lint catches explicit absolute pairs (always / never / only / must beside one field) and
word lists; it does not catch a conflict in meaning (D1 passed it). The paid gold is the gate for that class; the lint
promise above is narrowed accordingly.
Label rule (S4): "(answered)" in the template's State lines is printed only by #1772 (chat_state.py:278); no template
version gets a label before #1772 merges.
Routed to CHAT-STATE F2 (S5): the template asks for state ops skip / unclear that the strict schema's op enum lacks
(parser.py:702-704), a gap #1772 shares.

Progress (20 Oct): guards 7e22715aea (kill proofs), red 25e94928e5, fix e61181663e (68,865 chars, 124 passed);
reviewer re-check READY (code): B1/B2 kills K6/K4 now red, the four fix tests red on revert, no new rule pair.
Published v82 01c2e25b, unmeasured: the dev key (bG4A) answers 429 no credits. Stored v77/v80 re-graded with the S3
grader: 98 / 106 unchanged. Spend USD 4.96 (cap 7.1; 7.7 asked to fit the v82 rerun plus TRAIN).
Open nit: two listed schemes in one message is unspecified; downstream reads the first only.

## F1-F (owner ruling, 20 Oct ~07:15)

Owner, verbatim: "It should actually be stock for the code x10". R-P1-03 DOM-QTY is now: a stated quantity with no ask
word of its own is a stock ask (inventory, check_stock) whatever the last answer's domain, dealers included; an own
ask word ("ETA CODE x 5", "outstanding CODE 10") keeps its ask; switch_domain when the last answer was not inventory.
One rule, no code backstop. This reverses the a33610208 behaviour shift above. Red 71a9b33c48 (with gold: c1-02,
dq-09, dq-10 incoming -> inventory; c1-09 order/outstanding -> inventory, the lead's reading of "after any answer",
flagged to crew), fix 54f17dc6f6 (68,849 chars, 96 passed), published v83 023f836c. Stored outputs on the new gold,
19 quantity pairs: OLD v77 33/57, v80 39/57 (both still follow the old continuation rule on the changed rows).
F1-G (CHAT-STATE R7 LAST-REFERENT, owner rule 20 Oct, crew/state/files/r7/prompt-lines.txt): rule edits, ids kept:
P3 -> R-P1-05 (any row of the last list can be picked: product, file, promotion, order; its stock-question 'not a
pick' clause now holds only while no numbered list came after); P2 -> R-P1-06 (a bare number over the stock question
is a position when a numbered list came after it); P1 -> R-P1-03 (a number alone is the stock quantity only while the
stock check is newest; after a newer numbered list it is a position, state_changes pick n, reference_positions [n]
mirrored per R-X-05). Red 74e457e8c1, fix 57f5defb95 (69,410 chars, 99 passed), published v84 5f289272.
Next, when the dev key has credits: ONE full conflict gold N=3 run on v84 (~USD 0.62; measures F1-E and the owner's
quantity pairs together), then TRAIN x1 attachment + spec paired v77 vs v84.

## F1-H / F1-H2 (owner quantity rows after a held answer)

Full gold on v84 (F1-G, gold 71a9b33c48, USD 0.61): NEW 103 vs OLD v77 86/126 (v80 94). Held-answer rows N=3
(c1-02 "x 5" after ETA / dq-09 "x 15" after ETA / dq-10 "70 pcs" after ETA / c1-09 "10 pcs" after outstanding orders):
v84 3, 3, 0, 3; v85 (F1-H 1cf14e9eb5, an extra R-P1-02 sentence "a quantity is not a new value of the held ask") 3, 0,
0, 0; v86 (F1-H2 2265ca5a40, the R-P1-02 code sentence scoped at its source to a code with no quantity, see R-P1-03)
3, 3, 1, 0; control "ETA CODE x 5" incoming 3/3. The same rule text flips rows between versions: gpt-5.4-mini follows
this boundary unreliably under one rule. Asked crew: c1-09 scope (a quantity after an ORDER answer) and whether to
accept dq-10 at 1/3 and let TRAIN decide (a code backstop was ruled out by the owner). Spend about USD 6.01.

## TRAIN x1 attachment (20 Oct, crew a54067515: v86 frozen, cap 7.7)

Stack 8192/8292 per a38211499 (egress block, scheduler off, no worker, dev key bG4A; AI_ASSISTANT_MCP_URL needs the
/mcp path, config.py:333). Combined build sorento_crm-ccl-s1 9517384485. Paired attachment set (83 real items):
OLD v77 REAL 52/83 (63%), 83 run, USD 0.70; NEW v86 REAL 14/70 (20%), stopped at the error-rate guard after 73 (one
"out of shared memory" on eval_base with both arms in parallel), USD 0.38. Cause, measured: v86 emits an
attachment_type entity on 22 of 73 items, v77 on 70 of 83; without it the fetch never narrows (tool results 34 vs 78).
Same class as gold c2 (file words): the consolidated R-P2-06 does not make gpt-5.4-mini emit the file entity that the
old ATTACHMENT TYPE EXTRACTION section did. EARLY STOP: no full gold, no spec set. Spend about USD 7.13.
Known misses kept (crew a54067515): c1-09 0/3, dq-10 1/3 (a quantity after an order / ETA answer). Layer that would fix
them: code routing on the parsed quantity the parser already emits (entities carry quantity 10 / 70), not more prompt
text; the owner ruled a backstop out, so only if TRAIN shows the shape matters.

## F1-I (crew a54889127) and the stop

R-P2-06 first step "a file ask always carries one attachment_type entity per file word ... whatever the word" (red
5378fccc03, fix 43db077de7, 69,984 chars, 102 passed), published v87 3d375694. Gold c2 N=3: 11/12 (v86 7/12). TRAIN
attachment NEW arm alone (stored v77 baseline): v87 REAL 32/80 (40%) vs v77 52/83 (63%); attachment_type entity on
43/83 items (v86 22/73, v77 70/83); tool results 53 vs 78. Still under v77, so per crew a54889127: STOP, no further
wording. Spend about USD 7.65 of 8.5. The file-entity gap stands as the open blocker for the consolidated template.
Crew attachment audit (v77 TRAIN parser faults besides the entity drop), for the next R-P2-06 step-1 fix, as classes
(no per-word rules): (1) a bare number beside a document word (a catalogue year "2025") taken as a product code
(SRTJC2025): digits alone are not a code pick (R-P2-02 / CODE LOOKUP near-code rule); (2) a compound file phrase
("DRAWING PICTURE") split into two file types: words naming one file are one file word, one entity; (3) a file word
beside a code fragment ("8609 cert") gives no file entity: step 1 holds whatever stands beside the file word.
