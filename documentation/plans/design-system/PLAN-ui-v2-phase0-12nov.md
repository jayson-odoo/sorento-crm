# PLAN: UI v2 phase 0 (foundations)

Status: in progress. Full track (migration, a new permission, a new ingest route), so security-reviewer runs.
Lane UI-V2-PLAN, branch `claude/ui-v2-design-plan-3cmy20`, PR #2323.

- **UAC:** `documentation/plans/design-system/ui-v2-phase0-12nov-acceptance-criteria.md`.
- **Program:** `documentation/uiux/UI-V2-PLAN.md` revision 3, approved by the owner 12 Nov 2026 17:32 ("ok"),
  phase 0 row of section 10.
- **Repo:** no fork (crew recommendation, owner 12 Nov). v2 is built in this repo under `components/v2`, behind the
  per-user switch of program section 6, limited to the owner until he says it is very good.

**Paths:** BE = `sorento_crm_backend/`, FE = `sorento_crm_frontend/`.

## 1. Decisions taken here (simplest thing that works)

1. **Version.** The version is one column on `users` (`ui_version`) plus one permission (`ui.v2.preview`) plus one
   company kill switch (`system_settings.ui_v2_enabled`). No flag service.
   - `ui_v2_available` and the effective version are computed in the `/me` builder, so the FE reads one answer.
2. **Theme.**
   - **Brand:** stored once per company as `system_settings.theme` (JSONB `{preset, custom_hex}`).
   - **Mode:** stored once per user as `users.theme_mode`.
   - **Generator:** a pure FE module (`lib/theme/generate.ts`). The backend only stores the input, never colours.
3. **Telemetry.** Telemetry copies the client-error ingest exactly:
   - route under `/api/v1/system`
   - the user id from the session
   - a 16 KB body cap
   - the table as the rate-limit counter
   - 90-day retention in the existing daily cleanup job.
4. **Delivery to the FE.** The FE gets the version from the existing `/me` call (`hooks/useAccountProfileForHeader.ts`,
   react-query key `['account-profile']`). One `UiVersionProvider` mounted in `app/(protected)/layout.tsx` waits for
   it, behind the same `ScreenLoader`, before it chooses a shell. No second fetch.
5. **Tokens only in v2.** v2 tokens live under `:root[data-ui="v2"]` / `.dark[data-ui="v2"]`. The v1 pixels never
   change: D9 introduces `--toggle-selected-bg/fg`, which resolve to today's primary fill in v1.
6. **Out of this lane.** The `handle_not_found` wording fix is a separate small-fix lane (program phase 0 item j). It
   is not on this branch.

## 2. Slices (each red-first: tester commits the red tests, coder makes them green)

| Slice | UAC | Scope |
| --- | --- | --- |
| S0 | A-1, A-2 | `DESIGN-LANGUAGE.md` "UI v2 rules" + `PR-CHECKLIST.md` "UI v2" (captain, docs) |
| S1 | B-1..B-6, C-5, C-6, D-1..D-4 | BE: one migration, models, `/me` builders, two `/me` PUTs, settings write + app-config read, page-view ingest + retention |
| S2 | C-1..C-4, F-1, F-2 | FE pure modules: `lib/theme/{generate,presets}.ts`, `lib/format/date.ts` (+ helpers delegate) |
| S3 | B-7..B-12, C-7, C-9, D-5 | FE wiring: `UiVersionProvider`, `useUiVersion`, `<Versioned>`, avatar menu items, `data-ui`, v2 error boundary, fallback chip, v2 ThemeProvider, toggle tokens, `usePageView` |
| S4 | E-1..E-7, C-8 | FE v2 shell and shared patterns: `AppShell`, `Topbar`, `FloatingAction`, `SystemBanner`, `Lightbox`, `PanelTabs`, Settings > Appearance |
| S5 | C-10, D-6, G-1 | Guards: token test extension + inventory tests |
| S6 | G-2, G-3 | Tooling: `seed_ui_fixtures.py`, `scripts/ui-capture.mjs`, `scripts/ui-diff.mjs` |
| S7 | H-1..H-4 | Exit: E2E walk on the sandbox stack, captures, playbook conformance trace |

## 3. File map

### Backend (S1)

