# SCOUT: the picker mechanism (open numbered question), 28 Sep 2026

Issue #1352. Knowledge lane: no code change, no PR, no migration.
Read from origin/main at `5b18b6d0062616f82c67cb158e82bcf7c8898f9f`.
Alignment page: `documentation/plans/chatbot/ALIGN-picker-mechanism.html`.

## The ask, in the owner's words

> "code first hotfix and patching approach is wrong, i think we should see how we work out our
> picker, like the mechanism in which how we retain the picker, is very wrong"

On the prompt block "AN OPEN NUMBERED QUESTION IS ANSWERED WITH reference_positions":
> "like this, i don't know why we need this"

And earlier the same night: "why so many behaviour in forward asking and reverse asking?" and
"the upstream differentiate the forward asking and reverse asking by either if found by product
code -> forward asking, if cannot find product code, fallback to spec search -> reverse asking".

## Short answer

1. **The picker is retained by design.** A product, customer, tier, kind or top-selling roster is
   a "sticky roster" (`pending.py:48` `ROSTER_KINDS`): answering it does not close it, it only
   records the answered position (`apply.py:872` `with_answered_positions`), and the tail writes
   back `answer.question or state.pending` (`tail.py:32`: "No new question is not no question").
   It closes only when every option has been picked (`apply.py:2984`) or when a new ask about a
   DIFFERENT subject gets its own answer (`apply.py:3426`, gated by `_roster_is_about`). A
   follow-up about the product just picked is about the same subject, so the roster never closes.
2. **The retained roster is then re-shown to the parser as an open question on every turn**
   (`Open question: {...}`, `Pending: ...`, `Open question options: ...`,
   `parser.py:673-686`), and the prompt tells the model to answer it and to blank out domain and
   intent when it does. The model replays the pick.
3. **The engine trusts any pick over any domain signal.** `decide.picked_positions` returns the
   positions unconditionally (`decide.py:263`); only the label-match path checks
   `domain_in_message` (`decide.py:271`). `_answer_pending` then re-domains the turn to the
   roster's own domain (`apply.py:817-821`) and the domain lock ignores `domain_hint`
   (`apply.py:3191-3208`, it yields only to a non-empty `asks`).
4. So the owner's added prompt sentence could not change the reply: even a verdict that reads
   the domain word correctly (`domain_hint: inventory`) but still carries the pick is answered
   as incoming. Only a verdict with NO pick escapes, and even then the roster stays stored and
   the NEXT short reply is read against it (trace below: "5" to "How many units?" became a pick
   of variant 5 and returned incoming).

The fix is not another clause. It is to stop retaining the question, let the engine own the
pick deterministically before the parser, and stop showing the parser an open question.

## 1. The mechanism today, end to end

### Born

| Where | What |
| --- | --- |
| `turn/narrow.py` (domain narrowing policy) | a resolver candidate list too wide for the domain mints `f"{kind}_pick"` via `pending.ask(...)` |
| `turn/pending.py:118` `top_selling_pick` | the top X ranking's printed rows |
| `lanes/escalation`, `compose._team_pick_question` | `team_pick`, `member_offer`, `company_pick` |
| `turn/apply.py:541` `_answer_outstanding` and the outstanding lane | `outstanding_scope`, `outstanding_detail`, `sales_report_detail` |
| `turn/apply.py` `_reconcile_step` | `kind_pick` (one ambiguous token, customer or transporter) |
| stock did-you-mean (`payload.stock_pick`) | one or two option confirm |

All of them are one `Pending` object (`pending.py:77`), written to
`respond_contacts.session_vars.open_question` by `tail.session_payload` (`tail.py:32`).

### Stored between turns

- `tail.py:32`: `"open_question": to_wire(answer.question or state.pending)`. A turn that asks
  nothing new keeps the old question.
- `turn_runtime.load_state` (`turn_runtime.py:599`) reads it back through `pending.tick`
  (`pending.py:262`): only the three escalation offers have a clock (`OFFER_TTL = 3`,
  `pending.py:259`); every business question has no expiry.
- `pending.py:48` `ROSTER_KINDS` = product_pick, customer_pick, kind_pick, tier_pick,
  top_selling_pick, and `is_roster` (`pending.py:55`) also makes ANY operator-minted
  `*_pick` / `*_ask` kind a roster. `outstanding_detail` / `sales_report_detail` are sticky too
  (contract 39, `apply.py:649`).

