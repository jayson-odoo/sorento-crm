# Dealer Kit self-review verdict (2026-08-14)

**Requested by:** captain, via firstmate directive: audit (a) whether requirements and
acceptance criteria are actually met, traced to evidence, and (b) whether the design and
architecture follow the repo's binding standards. Three parallel audit agents traced every
AC in all four AC files and audited the code against PRINCIPLES.md,
`documentation/reference/ADR-PRODUCT-STANDARDS.md`, ADR 0008 and the module's own design
doc. Their key claims were independently re-verified before being accepted; two of their
justifications were corrected by measurement.

## Headline

**The core is real and the tests bite.** 455 backend tests and 209 frontend tests were
re-run green during this audit, one file at a time, on the shared database. Groups Z, A,
B, C, D, E, F of the flyer-seeding UAC and all seven groups of the reading-and-choosing
UAC are MET or MET-WEAK with named test evidence, with exactly one exception (AC-B5,
deliberately superseded by AC-I26; a doc fix, not a code fix). The architecture audit
found 17 of 20 binding-rule checks clean with file:line evidence: layering,
`extractApiError`, DataGrid contract, hard delete + confirmation, AppException, module
guard, company scoping, migrations, Decimal money, ADR 0008 single-price-resolver.

**But the branch state changed under us: the work is already on main.** PR #57
squash-merged the Dealer Kit to main at 11:32 today, including everything through the
AC-E5 commit. The design doc's "merge is blocked behind multi-company" was stale twice
over. Every fix below therefore targets main via follow-up, not this branch's merge.

## Code defects, ranked

