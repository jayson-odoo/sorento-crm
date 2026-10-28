# UAC: sales total asks the basis (SALES-TOTAL-ASK)

Plan: `PLAN-sales-total-ask-27oct.md`. Tests: `sorento_crm_backend/tests/chatbot/test_sales_total_ask.py`.

- AC-1 (T1, T3) "total sales Jan 2026" with no basis named: the reply is exactly
  "Invoiced, delivered, ordered or outstanding?" and nothing runs.
- AC-2 (T2) A basis named in the message runs at once, no question.
- AC-3 (T3, T4, T12, T13, T17) The parser's declared pick (1 invoiced, 2 delivered, 3 ordered, 4 outstanding)
  or declared fill (`sales_basis` / `basis`) runs the first message's ask on that basis.
- AC-4 (T8) The first message's period, channel and axis win over the answer's own parse.
- AC-5 (T5, T7, T18, T22) Outstanding, answered or named, runs the report ask's outstanding orders by channel
  (or by month), never `crm_sales_analysis`; no period said reads this calendar year to today.
- AC-6 (T6) A contact in two companies is asked the basis, then the company; the run carries both.
- AC-7 (T9, T10, T14, T16) A reply the parser declared no answer for drops the question; its typed text is
  never read (no digit, word or shape match in code).
- AC-8 (T19) A declared pick wins over a stray basis key on the same parse.
- AC-9 (T20) A declared cancel says "Sales report cancelled." and runs nothing.
- AC-10 (T21) A declared answer naming no option is asked again in the same words, then given up with a line
  that echoes no word.
- AC-11 (gold) On the live parser text, the gold rows in `parser_sales_total_ask.jsonl` pass.
