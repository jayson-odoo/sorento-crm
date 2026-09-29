# 13. Billing documents are one typed table in the `finance` schema

Date: 2026-09-27
Status: accepted

## Context

The owner asked for a finance module that receives AutoCount's billing documents through the
shared service (#1309), so the sales reports can count what was invoiced as well as what was
ordered. AutoCount's Sales module raises four billing documents that carry item lines and feed
its own sales analysis: invoice (IV), cash sale (CS), credit note (CN) and debit note (DN). The
owner ruled all four in on day one (ruling Q1, 27 Sep).

The four share one shape: a header (number, date, customer, agent, currency, net, tax, total,
cancelled flag) and item lines (product, quantity, price, discount, tax, total). They differ in
what they mean to a total, not in what they hold.

## Decision

1. **One header table and one line table**, `finance.billing_documents` and
   `finance.billing_document_lines`, told apart by `document_type`. Not four pairs of tables:
   every reader (the invoiced basis, the list, the record page, the SO and customer sections)
   reads all four, and four pairs would be four copies of the same query.
2. **In the `finance` schema, with no `finance_` prefix**, on the ADR-0011 precedent the `sales`
   module followed: the schema is the module key, so which tables the module owns is answered by
   `\dn`. Foreign keys to core tables are ordinary cross-schema foreign keys.
3. **`document_type` is a `varchar` with a CHECK constraint**, not a Postgres ENUM and not a
   lookup table. The list is closed and set by AutoCount, the repo's precedent for a closed
   vocabulary is a CHECK built in code, and adding a type later is one migration replacing the
   constraint, where an ENUM cannot drop a value and a lookup table is a table for four strings.
   The model declares the same CHECK, so a `create_all` database rejects what a migrated one
   rejects.
4. **Amounts are stored as AutoCount prints them**, positive on a credit note. The sign is
   applied in one place only, the invoiced-basis expression (S1). A stored negative would make
   every list and record page flip it back.

## Consequences

- A fifth type (AutoCount's AR-module documents, say) is one migration widening the CHECK and
  one line in the canonical schema's list; nothing else moves.
- Anything that sums billing documents must apply the sign itself; the stored figures are never
  netted. The invoiced basis is that one place.
- The idempotency key includes the type, `(company, document_type, source_ref)`, because
  AutoCount's DocKey is unique per document table, not across them (assumption A2).
