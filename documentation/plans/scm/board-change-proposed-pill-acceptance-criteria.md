# UAC: Change proposed pill

- AC-1 A confirmed line named by a pending planning change, with no saved draft, reads "Change proposed" on the board (list and grid), not "Saved".
- AC-2 That row shows no Undo arrow.
- AC-3 A line with a real saved draft still reads "Saved" with its Undo and "Saved by" popover.
- AC-4 Confirm (N) still counts the pre-marked line; pressing Confirm behaves exactly as today.
  Superseded 25 Sep 2026 (issue #1245, `PLAN-esb-change-row-refresh.md` S5): Confirm (N) counts
  only a SAVED verdict, never a bare pre-mark, and the payload leaves it out.
- AC-5 Usable at 375px and 1280px.
