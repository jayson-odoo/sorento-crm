# Cost price from supplier - Lane A end-to-end evidence (#1288)

Recorded with `agent-browser` (headless Chromium), session `tester-lane-a`, against the local
dev stack (FE :3000, BE :8000). Backend suite was green (124/124) before this run.

Seed data (scratch scripts under `/tmp/claude-0/scratch/`, not committed): supplier
XIAMEN TAIYANG TECHNOLOGY (code TAIYANG); products for most codes in
`tests/fixtures/cost_price/taiyang_price_list.xlsx`; existing links with CNY prices and a
45-day lead time so the fixture's rows land as changed / unchanged / new_link; two codes
(`ZZCPC-22-010`, `ZZCPC-28-020`) left unmatched; `CB2500SS-GY` bound only via the
separator-normalisation rung for source code `CB2500SS GY`; `ZZCPC-19-002` seeded as a
duplicate-code case against `ZZCPC-19-001`. Users: `captain@sorento-dev.com` (superadmin),
`meiling@sorento-dev.com` (purchasing), `kelvin@sorento-dev.com` (purchasing) - purchasing
role's cost-price permissions came from the migration, nothing granted by hand.

## S1 - upload, review, apply (as Mei Ling, purchasing role, not superadmin)

| Step | Screenshot | What it showed |
| --- | --- | --- |
| Sidebar nav | `01-list-1280.png` | Procurement > Cost Price Uploads reached via sidebar clicks from `/`, list renders as cards with Status/supplier filters and search. |
| Upload dialog | `02-upload-dialog-1280.png` | Supplier/currency selects, Valid from/to date fields, dropzone; `Upload` disabled until file + supplier + currency are set. |
| Review, Price changed | `03-review-changed-1280.png` | 258-row fixture: 235 changed, 21 new_link, 2 not-found, 2 duplicate-code, 2 needs-attention. Row 9 (`CB2500SS GY`) resolved to product `CB2500SS-GY` with an inline "supplier code rule: separator" hint, confirming the separator-only match rung. |
| Review, Not found filter + map | `04-review-mapped-1280.png` | Clicking the "Not found" stat card filters to just those rows; a "Pick a product" dropdown (searchable, human-readable codes, no UUIDs) is offered inline per row, with a Skip action. |
| Review, all resolved | `05-review-all-resolved-1280.png` | After mapping the Not-found rows and skipping/resolving the duplicate and needs-attention rows, all stat buckets read 0 except Price changed (235) and New for this supplier (21); Apply button reflects the live count ("Apply 256 changes"). |
| Review, mobile | `06-review-375.png` | Same review screen at 375px - stat cards wrap to a 2-column grid, table scrolls horizontally, floating Apply bar stays reachable; no clipping. |
| Applied | `07-applied-1280.png` | Set status pill flips to Applied; Lines tab keeps the resolved counts and the separator-match annotation. |
| History tab | `08-history-1280.png` | Set-level audit trail (Uploaded / Applied / Update events) with actor and timestamp. This is set-level only - see "Notes" below on per-line decision visibility. |
| Supplier > Prices tab | `09-supplier-prices-1280.png` | New cost rows appear with the upload's Valid-from date, status "Scheduled" (start date in the future), and a `Source` link back to CPC-0004. |
| Supplier > Prices, mobile | `10-supplier-prices-375.png` | Same tab at 375px, usable and non-clipped. |
| Product > Suppliers tab | `11-product-suppliers-tab-1280.png` | The mapped product's own Suppliers tab lists TAIYANG with the current/scheduled price, confirming the reverse relationship renders too. |
| Undated upload -> In force | `12-supplier-prices-inforce-1280.png` | A second, undated small upload (`ZZCPC-INFORCE-001`, no Valid-from/to) applies immediately; the resulting cost row shows Valid-from "Always", status "Always" (confirmed against `supplier_cost_service.price_in_force`/`cost_status` source - an undated winning row is labelled "Always", not "In force", by design), and is in force at 60.00 CNY straight away. |

## S2 - four-eyes verification (AC-S2-18)

