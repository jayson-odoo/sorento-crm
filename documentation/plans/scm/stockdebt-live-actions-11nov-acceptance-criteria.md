# UAC: STOCKDEBT-LIVE-ACTIONS

Plan: `PLAN-stockdebt-live-actions-11nov.md`.

- AC-1 After a snapshot, a PO link made from Decide shows in that line's Assigned, Covered by and
  Status (Pinned) as soon as the popup closes, and again after a reload.
- AC-2 An unlink after the snapshot drops the Pinned status and the PO from Now.
- AC-3 A move (the PO line now names another SO line) pins the other line instead.
- AC-4 Sales order, Line, Location, Delivery date, Ordered, Delivered and Outstanding read as
  frozen whatever happens to the book afterwards.
- AC-5 Short = frozen Outstanding less what covers the line in time today.
- AC-6 A line no longer in the book keeps its frozen cover; Now reads SO cancelled / Open 0.
- AC-7 Reserve requests, OI rows and the Decision follow today's state (unchanged behaviour).
- AC-8 Decide shows "Change PO..." under "Link to PO...". It is greyed with the reason unless
  every ticked line is covered by exactly one PO line and AutoCount can link and unlink.
- AC-9 The popup shows each line's current PO and a picker of the other open PO lines of the
  product (same book), with Free. Change unlinks the old PO line first and sends the new link only
  when the unlink is done; the old PO line stays open with its qty. A refused unlink changes
  nothing; a link refused after the unlink says the line is now uncovered.
- AC-10 A new PO line with less free than the linked qty is refused: "PO Y has only N free", and
  nothing is sent to AutoCount.
- AC-11 With "AutoCount links from Stock Debt" off, the change route answers 403 and Decide is
  not shown.
- AC-12 Change PO moves the open balance still due on the old PO line (ordered less received,
  cancels counted once); what was received stays with the old PO. With nothing open, Change PO is
  greyed "Nothing is left open on PO X to change" and the route refuses with the same words.
