# UI v2 phase 0: acceptance criteria

Lane UI-V2-PLAN, phase 0 of `documentation/uiux/UI-V2-PLAN.md` (revision 3, owner approved 12 Nov 2026 17:32,
"ok"). Plan: `documentation/plans/design-system/PLAN-ui-v2-phase0-12nov.md`.

Binding: `UI-V2-PLAN.md` R1-R16. R15 means every rule here follows the Foundryx playbook
(`skills/foundryx-playbook-uiux/SKILL.md`), deviating only where plan section 8.1 says an owner rule wins.
R16 means every item lands as ONE shared token, component or pattern.

**Tags:**
- `[BE]` backend, pytest on Postgres
- `[FE]` frontend, vitest
- `[E2E]` a recorded agent-browser walk on the sandbox stack
- `[T]` tooling or guard test
- `[UX]` visual or interaction check.

## Journey

1. The owner holds the new `ui.v2.preview` permission. Nobody else does.
2. In the avatar menu the owner sees "Switch to the new version", and clicks it.
3. The same URL now renders inside the v2 shell, with the Sorento Blue theme. The choice is saved on the server,
   so it follows the owner to another device.
4. A screen that has no v2 version yet still renders its v1 content inside the v2 shell, marked with a small
   "previous-version screen" chip only the owner sees.
5. In the avatar menu the owner picks Light, Dark or System. That too is saved on the server.
6. As an admin, the owner opens Settings, then Appearance. They pick a preset or type a custom brand colour, see
   the measured contrast, and save. Every v2 user of the company sees that brand.
7. If a v2 screen breaks, it says so in plain words and offers "Open in the previous version".
8. Any time, "Switch to the previous version" in the avatar menu brings v1 back on the same URL.
9. If v2 misbehaves, an admin turns the kill switch off, and every user gets v1 regardless of their choice.
10. While the owner moves around v2, one hook in the v2 shell records page views (route pattern, viewport class,
    time to first data). v1 records nothing.

## Phase A: contract (docs)

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| A-1 | [T] | Given `documentation/reference/DESIGN-LANGUAGE.md`, then it holds a section "UI v2 rules" listing R1-R16 with their enforcing mechanism, the D6-D10 shared-thing rows, and the TOGGLE-SELECTED rule rewritten for v2 (soft tint, primary text; v1 unchanged). |
| A-2 | [T] | Given `documentation/reference/PR-CHECKLIST.md`, then it carries a "UI v2" block: playbook conformance (deviations only per plan 8.1), holistic (no per-page variant of a shared v2 component), tokens only, and the X-1..X-15 screen checks by reference. |

## Phase B: version switch

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| B-1 | [BE] | Given any user, when `GET /api/v1/auth/me` (and the `get_user` builder) responds, then the body has `ui_version` (`"v1"` by default) and `ui_v2_available` (true only when the user holds `ui.v2.preview` AND `system_settings.ui_v2_enabled` is true). |
| B-2 | [BE] | Given a user with `ui.v2.preview`, when they `PUT /api/v1/auth/me/ui-version {"ui_version":"v2"}`, then 200 and a later `/me` returns `"v2"`; `{"ui_version":"v1"}` switches back. |
| B-3 | [BE] | Given a user WITHOUT `ui.v2.preview`, when they PUT `"v2"`, then 403 and nothing is stored; PUT `"v1"` is always allowed (a way back never needs a permission). |
| B-4 | [BE] | Given any value other than `"v1"`/`"v2"`, then 422. |
| B-5 | [BE] | Given `system_settings.ui_v2_enabled = false`, then `/me` returns `ui_v2_available: false` and an effective `ui_version: "v1"` for every user, whatever is stored; the stored choice is kept for when it is turned back on. |
| B-6 | [BE] | Given the migration, then the permission slug `ui.v2.preview` exists, is granted to NO role by default, and is grantable like any other slug; `users.ui_version` defaults to `'v1'`; `system_settings.ui_v2_enabled` defaults to true. Single alembic head. |
| B-7 | [FE] | Given `ui_v2_available` false, then the avatar menu shows no version item. Given true and `ui_version` v1, it shows "Switch to the new version"; given v2, "Switch to the previous version". |
| B-8 | [FE] | When the item is clicked, then the PUT is sent, the session's version updates, and the same URL (path and query) renders in the other version without a full sign-out; on a failed PUT the version does not change and a toast says it could not switch. |
| B-9 | [FE] | Given version v2, then `<html>` carries `data-ui="v2"` and the protected layout renders `components/v2/shell/AppShell`; given v1 (or `/me` failed, or no version field), `data-ui` is absent and `Demo1Layout` renders unchanged. |
| B-10 | [FE] | Given a route with no v2 client, when rendered in v2, then its v1 content renders inside the v2 shell with a "Previous-version screen" chip; the chip renders only for users with `ui_v2_available`. |
| B-11 | [FE] | Given a v2 screen throws, then the v2 error boundary shows "This screen hit a problem." + "Open in the previous version" (which PUTs v1 and reloads the same URL) and reports a client error carrying `ui_version: "v2"`. |
| B-12 | [FE] | Given `<Versioned v1={A} v2={B} />`, then it renders exactly one of A or B by the effective version; it reads the version once, from context (no per-page fetch). |

