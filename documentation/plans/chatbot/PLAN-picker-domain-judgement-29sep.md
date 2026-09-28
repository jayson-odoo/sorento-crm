# PLAN: a pick never overrides the message's own domain; the parser reports, the engine judges

Issue #1352. Status: in review (PR #1353); the parser version publish waits on the owner's label move. Small fix track by rule shape (no auth, no RBAC, no new
ingest surface) but carries one prompt-version data migration, so it runs the migration
gates of the standard track. UAC: `picker-domain-judgement-29sep-acceptance-criteria.md`.

Branched from origin/main `484d0364d59c22615a1a112afce7e90687ccf508`.

Evidence base: the scout report on `scout/picker-mechanism` (commit `a25092ff`,
`documentation/plans/chatbot/SCOUT-picker-mechanism-28sep.md`). Its mechanism map, traces,
divergence list and pin census are used here. Its PROPOSAL (an engine-owned pick table and a
one-shot close) is rejected by the owner and is not built.

## The methodology, in the owner's words

- 29 Sep 00:4x MYT: "code first hotfix and patching approach is wrong, i think we should see
  how we work out our picker, like the mechanism in which how we retain the picker, is very
  wrong"
- 29 Sep 00:5x MYT: "no I don't like this, I want the resolving to be still semantic, otherwise
  it is fragile, we need to find a methodology to maintain the sticky picker while solving our
  problem"
- 29 Sep 01:0x MYT: "ok this logic sounds good, but does it handle for like multi turn of
  different picker, like the outstanding, initially it ask for some customer picker, then ask
  for DO or SO, also like the top 100 selling item, initially ask for quantity or amount, then
  ask for top X if the user didn't specify, does this methodology stand against that? also i
  thought the resolving of typed code to the reference position is the parser job? like if we
  offer pick 1. A, 2. B, if the user answer B, the parser should be able to know it is
  position 2 and output reference position 2?"

So:

