# S4 evidence - tabs migration, row click, mobile one-offs

Verified with agent-browser (headless) against the `feat/apple-S4-tabs-rows-mobile` worktree,
FE http://localhost:3090, BE http://localhost:8000. Login via E2E_EMAIL/E2E_PASSWORD from
`sorento_crm_frontend/.env.local`. Navigated by sidebar/command-palette clicks from `/`, never a
deep URL. Session `--session s4-evidence`.

| AC | Screen | Pass/Fail | Screenshot | Note |
|----|--------|-----------|------------|------|
| S4-02 | Product create tab strip (375) | Pass | S4-02-product-create-375.png, S4-02-product-create-scrolled-375.png | overflow-x auto, right-edge mask fade, scrollWidth 655 vs client 343, page scrollWidth stays 375; scrolled view shows Suppliers/Attachments in full |
| S4-02 | Product create tab strip (1280) | Pass | S4-02-product-create-1280.png | icon + label, blue underline, matches Users-style tabs |
| S4-02 | Settings, 10 tabs (375) | Pass | S4-02-settings-375.png | scroll + fade confirmed via computed style (scrollWidth 1302/343), page scrollWidth 375 |
| S4-02 | Settings, 10 tabs (1280) | Pass | S4-02-settings-1280.png | same tab primitive as Product create; not all 10 fit at 1280 either, which is expected scroll behaviour |
| S4-02 | Project detail, 11 tabs (375) | Pass | S4-02-project-detail-375.png | pager "2/5" + gear + primary shown per D6; tab strip scrolls, page scrollWidth 375 |
| S4-02 | Lead detail (375) | Unreachable | - | No open leads exist in this dev DB ("No open leads" empty state on Project Sales > Leads); cannot open a lead detail to check its tab strip |
| S4-02 | Sales Order detail, 4 tabs (375) | Pass | S4-02-sales-order-detail-375.png | fits without needing scroll at 375; status pill "Outstanding" rounded+dot |
| S4-02 | Workflow builder, 5 tabs (375) | Pass | S4-02-workflow-builder-375.png | scroll + fade confirmed, page scrollWidth 375 |
| S4-02 | Order detail (Delivery Orders), 3 tabs (375) | Pass | S4-02-order-detail-375.png | status pill "Picked Up / In Transit" rounded+dot |
| S4-04 | Product Categories: Name column pinned (375) | **Fail** | S4-04-product-categories-375.png, S4-04-product-categories-scrolled-FAIL-375.png | Scrolling the table right takes the Name column with it (shows "iption"/Description at the left edge, no Name visible); Name is NOT pinned |
| S4-04 | Product Specifications out-of-date banner wraps normally (375) | **Fail** | S4-04-product-specifications-FAIL-375.png | Banner text renders one word per line stacked vertically ("The / rules / have / changed / since / the ..."), not a normal wrap; page also shows scrollWidth 465 (an off-screen element pushes width) |
| S4-04 | Tickets list / Ticket detail (375) | Unreachable | S4-04-ticket-detail-375.png (partial) | No sidebar entry reaches `/ticket-management/tickets` (grepped `menu.config.tsx`: no match) so the list/detail named in the AC cannot be opened via sidebar. The dashboard's "Ticket" task card instead opens Conversation SLA Tracking detail, checked instead: only one floating button (AI assistant), no overlap |
| S4-04 | Product detail Pricing Summary values (375) | Pass | S4-04-product-pricing-summary-375.png | List Price / Cost Price / Invoice Price each on its own line, clear spacing, never touch |
| S4-04 | SCM Reorder popover/ledger (375) | Pass | S4-04-scm-reorder-popover-375.png | "Suggested qty" explanation lightbox scrolls in its own container, page scrollWidth stays 375 |
| S4-04 | System > AI Assistant > Usage (375) | **Fail** | S4-04-ai-usage-FAIL-375.png | Page scrollWidth 497 (not 375); the "All AI usage" filter select (fixed 240px) does not wrap under the date-range control in the toolbar row, pushing the page to scroll sideways |
| S4-04 | Catalogue > Lookup Sets (375) | Pass | S4-04-lookup-sets-375.png | Raw table scrolls inside its own ScrollArea container, page scrollWidth 375 |
| S4-04 | Dashboard: page title + task card wrap (375) | **Fail** | S4-04-dashboard-FAIL-375.png | Page title "Dashboard" present (pass), but the "Ticket" task card's title renders as one character per line ("T/i/c/k/e/t") because its flex child computes to 0 width; the sibling "Complaint · CMP2026-0010" card wraps normally by comparison |
| S4-04 | Sign-in card centred (1280) | Pass | S4-04-signin-1280.png | Card ~446px wide, centred, bounded; verified via logout -> screenshot -> login back in |
| S4-03 | Brands row tap opens edit lightbox (375) | **Fail** | S4-03-brands-rowclick-FAIL-375.png | Row has `cursor-pointer` + onclick styling but clicking it (tried two different rows) opens nothing - no dialog in the DOM, no URL change, no console error |
| S4-03 | Contact Access Agents row tap opens edit lightbox (375) | **Fail** | S4-03-contact-access-agents-rowclick-FAIL-375.png | Only the Code cell is a real anchor, and its href goes to a detail ROUTE (`/user-management/access-agents/{id}?...`), not a lightbox; the rest of the row is not clickable at all |
| S4-03 | Campaigns row tap opens detail with list query in URL | Unreachable | - | No campaigns exist in this dev DB ("No data available" empty state on Marketing > Campaigns) |
| S4-03 | Units of Measure row tap opens detail with list query in URL (375) | Pass (with a note) | - | Row is a real anchor, navigates to `/master-data-management/units-of-measure/{id}?page=1&limit=50&sort=created_at&dir=desc` - a detail ROUTE, not the lightbox the AC text names for this entity. Functionally it satisfies D3 (detail route if one exists) but diverges from the AC's specific wording, same pattern as Contact Access Agents above |
| S4-03 | Log table has no pointer cursor / no navigation (Audit Logs, 375) | **Fail** | S4-03-audit-logs-cursor-FAIL-375.png | Row computed style is `cursor: pointer` (class `cursor-pointer` present) and the row carries an onclick; clicking it does nothing (no dialog, no navigation) - a dead affordance that should not exist on a log table |
| D2 | Products list badges (375) | Pass | D2-products-list-375.png | (list itself shows only the pinned Product Code column at this scroll position; status column confirmed round/tinted on other lists below) |
| D2 | Product Categories badges (bonus) (375) | Pass | S4-04-product-categories-375.png | "Active" pills rounded, tinted green, with dot |
| D2 | Administrative Users list badges (375) | Pass | D2-users-list-375.png | "Active" pills rounded, tinted green, with dot |
| D2 | Sales Agents list badges (375) | Pass | D2-sales-agents-list-375.png | "Active" pills rounded/tinted/dot; "Import" source tag is a plain rounded grey pill with no dot (correct - tags carry no dot per D2) |
| D2 | Email Outbox badges (375) | Pass | D2-email-outbox-list-375.png | "failed" pills rounded, tinted red, with dot |

