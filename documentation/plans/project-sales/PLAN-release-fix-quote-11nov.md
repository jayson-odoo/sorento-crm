# PLAN: RELEASE-FIX-QUOTE (11 Nov 2026)

Status: in progress (small fix track: test-only plus two one-line service fixes, no migration, no auth).

Release sweep on main 6e6657e2 found two behaviour regressions. This lane fixes both and nothing else.

## 1. A sent legacy (layout 2 / 3) revision reprints without its Purpose row

- Root cause: `app/services/quotation_cover_service.py:411-414` (#2302, ec8f02f6) skips the `purpose`
  key in `rows_for_design` unconditionally.
- `rows_for_design` is reached only through `cover_rows`, whose callers are the PDF's layout 2 and 3
  branches (`project_quotation_pdf_service.py:1250, 1257`) and the sign page's layout 2 / 3 branch
  (`project_quotation_document_service.py:2390`). Every issue written today is layout 4
  (`project_quotation_document_service.py:873`), and the draft preview (`preview_cover`) and the designer
  preview both render through `cover_sections`, whose sources carry no Purpose
  (QUOTE-COVER-FIELDS D3). So the skip changes nothing for new documents; it only rewrites revisions
  that already went out.
- Rule (QCF UAC D1, `projects/quote-cover-fields-10nov-acceptance-criteria.md:48`): revisions sent
  before this change print exactly as they went out. The owner removed Quotation Purpose for new
  documents (10 Nov), not retroactively. PFC-5 is scoped to that.
- Fix: drop the skip. Restore #2302's flipped legacy layout 2 / 3 assertions in
  `tests/test_project_quotation_cover_page.py` and `tests/test_quote_cover_design_issue.py` to the
  as-sent output. Add a guard that a NEW (layout 4) issue and the draft preview print no Purpose even
  when the document still stores one.

## 2. The agent reads the stored rich-text markup

- Root cause: `app/services/chatbot/agent/quotation_lines.py:32` (#2315) returns
  `row.description_snapshot` raw, so after #2304 the agent receives HTML.
- Fix: `svc.line_text(row)` (`project_quotation_service.py:418`, the plain-text reader every other
  plain reader uses). It is the only non-allowlisted reader
  (`test_no_plain_text_reader_reads_the_stored_markup_raw`). MCP has no line-level reader.
- Add a behavioural test: a rich description reaches the agent as plain text.

## Order

1. `test(red):` commit, tests only; post red-proof.
2. Fix commit; touched suites green.
3. Kill proof (revert each fix, same tests red, restore).
4. Reviewer, one PR, crew-done.