- **KEEP** the sticky roster exactly as retained today: `turn/pending.py` `ROSTER_KINDS` /
  `is_roster`, `with_answered_positions`, and `turn/tail.py`'s `answer.question or
  state.pending` carry. A roster closes only on the two rules it closes on today (every
  option picked, or a new ask about a subject not on it).
- **KEEP** the parser's semantic pick resolution: a number, a number word, an ordinal, a
  paraphrase, and a typed option label are all resolved to a reference position BY THE PARSER.
- **CHANGE**: the parser reports, the engine judges. The parser fills every field honestly on
  every message (the pick when it sees one, AND the domain fields as the message itself says);
  the engine reads the pick together with the domain fields and decides which domain the
  answer belongs to.

No word table in code, no one-shot close, no new domain reader beside the parser.

## Why case 1 failed (from the scout's trace, reproduced again on 484d0364)

"incoming srtwc286" -> "4" -> "check stock": the roster is still stored after "4"
(`with_answered_positions`), so the parser is shown it again and the prompt tells it to answer
a pick "and NOTHING else: entities [], domain_hint null, intent_hint null". The engine then
trusts any pick over any domain signal: `decide.picked_positions` returns the position with no
domain check, `_answer_pending` re-domains the turn to the roster's domain (apply.py ~817) and
the lock at apply.py ~3191 ignores `domain_hint`. Measured on this branch's base with the
console harness (`tests/chatbot/_r9_engine_console`): the verdict `domain_hint inventory,
domain_in_message true, reference_positions [4]` for "check stock" runs
`crm_incoming_stock_list` and rules `answer_pending, domain_locked_by_pick`.

## The judgement table (engine, `turn/decide.py` + `turn/apply.py`)

"Domain word" means the parser's own `domain_in_message: true` together with a domain it
named (`domain_hint`, or `asks`). `asks` alone also counts (hand pass 6 defect 1, unchanged).

| Row | Message (parser report) | Engine judgement | Roster after |
| --- | --- | --- | --- |
| J1 | pick, no domain word ("4", "the fourth", "four") | the pick, in the ROSTER's domain (today's behaviour, unchanged) | stored, position recorded |
| J2 | domain word, no pick ("check stock") | an ordinary ask on that domain over the carried subject | stored unchanged, for a later pick |
| J3 | pick AND domain word ("4 stock", "stock for the 4th", or "check stock" with the pick replayed) | the pick, in the MESSAGE's own domain | stored, position recorded |
| J4 | a typed option label ("SRTWC286-SH-NEW", "B") | the parser's reference position, judged by J1 / J3 | as J1 / J3 |
| J1b | pick AND a domain word naming the roster's own domain ("incoming for the 4th" over an incoming roster) | exactly J1, the roster's carried status included (AC-1704) | stored, position recorded |
| J5 | `domain_in_message: true` but no domain named (an inconsistent verdict; the new prompt rule forbids it) | nothing to judge against, so J1 (today's behaviour) | as J1 |

J4 detail: the parser resolves the typed label to its position (owner ruling 3, 01:0x). The
engine's own label match (`decide._positions_by_label`, a fallback for verdicts that carry the
code but no position) already reads `domain_in_message` and is unchanged: a typed label with
a domain word of its own is read as the entity it names, asked in the message's domain, which
is the same answer J3 gives.

J5 is flagged on the PR as an open question: it is the production verdict of case 1 on the
old prompt (`domain_in_message true, domain_hint null, pick [4]`). The prompt consistency rule
is what removes it; the engine keeps today's behaviour for it rather than inventing a rule.

Where each row lives:

- `decide.Decision` gains `own_domain: bool`, read once off the verdict by
  `decide.names_its_own_domain` (J1 to J5). `picked_positions` is unchanged in what it
  returns (the parser's semantic pick always counts); the Decision carries the domain half.
- `apply._answer_pending`: after building the picked entity, writes the roster's domain (and
  its carried status) onto the focus ONLY when the decision is not `own_domain`; on
  `own_domain` it leaves the domain to `_focus_rules` (which reads `asks` / `domain_hint`)
  and returns `domain_locked=False`. Rule names: `pick_in_roster_domain` /
  `pick_in_message_domain`.
- `apply.apply` domain chain: the branch that fired `domain_locked_by_pick` and ignored
  `domain_hint` is replaced by the J1 branch `pick_in_roster_domain`, reachable only when
  the message named no domain of its own. `domain_locked_by_pick` is retired.
- `apply._narrow_and_plan`: a kind a pick just settled is fetched as the picked option,
  never re-read from the resolver's candidates for the same message's typed code. This is
  AC-1704's existing focus rule ("a kind a pick just settled is not replaced again by this
  same turn's own entities") applied at the fetch seam too. It became reachable because a
  typed option code is now its position AND its entity (J4): measured, "stoick
  SRTWC286-SH-NEW" with position 4 fetched four variants (the resolver's prefix match on
  the code) until this line.

## Chained questions

Rule (owner ruling 2, 01:0x): the current question is shown to the parser as today; the engine
judges each message against the CURRENT question first; a domain word the current question
does not take is an ordinary ask over the carried subject; earlier rosters stay stored
underneath for a later bare pick.

| Flow | Current question | What answers it | Proof |
| --- | --- | --- | --- |
| Outstanding: customer pick, then SO / DO | `outstanding_scope` / `outstanding_detail` | a document word (`named_document`), a position (`picked_scope`) | `test_outstanding_lane.py`, journeys `outstanding-*`, `handpass5-outstanding-domain`, `handpass7-outstanding-quantity-domain`, `parity-f2-customer-picker-and-pick`, unchanged |
| Top selling: quantity or amount, then top X | `focus.top_selling` waiting for a metric / a count | the metric word / a number (`_top_selling_rules`, `engine._top_selling_verdict`) | `test_top_selling_*`, unchanged |
| Stock: the quantity task under a stored product roster | the stock task's "How many units of X?" when it was asked AFTER the roster | a bare number is that product's quantity, not a pick from the roster underneath | new AC-PK014 test; `handpass6-*`, `handpass9-*`, `stock-incoming-multipick-word-number`, unchanged |

The stock row is the one chained case the engine got wrong: the scout's T4 ("5" answering
"How many units?" with the roster still stored became a pick of variant 5 and fetched incoming).
`apply._bare_position_is_the_quantity` already turns a lone position into the stock task's
quantity, but only when no pending is stored at all. It now also applies when the stored
pending is a roster that was asked BEFORE the stock task was last touched (the task is the
current question) and the message names no domain of its own. The pending pick stays stored.

Top selling and outstanding need no engine change: their own arms already judge against the
current question first. The J3 rule is applied only on the generic roster path; a
`top_selling_pick` row keeps its own arm (it re-runs the ranking for the row; building a stock
ask from a ranking row is not covered by the rulings and is asked on the PR).

## The prompt diff

Repo default `app/services/chatbot_parser_prompt.py` AND a new unlabelled
`chatbot_semantic_parser` version published by migration `chatbot_picker_domain_1352`
(the `chatbot_top_selling_vocab_r6` pattern: idempotent on template equality, production label
unmoved; only the owner moves it).

1. "AN OPEN NUMBERED QUESTION IS ANSWERED WITH reference_positions": "emit that option's number
   in reference_positions and NOTHING else: entities [], domain_hint null, intent_hint null,
   order_status null, message_type "casual"" is replaced by "emit that option's number in
   reference_positions, AND fill every other field as the message itself says". Two examples
   are added ("4 stock" and "check stock" over a product roster). "Never emit BOTH an entity
   and a reference_position" goes: a typed option code is its position AND the entity the
   message names.
2. DOMAIN IN MESSAGE gains the consistency rule: domain_in_message true means domain_hint is
   non-null (the domain that word names).
3. POSITIONAL REFERENCES keeps the sticky roster sentence; "A LINE BEGINNING Last answered:"
   drops "that list was closed the moment one product was picked from it, and there is nothing
   left for a number to point into" (the contradiction) in favour of: the number is the
   quantity because the stock check is the question being answered, whatever list is still on
   screen.
4. THE OPEN QUESTION AND open_question_answer: one sentence added: a pick is reported in
   open_question_answer and the domain fields are still filled as the message says.
5. The owner's 28 Sep production sentence ("a decisive domain word is never an answer") is not
   in the repo default and is not in the new version (superseded).

## Pin migration

`domain_locked_by_pick` is asserted in exactly one file (measured, `grep -rl`):
`tests/chatbot/test_roster_label_vs_ask_24sep.py` (three `in` asserts at lines 140, 158, 231
and four `not in` at 99, 123, 180, 208). The `in` asserts move to `pick_in_roster_domain`
(each is a bare pick with no domain word, J1); the `not in` asserts stay true as written and
gain `pick_in_message_domain` where the verdict names its domain. The test that pins the prompt
text (`test_rearch_handpass3_owner_17sep.py` row 8) reads only the number-word examples, which
stay. Any other pin a red test names is quoted in the PR's closing comment.

Replay corpus: the prompt change does not change any recorded verdict's shape; nothing is
re-recorded unless the replay suite says so, and `TOLERATED_ABSENT` stays for old recordings.

## Risks

- A parser on the NEW prompt that fills the domain fields on a bare pick it previously blanked
  ("4" after an incoming turn, domain carried from context): J1 depends on
  `domain_in_message`, not on `domain_hint`, so a carried `domain_hint` with
  `domain_in_message: false` still answers in the roster's domain.
- Stored rosters now meet more messages with their own domain word; J2 keeps them stored,
  which is the owner's ruling ("the pick needs to retain to a certain extent").
