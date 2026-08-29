# S3 Phase 1 browser verification - detail header, action parity, page-scoped pager

Verified against `apple-alignment-acceptance-criteria.md` (S3-01 to S3-07, D3-D6, D15) and
`PLAN-apple-alignment.md` 3.3/3.4. Worktree `agent-a4fcc3bb35ba62b83`, branch
`feat/apple-S3-detail-header-pager`, FE `http://localhost:3090`, BE `http://localhost:8000`.
Entities wired in Phase 1: Users, Delivery Orders, Products. agent-browser 0.27.0, headless,
`--session s3-evidence`. Login via `E2E_EMAIL`/`E2E_PASSWORD`. No records created, saved or
deleted; all Delete/Trash menu items were opened for inspection then closed with Escape, never
confirmed.

## Result table

| AC | Pass/Fail/Unverified | Screenshot | Note |
|----|----|----|----|
| S3-01 (Users) | Pass | S3-01-users-toolbar-1280.png | Toolbar = title "User" + breadcrumb left, one "Back to users" right. Back href `?page=1&limit=10&sort=name&dir=asc`. |
| S3-01 (Delivery Orders) | Pass | S3-01-S3-02-do-toolbar-1280.png | Back href carries `page`, `limit` AND the active `order_status_id` filter (key-parity risk item 6, confirmed). |
| S3-01 (Products) | Pass | S3-01-S3-02-products-toolbar-1280.png | Back href carries `page`, `limit`, `sort`, `dir` AND the active `category_id` filter. |
| S3-02 record card order (Users/DO/Products) | Pass | S3-01-users-toolbar-1280.png, S3-01-S3-02-do-toolbar-1280.png, S3-01-S3-02-products-toolbar-1280.png | All three: pager, gear, one primary button, left to right. |
| S3-02 gear = secondary, separator, Delete last red (Users) | Pass | S3-02-users-gear-1280.png | Impersonate user, Send invitation link, separator, "Trash user" red last. |
| S3-02 gear (Delivery Orders) | Pass | S3-02-do-gear-1280.png | "Mark as Picked Up / In Transit", separator, "Delete delivery order" red last. |
| S3-02 gear (Products) | Pass | S3-02-products-gear-1280.png | Only "Delete product" (no secondary items on this record) - correctly still red, still last. |
| S3-02 list "..." = same items same order as gear (Users) | Pass | S3-02-users-rowmenu-1280.png | Identical to S3-02-users-gear-1280.png. |
| S3-02 list "..." parity (Delivery Orders) | Pass | S3-02-do-rowmenu-1280.png | Identical order to record gear. |
| S3-02 list "..." parity (Products) | Pass | S3-02-products-rowmenu-1280.png | Identical order to record gear. |
| S3-03 pager counter "n/pageSize", no extra request (Users) | Pass | (network eval, no screenshot) | Row 3 of a `limit=10` `sort=name` list opened as "3 / 10"; `performance.getEntriesByType('resource')` count for `/api/v1/user-management/users?` stayed at 2 before and after opening the detail. |
| S3-03 (Delivery Orders, status filter active) | Pass | (network eval) | Row 3 of a `New Order`-filtered, `limit=50` list opened as "3 / 50"; list-endpoint resource count unchanged (5 before, 5 after Next). |
| S3-04 Next/Previous walk + fetch-once at page boundary (Users) | Pass | (network eval) | 7x Next from 3/10 landed on 10/10, zero new `/users?` requests. One more Next crossed to page 2 ("1/10"), fired exactly one new request (`page=2`). Previous from there returned to page 1 landing on "10/10" with no further request (cache reuse). |
| S3-04 Previous disabled at page 1 row 1 | Pass | (eval, `.disabled` read) | Walked back to "1 / 10"; `Previous`.disabled === true, `Next`.disabled === false. |
| S3-04 Next disabled at the true last page's last row | Unverified | - | The dev DB's Users table has hundreds of scripted `test.local` rows (pytest leftovers); stepping Next reached page 207+ (2000+ users) without disabling. Impractical to reach the genuine end in this session. Boundary *mechanism* is verified by symmetry (start boundary above, and 200+ consecutive page-crossings all fetched exactly once with no errors). |
| S3-05 reload/deep link keeps pager | Pass | S3-05-users-deeplink-1280.png | Reopened `/user-management/users/<id>?page=1&limit=10&sort=name&dir=asc` fresh; pager read "3 / 10" immediately. |
| S3-05 `page=999` hides pager, Back still works | Pass | S3-05-users-page999-1280.png | Pager area gone (only gear + Edit remain); "Back to users" present and functional. |
| Item 6: DO with status filter | Pass | S3-01-S3-02-do-toolbar-1280.png | Covered above; `order_status_id` rides in both the row href and the Back href. |
| Item 6: Products with category filter | Pass | S3-01-S3-02-products-toolbar-1280.png | Covered above; `category_id` rides in both. |
| Item 7: row click opens detail | Pass | - | Confirmed on Users/DO/Products throughout the run. |
| Item 7: Enter on a focused row opens it | Pass | - | Focused a Users row (real DOM focus, `tabindex="0"`), pressed Enter via the tool, navigated to that row's detail. |
| Item 7: middle-click opens a new tab | **Fail** | - | See "Failures" below. `window.open` fires correctly with the right href, `_blank`, `noopener,noreferrer` - but the **current tab also navigates** to the same URL, which is not middle-click semantics. |
| S3-02 at 375 - wraps under identity, nothing clipped (Users) | Pass | S3-02-users-detail-375.png | Pager/gear/Edit user drop to their own row below the avatar+name; no clipping. |
| S3-02 at 375 (Delivery Orders) | Pass | S3-02-do-detail-375.png | Same wrap pattern. |
| S3-02 at 375 (Products) | Pass | S3-02-products-detail-375.png | Same wrap pattern (pager absent here because the deep-link URL I used dropped the original `sort`/`category_id`, which is itself a correct S3-05 "record not on this page's cache key" case, not a bug). |
| Item 8: "..." reachable in the scrolled grid (Users) | Pass | S3-08-users-list-375-start.png, S3-08-users-list-375-scrolled.png | Identifier column visible at scroll 0; "..." fully visible and tappable at max scroll. |
| Item 8: "..." reachable (Delivery Orders) | Pass | S3-08-do-list-375-scrolled.png | "..." is the last column at max scroll, fully visible. |
| Item 8: "..." reachable (Products) | Pass | S3-08-products-list-375-scrolled.png, S3-08-products-list-375-actionscol.png | At *maximum* scroll the actions column had already scrolled past (three more columns - Type, Variant of, Variants - follow it), so the first screenshot shows no "..." button. Scrolling to an intermediate offset shows it fully reachable and tappable. Column *order* is a listing/personalization detail outside S3's scope, not an S3 defect. |

