# PLAN: PARSER-TEMPLATE (F1, one consolidated parser prompt)

Status: Build, F1-E fix round after review (NOT READY: B1, B2 test gaps); TRAIN x1 attachment + spec paired is a merge
gate item waiting for dev-key credits (crew a38627742). Track L. Owner:
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
