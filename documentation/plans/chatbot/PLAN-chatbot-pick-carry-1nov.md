# PLAN: a picked customer is replaced by a code match (CHATBOT-PICK-CARRY, 1 Nov 2026)

**Status: in progress. Small fix track (no migration, no auth/RBAC change, no new ingest surface). Size S.**
UAC: `chatbot-pick-carry-acceptance-criteria.md`.

## Owner report

Chatbot Console, prompt v70. "Dealer <customer> oct total sales" asks which customer (1. dealer A, across two companies;
2. dealer B). "1" asks the sales basis. "invoiced" answers with ledger A1 (a project ledger of dealer A) and ledger Z, a
different customer in the other company, Total RM 0.00. Neither was offered or picked.

## Facts, measured

- Account codes are per company. On the crew copy one account code is two rows: A1 in one company, Z in the other, the exact
  two names in the owner's reply (`GET /order-management/customers/select?company_scope=grants&query=<code>`).
- A roster option for several ledgers carries one code. `apply._answer_pending` (`turn/apply.py:889-906`) writes every
  picked row with that one `canonical_code` and its own `uuid`, so nine picked rows on the copy all read one code.
- The parser is shown that code: the open question lists `{"position":1,"code":"<code>",...}`.
- A parse that echoes the option's code or label beside the pick is KEPT by `engine._with_the_picked_axis`
  (`engine.py:1033-1042`, `names_a_pick`), so the resolver looks it up (`resolve_gate`) and finds every company's row.
- `turn_runtime._entities_for` (`turn_runtime.py:5941-5951`) keeps a resolver row when its CODE matches a plan row, and once
  a kind is "answered" drops the plan's own rows of that kind. The picked uuids are replaced; the sales ask's slot holds
  the replacement (`report_ask.py:1391`), and the next turn runs it.
- Engine-level reproduction: an echo of the code at turn 2 gives `[A1, Z]`, the owner's shape; an echo of the name gives
  `[A1]`, the pick cut to one ledger. The focus stays right in both; only the fetch rows are wrong.

## Leads checked and ruled out (with evidence)

- Second clarify as such: the slot carries `customer_ids`; with no echo all picked ledgers reach the report (copy, 3 runs).
- Roster still open at turn 3, parser re-emitting `picked [1]`: reproduced on the copy, same parse as the owner's. The slot
  takes the answer first (`required_ask` `verdict_rule: required_ask_answer`) and the customer is kept. "1" there is the
  basis option Invoiced. Pinned by a guard test.
- "brand SORENTO (SRT) held" as the customer's "(SRT, MCH)" suffix: no. That label is the brand list's own row
  (`head/lookup_lists.py:546-560`). Seeding `focus.brands` on the copy reproduces the block and the customer is kept.
- "No customer held" in the same block: the same on copy runs that carry the customer right. It lists lookup rows only.

## ARCHITECTURE

- **Layer:** the turn runtime, between the resolver and the fetch (`_entities_for`). Not the parser, not the prompt, no
  word rules; nothing reads the typed text.
- **Shared mechanism:** a row holding a `uuid` is settled, which `carried_entities_except` already states. The fix makes
  the code match honour it, for every kind and every lane that fetches.
- **Classes fixed:** a settled row replaced or cut by a same-code row: a multi-ledger customer pick; a one-company product
  option whose code exists in another company; any later turn on which the resolver returns that code. Not one shape.
- **Explicit links only (owner rule):** a pick's ledgers come from the option, never from a re-match by code or name.
- **Prompt:** unchanged, so the prompt pinning gates do not apply.

## Fix

`_entities_for`: a resolver row answers for a code the plan holds settled only when it is one of the plan's own uuids; the
plan's settled rows of a code the resolver returned stay. A code the plan holds no uuid for (a word typed this turn) keeps
today's match. Add the `_with_the_picked_axis` change only if a test shows the kept echo still harms the turn.

## Tests (red first)

`tests/chatbot/test_chat_pick_carry.py`, engine level, real gate, parser and resolver faked, fake customers:
the owner's three turns with the code echo (red), the name echo (red), no echo (guard), "2" at turn 3 is Delivered with the
same customer (guard), plus unit guards on `_entities_for` for a word typed this turn.

## Separate defect, not in this fix

Invoiced sales for a contact with a location cap: `reports/ask.py:291` caps by policy, `billing_document_lines.py:118`
refuses any location, so the reply is "I could not fetch sales just now" (422 `location_needs_order_basis`). Whether such a
contact may see invoiced figures at all is an access decision: filed with crew as a question, not decided here.
