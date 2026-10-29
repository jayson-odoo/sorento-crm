# PLAN: Customer amendment requests on the quotation link (QUOTE-CUSTOMER-AMEND)

Status: Plan - behaviour card + mock pending owner approval; build blocked on QUOTE-SIGN-PAGE merge. Track: full (migration + new public write path).

Source: owner team meeting 29 Oct 15:40 (Project Sales module); owner answer Q3 29 Oct 22:45.

## Journey (one line)

A customer opens the quotation link, changes qty and/or unit price on the lines they disagree with
(description read-only), submits one request; the salesperson sees a per-line diff on the quotation
document, accepts or rejects each line; accepted lines become the next revision (below-minimum
prices go through the existing approval before it can be sent); the customer is told the outcome.

Sections below are filled from the behaviour card once the owner answers.
