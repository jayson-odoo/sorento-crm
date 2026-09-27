# S1 fix lane round 2: browser evidence (27 Sep)

agent-browser 0.27.0, headless Chromium, session `s1round2`. Stack: backend on :8000 against a
private database cloned from the CI schema (`sorento_browse`), frontend `npm run dev` on :3000.
Seeded: company SRT, a superadmin login, agents ALI, MEI, RAJ, FAN, team Fanny North (ALI, MEI,
FAN), brands MOC and TPE, categories BAS and TAP, three products, three September sales orders,
and targets TGT-000001 (team, Brands MOC, split monthly Sep to Nov), TGT-000004 (team, all
products, September), TGT-000008 (ALI, two products, quantity), TGT-000009 (RAJ, category TAP).

Every screen was reached by sidebar clicks from `/` (Sales > Targets, Sales > Sales Teams), then
clicks inside the app. At 375 `document.documentElement.scrollWidth` read 375 or less on every
screen.

| File | What it shows |
| --- | --- |
| 01-targets-teams-1280 / -375 | Targets > Teams: line tabs, search, Columns, Export, standard header row and pager, one row per team target; no Active on, no footer lines (F3) |
| 02-targets-agents-filter-1280 | Targets > Agents with the Team filter in Filters (F3) |
| 02-targets-agents-no-team-1280 | Team filter = No team: only RAJ's target |
| 03-team-record-details / -gear / -targets / -agents / -edit (1280, 375) | The Sales Team record: header card, tabs Details, Targets, Agents; the gear holds Edit and Delete team; edit in place (F2) |
| 04-target-record-view / -gear / -edit / -periods (1280, 375) | The target record: header card, tabs Details, Periods, Agents, Commission; gear holds Edit, Duplicate, Delete target; Brands shows "MOC - Mocha" (F1, F4) |
| 05-target-products-view / -edit-no-uuid (1280), -edit-375 | TGT-000008 in edit: the Products chips read "BSN-001 - Countertop basin", "BSN-002 - Wall basin"; a UUID regex over the page text found nothing (F5) |
| 06-new-target-defaults-1280 | Set target on Teams opens `/sales/targets/new?kind=team`: the record empty with Amount, Ordered, All products, today to month end, split off (F4) |
| 06-new-target-brands-1280 | Applies to lists All products, Categories, Products, Brands; MOC picked (F1) |
| 06-new-target-half-range-refused-1280 | Clear on the date picker: "Pick both a start date and an end date.", Save disabled; the Split helper line under the fields (F6) |
| 06-new-target-agents-1280 / -375 | Agents tab: one figure per member, the Team target sum |
| 06-new-target-saved-1280 | Save created TGT-000010 and opened its record |