### Shown to the parser (`engine.py:2417-2431`, `head/parser.py:604-722`)

- `Current subject: domain incoming; product SRTWC286-SH-NEW.` (focus)
- `Open task: ...` (stock task lines, `task.hint_lines`)
- `Open question: {"kind":"pick_one","options":[...10...],"owed":["pick"]}` (`turn/question.py:96`,
  the pending wins over the stock task, so a pending pick HIDES the quantity question)
- `Pending: the assistant is waiting for a product_pick reply.`
- `Open question options: SRTWC286-SH; ...` (D17, `engine.py:4425`)
- `Recent exchanges, oldest first:` (last three, `turn_runtime.recent_exchanges`)
- `Last answered:` (stock task)

### Asked of the parser (prompt, repo default `chatbot_parser_prompt.py`; line numbers are in the rendered text)

Clauses whose only job is the pick, or to stop a non-pick being read as one:

| Section | Purpose |
| --- | --- |
| "AN OPEN NUMBERED QUESTION IS ANSWERED WITH reference_positions" (~853-883) | answer = position AND "NOTHING else: entities [], domain_hint null, intent_hint null, order_status null, message_type casual"; paraphrase is an answer; "all" is every number; a NEW ask is not an answer; never both |
| "THE OPEN QUESTION AND open_question_answer" (~1182-1235), PICKING and CONFIRM parts | modes pick / yes / no with ordinals in EN, MS, ZH, pinyin |
| "POSITIONAL REFERENCES" (~573-587) | bare number is a position "even when some of those same positions were already answered ... (the roster stays on screen until its own topic changes)" |
| "REFERENCE TARGET" (~589-593) | which set a positional reply means (dym marker) |
| INTENT & DOMAIN carry exception (~212-224) | "This rule does NOT apply when the bare reply ANSWERS something the assistant just offered" |
| number words (~62-64) | "one", "satu", "lapan" go to reference_positions |
| "A LINE BEGINNING Last answered:" (~1165-1180) | "It is NEVER a position ... that list was closed the moment one product was picked" (contradicts POSITIONAL REFERENCES) |
| top selling: "A bare number after a ranked list picks that row", year is not a rank, "ANSWERING CUSTOMER OR SALES AGENT?" (~1395-1426) | pick vs count vs period vs metric |
| DOCUMENT / outstanding offer paraphrases (~722) | "both" over an offer |
| owner's 28 Sep production sentence | a decisive domain word is never an answer |

### Consumed by the engine (order inside `apply()`, `apply.py:2949`)

1. `_open_pick_answer` (`apply.py:2966`, write at `apply.py:2753`): `open_question_answer`
   mode pick becomes `verdict["reference_positions"] = sorted(picked)`. Runs FIRST, before any
   domain or shape rule.
2. `_stock_pick_takes_position_and_quantity`, `_open_question_answer` (stock task),
   `_asked_quantity_placed`, `_bare_position_is_the_quantity`,
   `_numbered_lines_are_the_products`: five more shape rules about what a number means.
3. `_fully_answered_roster` closes a roster whose every option was picked (`apply.py:2984`).
4. `decide()` (`decide.py:543`): `picked_positions` (`decide.py:218`) returns
   `reference_positions` as ANSWER with no domain check (`decide.py:263`); a label match counts
   only when `domain_in_message` is not true (`decide.py:271`); `broaden_axis: all` picks every
   option (`decide.py:275`).