- **Migration** `BE/alembic/versions/uiv2_0001_version_theme_views.py`. The revision id is 31 chars. `down_revision`
  is main's head at the time (re-parent with `scripts/alembic-reparent.sh`). It adds:
  - `users.ui_version VARCHAR(2) NOT NULL DEFAULT 'v1'`
  - `users.theme_mode VARCHAR(6) NOT NULL DEFAULT 'system'`
  - `system_settings.ui_v2_enabled BOOLEAN NOT NULL DEFAULT true`
  - `system_settings.theme JSONB NOT NULL DEFAULT '{"preset":"sorento-blue","custom_hex":null}'`
  - table `ui_page_views (id uuid pk, user_id fk users ON DELETE CASCADE, route varchar(200), viewport varchar(8),
    ui_version varchar(2), ms_to_first_data int null, viewed_at timestamp, created_at timestamp default now())`,
    indexed on `(created_at)` and `(user_id, created_at)`
  - the permission slug `ui.v2.preview`, inserted idempotently like `cer_0001_client_error_report.py:49-62`, granted
    to no role.
- **Models:**
  - `BE/app/models/user.py`: `User.ui_version`, `User.theme_mode`; `SystemSetting.ui_v2_enabled`, `SystemSetting.theme`.
  - New `BE/app/models/ui_page_view.py`, registered in the models package like `client_error_report.py`.
- **`/me` builders** (`BE/app/api/v1/user_management/users.py`): all three builders (`GET /me` around :440,
  `get_user` around :619, `PUT /me/profile` around :950) add `ui_version` (effective), `ui_version_stored`,
  `ui_v2_available` and `theme_mode`. A helper `ui_version_fields(db, user) -> dict` in new
  `BE/app/services/ui_version_service.py` computes them, so the builders cannot drift.
- **New routes** on the same router:
  - `PUT /me/ui-version`, schema `{ui_version: Literal["v1","v2"]}`. Gives 403 for v2 without `ui.v2.preview` or
    while the kill switch is off. v1 is always allowed.
  - `PUT /me/theme-mode`, schema `{theme_mode: Literal["light","dark","system"]}`.
- **Settings** (`BE/app/api/v1/user_management/settings.py`):
  - `SystemSettingUpdate` (:21) gains `ui_v2_enabled: bool | None` and `theme: {preset: Literal[...5], custom_hex:
    str | None (^#[0-9a-fA-F]{6}$)} | None`.
  - `_update_general_settings_impl` (:919) writes them.
  - `GET /` dict and `AppConfigResponse` (:267, built :602-645) return them.
  - Presets are the five ids `sorento-blue`, `sorento-red`, `teal`, `graphite`, `indigo`.
- **Telemetry:**
  - New `BE/app/api/v1/system/page_views.py` (`POST /page-views`, 204), mounted in `system/__init__.py` next to
    `client_errors`.
  - Request body: `{"items": [{"route", "viewport", "ms_to_first_data", "ui_version", "at"}, ...]}` (1-50 items).
    Any `user_id` in the body is ignored.
  - Service `BE/app/services/ui_page_view_service.py`: `normalise_route`, `is_rate_limited` (120 per user per hour),
    `record_batch`, `prune_older_than(days=90)`.
  - The prune runs in the same scheduled cleanup that prunes `client_error_report` (find its caller and add one line).
- **Tests:**
  - `BE/tests/test_ui_v2_version.py` (B-*)
  - `BE/tests/test_ui_v2_theme_settings.py` (C-5, C-6)
  - `BE/tests/test_ui_page_views.py` (D-1..D-4).
  - All of them on `_pg_fixture.blank_session` + `tests._ai_usage_client.api_client` (pattern
    `BE/tests/test_client_error_report.py`).

### Frontend (S2-S5)

- `FE/lib/theme/generate.ts`, `FE/lib/theme/presets.ts`, `FE/lib/theme/contrast.ts` + `generate.test.ts`. The
  algorithm is the mock's (`documentation/uiux/ui-v2-mocks/index.html`, "theme engine" script):
  - OKLCH ramp, L targets `[.97,.93,.87,.79,.71,.63,.55,.48,.41,.34,.27]`, chroma factors
    `[.12,.25,.45,.7,.9,1,1,.95,.85,.72,.6]`, gamut-clamped by reducing chroma.
  - Achromatic inputs (C < 0.02) have chroma 0.
  - **Light mode:** primary is the first of 600, 700, 800, 900 with white >= 4.5:1, else 500 with 950 ink.
  - **Dark mode:** primary is the first of 400, 300, 200 with >= 4.5:1 on `#111113`, with 950 ink.
