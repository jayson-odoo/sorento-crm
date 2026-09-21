# UAC: fulfilment board - left-out line is loud, reachable, fixable

Plan: `PLAN-board-confirm-left-out.md`. Track: small fix.

- **AC-1** Discontinued line whose suggestion is Buy: CS types a reason and presses Save
  decision with the quantities untouched. The reason stays in the box, the button reads Saved,
  the red "needs a reason" line is gone, and the pill reads Saved.
- **AC-2** That line is then counted in Confirm (N) and Confirm flips it to Confirmed. The
  frozen decision carries the reason (visible in the trail).
- **AC-3** A reason typed on a suggested borrow row survives an approving save the same way.
- **AC-4** Any line Confirm will leave out shows in a warning banner above the cards
  (`role="alert"`, warning tone, icon). Each left-out line is named as a link.
- **AC-5** Clicking a name in the banner, from Grid or List, lands on List view with that
  line's decision panel open and scrolled into view.
- **AC-6** After a Confirm that left lines out, the toast states both counts.
- **AC-7** Verdict column header sorts the list: Suggested, Saved, Confirmed, Rejected.
- **AC-8** Banner and list usable and non-clipped at 375px and 1280px.
