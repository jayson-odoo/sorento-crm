# UAC: preview-email-planchange-3nov

Each of these runs with the order-inquiry post-commit listeners registered, as production does.
Tests: `sorento_crm_backend/tests/test_confirm_preview_email_parity.py`.

- A1. Planning-change path (`_form_three` + another order's raised row + an open pool PO line):
  the confirm-all dry run's `email_lines` equal the lines of the email the real press builds,
  field for field and in the same order. The lines are ADVANCE, ORDER 15 for line 1 and
  CANCEL ALL for each closed line.
- A2. Ordinary confirm path, on a first confirm and on a re-confirm of a grown line: the same
  equality holds.
- A3. A dry run followed by the press in the same session sends what the press alone sends
  (the first two planning-change tests together: both pin the same three lines).
