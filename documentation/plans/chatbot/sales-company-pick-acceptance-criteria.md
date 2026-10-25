# UAC: SALES-COMPANY-PICK (24 Oct 2026)

Plan: `PLAN-sales-company-pick-24oct.md`.

- AC-1: A sales analysis ask with no company, from a contact holding two or more companies, gets "Sorento or Mocha?"
  (the contact's companies, default first) as a stored question; no analysis runs yet.
- AC-2: "Sorento" (read as a pick, a company pick or a company entity) runs the analysis for Sorento with the
  asked channel and period. It is never a brand filter and never an escalation.
- AC-3: "Mocha" (pick 2 or the company named) runs it for Mocha.
- AC-4: A contact with one company, or an ask that names its company, runs the analysis at once, with no question.
- AC-5: A different question while the company question is open is its own ask, and an older open question
  (By product / Delivery orders) does not come back.
- AC-6: After "SRT102-RG dealer sales May 2026", "SRT102-RG sales 2026" runs with no channel (Channel: all).
- AC-7: A follow-up keeps the channel: a customer-picker answer, "and for June", a top selling narrowing
  ("water closet only" over a dealer ranking).
- AC-8: The API route keeps its behaviour: same companies and order, 422 for an unknown company, 403 for a company
  the contact is not granted.

Round 2 (item 3):
- AC-9: "b2155-nl-blue dealer sales september 2026" parsed as sales_analysis with the product entity runs the sales
  report for B2155-NL-BLUE, channel dealer, September 2026 (the same call its sales_report parse makes). No company
  question, no company analysis, no whole-company figure.
- AC-10: A sales_analysis parse naming a customer this message runs the sales report for that customer.
- AC-11: A sales_analysis parse naming no product or customer this message (including one that only carries an earlier
  turn's product) is unchanged: company question (2+ companies) or the company analysis.
- AC-12: A named subject that arms a picker (customer picker, kind picker, did-you-mean) keeps the sales report: the
  answer ("1") runs crm_sales_report for the picked subject, never the company analysis.
- AC-13: A customer-hinted word that resolves as a product renders that product's sales report, as the sales_report
  parse of the same message does (not the miss text).
