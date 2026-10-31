# PLAN: user guides refresh for merges since 17 Oct

Status: in review (small fix track: docs plus the Outline sync script/workflow fix; no app code, no migration, no auth change)

Lane: DOCS-REFRESH

## Why

The in-app AI assistant answers "how do I" questions from the user guides
(`documentation/user-guides/`, mirrored to Outline and read through MCP `user_guides_read`).
The guides were last refreshed on 17 Oct (#1748). Since then roughly 50 merges changed
user-visible behaviour, so the assistant answers some questions from stale pages. Owner goal
(31 Oct): a staff member who does not know the system asks the assistant panel and understands
the answer without contacting the owner.

## Scope

1. Map every user-visible merge since 17 Oct to an existing guide page or "missing"
   (table below, filled in as the lane progresses).
2. Update or add guide pages, following `documentation/user-guides/README.md` conventions
   (H1 title, one-line summary, Steps with verbatim UI labels in bold, what gets created,
   how you are notified, See also) and register new pages in `.outline-sync.json` only through
   the sync script (new pages get their Outline id on the next push; no hand-made ids).
3. Before writing: check the Outline -> repo sync branch so Outline-side edits are not
   overwritten.
4. Do not dispatch the repo -> Outline push. The owner runs it after merge.

## Outline sync check (31 Oct)

`origin/bot/outline-user-guides-sync` (406ab415, 31 Oct 03:39 UTC) has no open PR. It adds
`docs/user-guides/README.md` + `.outline-sync.json` (a `docs/` path, not `documentation/`),
and its Overview body is an OLDER copy of the repo README (the repo has the later wording).
So no Outline-side edit is newer than the repo and nothing needs merging. The path mismatch is
reported to the owner separately: `scripts/sync_user_guides_outline.py:46` sets
`GUIDES_DIR = REPO_ROOT / "docs" / "user-guides"` and the workflow's `add-paths` is
`docs/user-guides/**`, while the guides live under `documentation/user-guides/`.

## Feature map

`git log origin/main --first-parent --since=2026-10-17` has 251 merges (202 from 17-29 Oct, 49
from 30-31 Oct). About half are CI, tests, performance, release fixes or chatbot-internal
resolver/prompt work with no staff-facing change. The user-visible ones, by area:

### Updated or added in this lane

| Merge(s) | Feature | Page |
|---|---|---|
| #1982 #1999 #2009 #2021 #2022 #2025 | Chatbot Console Agent mode: tools, confirm/undo, grace window, reasoning, Jev routing, budgets | `system-management/chatbot-console-agent-mode.md` (new); `troubleshoot-chatbot-turn-failures.md` (test-turn exception) |
| #2020 | Quotation lines catalogue-only, delete guard, New Product Application for bespoke | `project-sales-rep/work-a-project-quotation.md` (new); `product/manage-products.md` |
| #1997 | Send a quotation through the salesperson's own WhatsApp | `project-sales-rep/work-a-project-quotation.md` |
| #1987 | Quotation sign page + PDF (logo, Quotation No., sections, terms tick, signatures) | same |
| #1984 #2017 | Customer qty/price amendment suggestions, Apply decisions | same |
| #1983 #2023 | Escalate a missing drawing / photo from a quotation line; PIC side | same + `marketing/answer-a-drawing-or-photo-request.md` (new); `_shared/escalate-a-task-or-enquiry.md`, `_shared/dashboard-my-tasks-sla.md` |
| #1985 #2029 | Sample request starts from the project's quotation | `project-sales-rep/sample-request-from-quotation.md` (new) |
| #2000 | SO line description: SO lines, Fulfilment Planning, OI email per-product switch | `product/manage-products.md`, `supply-chain/order-inquiry-handover-email.md`, `supply-chain/local-buy-and-borrow-source.md` |
| #2019 | Product edit permission enforced (buttons hidden, access denied) | `product/manage-products.md` (Who can do what; stale menu path and row icons fixed) |
| #2026 #1742 | MCP access token on Settings > Integrations | `user-management/mcp-access-token.md` (new) |
| #2012 #1961 | Embeddings page (Lookup words, Records, Try a phrase, backfill) | `system-management/embeddings.md` (new) |
| #1986 | Order inquiry rows confirm themselves (To order / Done, manual override) | `supply-chain/upload-plan-data.md`, `supply-chain/order-inquiry-documents.md` |
| #1995 | Request CS to reserve: tick lines before sending | `supply-chain/order-inquiry-documents.md` |
| #1953 #1911 | Salesperson MY REQUESTS opens the CRM pages, only their own rows | `project-sales-rep/submit-via-portal.md` |
| #2008 | Server refuses a submit with required fields empty | `project-sales-rep/submit-via-portal.md` |
| #1991 #1957 #1966 | Register a project: Check first, secondary lead, no lead link, requirement before Spec In | `project-sales-rep/register-a-project.md` (new) |
| #1975 #1998 | Undated DOs import with a warning, never wiped; edit form never stamps today | `warehouse/upload-delivery-orders.md`, `delivery-orders/track-delivery-orders.md` |
| #1992 | A voided PR/SF can no longer be approved | `project-sales-admin/purchase-request-lifecycle-and-next-actions.md` |
| #2001 #1972 #1988 | Allowed item classes on contacts and tags | `user-management/contact-brands-and-item-classes.md` (new) |
| #2003 | Conversations search finds message text | `sla/search-conversations.md` (new) |
| #1952 #1925 | A rejected form sent back reads Appealed | `project-sales-rep/submit-via-portal.md`, `project-sales-admin/review-*.md`, `project-sales-manager/approve-via-email.md`, `technical-team/complaint-lifecycle-and-next-actions.md` |

### User-visible, still missing a guide (follow-up)

| Merge(s) | Feature | Where it would go |
|---|---|---|
| #1752 #1778 #1913 | Stock status table (AutoCount), Group by, stock position report | `inventory/` |
| #1770 | Billing documents pages, outstanding per invoice / customer | new `finance/` folder (add to `PARENT_TITLES`) |
| #1715 | Dealer sales targets and incentive schemes | `user-management/` or a sales folder |
| #1916 #1943 #1922 #1931 | Sales reports: one sales definition, Dealer / Project team / Set apart blocks | `system-management/chatbot-sales-report.md` + a staff reports page |
| #1749 #1794 #1799 #1818 #1830 #1828 #1935 #1919 | Delivery splits on SO lines, guided Confirm, Borrow is a plan not a hold | `supply-chain/local-buy-and-borrow-source.md`, `sales-order-changes.md` (partly covered) |
| #1821 #1822 | Order Inquiry download as Excel / PDF, reserve quantities in both views | `supply-chain/order-inquiry-documents.md` |
| #1875 #1893 #1910 #1790 #1839 | Bulk dealer-contact access sheet, preview, Allow/Deny field access, model per contact | `user-management/` |
| #1968 #1767 #1967 #1978 #1962 #1965 | Project PO actions, delivery schedules, project stages follow the document, quote UI wording, quotation stock follows Stock visibility | `project-sales-rep/` |
| #1912 #1855 | DO detail page, SO / DO / billing document relations | `delivery-orders/track-delivery-orders.md` |
| #1924 #1942 | Audit Trail lists every field change and resubmission | `_shared/` |
| #1928..#1941 | Filters take several values (every list) | `_shared/getting-started-for-new-users.md` |
| #1927 | DataGrid drag / range row selection | `_shared/getting-started-for-new-users.md` |
| #1797 | Chatbot Console swipe-to-reply, voice, paste image | `system-management/chatbot-console-agent-mode.md` |
| #1765 #1980 #1970 #1971 #1625 | Spec registry editing, real delivery status on notifications, parser answer budget setting, PO reader model setting, idea capture fields | `system-management/` |
| #1769 | New Product Application in the paper-form layout | `project-sales-rep/submit-via-portal.md` |
| #1811 #1923 | Barcode import, catalogue photo extraction | `product/manage-products.md` mentions both; no step-by-step yet |

Chatbot answer-quality merges (#2018 #2030 #2013 and the resolver / prompt / eval series) change
what the WhatsApp bot replies, not what staff do, so they need no guide page.

## UAC

See `user-guides-refresh-acceptance-criteria.md`.
