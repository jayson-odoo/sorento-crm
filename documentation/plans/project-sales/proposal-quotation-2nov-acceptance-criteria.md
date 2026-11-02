# UAC: PS-PROPOSAL-QUOTATION

Plan: `PLAN-proposal-quotation-2nov.md`. Card: `CARD-proposal-quotation-2nov.md`.

- AC-1 Every quotation document that existed before the lane reads as a Proposal with its number, issues,
  signatures and won scopes unchanged.
- AC-2 A proposal first issued after the lane is labelled A, then B, C. A proposal that already has an R1
  continues R2, R3. Quotations count R1, R2.
- AC-3 Issuing a proposal revision whose unit price for any product differs from the previous revision of the
  same proposal alerts management (in-app + email) with product, old and new price. A quantity-only change, or
  only added/removed lines, alerts nobody. The issue always goes out.
- AC-4 A proposal is addressed to a party of the project; Tender party and Subcontractor exist as party types.
- AC-5 "Make quotation" is available only on an issued proposal of a Won project with no quotation yet; it
  creates a quotation numbered from its own rule (QT-YYYY-NNNN by default), linked to the picked revision, with
  that revision's party, letter, terms and lines; lost scopes left out.
- AC-6 A quotation line priced below the same product's price on the source revision needs management approval
  before Issue; equal or higher prices and quantity changes do not.
- AC-7 Once a project has a quotation, a new PO cannot be bound to a proposal; scanned POs auto-bind to the
  quotation.
- AC-8 When the total PO quantity of a product (live POs checked against the quotation) exceeds the quoted
  quantity, saving or confirming asks for one reason; with a reason it saves, shows "Qty over quote" on the PO,
  and management is alerted. It never blocks without a way through.
- AC-9 PDF, Excel, sign page and emails say "Proposal" for a proposal and "Quotation" for a quotation; the cover
  page applies to both.
- AC-10 Forecast and conversion figures do not change because a quotation was made; the bot's project
  quotation list says which rows are proposal and which quotation.
