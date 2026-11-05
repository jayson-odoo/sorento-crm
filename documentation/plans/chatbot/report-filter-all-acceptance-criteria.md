# UAC: report filters, explicit ALL (lane REPORT-FILTER-ALL)

Plan: `PLAN-report-filter-all-5nov.md`. Each row is a test in `sorento_crm_backend/tests/chatbot/test_report_filter_all.py`
unless it names another file.

| Row | Given | When (the parse the ALL prompt writes) | Then |
|---|---|---|---|
| FA-1 | All 8 filter kinds held on a delivered Sep month breakdown | One slot ALL, every other filter slot left empty, no broaden field ("clear brand", "all customers", "any product", "all categories", "any agent", "all account types", "all channels", "clear company") | Only that filter goes, in the report and the held state; the rest, basis, period and axis stay; nothing is asked |
| FA-2 | Brand held, ALL prompt | `brands: []` beside legacy `broaden_axis` brand | The brand stays (the legacy signal is not read on an ALL prompt) |
| FA-2b | Brand held, prompt without ALL (v72) | `brands: []` + legacy broaden brand | The brand goes (temporary adapter) |
| FA-3 | All 8 kinds held | "clear all": every filter slot ALL | No filter; basis, period and breakdown stay; nothing is asked |
| FA-4 | Brands Sorento + Cabana held | `brands: ["Cabana"]` | Cabana only |
| FA-4b | Brand held | `brands: ["ALL", "Sorento"]` | No brand |
| FA-4c | No brand held | `brands: ["ALL"]` | The same report; nothing is asked |
| FA-5 | Company Sorento held | `company: "ALL"` | No company filter, no "no access", nothing is asked |
| FA-5b | Company Sorento total held | "break down project and retail", company null | Channel breakdown in Sorento |
| FA-5c | Company Sorento held | Object company "Sorenth", top-level sales_company null or Sorento | Sorento, no "no access" |
| FA-5d | Company Sorento held | Object company "Mocha" (an own company), no entity | Mocha |
| FA-6 | Dealer channel held | channel null, then channel ALL | Dealer kept, then no channel |
| SC-8 (test_report_semantic_carry) | Dealer channel held | A restated product ask that leaves channel null | Channel dealer kept (owner 3 Nov) |
| CL-1..CL-7 (test_report_totals_filters) | | Legacy-prompt clears | Unchanged |
| HT1-18..20 (test_report_totals_filters_ht1) | | Company echo, switch, forbidden | Unchanged |
| R1 | Company Sorento held, every agent | "sorento brand only", company null (said_as brand) | Company Sorento kept, the brand applied |
| R2 | Company Sorento held | The user types "Sorento SG" (not held), object company "Sorento SG" | "You do not have access to that company."; nothing runs |
| R3 | Company Sorento + brand SORENTO held | "sorento company only" (said_as company) | Company Sorento, no brand |
| U4 / U4b | | A brand moved to the company, an account type moved to brands, a new customer "Tan" beside a held agent "Tan" | The first two are not refilled; the agent refills; the company is never un-held by a move |
| U5 / U5b | | Company spellings | An own close name and a typed name or code are never echoes |
| K1 | An outstanding list open | A report object turn saying "all brands" / "clear the brand" / "no brand" / a bare brand word | No keyword rule fires; the object decides (the plain order list keeps its own clear) |
| K2 | | | The report lane imports no regex |
| G1 | All 8 kinds held, delivered Sep month breakdown | "clear all": every filter ALL, period, basis, frame, axis left null | No filter; delivered, Sep and month stay; nothing asked |
| G1b | Same | Every filter ALL, frame total | No axis; delivered and Sep stay |
| G3 | Same | The ZH clear-all parse: every filter ALL, no report status, message type casual or null | The report runs (delivered, Sep, no filters), never chit-chat |
| G5 | | A report object turn whose name the span list placed on suppliers | No supplier scope line; without a report object the supplier line still stands |
| H8 | Company Sorento held, channel split | "Sorento company, brands Sorento and Cabana": two Sorento entities (said_as company, said_as brand) in either order, Cabana brand | Company Sorento AND brands SORENTO + CABANA |
| H15 | No report held; the contact's company Sorento is also a brand and a stored SORENTO debtor type | "Sorento total sale delivered September 2026", then "brand" | ONE company-or-brand question (no account type option); then the brand across every company, no company filter |
| P1 | | | The candidate text is the v72 base (d29c1983) plus the ALL edits, md5 5a58739a, and defines ALL; v72 does not |
| G-1..40 (gold, crew-run) | `parser_report_filter_all.jsonl` | clear brand, all brands, any agent, clear company, all companies, clear all, remove one of two brands, all customers, all channels, two forgotten-echo controls, an ALL no-op; 16 EN / BM / ZH mixes ("buang semua filter", "清除所有筛选", "全部 la, 不要 filter", "semua brand", "所有公司", "any agent pun boleh" ...) | The parser writes ALL exactly there and keeps every other held slot |