- `FE/lib/format/date.ts` + `date.test.ts`. `lib/helpers.ts` date helpers delegate to it, and existing tests stay
  green.
- `FE/components/v2/version/{UiVersionProvider.tsx,useUiVersion.ts,Versioned.tsx,V2ErrorBoundary.tsx,
  PreviousVersionChip.tsx}` + tests.
- `FE/components/v2/theme/{V2ThemeProvider.tsx,useThemeMode.ts}` + tests. It sets CSS variables on
  `document.documentElement` and the `dark` class for v2 only.
- `FE/app/components/partials/topbar/user-dropdown-menu.tsx`: the version item after the Dark Mode item (:266-279).
  In v2 the mode becomes Light/Dark/System radio items persisted through `PUT /me/theme-mode`.
- `FE/app/(protected)/layout.tsx`: `UiVersionProvider` around the shell, which chooses `Demo1Layout` or
  `components/v2/shell/AppShell`.
- `FE/css/config.reui.css`:
  - `--toggle-selected-bg/fg` in `:root` (= primary / primary-foreground) and in `:root[data-ui="v2"]` (=
    primary-soft / primary).
  - `components/ui/toggle.tsx:10` and `tabs.tsx:106,108` use them (one style, D9).
  - The v2 neutrals/status block goes under `[data-ui="v2"]`. Brand variables come from the provider.
- `FE/components/v2/shell/{AppShell,Sidebar,Topbar,FloatingAction,SystemBanner,MobileNavSheet,usePageView}.tsx` +
  tests.
- `FE/components/v2/{Lightbox,PanelTabs}.tsx` + tests.
- **Floating action registration (R16):** `components/v2/shell/PrimaryActionContext.tsx` holds at most one registered primary
  `{label, onAction, blockedReason?, headerRef}`. `AppShell` mounts the single `FloatingAction` from it. A page never
  mounts its own: in phase 1+ the v2 `PageHeader` / `RecordHeader` register automatically. `SystemBanner` urgency:
  offline before impersonation.
- **Hex rule:** only `lib/theme/presets.ts` may hold hex literals (incl. the light and dark page backgrounds the
  generator measures against).
- `FE/app/(protected)/user-management/settings/appearance/page.tsx`, a new settings tab "Appearance" in
  `settings/layout.tsx`, gated on `user_management.settings.edit`.
- **Guards:**
  - `FE/css/design-tokens.test.ts` extended (C-10).
  - New `FE/components/v2/v2-holistic.inventory.test.ts` (D-6, D8, D9, D6 rows of G-1).
  - New `FE/components/ui/sheet-content.inventory.test.ts`, `FE/lib/native-date-input.inventory.test.ts`,
    `FE/components/ui/sort-off.inventory.test.ts`, `FE/components/ui/single-select-filter.inventory.test.ts`
    (allowlists seeded with today's matches, shrink-only, stale entries fail; pattern
    `components/ui/raw-table.inventory.test.ts`).

### Tooling (S6)

- `BE/scripts/seed_ui_fixtures.py`, promoted from the discovery seed and extended: fixed dates, every OI status
  present, an empty and an overfull record. It refuses non-local / non-`*_ci` databases.
- `scripts/ui-capture.mjs`, `scripts/ui-diff.mjs`: Node scripts using the pre-installed `playwright` library and
  `axe-core` (installed `--no-save` in the sandbox at run time). They are not test specs.

## 4. Test list (tester writes these red first; one line per UAC id)

**Backend:**
- `test_me_has_ui_fields_default_v1` (B-1): `/me` has `ui_version=="v1"`, `ui_v2_available is False` for a user
  without the slug.
- `test_me_ui_v2_available_with_permission` (B-1): with the slug and the kill switch on, it is True.
- `test_get_user_and_profile_builders_carry_ui_fields` (B-1): both other builders return the keys.
- `test_put_ui_version_v2_with_permission` (B-2): 200, then `/me` says v2; then v1, `/me` says v1.
- `test_put_ui_version_v2_without_permission_forbidden` (B-3): 403, the stored value is unchanged.
- `test_put_ui_version_v1_always_allowed` (B-3): 200 without the slug.
- `test_put_ui_version_invalid_422` (B-4): `"v3"`, `""` and `null` give 422.
- `test_kill_switch_forces_v1` (B-5): stored v2 with `ui_v2_enabled=False` gives `/me` effective v1,
  `ui_v2_available` False, and `ui_version_stored` v2.
