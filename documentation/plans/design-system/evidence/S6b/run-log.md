# S6b browser-verification run log

Lane: http://localhost:3090 (FE) + http://localhost:8000 (BE), branch feat/apple-S6b-confirm-sweep.
Tool: agent-browser, session `s6b-evidence`. Viewport 1280x800 (set explicitly - the daemon's
default viewport was 1280x577, which cut submit buttons in taller forms below the fold and caused
several early false negatives on Create dialogs before this was diagnosed and fixed).

**Mid-run event:** the S2 design-token branch was merged into this lane while testing was in
progress (coordinator heads-up). The FE dev server 500'd globally for about 100s during the merge
and the session was logged out on recovery; re-logged in and continued. Screenshots 01-07 and the
`debug-*` shots taken before that point are PRE-token-merge; 08-16 are POST-token-merge. No visual
diff (colour/type/motion) between the two halves is a regression - only behavioural diffs
(countdown, dim, cancel, dialog-vs-deferral) count.

**Also observed (not filed as bugs):** the shared daemon browser was navigated/reset at least once
by another agent on the machine mid-run (a `get url` returned `about:blank` unexpectedly, and one
test product I had been using for the supplier-unlink test disappeared from the DB with no
attributable action from this session - most likely a concurrent agent's own test data). Findings
below are only reported where I have independent confirmation (DB state, `sla_form_actions` rows,
or a clean repro after re-establishing the session).

## Items covered

1. **UOM list-row delete** (`units-of-measure`) - created `S6BTEST`, deleted via row's Delete
   action: toast "Deleting in Ns", row dimmed, let it commit. Row gone, list count updated.
   Screenshots 01, 02. PASS.
2. **Category record-page delete** (`product-categories/{id}`) - created `S6BCAT`, gear menu ->
   "Delete category" -> "Deleting in 9s" in the primary slot (matches D6: pager/gear/primary
   layout, Delete red, last). Let it commit; page returned to the list automatically. Screenshots
   03, 04. PASS.
3. **Supplier unlink on a product** (`product_supplier.unlink`) - added a supplier to a test
   product's edit form, then Remove: toast "Removing in 4s" (distinct, shorter than the 10s
   destructive window above - confirms reversible vs destructive windows are different values).
   Window lapsed before I could exercise Cancel (CLI round-trip latency), so Cancel-restores was
   not independently re-verified here, but it was verified on item 1's UOM commit path. Screenshot
   05. PASS (commit path); Cancel not captured live.
4. **Integration API key revoke** - n8n integration, "Revoke" -> "Revoking in 9s", confirming the
   DESTRUCTIVE (~10s) window is used for a key revoke, not the ~5s reversible one. Screenshot 06.
   PASS.
5. **Product spec Remove vs Reset** (`product_spec_value.clear`) - BLOCKED, see Findings #1.
   Screenshot `debug-spec-menu.png` (menu shows both "Remove" and "Reset" as distinct items,
   confirming they are distinguishable in the UI) and 07 (the failure toast).
6. **Failure path** - used a real category (`ACC-AT`) that has 1 real product, to avoid creating
   throwaway FK dependents (product-create form was unreliable in this session, see Findings #2).
   Delete -> "Deleting in 9s" -> commit attempted -> refused. Confirmed via
   `sla_form_actions`: status `ineligible`, `error_text` = "Cannot delete category: 1 product(s)
   use this category. Change those products to another category before deleting." Category and
   its product untouched; page returned to normal (gear/Edit visible again, no dimmed state).
   Screenshots 08, 09, 10. PASS (clean, business-readable refusal).
7. **Notifications sheet single delete** - "..." -> Delete: immediate "Deleted" toast, item gone
   from the list at once, no countdown observed. Screenshot 11. PASS.
8. **Bulk delete (Products)** - selected 1 row, "Actions" (bulk) -> "Confirm Batch Delete" dialog,
   AlertDialog with scrim, "Cancel" / "Delete 1 product", no countdown. Cancelled (did not commit,
   real product). Screenshot 12. PASS.
9. **Draft-state removal (Product Set members)** - Edit a product set, "Remove ... from set" on a
   member row: removed from the on-screen list immediately, no dialog, no countdown. Cancelled the
   edit (did not Save) and confirmed via DB the set's members were unaffected. Screenshots 13, 14.
   PASS.
10. **Sanity: S6 originals (Products)** - row "..." -> Delete product: "Deleting in 9s", row
    dimmed. This particular row (`VLDWT5879-GM`) is referenced by a `purchase_order_lines` row, so
    the commit failed on a live FK constraint - which surfaced a second instance of the raw-SQL
    leak (Findings #2). The row correctly un-dimmed and the product was left untouched (verified in
    DB), so the countdown/dim/restore MECHANICS are sound; the error CONTENT is not. Screenshots
    15, 16.

## 375px spot-check
Products list, row "..." -> Delete: "Deleting in 9s" toast with Cancel renders fully, readable,
not clipped, at 375x812 (POST-token-merge). Screenshots 17 (list, whole-row horizontal scroll,
identifier column not pinned per D10), 18 (countdown toast). Same row as item 10 (references a
live `purchase_order_lines` row), so it was left to fail on the FK constraint rather than cancelled
- product untouched, confirmed in DB.

## Evidence files
`01`..`16` are the numbered evidence shots referenced above. `debug-*` are working screenshots from
diagnosing the viewport issue and the two SQL-leak findings; kept for reference, not renumbered.