## Phase C: theme

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| C-1 | [FE] | Given `lib/theme/generate.ts` `generateTheme(hex, mode)`, then it returns the 11-step ramp (50-950) and the semantic tokens `primary`, `primary-hover`, `primary-foreground`, `primary-soft`, `ring`. |
| C-2 | [FE] | Given each preset (Sorento Blue `#3b82f6`, Sorento Red `#b44d2e`, Teal `#0f766e`, Graphite `#3f3f46`, Indigo `#4f46e5`) and stress inputs (`#facc15`, `#ffffff`, `#000000`), in light AND dark, then `primary` vs `primary-foreground` contrast is >= 4.5:1 and `primary` vs the page background is >= 3:1. |
| C-3 | [FE] | (D6) Given the Sorento Blue preset in light mode, then `primary` is exactly `#246bdd` and the foreground white. |
| C-4 | [FE] | Given an achromatic input (white, black, grey), then the ramp is neutral (chroma 0), not tinted. |
| C-5 | [BE] | Given `users.theme_mode` (`light`/`dark`/`system`, default `system`), when `PUT /api/v1/auth/me/theme-mode`, then 200 and `/me` returns it; other values 422; any signed-in user may set their own. |
| C-6 | [BE] | Given `system_settings.theme` (`{"preset": "sorento-blue", "custom_hex": null}` by default), when an admin with the settings-write permission PUTs a preset or a `#rrggbb` custom hex, then it is stored and `/me` returns the company theme; a non-admin gets 403; an invalid hex 422. |
| C-7 | [FE] | Given v2, then the v2 ThemeProvider sets the generated semantic tokens as CSS variables on `<html>` before the v2 shell paints (no flash of v1 colours) and applies the user's mode; v1 keeps `next-themes` behaviour unchanged. |
| C-8 | [FE] | Given Settings, then Appearance (admin): preset swatches, a custom colour input with a live contrast readout ("Button text 5.0:1, passes"), a preview (button, badge, selected row) in light and dark, Save, and "Reset to Sorento Blue". |
| C-9 | [FE] | (D9) Given v2, then a selected toggle, toggle-group item and pill tab use the soft tint with primary text through ONE token pair (`--toggle-selected-bg`, `--toggle-selected-fg`); in v1 the same tokens resolve to today's primary fill, so v1 pixels do not change. |
| C-10 | [T] | Given `css/design-tokens.test.ts`, then it also asserts the v2 token block exists under `[data-ui="v2"]` and that no file in `components/v2` or `lib/theme` uses a raw palette class or a hard-coded brand hex. |

## Phase D: page-view telemetry (D10)

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| D-1 | [BE] | Given a signed-in user, when `POST /api/v1/ui/page-views` with a batch of up to 50 items `{route, viewport, ms_to_first_data, ui_version, at}`, then 204 and one `ui_page_views` row per item, `user_id` from the session (never from the body). |
| D-2 | [BE] | Given a route containing an id-like segment (UUID, digits) or a query string, then it is stored as a pattern (`/project-sales/order-inquiries/[id]`), never the raw id or query. |
| D-3 | [BE] | Given more than 50 items, a viewport outside `phone/tablet/desktop`, a negative or > 600000 ms value, then 422 and nothing is stored. Unauthenticated: 401. |
| D-4 | [BE] | Given rows older than 90 days, when the daily retention job runs, then they are deleted; younger rows stay. |
| D-5 | [FE] | Given the v2 shell, then ONE hook `components/v2/shell/usePageView.ts`, mounted once in `AppShell`, records each route change and flushes in batches (on 10 items, after 15 s, and on page hide via `sendBeacon`); v1 sends nothing. |
| D-6 | [T] | Given the inventory guard, then no file outside `components/v2/shell` imports `usePageView`. |

