# PLAN: UI/UX playbook quick wins (UIUX-QUICK-WINS)

Status: built, in review (small fix track per item, size M overall; no migration, no auth/RBAC change). Item 3 moved to lane PRICETAG-REQUEST-LAYOUT (#2318) by crew, with the price tag form's own status pill.

## Journey

Owner go 10 Nov 2026 on the 10 quick wins in `documentation/uiux/playbook-uiux-audit.md` section 5,
with the agreed differences in section 6 (dd/mm/yyyy, one line per row, gear menu + right-click row
menus, Sorento brand + minimal UI with only the styled tooltip adopted, deferred countdown with the
playbook dialog wording).

## Items

1. OI detail: one filled CTA at a time (the one the state waits for), the other outline.
2. OI list: Reserve filter multi-select + Reserve column sortable server-side.
3. Price tag "Need by": shared DatePicker (dd/mm/yyyy) instead of native type=date. MOVED to #2318 (crew, 10 Nov): it lives in `PriceTagRequestForm.tsx`, which that lane rewrites.
4. Price tag status: shared `<Badge>`.
5. Blocked quotation primaries (Save/Submit/Approve/Issue) say why under the button.
6. Confirm dialog wording: shared confirm-dismiss dialog + RCD first, then the "Are you sure" files.
7. One shared no-access state replacing ad hoc "Forbidden - ..." text.
8. AttachmentDropzone: per-file upload failure with "Try again".
9. Shared Tooltip on header icon buttons (gear, prev/next).
10. Owner UI rules written into `documentation/reference/DESIGN-LANGUAGE.md`.

Coordination: lane PRICETAG-REQUEST-LAYOUT (#2318) reworks the price tag request screen. Items 3-4
touch only the portal form date field and the detail status pill; any overlap is reported via crew.

## Tests

Red-first where behaviour changes: vitest for shared components (confirm-dismiss dialog wording,
no-access state, dropzone retry, blocked-reason text, OI CTA variant helper); pytest for the Reserve
sort key and multi-value reserve filter.

## DoD

Reviewer, browser pass with before/after screenshots per item, hand-test script, crew-done.
