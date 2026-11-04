# Parser prompt change: report frame, one name one slot, message basis, held filters (CHATBOT-TOTALS-FILTERS)

Base: #2105's candidate, md5 `e4aa6d43fedd996579b8c1caa2c54556` (unlabelled; production is still v70, md5 57d7d412).
Result: md5 `1b5768554f62851002e99137f546ce41` (109,627 chars). Not published; only the owner moves the production label.
Plan: `PLAN-chatbot-totals-filters-4nov.md`. UAC: `chatbot-totals-filters-acceptance-criteria.md`.

Owner rule kept: no gold-message examples and no word lists. Every new line is a slot rule. The code side adds `frame` to
`parser.REPORT_ASK_KEYS` (schema + `Held report:` line).

Four edits, all inside the `== REPORT_ASK ==` section. Apply each by its anchor.

## Edit A: the object shape gains `frame`

Anchor: `{"kind": "sales|outstanding", "basis": same values as basis,`

```text
{"kind": "sales|outstanding", "frame": "total|breakdown|ranking", "basis": same values as basis,
```

## Edit D: the full-new-ask bullet (owner ruling 3 Nov: a held filter survives until the user changes it), then two new bullets

Replaces the bullet that starts `  - A message that asks a report again in full,`.

```text
  - A message that asks a report again in full, with its own report word, its own subject and its own period, still keeps every held filter it does not change: basis, channel, company and every list stay as held until a message changes or widens them. Its frame, group_by and top_n are this message's own.
  - frame is what the report gives back. total: one figure over every row the filters keep; group_by and top_n null. breakdown: one row per value of group_by, every row; top_n null. ranking: the rows of group_by in order, cut to a count or a direction. A message that changes only filters, the period or the basis keeps the Held report's frame, group_by and top_n. A message that asks for a total sets frame total with group_by and top_n null, whatever the Held report had. A message that asks to see two or more values of one slot side by side is a breakdown on that slot's group_by.
  - One name, one slot: a name that is both the company and a Brand candidate, or that fits any two lists, goes in the slot the message's kind word names (the word company -> company, the word brand -> brands, account type -> account_types), and its entity's kind_said is that word. When the message names two kinds for it, it goes in both slots and kind_said holds both words. With no kind word it goes in brands with kind_said null (the assistant asks which). A reply to the assistant's question about which one puts the name in the slot or slots the reply names. The same name sits in two slots only when the message or the reply names both.
```

## Edit C: the message's own basis is also on the top level

The parenthesis that starts `(The top-level basis, sales_basis` gains one sentence before its closing bracket:

```text
When this message says a basis, the top-level sales_basis is that same basis.
```

## Why each edit

| Edit | Failure (replay row) | What the engine does with it |
|---|---|---|
| A + frame bullet | F1: the ranking asks on a breakdown (new path C5) or a total (owner, prod) | `from_object` reads `frame` (M1); total never asks a count or a measure |
| one name, one slot | F2: "sorento company only" filled both company and brands (B4, C4); owner Q2 (c): a bare name asks once, both must work | the parser fills the slot(s) the words name; the engine asks once when no kind is said (M2) |
| C | "Total sale deliver ..." asked the basis 3 times (new path A1-A3): the object had delivered, the top level did not, and the V1 never-default guard dropped it | V1 unchanged |
| D | Q3 ruling (crew, 4 Nov): held filters survive a complete new question | carry already follows the object |

## Gate results

(filled after the gates: gold rows `sorento_crm_backend/scripts/chatbot_eval/gold/parser_report_totals_filters.jsonl` x1,
#2105's 16 rows as regression, parser-gold TRAIN no-op control both arms; gemini-3.5-flash-lite, ledger lines)