## Phase E: v2 shell and shared patterns

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| E-1 | [FE] | Given v2 at 1280, then `AppShell` renders the sidebar from the same `MENU_SIDEBAR` config (no demo entries), a top bar with the search trigger (opens the existing Cmd/Ctrl+K dialog), the company switcher, notifications and the avatar menu. |
| E-2 | [FE] [UX] | (P6) Given v2 at 360-720 px, when the page scrolls down, then the top bar keeps its height, its right-hand icons fold into one menu button and the search narrows to 36 px; scrolling up reverses it. |
| E-3 | [FE] | (P4) Given a page that registers a primary action, when the header's primary scrolls out of view on a phone, then `FloatingAction` shows the same label and runs the same handler at the lower right, and the page has bottom room equal to its height; when blocked it shows the block reason instead of acting. |
| E-4 | [FE] | (P16) Given impersonation (or offline), then `SystemBanner` shows ONE thin bar above the top bar, full width, warn tint, one line (two on a phone), at most one text button, no close for a still-true state; several banners show the most urgent with "1 of 2". |
| E-5 | [FE] | (D7) Given `components/v2/Lightbox.tsx`, then above 720 px it renders a centred `Dialog` lightbox and at 720 px and below a vaul bottom `Drawer`, with the same props (title, body, footer actions); it replaces any side Sheet in v2 code. |
| E-6 | [FE] | (P7) Given `components/v2/PanelTabs.tsx` with two or more panels, then above 720 px the panels render side by side, and at 720 px and below as browser-style tabs (rounded tops, active joins the panel, optional count), each keeping its own scroll; the default tab is the first (main) panel. |
| E-7 | [UX] | Given every E component, then it works at 360 px with no page-level sideways scroll, touch targets are 44 px on coarse pointers, and motion uses `lib/motion.ts` presets only (P17 owner override), with reduced motion respected. |

## Phase F: one date formatter (R1)

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| F-1 | [FE] | Given `lib/format/date.ts`, then `formatDate` gives `10/11/2026`, `formatDateTime` gives `10/11/2026, 9:42 am` (Malaysia time, from a naive UTC string), `formatDateRange` gives `01/01/2026 - 31/03/2026`, `formatTime` gives `9:42 am`; empty or invalid input gives `''`. |
| F-2 | [FE] | Given `lib/helpers.ts`, then its date helpers delegate to `lib/format/date.ts` and their existing tests still pass unchanged. |

## Phase G: guards and tooling

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| G-1 | [T] | Given the inventory tests, then each has an allowlist that may only shrink: `SheetContent` imports (D7), native `type="date"`/`datetime-local` (R1), `enableSorting: false` (R3), single-select filters in list toolbars (R4); and with zero allowance: hard-coded brand hex or raw palette classes in `components/v2` (D6), `bg-primary` on a selected toggle in `components/v2` (D9), per-list phone card components (D8), `usePageView` outside the shell (D10). |
| G-2 | [T] | Given `sorento_crm_backend/scripts/seed_ui_fixtures.py`, when run against a local `*_ci` database, then it lays a fixed, masked dataset (order inquiries with lines, customers, projects, products, suppliers) and refuses any other database. |
| G-3 | [T] | Given `scripts/ui-capture.mjs <manifest> <out>`, then it signs in, captures every route in {v1, v2} x {light, dark} x {1280, 360}, runs axe-core on each, and writes PNGs plus a JSON report; `scripts/ui-diff.mjs` compares two capture folders with pixelmatch at 0.1% and writes an HTML report. It is a script, not a Playwright test spec. |

## Phase H: exit (plan section 10, phase 0)

| ID | Tag | Given / When / Then |
| --- | --- | --- |
| H-1 | [E2E] | On the sandbox stack, the owner persona switches v1 -> v2 -> v1 on three routes (OI list, OI record, Settings) and the URL and list state survive each switch. |
| H-2 | [E2E] | The kill switch off makes the same persona v1 with no menu item; on again restores v2. |
| H-3 | [E2E] | The v2 shell is captured on 6 routes x {light, dark} x {1280, 360}; axe shows 0 serious/critical; no page-level sideways scroll at 360. |
| H-4 | [T] | Playbook conformance check: every E item is traced to its section 8.1 P-row in the plan, and no deviation exists outside the plan's register (R15). |
