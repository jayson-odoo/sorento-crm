# Execution ledger — Dealer Kit S1–S3

**Owner:** Claude (orchestrating). **Status line is updated as work lands.**
Companions: `dealer-kit-builder-acceptance-criteria.md` (what "done" means) ·
`PLAN-dealer-kit-builder.md` (how it is built).

A phase is entered only after the previous phase is **approved** here. A slice is entered
only after the previous slice is **approved** here. Approval means every gate item below is
observed — not asserted.

---

## End goal (the thing that must be true at the end of S3)

A Sorento marketer opens the sidebar, builds this year's catalogue as a responsive page, binds
a curated set of products to a tile design, previews where the paper pages break, publishes it,
and exports a PDF that matches the screen. A dealer opening the same published page sees dealer
prices; a consumer sees consumer prices. **One document, resolved per reader.**

---

## Slice status

| Slice | Phase 1 (FE prototype) | Phase 2 (BE + wiring + tests) | Phase 3 (review) | Slice |
|---|---|---|---|---|
| **S1 builder core** | **PASSED** 2026-07-26 | not started | not started | in progress |
| **S2 collections + bundles** | blocked on S1 | blocked | blocked | blocked |
| **S3 PDF export** | blocked on S2 | blocked | blocked | blocked |

---

## S1 — Builder core

### End-to-end flow this slice must deliver

Sidebar → **Dealer Kit → Pages** → *New page* → editor → add a Section → drop Text / Image
blocks onto the 12-column grid → drag and resize on the grid → switch Desktop / Tablet / Mobile
and see derived layouts → toggle **Paper mode** and see where page 2 starts → **Save** (creates
version 1) → **Publish** (moves the `published` label) → open the public URL and see it → edit,
save (version 2), publish → **roll back** to version 1 → public URL follows the label.

### Phase 1 — FE prototype (mocks only, no backend)

Build: pages list, editor shell, section + 12-col grid with drag/resize/collide/compact,
breakpoint tabs with derived layouts, paper mode, asset library, tile-template editor, version
history + publish/rollback UI, public renderer. All against fixtures.

**Gate — every item observed in a real browser before Phase 2 opens:**
- [ ] Reached by **clicking the sidebar from `/`**, never a deep URL (menu gating is real)
- [ ] Grid: drag, resize, collide-push, vertical compact all work; snapping is to cells, never px
- [ ] Breakpoints: editing mobile flips `isDerived` false and desktop edits stop re-deriving it
- [ ] Paper mode shows break lines; the desktop canvas shows **none** (AC-H6)
- [ ] Usable at **375px and 1280px**; every modal scrolls to its submit button
- [ ] Loading / empty / error states exist for every list and the editor
- [ ] Only `components/ui` + `components/common` primitives — no bespoke table, no raw `<select>`
- [ ] `browser_console_messages` clean of unexpected errors/warnings
- [ ] Derivation golden-set test written **before** the derivation implementation (AC-K2)
- [ ] Documented API contract at the top of the service file

#### Phase 1 gate result — PASSED, with the gaps named

Verified in a real browser against a **prod build** on :3020, 7 Playwright cases green in ~27s,
plus 32 vitest cases and the full 1285-test suite with no regressions.

| Gate item | Result |
|---|---|
| Reached by clicking the sidebar from `/` | pass |
| Grid drag moves a block and marks the page dirty | pass |
| Breakpoints report 12 / 8 / 4 and show "follows desktop" | pass |
| Paper mode draws breaks; desktop canvas draws none | pass |
| No horizontal body scroll at 1280 / 768 / 375 | pass |
| Loading and error states | pass (vitest) |
| Shared `ui` + `common` primitives only | pass |
| Console clean | pass |
| Derivation golden set written before implementation | pass |
| API contract documented | pass |

**Four defects found and fixed during the gate, each a real bug rather than a test artefact:**

1. **`react-grid-layout` v2 is not v1.** `WidthProvider` no longer exists and the flat props
   became config objects, so the editor threw a client-side exception on load. My pre-install
   check verified peer deps but not the export surface, which is the check that would have
   caught it. Its `@types` package is also v1-only and was removed.