## Ranked failures

1. **Middle-click on a `rowHref` row also navigates the current tab, not just a new one.**
   Entity: Users (list `/user-management/users`), reproduced twice with a clean synthetic
   `auxclick` (`button: 1`) dispatch after wrapping `window.open`. Observed: `window.open(href,
   '_blank', 'noopener,noreferrer')` fires (correct) **and** `window.location.pathname` changes
   to the same detail URL in the current tab (incorrect). Expected per plan 3.2 D5: `onAuxClick
   (middle) -> window.open` only: current tab must stay on the list. This looks like a shared
   click handler that doesn't `return` after the `window.open` branch, so it falls through to
   the `router.push`. Not part of the S3 UAC ids directly (it is S1-06/D5, which S3's rowHref
   reuse depends on), but it affects every `rowHref` list, so flagging here. Not screenshotted
   (a `window.open` call is not visible in a static image); reproduction is the eval script
   output quoted in the table above.

## Unreachable / not exercised

- **S3-04's true "last page, last row, Next disabled" case** - the dev Users table carries
  several hundred pytest-seeded `*.test.local` rows; walking to the genuine last page (200+
  pages at limit 10) was not practical in this session. See table row above for what was
  verified instead.
- Delivery Orders / Products S3-04 boundary walk (Previous-disabled-at-row-1,
  Next-disabled-at-last-row) was not separately re-driven to exhaustion; only the "walks forward
  one page-crossing, fetches once, cache reuses on the way back" mechanics were confirmed on
  Delivery Orders (16/50 -> 17/50, zero new list requests), relying on the Users run for full
  boundary coverage since the pager is one shared implementation (`useListPager`/`ListPager`).
- One instance during rapid iteration (Delivery Orders list) showed the `order_status_id` filter
  reset to unset when I chained an Escape + row click, and the list issued a stray
  `.../users?...page=1...` request that returned 401 during a scripted 150-click stress loop on
  the Users pagination "Go to next page" control (unrelated legacy `DataGrid` list pager, not the
  S3 record pager). Neither was cleanly reproduced in isolation; noted for awareness, not filed
  as a ranked failure.

## Browser session

`agent-browser@0.27.0`, session `s3-evidence`, closed cleanly at the end of this run (not
`close --all`).
