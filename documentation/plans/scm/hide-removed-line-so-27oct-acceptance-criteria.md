# UAC: hide the book S/O on a removed PO line (27 Oct 2026)

Plan: `PLAN-hide-removed-line-so-27oct.md`

- AC-HR-01 PO detail (`GET /scm/purchase-orders/{id}`): a line AutoCount removed (cancelled,
  header not cancelled, not cancelled by a Cancel PO document) returns `book_so_number = null`
  and `book_so_unresolved = false`, the same as a line whose book named no S/O. The Lines tab
  S/O cell reads "-".
- AC-HR-02 A line cancelled by AutoCount Cancel PO documents (`cancelled_by_cancel_doc`) still
  returns its S/O number.
- AC-HR-03 A line on a cancelled PO header still returns its S/O number.
- AC-HR-04 An open line is unchanged.
- AC-HR-05 The stored `purchase_order_lines.from_so_line_ref` is not modified.
- AC-HR-06 Every other screen that prints the book S/O of a PO line applies the same rule (list
  in the PR body).