## Ranked failures

1. **Dashboard task card title wraps character-by-character** (S4-04) - the "Ticket" card's title
   sits in a flex child that computes to 0px width, so `overflow-wrap: break-word` breaks every
   character onto its own line. Observed: "T/i/c/k/e/t" stacked vertically. Expected: normal word
   wrap, as the sibling "Complaint · CMP2026-0010" card does correctly.
2. **Product Specifications out-of-date banner wraps the same way** (S4-04) - "The rules have
   changed since the..." renders one word per line. Same 0-width-flex-child symptom as #1, on a
   different page; likely a shared component or pattern.
3. **Brands and Contact Access Agents rows do not open an edit lightbox on tap** (S4-03) - Brands
   shows a pointer cursor and an onclick but the click is a no-op; Contact Access Agents only
   hyperlinks its Code cell, to a detail route, and the rest of the row is dead. Neither matches
   "row tap opens the edit lightbox."
4. **Product Categories Name column is not pinned** (S4-04) - scrolling the table right takes the
   Name column with it instead of holding it at the left edge.
5. **Audit Logs (a log table) shows a pointer cursor and an onclick with no resulting action**
   (S4-03) - should have neither, per "log and sub-tables have no pointer cursor."
6. **AI Assistant > Usage page scrolls sideways at 375** (S4-04) - the filter toolbar's "All AI
   usage" select (fixed 240px) does not wrap under the date-range control, pushing page
   scrollWidth to 497.

## Unreachable (with reasons)

- **Lead detail** - no open leads exist in this dev DB (Project Sales > Leads is empty).
- **Tickets list / Ticket detail** (as named in the AC) - `/ticket-management/tickets` has no
  sidebar entry (`menu.config.tsx` grepped, no match), so it cannot be reached by sidebar
  navigation under this task's constraints. Checked Conversation SLA Tracking detail instead,
  reached from the dashboard's "Ticket" task card, since that is what "Ticket" actually links to
  today; no floating-button overlap there.
