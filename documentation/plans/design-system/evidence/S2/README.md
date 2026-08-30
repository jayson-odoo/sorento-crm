# S2 Tokens and CSS - browser verification evidence

Branch: `feat/apple-S2-tokens` (cut from `origin/main`, no S1 - dialogs are non-modal here,
Escape closes them, that is expected). Served at `http://localhost:3090` (BE `:8000`). Verified
with `agent-browser@0.27.0` headless, session `s2-evidence`, logged in as the `E2E_EMAIL` user.
All navigation from `/` via sidebar clicks unless noted.

## Results

| AC | Pass/Fail/Unverified | Screenshot | Note |
|----|----|----|----|
| S2-01 (mono darker) | Pass | S2-03-product-detail-light-1280.png (synthetic test, no screenshot needed) | `--mono` = `oklch(14.1% ...)` (zinc-950), `--mono-foreground` = `#fff`. Synthetic `.text-mono` element computed `color: oklch(0.141 ...)` vs `.text-muted-foreground` computed `oklch(0.552 ...)` - mono is darker/stronger ink. |
| S2-01 (success toast coloured) | Pass | S2-01-success-toast-1280.png | Duplicated a Product Category and submitted Create; toast "Category created successfully" rendered with a green check icon. Source `components/ui/sonner.tsx` wires `[data-type=success]>[data-icon]` and the title to `text-success` (the `--success` token), confirmed via grep. |
| S2-01 (error toast coloured) | Pass | S2-01-error-toast-1280.png | Submitted Create Category with an existing code ("ACC-ALAN"); toast fired with `data-type="error"`, text "Category code already exists." Source wires `[data-type=error]` to `text-destructive`; `--destructive` resolves to `oklch(57.7% 0.245 27.325)` (chroma 0.245 = clearly red, not neutral ink). Toast auto-dismissed before the screenshot round-trip landed, so the shot shows the dialog only; the eval capture of the live toast node is the primary evidence. |
| S2-01 (`--mono`/`--success` non-empty) | Pass | n/a | `getComputedStyle(document.documentElement)`: `--mono` = `oklch(14.1% 0.005 285.823)`, `--mono-foreground` = `#fff`, `--success` = `oklch(72.3% 0.219 149.579)`, `--info` = `oklch(54.1% 0.281 293.009)`, `--warning` = `oklch(79.5% 0.184 86.047)`. All non-empty. |
| S2-01 (extra finding) | N/A (logged, not an AC) | S2-01-export-dialog-crash-1280.png | Clicking **Export** on the Products list threw a React "Maximum update depth exceeded" runtime error inside `components/ui/dialog.tsx` `DialogContent` (call stack: `ProductsPage` -> `DialogContent`). This blocked using Export as a toast trigger; worked around by using Product Categories Create/Duplicate instead. This is a functional bug, not a CSS/token defect, so it is reported here rather than failing S2-01 - see ranked findings below. |
| S2-02 (dark: 3 distinct steps) | Pass | S2-02-product-detail-dark-1280.png | Added `dark` class to `<html>`, opened a Product detail row. `--background` = 14.1%L, `--card` = 21%L, `--popover` = 27.4%L - three distinct steps, ascending. |
| S2-02 (dark: active tab lighter than track) | Pass | S2-02-create-product-tabs-dark-1280.png | Product create page pill tabs (`variant="default"`, `bg-muted` track). Active "Basic Information" tab `background-color: oklch(0.274 ...)` (= `--popover`) vs track `background-color: oklch(0.21 ...)` (= `--card`). Active is lighter than its track. |
| S2-02 (light mode looks like today) | Unverified | S2-02-create-product-tabs-light-3090-1280.png | `:3000` (the "main checkout" baseline) had no dev server running (`curl` connection refused, `lsof -i :3000` empty) - cannot do the requested cross-port comparison. Captured the same page in light mode at `:3090` instead as a fallback reference; visually unremarkable (clean white/grey pill tabs, no regression apparent), but the explicit A/B against `:3000` could not be done. |
| S2-03 (type scale) | Pass | S2-03-product-detail-light-1280.png | Injected/measured Tailwind size classes: `text-2xl` 24px / `-0.48px` letter-spacing (`-0.02em`) / `27.6px` line-height (1.15); `text-xl` 20px / `-0.3px` (`-0.015em`) / `24px` (1.2); `text-lg` 18px / `-0.18px` (`-0.01em`) / `23.4px` (1.3); `text-base` 16px / `normal` (0) / `24px` (1.5); `text-xs` 12px / `0.12px` (`+0.01em`); `text-2xs` 11px / `0.22px` (`+0.02em`). All match the AC table exactly. |
| S2-03 (`--font-sans` -> Inter) | Pass | n/a | Product detail `h1` (`text-2xl font-bold`) computed `font-family: Inter, "Inter Fallback", ui-sans-serif, system-ui, sans-serif`. |
| S2-03 (`font-optical-sizing: auto` on body) | Pass | n/a | `getComputedStyle(document.body).fontOpticalSizing === "auto"`. |
| S2-03 (CardTitle / dialog titles not clipped) | Pass | S2-03-create-category-dialog-1280.png | Quick Info `CardTitle` (`h3`, "Quick Info"): class `text-base font-semibold leading-tight tracking-normal`. Create Category dialog title (`h2`, "Create Category"): class `text-lg font-semibold leading-tight tracking-normal`, `scrollHeight === clientHeight` (23px both) - no clipping. |
| S2-04 (dropdown: fade only, no slide/zoom) | Pass | S2-04-columns-dropdown-reduced-motion-1280.png | `set media light reduced-motion`, opened Products list "Columns" dropdown. `[data-slot="dropdown-menu-content"]` computed `animation-name: enter`, `animation-duration: 0.15s`, `--tw-enter-scale: 1`, `--tw-enter-translate-x/y: 0` - fade only, 150ms, no transform. |
| S2-04 (dialog: fade only, no slide/zoom) | Pass | S2-04-create-category-dialog-reduced-motion-1280.png | Same reduced-motion state, Create Category dialog: `animation-name: enter`, `animation-duration: 0.15s`, `--tw-enter-scale: 1`, translate 0/0. |
| S2-04 (spinner keeps spinning) | Pass | n/a (synthetic; no live spinner caught on screen in time) | Injected a `.animate-spin` element under the same reduced-motion state: `animation-name: spin`, `duration: 1s`, `iteration-count: infinite`, `play-state: running` - unaffected by the reduced-motion block. |
| S2-05 (header material) | Pass | S2-05-products-list-scrolled-header-edge-1280.png | `<header>` computed `backdrop-filter: saturate(1.8) blur(24px)` (non-none), `background-color` alpha `0.72` (< 1), `z-index: 10` via `z-(--z-header)`; `top: var(--impersonation-banner-height,0px)`. Scrolling the Products list shows a soft blurred edge under the header, not a hard 1px line. |
| S2-05 (sidebar material) | Pass | S2-05-impersonation-banner-header-1280.png | `.sidebar.material-thick`: same `backdrop-filter: saturate(1.8) blur(24px)`, background alpha `0.88` (more opaque/"thicker" than header's `0.72`, per the `material-thick` vs `material-regular` classes), `z-index: 20` via `z-(--z-sidebar)`. |
| S2-05 (material tokens + z-scale exist) | Pass | n/a | `--material-thin` = `color-mix(in oklab, #fff 55%, transparent)`, `--material-regular` = 72%, `--material-thick` = 88%, `--scrim` = `color-mix(in oklab, black 50%, transparent)`, `--elev-1` and `--elev-3` both resolve to real shadow values. `grep -rn "z-\[[0-9]" app/components/layouts/` returns nothing - no ad-hoc `z-[N]` left in the shell. |
| S2-05 (impersonation banner offsets header) | Pass | S2-05-impersonation-banner-header-1280.png | Impersonated a test user (Administrative Users list -> Impersonate -> confirm dialog -> Impersonate). Banner rendered full-width above the header with `--impersonation-banner-height: 40px`; header's own `getBoundingClientRect().top === 40`, matching the banner height exactly - header is offset, not covered. Exited impersonation cleanly afterward. |
| S2-06 (motion tokens + equal open/close duration) | Pass | S2-06-notifications-sheet-1280.png | Opened the notifications Sheet (bell icon). `[data-slot="sheet-content"]` class carries a single `duration-(--duration-slow)` applied to both `data-[state=open]:animate-in` and `data-[state=closed]:animate-out` - open and close share one duration token (300ms), so they are equal by construction. `--duration-base` = `200ms`, `--duration-fast` = `150ms`, `--duration-slow` = `300ms`, `--ease-standard` = `cubic-bezier(0.2, 0, 0, 1)`, all defined. |
| S2-07 (card shadow tint) | Pass | S2-07-card-shadow-1280.png | Live `[data-slot="card"]` element carries `shadow-xs shadow-black/5`; computed `box-shadow` includes `oklab(0 0 0 / 0.05) 0px 1px 2px 0px` - non-zero alpha tint is real. |
| 375x812 Products list | Pass | S2-products-list-375.png | Toolbar wraps cleanly (search, Filters/Columns/Export row, then Actions/Create Product row), grid readable, no overflow or clipping. |
| 375x812 mobile nav drawer | Pass | S2-mobile-nav-drawer-375.png | Hamburger opens the drawer over a dimmed/blurred backdrop; sidebar groups render full-width, no clipping. |

## Ranked findings (not part of the S2-01..07 pass list above)

1. **Export button on Products list crashes the page** (`S2-01-export-dialog-crash-1280.png`).
   Clicking Export threw `Runtime Error: Maximum update depth exceeded`, originating in
   `components/ui/dialog.tsx:154` (`DialogContent`), triggered from `ProductsPage`
   (`app/(protected)/master-data-management/products/page.tsx:48`). Observed: full-page Next.js
   dev error overlay, app unusable until reload. Expected: Export opens its dialog/flow without
   error. This is a functional regression, not a token/CSS issue, but it sits directly in the
   S2 code path (`DialogContent`) so it is worth flagging to the S2 coder even though it is out
   of the S2-01..07 AC list. Not filed as a failure against any S2 AC since none of S2-01..07
   claims Export works; logged here for visibility.

2. **`:3000` unreachable for the S2-02 cross-port light-mode comparison.** `curl` to
   `http://localhost:3000` returned connection refused and `lsof -i :3000 -sTCP:LISTEN` found no
   listener. The instruction was explicit ("compare with a screenshot of the same page at
   `http://localhost:3000`"), so this sub-check is marked Unverified rather than Pass, with a
   same-page `:3090` light-mode screenshot captured as a fallback reference. No regression is
   visible in that fallback shot, but the actual A/B against the pre-S2 baseline was not possible
   in this run.

## What was NOT reachable / not attempted

- The `:3000` baseline comparison (see finding 2 above).
- No other blockers. Backend `:8000` answered throughout (never needed to poll or report it down).

Session `s2-evidence` closed cleanly at the end of this run (`agent-browser close --session
s2-evidence`), not `close --all`.

## Run 2 (scoped re-check after review fixes)

Served at `http://localhost:3090` (BE `:8000`). Session `s2-run2`, `agent-browser@0.27.0`
headless, logged in as the `E2E_EMAIL` user, navigation from `/` via sidebar clicks. `:3000`
(main checkout) was up this run, so the S2-01 A/B comparison unblocked from Run 1's
"Unverified" is now done for real.

Note: the `/user-management/logs` page (Users & Access > Logs) had `No data available` for
every date range tried, so `bg-warning text-warning-foreground` (the avatar fallback class in
`log-list.tsx`) and `bg-success text-success-foreground` (`sheet-chat.tsx`) were verified by
injecting live elements carrying those exact Tailwind classes into the running page (same
synthetic-on-live-page method Run 1 used for `--mono`) rather than by finding populated rows.
System Management > Audit Logs (the suggested alternative) had real data but its Action badges
use a different `warning-soft`/`success-soft` token pair, not the AC's `bg-warning`/`bg-success`
pair, so it was not used for the primary measurement.

Also hit a real navigation gotcha this run: sidebar links repeatedly no-op'd on click. Root
cause was the documented one in `browser-verification.md` - the target button/link was below the
fold in the scrollable sidebar (e.g. `Users & Access` toggle at `y=1272` against an 800px
viewport) and `click @ref` without a prior `scrollintoview @ref` silently misses. Fixed by always
scrolling into view first; not a product bug.

| AC | Pass/Fail | Screenshot | Note |
|----|----|----|------|
| S2-01 semantic contrast (`bg-warning`/`text-warning-foreground`) | Pass | run2-S2-01-semantic-contrast-badges-1280.png | Injected live element with these exact classes: computed `background-color: oklch(0.554 0.135 66.442)` = rgb(166,95,0), `color: rgb(255,255,255)`. Contrast ratio 4.93:1 (>= 4.5). |
| S2-01 semantic contrast (`bg-success`/`text-success-foreground`) | Pass | run2-S2-01-semantic-contrast-badges-1280.png | Same method: `background-color: oklch(0.527 0.154 150.069)` = rgb(0,130,54), `color: rgb(255,255,255)`. Contrast ratio 4.95:1 (>= 4.5). |
| S2-01 `text-warning` KPI ink on page background | Pass | run2-S2-01-semantic-contrast-badges-1280.png | No live "text-2xl font-bold text-warning" tile was found on Inventory > Stock (that page is a DataGrid listing, no KPI tiles) or on Dashboards, so also measured via live injected element: ink `oklch(0.554 0.135 66.442)` = rgb(166,95,0) on white page background. Contrast ratio 4.93:1 (>= 4.5). |
| S2-04 notifications Sheet, reduced motion | Pass | run2-S2-04-notifications-sheet-reduced-motion-1280.png | `set media light reduced-motion` (confirmed `matchMedia('(prefers-reduced-motion: reduce)').matches === true`), opened the bell. `[data-slot="sheet-content"]` computed `animation-name: enter`, `animation-duration: 0.15s`, `--tw-enter-translate-x: 0`, `--tw-enter-translate-y: 0`, `--tw-enter-scale: 1` - a 150ms fade with zero translate, even though the class list still carries `slide-in-from-right` (the reduced-motion override zeroes the translate custom properties rather than removing the classes). Media reset to no-preference afterward and reduced-motion confirmed off. |
| S2-02 dark mode contrast (Products detail) | Pass | run2-S2-02-product-detail-dark-1280.png | Added `dark` to `<html>` on the Product detail page (ZZTOI test item BCF910). `text-muted-foreground` computed `color: oklch(0.705 0.015 286.067)` = rgb(159,159,169); nearest `[data-slot="card"]` computed `background-color: oklch(0.21 0.006 285.885)` = rgb(24,24,27). Contrast ratio 6.75:1 (>= 4.5). `dark` class removed afterward. |
| S2-01 light-mode A/B, `:3090` vs `:3000` | Pass | run2-S2-01-products-list-3090-1280.png, run2-S2-01-products-list-3000-baseline-1280.png | `:3000` was reachable this run (unlike Run 1). Same account already authenticated cross-port (shared `localhost` cookie). Catalogue > Products list screenshotted on both at 1280 light mode: table data, column layout, borders, typography and row styling are visually identical between the two; only sidebar panel scroll/expand state differs (an interaction artifact of the nav path taken, not a token difference), consistent with the expected "no differences beyond header/sidebar translucency and card shadow tint." |

**Verdict: PASS.** All six Run 2 checks hold under review-fixed S2 code; no regression found, and
the one A/B check Run 1 could not complete is now confirmed clean.
