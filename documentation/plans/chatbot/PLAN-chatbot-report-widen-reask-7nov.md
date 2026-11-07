# PLAN: report follow-ups widen what the parser widened; a settled name is not asked again (7 Nov 2026)

Status: Build (small fix track: code only, no migration, no prompt change, expected diff under 300 lines). Crew go
5 Nov (fixes 1 and 2 of the prod-transcript diagnosis, #2156 crew-note 6652690440); fix 3 (prompt) skipped by crew:
report follow-ups move to the agent path (lane AGENT-REPORTS), so no more parser prompt spend.
UAC: chatbot-report-widen-reask-acceptance-criteria.md.

## Journey

The owner, on prod parser v72 (md5 d29c1983, release 30bbcc6a7c), 5 Nov ~15:45:
- T1: "Total quantity sale for Sorento brand kitchen sink on September 2026" gave Company Sorento + Brand SORENTO +
  Category Kitchen Sink.
- T3 "clear all", T5 "all", T6 "all brand all category", T7 "for all brands and categories": the reply still held
  Brand SORENTO + Kitchen Sink.
- T4 "sorento total slaes by delaer and proejct" asked "SORENTO: brand, account type or company?" although Sorento was
  the settled company and brand of the report on screen.

## Root cause (file:line at main 61e9d21733)

1. `report_ask._carry` (lanes/business/report_ask.py ~:3684): per kind, a held value comes back when this message's
   entities name nothing of the kind and the object holds none. A widen counts only through
   `turn/decide.widened_kinds` (~:446): ONE `broaden_axis` read as a kind hint with `broaden_to` "all".
   - "all" names no kind, so nothing widens (repro step 8: broaden_axis "all").
   - T7 widens the brand only (repro step 9: broaden_axis "brand"), so the held category comes back.
   - The object that emptied both lists is overruled by the carry.
2. `_kind_ask` (~:1724), via the #2105 C6-1 `kind_company` three-way question (~:437): it asks for a word the message
   leaves unsaid (said_as null) even when the held report already settled that name as its company and its brand.
   ON-12 and CP-5 cover a held company, but not this three-way ask. (Prod data has SORENTO as an account type; the dev
   DB 1020 does not, so tests seed one.)

Repro traces: crew/state/handtest/2156/prod-v72-repro/ (copy at 30bbcc6a7c, v202 = the same text).

## Architecture

- Layer: backend only, staff chatbot report-ask lane (`app/services/chatbot/lanes/business/report_ask.py`), the new
  report-ask object path behind `REPORT_ASK_LINE`. No route, schema, MCP or FE change.
- Mechanism:
  - Fix 1 (carry): when the parse itself widens (`broaden_to` "all" for any axis, `entity_op` "clear", or
    `topic_reset`), a kind whose list the object emptied is not carried back from the held report. The object is the
    report after this message. Parser fields only; when the parse marks no widen, `_carry` is unchanged (C6-2's
    protection against an object that dropped a held list stays). Coder deviation (7 Nov): the company is not a list;
    it is dropped only on the parser's clear of every axis (`entity_op` "clear", WR-4). One kind's widen ("all sale
    agents") keeps the held company, as the HF-2 lock (test_report_totals_filters.py:728, owner Q3) requires.
  - Fix 2 (re-ask): a word whose name the held report already settled is not asked again while this message leaves the
    kind unsaid (said_as null or absent); the held kinds stay. "Settled" = the held brands contain it. A word the
    message types with a kind still decides as today. Coder deviation (7 Nov): a name held only as the company is still
    asked brand, account type or company when it is a brand and an account type too (the R5-1c lock,
    test_report_semantic_carry.py:1468); CP-5 already covers a held company with no account type.
- Classes / functions touched: `_carry`, and `_word_kinds` with its caller in `from_object` (the step that hands the
  kind question its unsure word). `turn/decide.widened_kinds` is shared with the open which-one customer pick, so it is not changed;
  the report-ask path reads the widen fields itself.

## Tickets

1. Tester: red engine tests from the repro parses (UAC WR-1..WR-5) + locks (WR-6..WR-8).
2. Coder: fix 1 + fix 2, kill-proof.
3. Reviewer: one pass (security reviewer skipped: no auth, RBAC, ingest, upload or scoping change).
4. crew-tests on the head, PR, crew-done. Archive: #2156's plan, UAC and prompt doc move to
   `documentation/plans/_archive/chatbot/` in this PR.
