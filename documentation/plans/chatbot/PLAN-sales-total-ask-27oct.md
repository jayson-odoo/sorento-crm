# PLAN: sales total asks the basis (SALES-TOTAL-ASK)

Status: in review, reviewer READY (small fix track: chatbot, no migration, no auth change). PR #1931.

## Ruling

Owner, 27 Oct ~23:35 MYT: "total sales should ask". A chatbot question for a sales TOTAL
("total sales for X in Jan") asks the basis exactly like a sales ranking already does:
"Invoiced, delivered, ordered or outstanding?", Invoiced listed first. It never silently
defaults to Invoiced, and Outstanding is never defaulted either.

## Findings (main 798217119d)

- `sorento_crm_backend/app/services/chatbot/lanes/business/fetch.py:1224` set `basis` to
  `invoiced` on every `crm_sales_analysis` call whose parse named none: "total sales Jan 2026"
  (`order_status` sales_analysis) answered invoiced with no question.
- `fetch.py:440-441` comment still said "none is Delivered, the report's default".
- `head/parser_template.py:315` (sales_analysis rule) said "else null (invoiced is the default)".
- `sorento_crm_mcp/sorento_crm_mcp/catalog.py` `crm_sales_analysis`: "`basis` ...; absent = invoiced".
- The report ask (`lanes/business/report_ask.py`, `settle` / `_given_choices`) already asks the
  basis for rankings AND axis-less totals ("how much did we sell of Cabana in August"): unchanged.
- `crm_sales_report` (one customer's or product's sales, delivered only) never asks either; lane
  REPORT-UNIFY (#1922) moves every sales report onto the report ask, which asks, so it is left to
  that lane (crew-note posted on #1922).
- The route's own default (`app/api/v1/sales/analysis.py` `DEFAULT_BASIS`) serves API callers and
  the Sales pages; not the chatbot's question, unchanged.

## Change

- New `lanes/business/sales_basis_ask.py`: a `required_fields` slot (like `sales_company_ask`)
  asking `ranking_ask.RANKING_BASIS_LINE` with the four bases as options, Invoiced first. The
  answer is the parser's `sales_basis` / `basis`, its declared pick, or the typed word / number.
- `lanes/business/__init__.py`: the sales analysis condition is computed once
  (`sales_analysis_ask`); before the tool chain the basis is settled (asked when none is named,
  before the company question). Invoiced / delivered / ordered run `crm_sales_analysis` with the
  first message's axes; outstanding (the analysis has none) runs the report ask's outstanding
  orders by channel (or by month), in RM.
- `fetch.py`: no invoiced default in the `crm_sales_analysis` builder.
- Parser template line and MCP description say the basis is asked.

## Tests

`tests/chatbot/test_sales_total_ask.py` T1 to T6 (lane and real-engine turns), red first.
Existing tests that ran a basis-less sales analysis now name the basis (listed in the PR body).
No parser gold expectation changes: the parser still emits `sales_basis` null for "total sales".