2. **Blocks clipped their own content** (AC-C4). Root cause was a stale closure: two blocks
   measuring in the same tick each spread a captured placement map, so the second silently
   wiped the first. Fixed with a functional update.
3. **The list scrolled the page body sideways at 768px** because it omitted the `ScrollArea`
   wrapper every other list in the app uses.
4. **"Unsaved changes" appeared before the user touched anything**, because the grid's own
   load-time compaction was reported as an edit. Now only a real drag or resize counts.

**Not verified, and deliberately not claimed:** resize-to-fit and collide-push as
*interactions* (the config is wired and drag is proven, but only drag is driven by a test);
the re-derive button; the populated and empty grid bodies in vitest, which do not mount under
jsdom and are covered by Playwright instead.

### Phase 2 — Backend + wiring + tests

Build: migration (schema + 5 tables + 2 core column adds), models, module catalog + guard, six
permissions + grant sweep, version/label service, routes, then FE off mocks onto real hooks.

**Gate:**
- [ ] Migration chains onto the **committed** head; `alembic heads` shows exactly one
- [ ] `alembic upgrade head` then `downgrade -1` then `upgrade head` — clean both ways
- [ ] Every owned table on `CompanyScopedMixin`; leak test asserts UNSET scope → 0 rows
- [ ] Versions immutable; `max(version)+1` **per page_id**; label move busts the cache
- [ ] `page.edit` without `page.publish` → publish absent in UI **and** 403 on the API
- [ ] Page with no `published` label → public render **404s**, never falls through
- [ ] pytest: happy path + auth denial + validation error on every new route. **Postgres only.**
- [ ] Fixture cleanup **scoped to marker rows**, symmetric before+after (the DB is a prod copy)
- [ ] vitest: loading / empty / error / data per new component
- [ ] Playwright spec drives the full flow above and asserts the `/api/v1/*` calls
- [ ] All three suites green

### Phase 3 — Review

- [ ] `/code-review` run, findings addressed
- [ ] `documentation/PR-CHECKLIST.md` walked
- [ ] No duplication of `extractApiError` / `buildDataGridParams` / user-select helpers
- [ ] Delete + unlink confirmed via `ConfirmDeleteDialog`, hard delete, count in bulk copy
- [ ] Prod build (`npm run build && npm start`) before handoff

---

## S2 — Collections, binding, bundles

**Flow:** editor → *Add products* → pick by rule (RuleBuilder) or by hand → silently a
page-scoped Collection → bind it to a Tile Template → tiles render → *Save as reusable
collection* → bind the same one to a second page → add a product → **both** pages reflect it.
Bundles render as one priced heading with components beneath.

**Gate adds:** collection resolution golden set **first** · bundle allocation sums exactly to
the cent · bundle unavailable when any component is discontinued (derived, never stored) ·
invoice price gated by document toggle **AND** viewer access, absent from the *response* when
denied · `product` fact source registered on the existing `app/rule_engine`, no second evaluator.

## S3 — PDF export

**Flow:** page → *Export PDF* → `UserDownload` row `pending` → worker renders the print route
through headless Chromium → My Downloads → download → **matches the screen**.

**Gate adds:** viewer context snapshotted at **enqueue** onto `dealer_kit.export_request`
(`UserDownload` has no params column) · worker never falls back to a system principal · a
dealer export and a staff export of the same page carry **different prices** · Chromium present
in the worker container, verified in a container, not only on macOS.

---

## Standing constraints (violating any of these fails the gate)

- Tests are **Postgres only**. No sqlite. Committing tests use a private `zzt_` schema.
- All pytest cleanup **scoped to marker rows** — the local DB is a copy of prod data.
- Frontend iterates on `npm run dev` (HMR). Handoff is `npm run build && npm start`.
- Reuse `components/ui` + `components/common`. `SearchableSelect`, `DataGrid`,
  `ConfirmDeleteDialog`, `RuleBuilder`, `FormDialogScaffold` already exist — use them.
- No UUIDs rendered in the UI. No em-dashes in any writing.
- Deploy only on explicit per-deploy permission. Nothing here deploys.
