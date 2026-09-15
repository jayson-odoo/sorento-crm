# Meetings S6 - Sorento embed + linkage: Acceptance Criteria (UAC)

**Status:** contract, pre-build. Written FIRST per PRINCIPLES.
**Scope:** `sorento_crm` (host side). Shared-service side is `foundryx-shared-service/documentation/plans/meetings/PLAN-meetings-program.md` section 5 (contracts 5.1, 5.2).
**Goal:** a logged-in sorento user manages their meeting opt-in, reads minutes, and sees meetings on the contact / company they belong to, all inside sorento, no second login.

---

## A. Module + navigation

**AC-S6-1** - Given the `meetings` module is enabled for the tenant, when a user with `meetings.view` opens sorento, then the sidebar shows **Meetings** with children **My meetings** and **All meetings**; without the permission the item is absent; with the module disabled every `/api/v1/meetings/*` route answers 403.

**AC-S6-2** - Given an admin, when they open System -> Meetings Embed, then they can set `connection_id`, signing secret (encrypted at rest, never echoed back), backend base URL and frontend base URL, stored in the DB, not `.env`. A Test button mints a session and shows the outcome.

## B. Iframes (SSO)

**AC-S6-3** - Given a user opens My meetings, when the page loads, then sorento mints an assertion (`aud: meetings-embed`, `sub: <user email>`, 5 min, single-use `jti`), exchanges it at `POST <shared-service>/meetings/embed/session`, and renders the shared-service `embed/meetings/settings` page in an iframe with the token in the URL fragment. No shared-service login screen ever appears.

**AC-S6-4** - Given All meetings, then the `embed/meetings/list` page renders the same way; clicking a row opens `embed/meetings/[id]` inside the same iframe (no sorento navigation), and the browser back button returns to the list.

**AC-S6-5** - Given the embed session cannot be minted (bad secret, shared-service down), then the panel shows an empty state with a Retry CTA and the error text from `extractApiError`; nothing is logged to the console as an uncaught error.

## C. Linkage

**AC-S6-6** - Given shared-service posts `POST /api/v1/external/meetings/ready` with `X-API-Key`, when the body lists attendee emails, then sorento writes one `meeting_links` row per matched contact (by email) and per matched company (through the contact), idempotent on `meeting_id`; unmatched emails are ignored and counted in the response.

**AC-S6-7** - Given a contact detail page, when the contact has linked meetings, then a **Meetings** tab lists them (title, date, status) and clicking one opens the minutes in the embed. Same on company detail. Empty state with an explicit "no meetings yet".

**AC-S6-8** - Given a user with `meetings.manage` on a contact detail page, when they choose Link meeting, then a `SearchableSelect` (server-searched by title / date over `GET /meetings/embed/meetings?attendee_email=`) lets them link a meeting manually; Unlink asks for confirmation (`ConfirmDeleteDialog`) and hard-deletes the link row.

## D. Isolation + responsive

**AC-S6-9** - Given tenant A's API key, when the ready webhook names a `tenant_id` that is not A, then 404 and nothing is written.

**AC-S6-10** - My meetings, All meetings and the Meetings tab are usable and non-clipped at 375 px and 1280 px.
