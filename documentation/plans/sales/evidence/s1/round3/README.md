# S1 fix lane round 3: browser evidence (27 Sep)

agent-browser 0.27.0, headless Chromium (Playwright's bundled build at
`/opt/pw-browsers/chromium-1194`, via `AGENT_BROWSER_EXECUTABLE_PATH` - the CLI's own
`agent-browser install` could not reach the Chrome-for-Testing CDN from this container),
session `s1round3`. Stack: backend on :8000 against a private database `sorento_browse`
(`CREATE DATABASE ... TEMPLATE sorento_ci`, already at alembic head
`sales_0005_commission_tiers`, so no migration was needed), frontend `npm run dev` on :3000.
Every module in the app-store catalog was installed for the tenant (`POST
/api/v1/system/modules/install`) so the Sales sidebar group renders - a fresh `sorento_browse`
clone has zero `tenant_modules` rows, and the frontend's own module-gated sidebar filter (unlike
the backend's `require_permission` guard) has no "legacy install, allow everything" exception,
so without this step the whole Sales menu group is invisible.

Seeded via direct SQLAlchemy insert (user + sales agents) then the real `/api/v1/sales/*`
endpoints (team, target, figures): company SRT (pre-existing default tenant), superadmin login
`round3.superadmin@sorentocrm.dev`, agents ALI, MEI, CIN (Cindy Lee), RAJ, a sales team "North"
(ALI, MEI, CIN), and a TEAM target "2026 Q4 Target" (TGT-000001, all products, Amount/Ordered,
1 Oct to 31 Dec 2026, split every 1 month) with agent figures ALI 600 and CIN 400 (MEI left
without a figure, as asked). No sales orders were seeded, so Achieved reads 0 / "-" throughout
(marked optional in the brief; skipped for time - the SCM sales-order chain needed for
achievement is not part of the sales-targets slice under test).

Every screen was reached by sidebar clicks from `/` (Sales > Targets), then clicks inside the
app - CIN's agent target was opened by clicking her name in the team's Agents grid, and the team
target was re-opened from CIN's "Open team target" link, never a deep URL. `get url` was checked
after each navigation.

## Defect found

**Commission tab, Edit mode: the tier table overflows the page at 375px, not just its own box.**

- Repro: any target record (tested on the team target TGT-000001, and the pattern is shared code
  so the same applies to an agent target) → Commission tab → gear → Edit (or, empty state, "Add
  tier") → set viewport to 375 wide.
- Expected (per brief): "no horizontal page scroll... the grids may scroll inside their own box."
  Every other grid on these records (Periods, the team's Agents grid, both wider than 375 too)
  honours this - `document.documentElement.scrollWidth` stayed 375 with those tabs' edit modes
  open.
- Actual: `document.documentElement.scrollWidth` reads **460** with the Commission tab's tier
  table visible in Edit mode (one tier row is enough to trigger it; two tiers doesn't make it
  worse). The table itself does scroll inside its own bordered box (a scrollbar is visible under
  the From/Rate columns in `06-commission-edit-375.png`), but the PAGE also grows a second,
  full-width horizontal scrollbar - visible at the very bottom of the same screenshot, below the
  footer text and the floating AI-assistant button. Confirmed causal, not a snapshot artifact: with
  the table's own wrapping `<div class="overflow-x-auto rounded-lg border">` toggled to
  `display:none` via `eval`, `document.documentElement.scrollWidth` drops from 460 to 375;
  restoring the div brings it back to 460. Read again three times a second apart (460, 460, 460),
  so not a mid-transition frame either.
- Root cause pointer for the coder: `TargetRecord.tsx` line ~1503, the tier table
  (`<table aria-label="Commission tiers" className="w-full min-w-[28rem] text-sm">`, 448px) sits
  inside `<div className="overflow-x-auto rounded-lg border">` inside `<section
  className="flex flex-col gap-3 p-5">` (the Commission tab panel). The Periods table one tab
  over uses the identical wrapper pattern (`overflow-x-auto rounded-lg border` around a
  `min-w-[32rem]` table, 512px - wider than Commission's) and does NOT leak past the page at
  375px, so the difference is something specific to the Commission section's markup or its
  `sm:w-80` "How tiers pay" sibling block, not the overflow pattern itself. No console error and
  no uncaught exception accompanies it (`console`/`errors` both clean) - it is a pure CSS layout
  defect, not a JS one.
- Everything else in F1/F2/F3 passed clean at both widths; this is the one open item.

## Screenshots

| File | What it shows |
| --- | --- |
| 01-team-periods-read-1280 / -375 | Team target Periods tab, read mode: values only, no pencil icons, no inputs (F1) |
| 02-team-periods-edit-1280 / -375 | Same tab in Edit mode (Cancel/Save in the header card): still read-only, live-recomputed sums - a team's periods are the SUM of its agents' figures, not directly editable (F1, by design; confirmed against `TargetRecord.tsx`) |
| 03-team-agents-read-1280 / -375 | Team target Agents tab, read mode: ALI 600/600/600, CIN 400/400/400, MEI "No figure yet", Team target totals row 1,000/1,000/1,000 |
| 04-team-agents-edit-live-total-1280 / -375 | Same tab in Edit mode: every cell an input including MEI's row; typing MEI's Oct figure (200) live-updates the Team target totals row to 1,200 before Save |
| 05-commission-empty-1280 | Commission tab, no tiers: "No commission" + "Add tier" button (F2) |
| 06-commission-edit-1280 / -375 | Edit mode, two tiers typed (0% / rate 2, 100% / rate 4 / bonus 500) - the 375 shot is also the defect screenshot (see above) |
| 07-commission-read-1280 / -375 | Read mode after Save: tiers as read-only rows |
| 08-agent-record-header-1280 / -375 | CIN's agent target (opened from the team's Agents grid): header reads "2026 Q4 Target / For CIN - Cindy Lee / Agent target, part of 2026 Q4 Target" with a link |
| 09-agent-team-target-tab-1280 / -375 | CIN's Team target tab: parent's name/number, measure, counts, applies to, dates, split, periods (with the post-save figures) and "Open team target" |
| 10-agent-details-edit-readonly-1280 | CIN's Details tab in Edit mode: Name is an input, but What counts and Dates stay read-only with exactly one line, "Set on the team target" (only under What counts - Dates has no such line and simply shows the inherited values, so there is exactly one such note in the whole tab, never two, and never "Set on 2026 Q4 Target") |
| 11-agent-periods-edit-1280 / -375 | CIN's Periods tab in Edit mode: a number input per period; typed 500/450/600 |
| 12-team-after-write-through-1280 / -375 | Back on the team target (via CIN's "Open team target" link) after Save: Periods tab shows 1,300 / 1,200 / 1,300 - the write-through from CIN's 500/450/600 (Oct 400→500 = +100, Nov 400→450 = +50, Dec 400→600 = +200 against the prior 1,200/1,150/1,100) |

## scrollWidth readings at 375

All screens read `document.documentElement.scrollWidth <= 375` except the one noted above:

| Screen | scrollWidth |
| --- | --- |
| Team Periods, read | 375 |
| Team Periods, edit | 375 |
| Team Agents, read | 375 |
| Team Agents, edit (live totals) | 375 |
| Commission, edit (team target) | **460 - defect** |
| Commission, read (team target, after save) | 375 |
| Agent record header (CIN) | 360 |
| Agent Team target tab (CIN) | 360 |
| Agent Periods, edit (CIN) | 375 |
| Team target after write-through | 375 |

No UUID was found in page text on any screen checked (regex scan of `document.body.innerText`
came back empty each time).