| Step | Screenshot | What it showed |
| --- | --- | --- |
| Setting on | `13-settings-verification-on-1280.png` | As captain (superadmin), System Settings > Purchasing > "Verify cost price uploads by a second person" toggled on, with its off-state description visible. |
| Submit | `14-review-submit-verification-1280.png` | Mei Ling uploads a second small file (`ZZCPC-S2-DEMO-001`) and submits; the set moves to Pending Verification with a banner: "Submitted by Mei Ling ... A second Sorento person decides each line before anything changes." |
| Uploader cannot apply | `15-meiling-cannot-apply-1280.png` | Still logged in as Mei Ling, the set is Pending Verification and the review screen no longer offers her a bare Apply action on the still-undecided line - the four-eyes rule (same person cannot both submit and decide/apply) is enforced. |
| Verifier decides | `16-kelvin-decision-1280.png` | Kelvin (purchasing, different person) opens the same set; each line has independent Accept/Reject actions plus "Accept all" / "Return to submitter" / "Apply" at the bottom. |
| Line rejected | `17-kelvin-rejected-1280.png` | Kelvin rejects the one line with a reason (reason capture confirmed via the reject action's own dialog, not shown as a separate screenshot). |
| Applied after verification | `18-kelvin-applied-1280.png` | Kelvin applies; set status flips to Applied. Verified via a direct DB check that the rejected line's `unit_cost` was left unchanged (nothing written for a rejected line), matching the four-eyes contract even though the applied set's Lines tab still displays the file's proposed price/percentage for that row (see "Notes"). |
| Setting off | (not screenshotted, confirmed via settings page reload) | Toggled back off after the run, restoring default behaviour for other agents sharing the stack. |

## Mobile pass (375px), separately, as Mei Ling

| Step | Screenshot | What it showed |
| --- | --- | --- |
| List | `19-list-375.png` | Cost Price Uploads list at 375px: cards, search, filters, Upload button all usable, no clipping, no console errors. |
| Upload dialog | `20-upload-dialog-375.png` | Dropzone, supplier/currency selects, date fields all stack cleanly in a single column. |
| Review | `21-review-375.png` | Draft set (1 line) at 375px: stat grid, search, line card, floating Apply bar all reachable and legible. |
| Applied | `22-applied-375.png` | Set applied from the mobile viewport with no console errors. |

Console was checked after every step above (`agent-browser console` / `errors`); the only
recurring log lines were pre-existing Next.js dev noise (`Missing Description ... DialogContent`
Radix warning) and debug-level JWT extraction logs, not errors introduced by this feature.

## Notes / defects

1. **Rejected line has no visible marker after Apply (minor, worth a look).** After Kelvin
   rejects a line and applies the set (S2 flow), the Lines tab for the now-Applied set still
   shows that line in the "Price changed" bucket with the same "+14.3%" change badge as an
   accepted line - there is no "Rejected" badge or strike-through, and the set-level History tab
   (`08-history-1280.png`) only logs set-level events (Uploaded / Applied / Update), not
   individual line decisions or the reject reason Kelvin entered. The underlying data is correct
   (confirmed via a direct DB query: the rejected line's `unit_cost` was not written), so this is
   a display/traceability gap, not a data-integrity bug - a reviewer coming back later to CPC-0006
   cannot tell from the UI alone which line was rejected or why. Screen: `17-kelvin-rejected-1280.png`
   -> `18-kelvin-applied-1280.png`. Repro: enable the verification setting, submit a set as one
   user, reject one line with a reason as a second user, apply, then reopen the applied set's
   Lines tab.

2. **Mobile sidebar drawer link-click: one flaky non-navigation, not reproducible.** During the
   375px pass, clicking a link inside the mobile nav drawer (hamburger menu) once closed the
   drawer without navigating, on two different links, immediately after the harness had just
   recovered from a `CDP command timed out` / wedged-daemon episode (consistent with the shared
   agent-browser daemon note in CLAUDE.md - another agent's activity can disturb a session). On a
   clean retry from a fresh page load with fresh element refs, the identical drawer click
   (Procurement > Cost Price Uploads) navigated correctly on the first attempt (see
   `defect-mobile-drawer-before-click-375.png` for the pre-click state, and `19-list-375.png` for
   the successful result). I could not reproduce the non-navigating click cleanly, so I'm not
   filing it as a confirmed app defect - flagging it only in case another agent sees the same
   symptom and can correlate it with daemon contention.

No other defects found. The separator-only code match, the duplicate-code and needs-attention
buckets, the "Always" vs "Scheduled" cost-row status labelling, and the four-eyes verification
gate (submitter cannot self-apply) all matched the UAC and the service-layer source.

## Housekeeping

- Backend suite: 124/124 passing at the start of this run (see prior commit
  `test(purchasing): tighten three cost price tests (#1288)`).
- Evidence PNGs and this README are committed with `[skip ci]`, no push.
- Browser session `tester-lane-a` closed at the end of the run (not `close --all`).
- Verification setting was switched back off after S2, and the discarded/superseded draft set
  from the seeding false-start was removed via its own 10s deferred Discard action, not by
  editing the database.
