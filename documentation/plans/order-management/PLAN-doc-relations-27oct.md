# PLAN: SO / DO / billing document relations (DOC-RELATIONS)

Status: built, in review (size M, cloud lane, standard track: no migration; touches permission
masking across modules, so security-reviewer joins). PR #1912.

UAC: `doc-relations-27oct-acceptance-criteria.md`. Mock: `doc-relations-27oct-mockup.html`
(v2 approved by the owner 27 Oct 15:53).

## Owner request (27 Oct)

1. Delivery orders get a detail page like the sales order's, sharing its components.
2. SO > Invoices shows the invoices (SO427775 showed none although invoice 202610-3905 came
   from DO 202610-3905, which delivers SO427775).
3. DO detail shows its invoices and related billing documents.
4. Related distinguishes Sales order / Delivery order / Billing document on all three records,
   every number a link. Owner 15:51: Related is a TABLE, sortable.
5. Bug: SO427775 Delivery tab said "Nothing delivered yet" above four DO rows.

## Findings

- Invoices tab empty: the billing list's `sales_order_id` filter matched only billing lines with a
  resolved `sales_order_line_id` (`billing_document_query_service.py`, old lines 107-115). A
  "transfer from DO" line resolves it by hopping through the CRM DO line's own
  `sales_order_line_id` (`billing_document_ingest_service.py:574-602`), which is NULL when the
  DO line names the SO by number only, or when the invoice arrived before the DO.
- Bug 5: the sentence reads the SO header's `total_qty` / `committed_qty`, computed from the
  lines' `qty_delivered` (`sales_order_service.py:477-502`); the table reads DO lines
  (`so_line_history.py:58-63`). A stale `qty_delivered` (the line sweep gap fixed 27 Oct) made
  them disagree. No status filter involved.

## Design (owner rulings Q1a-Q4a, mock v2)

- `app/services/document_relations.py`: relations derived at read time from columns the feeds
  already write, every query on the anchor's company. No link table, no backfill.
- `/related` on each record (its own view slug); each kind masked by its view slug; `rows` is the
  one table, sorted server side.
- Billing list: `sales_order_id` widened through DOs and notes; `delivery_order_id` added.
- FE: `OrderInvoices` (SO and DO), `RelatedDocumentsPanel` (SO, DO, billing doc),
  `PanelDataGrid.serverSorting`; DO detail tabs General, Lines, Delivery, Invoices, Related;
  SO gains Related; SO Delivery sentence only when there is no DO row.

## Trigger for a stored link

If `/related` latency on a large order becomes measurable (EXPLAIN shows the `from_doc_no`
IN-subquery dominating), add a link column then, with a backfill; not before.
