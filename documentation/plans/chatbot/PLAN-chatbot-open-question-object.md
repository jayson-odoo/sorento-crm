# PLAN - Chatbot: one open-question object for every question the bot asks, answered by the parser

Status: built 26 Sep 2026 (issue #1293, PR #1294), W1 to W4 done, W5 (live console pass) owed
to the orchestrator: this VM has no parser key. The prompt goes live once the version
`oq_0001_parser_open_question` publishes is promoted. Track: small fix track by intent (no auth,
RBAC or permission change, no new external ingest surface), with one data migration that
publishes a parser prompt version (no schema change). Branch
`claude/chatbot-open-question-object-1t9q4k`, stacked on PR #1247's head `b896380f` with
`origin/main` merged in; rebased once #1247 lands.
Issue: #1293. Continues PR #1247 round 8 (`PLAN-chatbot-stock-ask-v2-24sep.md`).
UAC: `chatbot-open-question-object-acceptance-criteria.md`

## The owner's words (binding)

> "I think round eight is pretty good already. It's just that there's a bit of an inhuman in the
> recent conversation. Like I want to say 'the first one I need two'. It's quite weird that it
> replies in that way. So maybe our parser can be better. And I'm also curious in your
> methodology in making this work because I want to make sure this is as human and as natural
> as possible and not too much hard coding, hard routing."

The exchange (:3087, 26 Sep 14:07Z to 14:08Z, contact 437264483):

```
check stock STWC2867 ...
-> Couldn't find STWC2867. Did you mean: 1. SRTWC286-SH 2. SRTWC286-SH-P
the first one, I need 2
-> STWC2867 x 2: which one? 1. SRTWC286-SH 2. SRTWC286-SH-P
1, I need 2
-> (the same reply)
SRTWC286-SH x 2
-> SRTWC286-SH x 2: the quantity is more than what I can confirm here, please refer to your salesman.
```

Standing rulings kept: every message goes through the parser; no timers; no "more"/"next"
paging; full counts; no silent defaults (clarify); the fixed reply sentences stay.

## Diagnosis

Round 8 gave the parser the open question as an object only for the stock QUANTITY question
(`task.open_question`, kind `stock_quantities` / `last_answer`), and only when nothing else was
pending. The did-you-mean list is a `product_pick` pending: the parser saw it only as the flat
`Open question options:` line and could answer it only with `reference_positions`. The live
parser read "the first one, I need 2" as `demand_qty 2` (with or without a position), and
`apply._stock_pick_requantified` then took ANY stated quantity under an open stock pick as "the
quantity, not a pick": it re-asked the pick carrying the 2, with the header
`pick_question(typed, ...)`, which printed the code the resolver had NOT recognised
("STWC2867 x 2: which one?"). A message that answers the pick and the quantity in one breath
was half understood, by a shape rule.

## Method: the parser READS, the code APPLIES (the design rule)

1. **Every question the bot asks is an open question object.** One pure builder,
   `turn/question.py::open_question(pending, tasks)`, states whatever is on the table:
   the open pending (a pick list, a confirm, a brand roster) first, else the stock
   quantities question. Its shape:
   `{"kind", "options": [{"position", "code", "label"?}], "owed": [...], "qty"?}` for a
   question over options, `{"kind": "quantities", "status": "asked"|"answered", "items":
   [{"position", "code", "qty"}], "owed": [positions], "asked_qty"?}` for the quantities.
   It never carries a code the resolver did not recognise.
2. **Kinds** (`QUESTION_KINDS`): `pick_one` (a numbered list; "both", "all", "1 and 3" still
   pick several), `quantities`, `confirm` (a yes/no, or a one-option did-you-mean),
   `choose_brand` (a `brand_pick` roster), `free` (a question with no options).
   `how_many_to_show` is NOT a kind: no reply asks it (full counts, no paging, standing
   rulings). Trigger to add it: the first reply that asks how many rows to show.
3. **The parser returns one declared answer object**, `open_question_answer`, strict-schema
   safe (fixed keys, list of fixed-shape items): `mode` pick | yes | no | fill | all | done |
   cancel | null, `items` [{position, code, qty}], `qty_for_all`. Which options were picked
   (by position, by code, by ordinal word, by "both"/"all"; "none" is `no`), which quantities
   for which lines, a confirmation, or `null` = "not an answer", in which case the rest of the
   verdict IS the new ask, read as usual. The parser sees the object plus the last three
   exchanges (round 8's `Recent exchanges`).
4. **The apply layer acts on the object.** `apply._pick_answer` writes a pick onto the
   fields the pick path already reads (`reference_positions`, `is_affirmative`) and the
   quantities onto the pick itself (`payload.picked_qty`), which `_spend_stock_pick` stamps on
   the fetch. `apply._open_question_answer` (round 8) does the same for the quantities. The
   shape rules run ONLY when the object is absent, mode null, or unusable (an item that places
   on no option): `_stock_pick_position_takes_quantity` (a position on the list beside a
   quantity is the pick at that quantity), round 4 to 8's bare-number rules.
5. **No new keyword routing.** Nothing in `turn/` reads a message word. Ordinals and numbers in
   English, Malay and Chinese ("the first one", "second", "both", "1 and 3", "dua", "yang
   pertama", "第一个", "san ge") are in the parser's question contract (the prompt), never in
   code. If a fix needs "if the message contains 'first'", it goes in the contract instead.
6. **Headers never repeat an unrecognised code.** A did-you-mean's own first sentence names the
   miss ("Couldn't find STWC2867."), and that fixed sentence stays. Every later line leads with
   a recognised code: once the pick resolves the answer is the presenter's "SRTWC286-SH x 2:
   ...", and a quantity with no pick asks "Which one do you need 2 of?" over the numbered
   options. A family the dealer typed and the resolver recognised ("SRTWC286 x 88: which
   one?") keeps its header.

## Work items

- **W1** `turn/question.py` (the object and the kinds); `task.open_question` renamed to the
  `quantities` kind; the engine states the object for any open question; the schema's `mode`
  gains pick / yes / no; the prompt section rewritten as the general contract; a migration
  (`oq_0001_parser_open_question`) publishes the new fallback as the next
  `chatbot_semantic_parser` version through s4's `publish_policy_blocks`, label unmoved.
- **W2** the did-you-mean pick answered with or without a quantity in the same message
  (`_pick_answer`, the fallback, the header).
- **W3** ordinals and numbers in three languages, in the prompt contract only.
- **W4** the owner's 26 Sep console sessions (07:18Z, 08:18Z, 10:11Z, 14:06Z on contact
  437264483) replayed through `engine.run_turn` with the parser stubbed as it should answer,
  plus ten natural phrasings per question kind.
- **W5** a live console pass when the VM has a parser key; else the exact orchestrator steps.

## Tests

`tests/chatbot/test_chatbot_open_question_1293.py` (object, contract, the owner's exchange,
phrasings) and `tests/chatbot/test_chatbot_open_question_1293_replay.py` (the four sessions
through `engine.run_turn`). Red first, then green; every repair kill-tested.
