# UAC: a follow-up keeps the customer the user picked (CHATBOT-FOLLOWUP-CARRY)

Start of every case: a staff contact with two companies asks a dealer's October total, picks the dealer from the list, answers
the sales basis, and sees the report on every picked ledger.

- **AC-1.** "how about ordered": the report runs on ordered, same ledgers, same period. No company or period question.
- **AC-2.** "and delivered?": the report runs on delivered, same ledgers, same period.
- **AC-3.** "what about last month": same ledgers, last month's dates. The customer is never asked again.
- **AC-4.** Whatever `entity_op` the parser reads for those (`reuse`, `modify`, `replace_combine`), AC-1 to AC-3 hold.
- **AC-5.** "by product": same ledgers, same period, the product axis.
- **AC-6.** A ranking held for a customer: "how about ordered" stays on that customer and period.
- **AC-7.** A new customer named replaces the held one, and only that customer's ids run.
- **AC-8.** "all customers" drops the customer. The company question comes back when there is no other subject.
- **AC-9.** A topic reset ("start over ...") drops the customer and the period.
- **AC-10.** A code or name never brings in another row: the ids on the follow-up are exactly the ids of the report before it.
