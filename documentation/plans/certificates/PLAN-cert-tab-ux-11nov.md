# PLAN: Certification tab UX (CERT-TAB-UX)

Status: Build. Track: small fix / M (no migration expected, no auth/RBAC change). UAC: `cert-tab-ux-11nov-acceptance-criteria.md`.

Lane: CERT-TAB-UX. Owner feedback 11 Nov 2026 ~15:10 MYT on the Certification tab built by QUOTE-CERT-TAB (#2245).

## Owner ask (gist)

1. Tab loads slowly: measure, fix, list visible < 1 s at 34 certificates.
2. One line per row; certificate number only, description in a tooltip.
3. Search + multi-select filters (Scheme, Validity, Rows marked, Source) + sorting.
4. Box editor: no "Remove box" button; select + Delete/Backspace, right-click context menu Delete.
5. "Go to box" in one click from the list row and the right panel product entry.
6. Save is the page's obvious primary CTA with unsaved/saved state (or the system's designer auto-save).
7. "Suggested, check": explain, recommend, ask the owner before changing the state model.

## Findings

(filled in as the lane progresses)
