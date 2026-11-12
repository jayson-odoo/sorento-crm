# UAC: quotation line note in the customer REMARK column (QUOTE-LINE-NOTE-REMARK)

Approved via behaviour card (PR #2378, 12 Nov). Hint text: "Shown to the customer". Masked data only.

- AC-1 `quotation_columns.remark(line)`: flag only -> "Non-cancellable"; note only -> the trimmed
  note; both -> "Non-cancellable\n<note>"; neither, or note blank/whitespace -> "". A heading row
  (`is_section`) -> "" whatever its note. Never joined with " · ".
- AC-2 Line breaks inside a note are kept; the note is never truncated (a 500-char note comes back
  whole).
- AC-3 `quotation_columns.for_lines(lines)` includes REMARK when any non-section line has a flag OR
  a non-blank note; otherwise the column set is unchanged.
- AC-4 Sign link page: `GET /public/quotation-sign/{token}` returns `remark` per line equal to
  AC-1, and the page renders it in the REMARK column with line breaks, wrapping long text.
- AC-5 PDF (the email attachment): the REMARK cell prints AC-1's text, flag and note on separate
  lines, long notes wrap.
- AC-6 Excel export: the REMARK cell holds AC-1's text with wrap on.
- AC-7 Editor: the line note popup shows a one-line hint that the note is shown to the customer.
