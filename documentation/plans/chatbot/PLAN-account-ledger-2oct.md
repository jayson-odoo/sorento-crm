# PLAN: "account N" in a chatbot message selects the [A/C N] ledger

Status: planning, FULL track (M: new parser key + engine rule; data-only prompt publish migration). Behaviour card filed 2 Oct 2026, awaiting owner answers.
Lane: ACCOUNT-LEDGER (branch `crew/account-ledger`). Card: `account-ledger-behaviour-card.md`.
UAC: `account-ledger-acceptance-criteria.md`.

## Owner ask (2 Oct 2026)

"account 1 means the A/C I ledger, so maybe the parser needs to emit this signal, maybe an
account parameter for the case of customer to be processed".

## Design (simplest thing that works)

1. **Parser key.** Per-entity `account` (string or null) in the strict schema
   (`app/services/chatbot/head/parser.py:139-193`, added to `required`). A small
   `ACCOUNT_LEDGER_ADDENDUM` in `app/services/chatbot_parser_prompt.py` teaches it: roman
   numeral, arabic converted, account words removed from `raw`; "my account N" or an account
   with no name in the message rides on a customer entity with `raw` null (or the carried
   customer, current_message false). Published as a new UNLABELLED version by migration
   `acct_ledger_0001_vocab` (pattern: `alembic/versions/chatbot_self_reference_vocab.py`);
   the owner moves the `production` label.
2. **Ledger rule, core.** `ledger_number(name) -> str | None` in `app/services/ledger_family.py`
   (no `re`, string ops, same reason as the module docstring): the `A/C <n>` marker inside
   any bracket, arabic and roman normalised to roman. `account_label(numeral)` -> "A/C I".
3. **Linked contacts.** `ContactCustomerScope.match_words` gains an optional per-word
   account: name match as today, then keep links whose `ledger_number` equals it.
   `engine._customer_scope_gate` passes the entity's account; a null-raw customer entity with
   an account narrows the links (the "my" / bare case). Nothing left -> refused with a line
   naming the contact's linked ledgers of that name only.
4. **Staff.** `resolve_gate.run`, right after `services.resolve_entity` and before
   `run_gate` (`app/services/chatbot/lanes/business/resolve_gate.py` ~1030): drop customer
   matches whose ledger differs from the asked account for that entity's token (resolutions,
   intersection, by_entity_type). The family grouping then sees one ledger. A token whose
   customer matches all fall out -> the turn refuses naming the ledgers the name has.
5. **Refusal plumbing.** Reuse `customer_scope_refused` in `engine.py` (~4126, ~5212) with
   the line carried as the turn's refusal text, so nothing new reaches the fetch path.

## Not in scope

- Non-numbered ledgers (`(PROJECT)`, `[CERAMIC]`, `(SRT)`): no "project account" signal.
- Customer-code ledger inference (bare row sharing 300-S002 with [A/C I]).

## Coordination

PR #1405 (PROMPT-DYNAMIC) turns the parser prompt into variables and ships owner text as a
version. This lane's prompt change is one trailing addendum + one schema key; whichever
lands second re-applies the addendum onto the other's text.

## Test list (red first)

- `tests/test_ledger_family.py`: `ledger_number` over real names (I-V, `(A/C 2)`,
  `[A/C II]-( KL OUTLET)`, `[A/C III] - PRICETAG`, bare, `(PROJECT)`).
- `tests/test_contact_customer_scope.py`: match_words with account; "[A/C I]" vs "[A/C II]".
- `tests/chatbot/test_account_ledger_scope.py`: engine scope gate (linked) and refusal line.
- `tests/chatbot/test_account_ledger_staff.py`: resolve_gate narrowing + picker of 3 + refusal.
- Parser schema test: `account` declared and required.
- Kill tests: revert each rule and confirm the matching test goes red.