- **Campaigns row click** - no campaign records exist in this dev DB (empty state only).
- **Loading Plan detail** - skipped per the brief (known 500 on this dev DB).

## Deviation worth flagging (not scored as fail)

UOM row click opens a detail route, not the edit lightbox the S4-03 AC text names for it
(same pattern as Contact Access Agents). This is likely an intentional evolution since a real
detail page now exists, but it means the AC's own categorisation of "lightbox-edited" entities is
stale for at least two of its three named examples.

## Run 2

Targeted re-check of 9 items after fixes, agent-browser headless, session `s4-run2`, FE
http://localhost:3090, BE http://localhost:8000. Logged in via E2E_EMAIL/E2E_PASSWORD, navigated
by sidebar clicks from `/`. No code touched, no git commands run.

| # | Check | Pass/Fail | Screenshot | Note |
|---|-------|-----------|------------|------|
| 1 | Dashboard task card wraps normally (375) | Pass | run2-dashboard-task-card-375.png | "Ticket" title on one line, "Complaint · CMP2026-0010" wraps by word, not per-character |
| 2 | Product Specifications out-of-date banner (375) | Pass | run2-product-specifications-banner-375.png, -full-375.png | Badge on own line, message wraps in normal words, button below; `document.documentElement.scrollWidth` = 375 |
| 3 | Product Categories Name column pinned (375) | Pass | run2-product-categories-initial-375.png, -scrolled-375.png | Scrolled the inner container to max (scrollLeft 433/774); Name header stays `position: sticky; left: 0px; z-index: 10`, opaque bg; Actions column reached; one scrollbar |
| 4 | AI Assistant Usage: width + filter wrap + table scroll (375) | Pass | run2-ai-usage-375.png, -recentqueries-before/scrolled-375.png | scrollWidth 375; "All AI usage" select wraps under date range; "Recent queries" table has `thead.sticky.top-0`, scroller `max-h-[420px] overflow-auto` (scrollHeight 2627), header stayed fixed while rows changed underneath after `scrollTop=600` |
| 5 | SCM Reorder Planning locations popover sticky header (375) | **Fail** | run2-reorder-locations-popover-top-375.png, -scrolled-375.png | Header `th/tr/thead/table` all `position: static`; `getBoundingClientRect().top` moved 1:1 with scrollTop (168.9px at scrollTop=0 -> 153.9px at scrollTop=15, a 15px shift) - header scrolls away with content, not pinned |
| 6 | Brands row click / View products / keyboard (1280) | Pass | run2-brands-rowclick-1280.png, run2-brands-keyboard-enter-1280.png | Row body click opens Edit Brand lightbox, no nav; "View products" link (target=_blank, real href) opens a new tab only, no lightbox, current tab unchanged; Tab-focus + Enter on row opens the lightbox |
| 7 | Audit Logs row opens dialog (1280) | Pass | run2-audit-logs-dialog-1280.png | Row click opens "Audit entry details" dialog |
| 8 | UOM page/limit/sort restore via Back (1280) | Pass (adapted) | run2-uom-back-restore-1280.png | Only 8 UOM rows exist in this dev DB (no limit option, 25/50/100, produces a page 2), so "page 2" is unreachable by construction; verified limit=25 + sort=uom_name + dir=asc instead - Back restored all three via URL `?page=1&limit=25&sort=uom_name&dir=asc` |
| 9 | Project detail tabs are real Radix tabs (1280) | Pass | run2-project-detail-tabs-1280.png | All 14 `[role="tab"]` elements' `aria-controls` resolve to an existing element with `role="tabpanel"` |

## Run 2 ranked failures

1. **SCM Reorder Planning "On hand" locations popover header is not sticky** (check 5) - `position: static`
   the whole way up the DOM (th/tr/thead/table); the header row scrolls off with the content instead of
   staying pinned while the row body scrolls beneath it. Confirmed by measuring `getBoundingClientRect().top`
   before/after a 15px programmatic scroll: it moved by exactly 15px.

   Fixed in 6798e65c9 (item 1): the head is `sticky top-0 z-10 bg-popover` on the
   `max-h-72 overflow-auto` scroller. Note for the re-run: the reported `position:
   static` is not explained by that file, which has carried `sticky top-0` since
   before S4, and a controlled probe in the running app (a collapsed table and a
   separate one, sticky thead in each) showed both stick - as check 4 on this very
   run also found. Please name the exact popover on the re-run if it recurs.

## Run 2 verdict

7 of 8 testable items pass; the one carried-over regression is the SCM Reorder Planning product-locations
popover, whose table header is not actually sticky despite the surrounding scroll container being correct.