5. `_answer_pending` (`apply.py:669`): builds the picked entity, sets
   `focus.domains = pending.payload.domain` (`apply.py:817-821`, "a pick never re-domains the
   turn"), keeps a roster open with `with_answered_positions` (`apply.py:872`), and on "not an
   answer" keeps the pending unchanged (`apply.py:940`).
6. Domain lock (`apply.py:3191-3208`): with a pick, the plan's domain is the roster's unless
   `asks` is non-empty. `domain_hint` is not read.
7. `new_ask_closes_stale_roster` (`apply.py:3400-3426`): closes only on NEW_ASK or
   `domain_in_message` AND a fetch AND `not _roster_is_about(...)` (`apply.py:3448`).

Separately, `engine._top_selling_verdict` (`engine.py:1550`, `engine.py:1630`) already resolves
a top-selling pick in code from the raw text (`bare.isdigit()`) and overrides the parser. That
is a working precedent for the engine owning the pick.

### Closed

| Close rule | Where |
| --- | --- |
| offer kinds: on their own answer | `apply.py:874` |
| roster kinds: never on their own answer; when every option is picked | `apply.py:2984` |
| roster kinds: a new ask with a fetch about a subject NOT in the options | `apply.py:3426` |
| escalation offers: three turns | `pending.py:262` |
| a new question replaces it | `tail.py:32` |

Every place that keeps it open: `tail.py:32` (`or state.pending`), `apply.py:872`
(`with_answered_positions`), `apply.py:940` (`answer_pending_not_an_answer`), `apply.py:921`
(`answer_pending_own_entities`), `apply.py:931` (`offer_hold`), `apply.py:737`
(`answer_pending_unresolved` re-print), `apply.py:3448` (`_roster_is_about` veto),
`pending.py:48` and `pending.py:55` (sticky kinds), contract 39 detail offers.

## 2. Case 1 reproduced (console harness, real engine, parser stubbed)

Harness: `tests/chatbot/_r9_engine_console.EngineConsole` over `engine.run_turn`, Postgres 16 +
pgvector in the container, `scripts.bootstrap_env`, the SRTWC286 family seeded (10 variants).
Only the parser verdict and the MCP tool read are stubbed. Script (not committed) lives in the
scout's scratchpad; its shape: T1 "incoming srtwc286", T2 "4", T3 "check stock" with four
readings, T4 "5".

T1 reply: `incoming search needs to be more specific. Multiple matches found. Please choose: 1.
SRTWC286-SH ... 10. SRTWC286-SH-UF`; stored `open_question` = `product_pick`, 10 options.

T2 "4": `decision answer/positions`, rules `open_question_answer_pick, answer_pending,
reuse_alive, domain_locked_by_pick`, fetch `incoming`, reply for SRTWC286-SH-NEW. Stored
afterwards: **`product_pick`, 10 options, answered_positions [4]** (still open).

User block the parser saw on T3 (verbatim, `Known brands` line omitted):

```
Previous response: Here's what you want:
• product: SRTWC286-SH-NEW

But no incoming matched these.
No incoming and no stock for SRTWC286-SH-NEW.

Would you like me to escalate to purchasing team?
Current user message: check stock
Current subject: domain incoming; product SRTWC286-SH-NEW.
Open question: {"kind":"pick_one","options":[{"position":1,"code":"SRTWC286-SH"},{"position":2,"code":"SRTWC286-SH-150"},{"position":3,"code":"SRTWC286-SH-200"},{"position":4,"code":"SRTWC286-SH-NEW"},{"position":5,"code":"SRTWC286-SH-NEW-150"},{"position":6,"code":"SRTWC286-SH-NEW-200"},{"position":7,"code":"SRTWC286-SH-NEW-P"},{"position":8,"code":"SRTWC286-SH-P"},{"position":9,"code":"SRTWC286-SH-PP"},{"position":10,"code":"SRTWC286-SH-UF"}],"owed":["pick"]}
Pending: the assistant is waiting for a product_pick reply.
Open question options: SRTWC286-SH; SRTWC286-SH-150; SRTWC286-SH-200; SRTWC286-SH-NEW; SRTWC286-SH-NEW-150; SRTWC286-SH-NEW-200; SRTWC286-SH-NEW-P; SRTWC286-SH-P; SRTWC286-SH-PP; SRTWC286-SH-UF
Profile:
Recent exchanges, oldest first:
User: incoming srtwc286
Assistant: incoming search needs to be more specific. ... 10. SRTWC286-SH-UF - no incoming / None of these have incoming stock right now.
User: 4
Assistant: (the Previous response)
```

The model is told, in the same block, that the assistant is still waiting for a product pick
from a list whose item 4 was the last reply. "check stock" names no entity, and the prompt says
a paraphrase is an answer and only a message naming a code, customer, order or "other topic" is
new. The production verdict (`user_goal "trying to check stock for the selected product"`,
`domain_in_message true`, `domain_hint null`, `intent_hint null`, `casual`, pick [4]) is the
prompt followed faithfully.

T3 engine path for each reading:

| Reading of "check stock" | Decision | Rules | Fetch | Reply | Stored after |
| --- | --- | --- | --- | --- | --- |
| A production verdict (casual, no domain, pick [4]) | answer / positions | open_question_answer_pick, answer_pending, reuse_alive, domain_locked_by_pick | incoming | the same incoming reply for SRTWC286-SH-NEW | product_pick [4] |
| B owner's sentence half obeyed (domain_hint inventory, intent check_stock, pick [4]) | answer / positions | same | incoming | incoming again | product_pick [4] |
| C legacy field only (inventory + reference_positions [4]) | answer / positions | answer_pending, reuse_alive, domain_locked_by_pick | incoming | incoming again | product_pick [4] |
| D owner's sentence fully obeyed (inventory, no pick) | carry / nothing_answered | answer_pending_not_an_answer, reuse_alive, domains_from_asks | inventory | "How many units of SRTWC286-SH-NEW?" (correct) | **product_pick [4], still open** |

T4 "5" after reading D (the dealer answering "How many units?"): the block shows
`Open task: stock check. Still needs a quantity for: SRTWC286-SH-NEW.` AND, below it,
`Open question: {"kind":"pick_one", ... 10 variants ...}` and
`Pending: the assistant is waiting for a product_pick reply.` The pending pick outranks the
stock task (`question.py:96`). With the pick the prompt asks for, the engine answered
`answer / positions`, `domain_locked_by_pick`, fetch incoming, reply for **SRTWC286-SH-NEW-150**,
stored answered_positions [4, 5].

### Why the owner's sentence did not change the reply

The sentence works on the model, and the model is not where the decision is. Readings A, B and
C show the engine answers incoming for every verdict that carries a pick, whatever it says about
the domain: `decide.py:263` never reads `domain_in_message` for a position, `apply.py:817`
re-domains to the roster, and `apply.py:3191` ignores `domain_hint`. The model kept the pick
because the block still says the pick is owed (`Pending: ... waiting for a product_pick reply`)
and the same prompt block tells it to null the domain when it answers. Even a perfect verdict
(D) only moves the failure one turn later, because the question is still stored.

### Case 2 ("stoick SRTWC286-SH-NEW" after the incoming pick)

Same harness, verdict `domain_hint null, domain_in_message false, entities [SRTWC286-SH-NEW]`:
`decision answer / label_match`, rules `answer_pending, reuse_alive, domain_locked_by_pick`,
fetch incoming. The typo is not the cause on its own: the typed code equals option 4's label
on the roster that is still stored, `_positions_by_label` (`decide.py:128`) turns it into a
pick, and the pick locks the domain. With no stored roster the message is an ordinary refine
over the carried focus and would still fall back to the carried domain (row 5 below).

### Case 3 ("7820 stock")

Not the picker. It is the resolver's forward/reverse split: `_has_exact_product_match`
(`references.py:1523`) exempts only a code-SHAPED token from the HAS branch, "7820" is digits
only, so `resolve_product_set` narrowed seven code matches to the two with stock and
`_strip_word_token_product_matches` dropped the rest (trace in PR #1351 round 2). The console's
five with zeros was `fetch.py:1033` `product_ids[:5]`. It belongs in the divergence table because
it is the same owner rule (code first, spec only when no code matched).

## 3. Divergence list

Owner methodology: a message is parsed for domain, intent and entities; entities resolve code
first, spec search only when no code matched; forward and reverse asking are the same from the
tool's view; a picker is a short-lived question that closes the moment it is answered; a
message with its own domain word is never a pick.

| # | Owner rule | What the code does | File:line | Case |
| --- | --- | --- | --- | --- |
| 1 | A picker closes the moment it is answered | roster kinds stay open after their pick, recording `answered_positions` | `pending.py:48`, `apply.py:872` | 1, 2 |
| 2 | ... | a turn that asks nothing new keeps the old question | `tail.py:32` | 1 |
| 3 | ... | a new ask closes the roster only if its subject is NOT one of the options | `apply.py:3400-3448` | 1 (D), 2 |
| 4 | ... | a non-answer keeps the question open "exactly as it was" | `apply.py:940` | 1 (D) |
| 5 | A message with its own domain word is never a pick | a parser position is an ANSWER without reading `domain_in_message` | `decide.py:263` | 1 |
| 6 | ... | the pick's domain overrides the message's own `domain_hint` | `apply.py:817-821`, `apply.py:3191-3208` | 1, 2 |
| 7 | ... | the prompt tells the model to null domain_hint and intent_hint when it answers | prompt "AN OPEN NUMBERED QUESTION" | 1 |
| 8 | ... | the prompt says paraphrases ("show me") are answers; only a code, name, order or "other topic" is new | same block | 1 |
| 9 | ... | "the roster stays on screen until its own topic changes" | prompt POSITIONAL REFERENCES | 1 |
| 10 | Parse for domain, intent, entities | the parser is also asked to decide pick vs ask, with a 7-mode answer object | parser schema `open_question_answer`, `parser.py:363` | 1 |
| 11 | ... | the parser block shows two open questions at once (pick and stock task); the pick hides the task | `question.py:96`, `parser.py:666-686` | 1 (T4) |
| 12 | ... | two contradicting clauses: "roster stays on screen" vs "that list was closed the moment one product was picked" | prompt POSITIONAL REFERENCES vs Last answered | 1 (T4) |
| 13 | A typed code is an entity, resolved code first | a typed code equal to an option label becomes a pick of the OLD question (and its domain) | `decide.py:128`, `decide.py:271` | 2 |
| 14 | No domain word: carry the domain | correct in principle; the typo "stoick" reads as no domain, so the carried incoming wins | `apply.py` domain chain `elif focus.domains` | 2 |
| 15 | Code first, spec only when no code matched | a digits-only fragment that matched by code still runs the HAS predicate | `references.py:1523`, `references.py:2642` | 3 |
| 16 | Forward and reverse identical from the tool's view | a predicate turn fetches only the first five ids; the page carry exists for "more" | `fetch.py:1033`, `turn_runtime.py:2733` | 3 |
| 17 | The picker is short-lived | escalation offers live three turns; business questions never expire | `pending.py:259-290` | general |
| 18 | One mechanism | the top-selling pick is already resolved in code from raw text, other picks by the parser | `engine.py:1630` vs `apply.py:2753` | general |

## 4. The smallest mechanism that meets the methodology

### Rules

1. **One-shot question.** The stored `open_question` lives for exactly the next inbound message.
   On that message it is either answered (consumed) or dropped. Nothing is sticky. The only
   thing that survives is the FOCUS (domain + subject), which is what the conversation is about.
2. **The engine owns the pick, before the parser.** A new pure module `turn/pick.py`
   (one function, about 100 lines) reads the message against the stored options and returns
   the positions or None. A message is a pick ONLY when the whole message, after trimming
   punctuation and a small filler set ("no", "number", "#", "the", "option"), is one of:
   - a number or a list of numbers in range ("4", "1,3", "1 and 3", "1 & 3");
   - an ordinal or number word in EN / MS / ZH / pinyin ("first", "second", "last", "pertama",
     "kedua", "satu", "dua", "第一个", "yi hao"): one table, about 40 words, beside the code;
   - an option's label or code, case and separator blind ("srtwc286-sh-pp", "SH PP");
   - an all-word over the list ("all", "semua", "both", "dua-dua", "全部", "都要");
   - for a confirm (one option or yes/no offer): a yes-word or no-word.
3. **A pick skips the parser.** The engine builds the verdict for a pick itself (the option's
   entity, the question's domain), exactly the verdict `_answer_pending` builds today, and the
   turn continues. Cheaper and deterministic.
4. **Anything else is an ordinary message.** The question is dropped, the parser runs with NO
   open question in its block (no `Open question`, no `Pending`, no `Open question options`),
   and the message is read for its domain, intent and entities over the carried focus. "check
   stock" becomes inventory over SRTWC286-SH-NEW; "stoick SRTWC286-SH-NEW" becomes a refine
   whose domain falls back to the carry (a separate, known gap: typo tolerance for domain words,
   which is a parser concern).
5. The stock quantity task (`focus.tasks`, "Open task:") is a different thing (a slot filler,
   not a picker) and keeps its lines for now; with no pending pick to hide it, `question.py:96`
   shows the task's own question again. Folding it into the same one-shot rule is phase 2.

### What gets deleted

Prompt (production registry, next `chatbot_semantic_parser` version, and the repo default):
- "AN OPEN NUMBERED QUESTION IS ANSWERED WITH reference_positions" (whole section).
- "THE OPEN QUESTION AND open_question_answer": the header, PICKING and CONFIRM parts (the
  QUANTITIES / LAST_ANSWER part stays until phase 2).
- POSITIONAL REFERENCES: the "roster stays on screen" clause and the bare-number clause.
- REFERENCE TARGET, if no reply still prints the dym marker (verify in the lane).
- INTENT & DOMAIN: the "This rule does NOT apply when the bare reply ANSWERS ..." exception.
- Number-words-are-positions clause; top selling "a bare number after a ranked list picks that
  row" and "ANSWERING CUSTOMER OR SALES AGENT?" position lines (the engine answers those).
- The owner's 28 Sep "decisive domain word is never an answer" sentence (no longer needed).
- Schema: `reference_positions`, `reference_target`, and modes pick / yes / no of
  `open_question_answer` (kept in `TOLERATED_ABSENT` for old recordings).

Engine:
- `parser.build_user_block`: the `Open question` (for picks), `Pending:` and
  `Open question options:` lines; `engine._pending_option_labels`; `question.of_pending`.
- `apply._open_pick_answer`, `_stock_pick_takes_position_and_quantity` (a pick with a quantity
  becomes two turns, or `pick.py` accepts "<pick> <number>" on a stock pick: open question 4).
- `decide.picked_positions`, `_positions_by_label`, `broadens_the_roster` (replaced by
  `pick.py`'s result); the pending half of `decide()` shrinks to "answered or not".
- `pending.ROSTER_KINDS`, `is_roster`, `with_answered_positions`, `tick`, `OFFER_TTL`;
  `apply._fully_answered_roster`, `_roster_is_about`, `new_ask_closes_stale_roster`,
  `answer_pending_not_an_answer` carry, `answer_pending_own_entities`, `offer_hold` re-print
  becomes a drop; `tail.py:32` `or state.pending`.
- `engine._top_selling_verdict` pick half (the generic pick covers it; its year and metric
  rules stay because they are not picks).
- `_answer_top_selling_pick`'s `with_answered_positions`.

What stays: `_answer_pending`'s EFFECTS (what a pick settles on the focus, the question's own
domain for a pure pick, escalation acceptance on an explicit position or the parser's
`is_escalation_confirmation`), the outstanding lane's document handling (`decide.py:583`
"named_document" already turns "Sales order" into a new ask, which is what a paraphrase becomes).

### Migration of the pins

Measured on main: 39 test files in `tests/chatbot` assert a non-empty `reference_positions`;
114 mention `product_pick` / `customer_pick`; 26 pin `answered_positions`; 14 pin
`is_roster` / `ROSTER_KINDS`; 11 pin `open_question_answer`; 52 journey files and 5 replay
corpus files carry `reference_positions` keys (all recorded empty or absent at the top level of
the corpus; the non-empty ones are in the py tests). Plan:
- Stub verdicts that pick by position: replace with the message text ("4"), since the engine now
  picks from text and never calls the parser for it. Mechanical.
- Tests that pin "the roster survives its pick" (contract 36, hand pass 9 D3, `tier_pick` second
  pick, top selling second rank): these pin the behaviour being retired. Rewrite to the new rule:
  a second number after an answered pick is an ordinary message (a quantity, or a miss).
  Needs an owner ruling (open question 2).
- Paraphrase-pick tests ("gimme the list plss", "the DO one"): re-pin as ordinary messages that
  resolve through the document path or ask again. Owner ruling (open question 3).
- Replay corpus: re-record after the prompt version ships; `TOLERATED_ABSENT` keeps old
  recordings readable.

### Risks

- Paraphrased picks ("the SH PP one", "gimme the list") stop being picks. Most resolve as
  ordinary asks (a code is an entity; "DO list" is a document); some become a re-ask. Accepted
  by the methodology, but the owner should see it (open question 3).
- The second-pick-from-the-same-list habit (a dealer picking 4 then 7 from one roster) now
  needs the list again, or a typed code. Case 1 shows why the habit is the bug.
- A word table in code crosses the D17 rule ("deterministic code never reads words"). The owner
  is overruling that rule with this design; say so in the plan. The precedent exists
  (`engine.py:1630`).
- Escalation offers lose their three-turn window; a "yes" two turns later no longer escalates.
  That is the owner's short-lived rule, and it removes the stale-yes risk AC-816 guards against.
- Multi-intent picks with extra words ("4, check stock too") become ordinary messages: the
  parser sees "4" with no list and emits no position. Acceptable: the reply asks.

### Estimate

- Lane 1 (engine owns the pick, one-shot close, parser block and prompt deletions, pins
  migrated): standard track, about 1 lane (diff well over 300 lines, mostly deletions and test
  rewrites; no migration; no auth).
- Lane 2 (optional, phase 2): the stock quantity task on the same one-shot rule, and the
  `open_question_answer` object retired entirely. About half a lane.
- The forward/reverse routing (case 3) is its own small lane, see section 5.

## 5. Ruling on the parked patches in PR #1351

| Patch | Ruling | Reason |
| --- | --- | --- |
| Round 1: five-product page removal (`fetch.py:1033` slice, `set_page` carry, "more" continuation) | **Keep, ship on its own** | Not a picker patch. It deletes a mechanism (paging) the owner already ruled out on 26 Sep ("never pages"), and #833 removes the same hunks. It is a deletion, not a hotfix layer, so it meets "simplest thing". |
| Round 2: code-fragment exemption (`_code_fragment_matched` beside `_has_exact_product_match`) | **Fold, as a rename of the one rule rather than a second exemption** | It is exactly the owner's rule ("found by product code -> forward; cannot find -> spec search"), but written as a second exception on top of the shape test. The smallest honest form is one predicate: "did any caller token match a product at a CODE tier (exact / prefix / substring / head_code / and)?" replacing `_has_exact_product_match`'s shape test. That is round 2's helper with the shape test deleted. Do it in the routing lane, not the picker lane. |

## 6. PR #1329 routing patches and #833

| Item | Ruling | Reason |
| --- | --- | --- |
| #1329 `domain_words.py` switch-word table + typo tolerance | **Drop** | It patches divergence 5 and 6 from outside: a second domain reader in code to out-vote a pick that should never have happened. With the one-shot question and the engine-owned pick, "check stock" never reaches a pick. The typo case ("stoick") is a parser spelling issue; the prompt already says "read for meaning not spelling". |
| #1329 decide.py rows (domain_in_message true + null domain_hint derives the domain) | **Drop** | Same reason; also a second domain source. |
| #1329 prompt clauses (decisive word never an answer; domain_in_message implies domain_hint) | **Drop the first** (the section it amends is deleted). **Keep the second** as a plain parser consistency rule; it is not picker machinery. |
| #1329 dealer incoming reply, merged identical rows | Keep (already the owner's ruling). |
| #833 attribute-first rewrite, as far as it touches the picker | **Keep the answer shape; drop its pick guards on rebase** | Measured on its diff (head `9c66a87a`): it does not touch `pending.py`, `decide.py` or the parser block, and its own comment says "a set answer mints no pick roster". But it adds five more defences of exactly the kind this report retires: `turn_runtime.py` sets `"reference_positions": []` on its count / "more" / "top 40" readings so a number over a counted set is not taken as a row pick, and `engine.py` comments that the positional rule "pulls a bare number toward reference_positions". Under the new mechanism the parser emits no positions and no list is stored after a set answer, so those guards are dead code: drop them when #833 is rebased. Its paging carry (`set_page`, "more") is removed by #1351 round 1 and should go too. Its `_CODE_MATCH_TIERS` vocabulary is the one the round 2 fold should use. |

## Numbered open questions (recommendation in bold)

1. Should a pick skip the parser entirely? **Yes: the engine answers a pure pick without a
   parser call; everything else is parsed with no open question in view.**
2. After a pick, is a second number from the same list still a pick? **No: the list closed on
   the first answer. A second number is an ordinary message (a quantity when a stock task asks
   for one, else read as-is).**
3. Paraphrased picks ("show me the DO one", "gimme the list"): pick or ordinary message?
   **Ordinary message. The DO/SO words already resolve through the document path; anything
   else re-asks.**
4. A pick with a quantity in the same message ("1, I need 2") on a stock did-you-mean?
   **Allow exactly "<pick> <number>" on a stock pick in `pick.py`; nothing wider.**
5. Escalation offers: one-shot like every other question, or keep the three-turn window?
   **One-shot.**
6. Which languages does the ordinal table carry? **EN, MS, ZH characters and pinyin, the four
   the prompt already lists; nothing else until a real message needs it.**
7. Ship #1351 round 1 now? **Yes, on its own, before the picker lane.**
8. Round 2 of #1351: merge as is, or fold? **Fold into one code-tier predicate in a small
   routing lane after the picker lane.**
