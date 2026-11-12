# UAC: Certification tab follow-ups (CERT-TAB-FOLLOWUPS)

Plan: `PLAN-cert-tab-followups-11nov.md`.

## AC-1 Right-click row menu

- AC-1.1 The certificate list has no Actions column and no "..." button on any row.
- AC-1.2 Right-clicking a row (long-press on touch) opens a menu with Open and Download; with the edit right,
  also Remove.
- AC-1.3 Open goes to the certificate; Download saves the file (disabled when the certificate has no file);
  Remove starts the usual removal countdown with Cancel.
- AC-1.4 Right-clicking outside a row shows the browser's own menu (no empty app menu).
- AC-1.5 Clicking a row still opens the certificate.

## AC-2 Every open lands on the first box

- AC-2.1 Opening a certificate from the list scrolls the viewer to its first box (reading order) and outlines it.
- AC-2.2 Going back and opening the same certificate again does the same.
- AC-2.3 Opening another certificate does the same for that certificate's first box.
- AC-2.4 A certificate with no boxes opens at page 1, nothing waits forever.

## AC-3 Unsaved boxes warn before leaving

- AC-3.1 With unsaved box changes, Back to certification, a breadcrumb or any other in-app link asks
  "Leave without saving?" with "Keep editing" and "Leave without saving"; Keep editing stays with the changes,
  Leave goes where the click pointed.
- AC-3.2 Browser Back with unsaved changes asks the same question.
- AC-3.3 Refresh or closing the tab with unsaved changes gets the browser's own leave prompt.
- AC-3.4 With nothing unsaved (or after Save boxes), every exit goes straight through with no prompt.
- AC-3.5 Save boxes stays the one main button; there is no Remove button inside the box editor.
