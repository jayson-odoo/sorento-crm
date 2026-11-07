# PLAN: report follow-ups widen what the parser widened; a settled name is not asked again (7 Nov 2026)

Status: Review, PR #2224 READY (7 Nov 2026; reviewer READY at 0885547437 after 3 rounds). Small fix track by kind (code
only, no migration, no prompt change, about 60 lines of code) but the diff is about 540 lines with tests and docs, over
the ~300-line guide. Crew go 5 Nov (fixes 1 and 2 of the prod-transcript diagnosis, #2156 crew-note 6652690440); fix 3
(prompt) skipped by crew: report follow-ups move to the agent path (lane AGENT-REPORTS), so no more parser prompt spend.
Known trade (lead ruling WR-10): the owner's T5 "all" was parsed as a date widen, so it still keeps the held brand and
category; "all brand all category" / "for all brands and categories" / "clear all" widen.
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
  - Fix 1 (carry): when the parse itself widens the lists (`entity_op` "clear" on any axis, WR-12b; or `broaden_to`
    "all" on the axis "all", none, or a product-filter kind: brand, category, account type; review round 1, WR-10), a
    list the object emptied is not carried back from the held report; a customer, sales agent or date `broaden_to`
    widen keeps the held lists.
    `topic_reset` carries nothing already. The object is the report after this message. Parser fields only; when the
    parse marks no widen, `_carry` is unchanged (C6-2's protection against an object that dropped a held list stays).
    The company is dropped only on `entity_op` "clear" (WR-4); one kind's widen ("all sale agents") keeps the held
    company (HF-2, test_report_totals_filters.py:728, owner Q3).
  - Fix 2 (re-ask): a word left unsure (the kind question would ask it) whose name the held report already settled is
    not asked again; it is the brand. "Settled" = the held report has the name as its company AND among its brands
    (the prod T4 shape, review round 1); a brand or a company held alone still asks (WR-11, R5-1c). The rule runs after
    the C6-1 company reading (WR-9) and never settles a word the open question owes or the object put in
    `company_or_brand`; on a widen, a `company_or_brand` word equal to the object's own company is that company (WR-1,
    WR-2). A word the message types with a kind still decides as today.
- Classes / functions touched: `_carry`, and `_word_kinds` with its caller in `from_object` (the step that hands the
  kind question its unsure word). `turn/decide.widened_kinds` is shared with the open which-one customer pick, so it is not changed;
  the report-ask path reads the widen fields itself.

## Tickets

1. Tester: red engine tests from the repro parses (UAC WR-1..WR-5) + locks (WR-6..WR-8).
2. Coder: fix 1 + fix 2, kill-proof.
3. Reviewer: one pass (security reviewer skipped: no auth, RBAC, ingest, upload or scoping change).
4. crew-tests on the head, PR, crew-done. Archive: #2156's plan, UAC and prompt doc move to
   `documentation/plans/_archive/chatbot/` in this PR.
