# PLAN: NO-AC-MOVED-WARNING

Status: in review, PR #2123. Track: small fix track (frontend only, no migration, no auth/RBAC change).
UAC: `no-ac-moved-warning-3nov-acceptance-criteria.md`.

## Why

Owner, 3 Nov ~10:30 MYT, on prod Confirm SO423361: every one of the 6 lines showed "Line 864
CKSW015: AutoCount moved this line: suggestion Use BRW 1 from BRW, you keep Borrow 1 from BRW-BB
[Keep] [Take suggestion]". "I don't want these, I already decided so why are you still suggesting
to me, it should follow previous behaviour, the warning shouldn't even appear."

The rows came with #2091 (CONFIRM-PREVIEW-STALE, `PLAN-confirm-preview-stale-2nov.md` item 5).
Trigger on SO423361: a 2 Nov SO book upload moved the lines' date 28/09 -> 02/11; the saved
decision is Borrow from BRW-BB (order back already raised).

## Change

A saved decision stands silently, as before #2091: no suggestion, no prompt.

1. `ConfirmGuideDialog.tsx`: drop the `confirm-guide-moved` rows, the `moved` line field, the
   `onTakeSuggestion` prop and the Keep / taking state.
2. `FulfilmentBoardPanel.tsx`: stop computing `moved` (`suggestionMovedOf`) and stop passing
   `onTakeSuggestion`.
3. `_shared/lib/confirmPreviewFresh.ts`: delete `suggestionMovedOf`, `SuggestionMoved`,
   `sameComposition`; `boardChangeAnnotations.ts`: delete `nowParts`, which only they read.
4. No backend field exists only for these rows (checked #2091's diff: `based_on_saved_at`,
   `quiet`, `email_lines` all serve other items), so the backend is untouched.
5. User guide `sales-order-changes.md`: drop the paragraph describing the flag.

Kept unchanged: fresh board re-read on open, popup = email = Excel REMARK from the dry run, one
dry run per change, Was -> Now / NEW DATE on pending changes, order remark in the email (#2116).

## Tests

- `FulfilmentBoardPanel.confirmGuide.test.tsx`: a saved Borrow on a line a pending change suggests
  something else for: the Review split shows no "AutoCount moved this line", no Keep, no Take
  suggestion and Next is on (red on main); Confirm posts the saved decision (a regression guard:
  the warning never blocked Confirm, so this one is green on main too).
- `ConfirmGuideDialog.moved.test.tsx`: the warning tests go; the fresh-read test stays.
- `confirmPreviewFresh.test.ts`: the `suggestionMovedOf` tests go with the function.
