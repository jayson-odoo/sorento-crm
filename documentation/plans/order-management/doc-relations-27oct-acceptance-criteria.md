# UAC: DOC-RELATIONS

- R1 SO -> DOs: DO lines naming the SO by `from_doc_no` (type SO or NULL), DO lines whose
  `sales_order_line_id` is on the SO, or the DO header's `sales_order_id`. Deleted and cancelled
  DOs excluded (same as the Delivery tab).
- R2 SO -> billing documents: lines resolved onto the SO's lines, transferred from the SO by
  number, or from one of its DOs by number; plus credit/debit notes against those. SO427775 lists
  invoice 202610-3905.
- R3 DO -> SOs and DO -> billing documents (and notes against them). One DO, many invoices: all.
- R4 Billing document -> SOs and DOs; a DO number not in the CRM shows without a link; a note
  inherits its invoice's SO and DO; the invoice lists its notes.
- R5 Another company's same-numbered document never links.
- R6 `/related` on SO, DO and billing doc: 403 without the record's own view slug; 404 for
  another company's record; each kind null without its view slug; `rows` one table, sortable
  server side by Type, Number, Date, Status, Amount.
- R7 SO and DO Invoices tabs: same grid, server-side sort on every column.
- R8 DO detail tabs: General, Lines, Delivery, Invoices (with billing view), Related.
- R9 Related tab on SO, DO and billing doc: one table, every number a link (except a DO the CRM
  does not hold), empty state "No related documents".
- R10 SO Delivery tab: no sentence when DO rows exist; "Nothing delivered yet." only with no DO.
- R11 Billing doc Lines "From" column links a DO the CRM holds.
