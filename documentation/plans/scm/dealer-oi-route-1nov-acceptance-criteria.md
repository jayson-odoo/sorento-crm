# UAC: Order inquiry emails routed by sales order class (DEALER-OI-ROUTE)

Plan: `PLAN-dealer-oi-route-1nov.md`.

- **AC-R1** The "Order inquiry handover to purchasing" and "Order inquiry undone" triggers offer the condition field **Sales order class** with the values Retail and Project. Retail and Other orders read Retail; Project and unclassified orders read Project.
- **AC-R2** A Confirm of one order sends one handover email carrying that order's class.
- **AC-R3** One write that touches a retail and a project order sends two handover emails, each with only its own class's orders and lines. Two project orders in one write still send one email.
- **AC-R4** A row with the condition "Sales order class is Retail" sends only for retail; "is Project" only for project; a row with no condition sends for both (no change on deploy).
- **AC-R5** The undo email follows AC-R4.
- **AC-R6** Send to purchasing (resend) uses the oldest enabled row whose condition matches the OI's class; with none enabled, the oldest row of the trigger as before.
- **AC-R7** The recipient picker has a To block and a Cc block, each with users, roles and external emails. "Cc the person who raised it" (and the inquiry raiser / requester) sit in Cc.
- **AC-R8** With "One email" on, every To address is on the To line and every Cc address (then the person who raised it) on the Cc line. An address on both is To. A row with only Cc still sends with its first Cc as To.
- **AC-R9** A row saved before Cc existed lists all its recipients on To; nothing is migrated and nobody stops receiving the email.
- **AC-R10** Every other email sender keeps "first address To, rest Cc".
- **AC-R11** No real names or addresses are seeded; the owner creates the retail row.
