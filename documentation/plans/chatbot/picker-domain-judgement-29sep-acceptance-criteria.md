# UAC: picker domain judgement (issue #1352)

Plan: `PLAN-picker-domain-judgement-29sep.md`. Every AC is pinned by a named test; the closing
PR comment maps AC -> fix -> file:line -> test.

Harness for the journeys: `tests/chatbot/_r9_engine_console.EngineConsole` over
`engine.run_turn` (real engine, resolver, presenter; parser verdict and MCP read stubbed), the
SRTWC286 family seeded (10 variants).

## Judgement rows

- **AC-PK001 (J1)** A pick with no domain word of its own answers in the roster's domain.
  "incoming srtwc286" -> "4" answers incoming for SRTWC286-SH-NEW; rule `pick_in_roster_domain`;
  the roster stays stored with answered position 4.
- **AC-PK002 (J2)** A domain word with no pick is an ordinary ask over the carried subject.
  "incoming srtwc286" -> "4" -> "check stock" (verdict inventory, no position) answers stock
  for SRTWC286-SH-NEW and the roster is still stored, unchanged.
- **AC-PK003 (J3)** A pick AND a domain word answers the pick in the message's own domain.
  "4 stock" answers stock for the 4th option; "check stock" whose verdict replays pick [4]
  beside `domain_hint inventory, domain_in_message true` answers stock for SRTWC286-SH-NEW;
  rule `pick_in_message_domain`; the roster stays stored; the roster's carried status is not
  written onto a turn in another domain.
- **AC-PK004 (J4)** A typed option label is the parser's reference position, judged the same
  way. "stoick SRTWC286-SH-NEW" after an incoming pick with a parser reading of inventory
  (position 4, entity SRTWC286-SH-NEW) answers stock; the same message read as the entity alone
  (no position) is an ordinary stock ask, and the roster stays stored.
- **AC-PK005** After AC-PK002 or AC-PK003, a later bare "7" picks option 7 from the still
  stored roster, in the roster's domain (incoming for SRTWC286-SH-NEW-P).
- **AC-PK006 (J5)** `domain_in_message: true` with no domain named is judged as no domain
  word: the pick answers in the roster's domain (today's behaviour).
- **AC-PK007** A pick whose own domain word is the roster's own domain ("incoming for the
  4th" over an incoming roster) answers exactly as J1, the roster's carried status included.

## Chained questions

- **AC-PK010** Outstanding: customer pick then the SO / DO question works unchanged
  (`test_outstanding_lane.py`, journeys `outstanding-*`, `parity-f2-customer-picker-and-pick`).
- **AC-PK011** Top selling: the quantity-or-amount question then top X works unchanged
  (`test_top_selling_*`).
- **AC-PK012** The stock quantity task journeys work unchanged (`handpass6-*`, `handpass9-*`,
  `stock-incoming-multipick-word-number`).
- **AC-PK013** A domain word the current question does not take is an ordinary ask over the
  carried subject; the earlier roster stays stored underneath and a later bare pick reads it.
- **AC-PK014** A bare number answering the stock task's "How many units of X?", asked after a
  product roster, is X's quantity and never a pick from that roster; the roster stays stored.

## Prompt rules

- **AC-PK020** The open numbered question block no longer says "NOTHING else: entities [],
  domain_hint null, intent_hint null, order_status null, message_type casual"; it says every
  other field is filled as the message itself says.
- **AC-PK021** Consistency rule: domain_in_message true means domain_hint is non-null.
- **AC-PK022** The sticky roster wins: "that list was closed the moment one product was picked"
  is gone; "the roster stays on screen until its own topic changes" stays.
- **AC-PK023** The owner's 28 Sep production sentence ("decisive domain word is never an
  answer") is absent from the repo default and the new version.
- **AC-PK024** "Never emit BOTH an entity and a reference_position" is gone; a typed option
  code is its reference position.
- **AC-PK025** The text is published as the next `chatbot_semantic_parser` version by
  migration `chatbot_picker_domain_1352`, idempotent, production label unmoved, one alembic
  head.

## Deleted engine rules

- **AC-PK030** `_answer_pending` no longer re-domains the turn to the roster when the message
  names its own domain (apply.py, the "Contract 121: a pick never re-domains the turn" write).
- **AC-PK031** The domain lock that ignored `domain_hint` under a pick is gone;
  `domain_locked_by_pick` never fires.
- **AC-PK032** `decide()` reads the domain fields together with the position:
  `Decision.own_domain` is set from the parser's own `domain_in_message` + `domain_hint` /
  `asks`, and appears in the decision trace.
