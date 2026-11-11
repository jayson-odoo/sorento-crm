# PLAN: Certification tab follow-ups (CERT-TAB-FOLLOWUPS)

Status: Hand test (PR #2353): red/kill proofs, reviewer READY, sandbox browser pass PASS at 1280 and 375. Track: small fix track (size S; frontend only, no migration, no auth/RBAC change, no new ingest).
UAC: `cert-tab-followups-11nov-acceptance-criteria.md`.

Lane: CERT-TAB-FOLLOWUPS. Owner go 11 Nov 2026 ("Cert-tab follow-ups go"): the three items crew's browser
pass found on the quotation Certification tab during #2333 (all pre-dated #2333).

## Items

1. Row "..." menu (Open / Download / Remove) becomes the app's right-click row menu, same actions.
   Reuse: `components/ui/context-menu.tsx` wrapped around `PanelDataGrid` with `rowAttributes`, exactly as
   the sibling Purchase orders tab does (`app/(protected)/project-sales/[projectId]/components/PurchaseOrdersPanel.tsx:450`).
   The Actions column goes. Radix ContextMenu opens on long-press on touch. Remove keeps the deferred countdown
   (`useDeferredRowAction`).
2. Opening a certificate (first time, second time, after switching certificates) lands on its first box.
   Reproduce first, then fix at the cause in `CertificateReader.tsx` (the landing jump vs the PDF viewer's own
   "land on page 1" layout pass).
3. (Crew ruling: option b, one shared hook `hooks/useUnsavedChangesGuard.tsx`, used only here.) Leaving the box editor with unsaved boxes warns: Back to certification, the breadcrumbs, any in-app link,
   switching certificate, browser back, refresh / close. "Save boxes" stays the one main button; no Remove
   button in the editor.

## Standing rules that apply

- One main CTA (Save boxes stays the only filled button).
- Right-click over icons; rows have no action icon buttons.
- Plain words in every new label and prompt.
- Nothing hangs (the jump gives up quietly; the guard never traps the user).
- Every row is one line (unchanged).
