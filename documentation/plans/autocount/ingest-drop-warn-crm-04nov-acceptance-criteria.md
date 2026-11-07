# UAC: INGEST-DROP-WARN-CRM

- AC-1: A sales or purchase order pushed with a line that has no `product_code` lands (the other
  lines are written), `lines.dropped` counts the line, and the record's `warnings` holds
  `line_product_unresolved:doc=<number>:line_ref=<line source_ref>:line_no=<line_number>:product_code=`.
- AC-2: A line with an unknown `product_code` gives the same entry with that code after
  `product_code=`. Two dropped lines give two entries.
- AC-3: A real (non dry-run) push logs an `ingest.record` line for that record naming the same
  warning(s). A dry run logs nothing, as before.
- AC-4: A document with no dropped line carries no `line_product_unresolved` warning and logs no
  `ingest.record` line.