- `test_kill_switch_blocks_put_v2` (B-5): 403 while off.
- `test_permission_slug_seeded_ungranted` (B-6): the slug exists and no role grants it.
- `test_put_theme_mode` (C-5): light/dark/system round-trip; `"blue"` gives 422.
- `test_settings_theme_write_and_app_config_read` (C-6): an editor writes a preset, then a custom hex; app-config
  returns them; a non-editor gets 403; `#12345` and `red` give 422.
- `test_app_config_has_ui_v2_enabled` (C-6/B-5): app-config returns it for any signed-in user.
- `test_page_views_batch_stored_with_session_user` (D-1): 3 items give 204 and 3 rows with the session user, even
  when the body names another user id.
- `test_page_views_route_normalised` (D-2): a UUID segment, a numeric segment and a query string are stored as
  `[id]`, with no query.
- `test_page_views_validation` (D-3): 51 items, viewport `watch`, ms `-1` or `600001` each give 422 and 0 rows.
- `test_page_views_unauthenticated_401` (D-3).
- `test_page_views_body_cap_413` (D-3).
- `test_page_views_rate_limited_429` (D-3).
- `test_page_views_prune_90_days` (D-4): a 91-day-old row is deleted, an 89-day-old row kept.

**Frontend:**
- `generate.test.ts`:
  - `returns the ramp and semantic tokens` (C-1)
  - `every preset and stress input clears AA in light and dark` (C-2)
  - `Sorento Blue light primary is #246bdd with white ink` (C-3)
  - `achromatic input yields a neutral ramp` (C-4).
- `date.test.ts`:
  - `formatDate`, `formatDateTime` from a naive UTC string in Malaysia time, `formatDateRange`, `formatTime`, and
    empty/invalid input give `''` (F-1)
  - `lib/helpers` date functions return the same strings as `lib/format/date` (F-2).
- `UiVersionProvider.test.tsx`:
  - menu item hidden when unavailable, "Switch to the new version" in v1, "Switch to the previous version" in v2
    (B-7)
  - a click PUTs, flips the version and keeps path + query; a failed PUT keeps the version and toasts (B-8)
  - `data-ui="v2"` set only in v2, and v1 when `/me` errors (B-9).
- `Versioned.test.tsx`: renders exactly one side and reads context only (B-12).
- `PreviousVersionChip.test.tsx`: shown only for `ui_v2_available` (B-10).
- `V2ErrorBoundary.test.tsx`: message + "Open in the previous version" PUTs v1, and the report carries
  `ui_version` v2 (B-11).
- `V2ThemeProvider.test.tsx`: CSS variables set on `<html>` from the company theme + mode before children render; v1
  untouched (C-7).
- `toggle-tokens.test.ts`: toggle and pill-tab selected classes use `--toggle-selected-*`; the v1 values equal the
  primary pair, the v2 values the soft pair (C-9).
- `usePageView.test.tsx`: batches at 10, flushes at 15 s and on `pagehide` via `fetch` with `keepalive` + bearer token, normalises nothing
  client-side except dropping the query, and is mounted once in `AppShell` (D-5).
- Shell components: `AppShell.test.tsx` (E-1), `Topbar.test.tsx` (E-2 class/state on scroll), `FloatingAction.test.tsx`
  (E-3), `SystemBanner.test.tsx` (E-4), `Lightbox.test.tsx` (E-5 dialog vs drawer by width), `PanelTabs.test.tsx`
  (E-6).
- `appearance/page.test.tsx`: presets, live contrast text, Save sends `PUT /settings/general` with theme, Reset
  (C-8).
- Guards (S5): as in the file map.

## 5. Playbook conformance (R15) per E item

| UAC | Playbook (plan 8.1) | Deviation |
| --- | --- | --- |
| E-2 | P6 | none |
| E-3 | P4, P5 | P5 pulse replaced by the plain reason (owner override, registered) |
| E-4 | P16 | none |
| E-5 | D7 + P7 "side panels on phones" | none (bottom sheet below 720 px) |
| E-6 | P7 | none |
| E-7 | P1, P2, P17 | P17 motion timings: `lib/motion.ts` presets (owner override, registered) |

## 6. Risks

- **The three `/me` builders drift.** One helper plus a test on all three.
- **v1 pixels change by accident.** Toggle tokens resolve to today's values in v1, and the H-3 captures include v1
  on the same routes.
- **Re-bootstrap on an existing sandbox DB fails on a redefined view.** Drop and recreate the throwaway DB (seen 12
  Nov).