1. **Brand visibility leak in collection resolution (AC-G3, NOT-MET).** `Product` carries
   no `access_levels`; the visibility contract is brand-level, and the repo already
   enforces it elsewhere (`app/api/v1/system/references.py:482-508` filters products by
   `brand.access_levels` intersecting the viewer's codes). Dealer-kit's
   `collection_service._sellable_products` applies no such filter, so a dealer-restricted
   brand's products render on the anonymous public catalogue. Prices are gated; presence
   is not. **Fix:** mirror the references.py brand filter in `_sellable_products` /
   `_sellable_by_ids`, plus a test with a dealer-only brand and an anonymous viewer.
2. **No audit trail on Edition transitions (AC-L11, NOT-MET).** An approval workflow
   whose approvals leave no record of who moved what, when. `Edition` has no audit
   columns and no transition log. **Fix:** audit-track `status_key` changes or write a
   transition log row per move.
3. **Artboard is a reachable stub (AC-C10, NOT-MET).** In the block palette
   (`PageEditor.tsx:91`); placing one yields a permanent placeholder, `children` always
   `[]`, no inspector case. **Fix:** pull it from the palette until the sub-canvas
   exists.
4. **`buildDataGridParams` bypassed** at
   `dealer-kit/services/brochureImageService.ts:130` (hand-built `URLSearchParams` with
   page/limit/query). Mechanical fix.
5. **Missing list search** on `TileDesignsList` (a real DataGrid; every sibling has one)
   and `BundlesList` (card grid is a documented, acceptable deviation; missing search is
   not). Mechanical.
6. **Raw `<select>`** in `RoomDesigner.tsx:985` against the SearchableSelect standard
   (AC-J2). Mechanical.

## Feature groups that are stubs, needing a build-or-descope decision

These are not defects; they are ACs written for features whose schema landed and whose
feature did not. Each needs an explicit product call, recorded in the plan doc:

- **Certification badges (AC-E1, E4-E9):** `collection_service.py` hardcodes
  `"badges": []`; no admin cert-logo route, no `valid_until` gating, no multi-image tile.
  Schema (migration 309) is ready.
- **Asset library UI (AC-D2, D4, D5):** no route, no sidebar entry, no delete-with-usage
  warning; SVG is not an accepted mime type. Assets exist only as flyer-seed artifacts.
- **Interactive print-hidden blocks (AC-H2):** `INTERACTIVE_BLOCK_TYPES` is an empty
  set, and the block types it would name do not exist. Vacuous today, a trap later.
- **S4 journey gaps:** floor-plan upload + tracing (AC-R3/R4) never built - a headline
  journey step, currently undocumented as deferred; no FE to rename/delete a Selection
  (AC-S7); no photo on 3D boxes (AC-V3); no perf degrade path (AC-V5).
- **Quote handoff (AC-Q2/Q3/Q4):** already an explicit, reasoned deferral awaiting the
  product decision in the design doc §7.1. Nothing new.

## Spec and doc honesty debt

- **AC-B5** superseded by AC-I26 (single candidate auto-taken): strike or cross-reference
  in the flyer-seeding UAC.
- **AC-L2** names a transition graph that was improved in the build (`rejected->draft`,
  `approved->pending_approval`; `done->draft` withdrawn): update the AC to the shipped
  edges.
- **AC-G5** says server-rendered; the public and print routes are `'use client'` CSR.
  Either convert or correct the AC to the actual print-ready-signal architecture.
- **AC-H3** claims Print Preview uses the same route the PDF renders. It does not:
  preview renders `PaperCanvas`+`BlockPreview`, the PDF renders `CatalogueRenderer`. Two
  paths where the design promises one renderer - a real parity risk, not just doc drift.
  Decide: converge them, or rewrite the AC and accept the risk knowingly.
- **DEALER-SALES-KIT-DESIGN.md is stale:** wrong branch name, dead merge blocker,
  §4.3 "absent from the response" contradicting ADR 0008's 2026-08-01 correction.
- **EXECUTION-LEDGER's S9 excuse is false:** "DataGridTable does not mount rows under
  jsdom" was later disproven (mock `useListingColumnPreferences`); the vitest coverage
  that note excused is writable today.
- **PLAN-edition-approval.md omits the B2 caveat** (an approval attests a version id, but
  collections resolve live, so approved content can drift under the label). It lives only
  in a ledger footnote; the plan should carry it.

## Deployment blockers (pre-existing, on record, unchanged)

- **Container PDF export has never run in a running stack** (AC-I8). The worker image is
  proven; the compose wiring is not: `frontend_blue` has no network alias and
  `DEALER_KIT_PRINT_BASE_URL` is unset on the worker, which per the runbook means every
  export fails on a render timeout. `CONTAINER-PDF-EXPORT-RUNBOOK.md` names the exact two
  changes. Must run one real export in the stack before any deploy.

## Branch mechanics

- Main renamed two alembic migration files during the PR #57 merge
  (`319_merge_dealer_kit_and_form_sla.py`, `320_dealer_kit_page_tile_template.py`) with
  small content edits, and touched `test_dealer_kit_selection.py`. The next merge of
  main into any dealer-kit worktree must adopt main's versions or alembic grows
  duplicate heads.
- This branch also carries non-dealer-kit strays main lacks (SCM cash-copilot
  components, a `.claude/skills` file). Recommend: start follow-up work on a fresh
  branch off main; retire `feat/dealer-kit-hardening` once its delta is confirmed empty.

## What was checked and found clean (no action)

FE layering end to end; `extractApiError` in all seven services; DataGrid contract on
all six real grids; hard delete + `ConfirmDeleteDialog` everywhere, zero `confirm()`;
no UUIDs rendered; modal-default CRUD; AppException-only error flow; module guard;
company scoping with 404 gates (including the documented `None == None` fix); a
migration for every model column; Decimal end to end with floats only on geometry;
post-commit side effects best-effort; ADR 0008 honored at all four call sites;
`sectionSurface` as single geometry owner; no dormant routes; no over-engineering found
- the module is well-factored.

## Verdict

**Quality of what was built: high.** Test evidence is real, the architecture follows the
repo's own rules with unusually few exceptions, and the one supersession (B5 to I26) was
done deliberately with the reversal documented in the test itself.

**Completeness against the AC files as literally written: overstated in three places.**
Certification badges, the asset library, and the S4 floor-plan step read as delivered in
the AC files but are stubs. The honest state is: S1-S3 and S7/S9 delivered and
evidenced; S2.5 delivered minus its audit trail; S4 part-delivered exactly as the design
doc says, plus two undocumented gaps (R3/R4, S7-selection UI).

**Recommended order of work:** (1) G3 brand filter - the only leak; (2) Edition audit
trail; (3) pull artboard from the palette; (4) the three mechanical FE fixes; (5) the
doc honesty pass; (6) container export smoke test before any deploy; (7) build-or-descope
decisions from product on badges, asset library, floor-plan upload.
