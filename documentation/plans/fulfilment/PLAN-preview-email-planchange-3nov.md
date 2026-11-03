# PLAN: Confirm preview email equals the purchasing email on the planning-change path

Status: in progress (small fix track: backend only, no migration, no auth change)

Lane: PREVIEW-EMAIL-PLANCHANGE. Owner rule: email = preview = attachment, all three tally
(see `PLAN-confirm-preview-stale-2nov.md`).

## Problem

On the `_form_three` fixture (`tests/test_planning_change_apply_on_board.py`) the confirm-all
dry run's `email_lines` hold ADVANCE, ORDER 25 and one CANCEL ALL, but the real press hands
purchasing ADVANCE, ORDER 25, CANCEL ALL, CANCEL ALL. One CANCEL ALL is missing from the preview.

Second report: running the dry run and then the press in one session made line 1 read ORDER 15.

## Fix

1. The preview builds its email lines from the same items, grouped the same way
   (`handover_class_groups`) and rendered by the same builder, as the post-commit send.
2. Prove whether a dry run leaves state behind for a later press; fix if real.

## Tests (red first)

See `preview-email-planchange-3nov-acceptance-criteria.md`.
