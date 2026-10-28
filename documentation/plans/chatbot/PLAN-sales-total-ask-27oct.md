# PLAN: sales total asks the basis (SALES-TOTAL-ASK)

Status: in review, crew audit round (owner rule: parser only) fixed (small fix track: chatbot, no migration, no
auth change). PR #1931. UAC: `sales-total-ask-27oct-acceptance-criteria.md`.

## Ruling

Owner, 27 Oct ~23:35 MYT: "total sales should ask". A chatbot question for a sales TOTAL
("total sales for X in Jan") asks the basis exactly like a sales ranking already does:
"Invoiced, delivered, ordered or outstanding?", Invoiced listed first. It never silently
defaults to Invoiced, and Outstanding is never defaulted either.

Owner rule, re-stated 28 Oct (crew audit of this PR): chatbot understanding comes from the semantic
parser only. No regex, word list or word-shape read of the message text, and no matching typed words
to option labels in code. A parser miss is fixed in the prompt and gated by the eval.

## Findings (main 798217119d)

- `sorento_crm_backend/app/services/chatbot/lanes/business/fetch.py:1224` set `basis` to
  `invoiced` on every `crm_sales_analysis` call whose parse named none: "total sales Jan 2026"
  (`order_status` sales_analysis) answered invoiced with no question.
- `fetch.py:440-441` comment still said "none is Delivered, the report's default".
- `head/parser_template.py:315` (sales_analysis rule) said "else null (invoiced is the default)".
  Inert on prod: the live text (prod v69, dev v188, crew's v68.txt) has no PARSER TEMPLATE block.
- `sorento_crm_mcp/sorento_crm_mcp/catalog.py` `crm_sales_analysis`: "`basis` ...; absent = invoiced".
- The report ask (`lanes/business/report_ask.py`, `settle` / `_given_choices`) already asks the
  basis for rankings AND axis-less totals: unchanged.
- `crm_sales_report` (one customer's or product's sales, delivered only) never asks either; lane
  REPORT-UNIFY (#1922) moves every sales report onto the report ask, which asks, so it is left to
  that lane (crew-note posted on #1922, acked).
- The route's own default (`app/api/v1/sales/analysis.py` `DEFAULT_BASIS`) serves API callers and
  the Sales pages; not the chatbot's question, unchanged.

## Change

- New `lanes/business/sales_basis_ask.py`: a `required_fields` slot (like `sales_company_ask`)
  asking `ranking_ask.RANKING_BASIS_LINE`; the next turn's parser is shown it as a pick_one with the
  four options, Invoiced first (`turn/question.of_required_ask`). The answer is ONLY the parser's
  declared answer: the option it picked (`picked`), else the basis it filled (`sales_basis` /
  `basis`). A reply the parser declared no answer for drops the question (`answered_by_parser`, no
  shape fallback); a declared cancel cancels; a declared answer naming no option is asked again,
  then given up. No code reads the typed text.
- `lanes/business/__init__.py`: the sales analysis condition is computed once
  (`sales_analysis_ask`); before the tool chain the basis is settled (asked when none is named,
  before the company question; an axis the analysis cannot draw is said first, as before).
  Invoiced / delivered / ordered run `crm_sales_analysis` with the first message's axes;
  outstanding (the analysis has none) runs the report ask's outstanding orders by channel (or by
  month), in RM, over the first message's period or this calendar year to today.
- `fetch.py`: no invoiced default in the `crm_sales_analysis` builder.
- Parser template line and MCP description say the basis is asked.

## Parser contract and gate

- Gold rows `scripts/chatbot_eval/gold/parser_sales_total_ask.jsonl` (graded on the new
  `sales_basis` key in `parser_gold.py`): "total sales Jan 2026" (and Malay) -> `sales_basis` null;
  a named basis -> that basis; under the shown pick_one question, "1", "2", "invoiced", "delivered",
  "ordered", "outstanding", "已开票" -> `answer_mode` pick with that option's position (the pick is
  the contract; the lane also accepts a declared fill); "stock for SRTWC286" -> no answer.
- The live text's sales basis rule already reads "none said -> null" (`chatbot_prompt_diet_edits.py:232`).
  Whether it declares the picks is what the gold run on v188 decides (crew: Gemini org key, cap
  USD 0.25/run); a miss gets a prompt edit against v68.txt and a re-run, never a code rule.

## Tests

`tests/chatbot/test_sales_total_ask.py` T1 to T22 (lane and real-engine turns), red first, kill-tested.
T15 runs on the live text when crew points `SALES_TOTAL_ASK_PROMPT_FILE` at it.
Existing tests that ran a basis-less sales analysis now name the basis (listed in the PR body).
