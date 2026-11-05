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
| K1 | An outstanding list open | A report object turn saying "all brands" / "clear the brand" / "no brand" / a bare brand word | No keyword rule fires; the object decides (the plain order list keeps its own clear) |
| K2 | | | The report lane imports no regex |
| P1 | | | The candidate text is the v72 base (d29c1983) plus the ALL edits, md5 698e137b, and defines ALL; v72 does not |
| G-1..28 (gold, crew-run) | `parser_report_filter_all.jsonl` | clear brand, all brands, any agent, clear company, all companies, clear all, remove one of two brands, all customers, all channels, two forgotten-echo controls, an ALL no-op; 16 EN / BM / ZH mixes ("buang semua filter", "清除所有筛选", "全部 la, 不要 filter", "semua brand", "所有公司", "any agent pun boleh" ...) | The parser writes ALL exactly there and keeps every other held slot |
