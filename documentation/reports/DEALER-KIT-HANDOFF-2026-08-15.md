# Dealer Kit session handoff (2026-08-15)

Self-contained state document per the no-compact directive: everything a fresh session
needs to continue, with file pointers. Companion to
`DEALER-KIT-SELF-REVIEW-2026-08-14.md` (the audit that drove this work).

## Where things stand

**The Dealer Kit is on main** (PR #57, squash-merged 2026-08-14 11:32, commit `392d26fd2`).
The working branch `feat/dealer-kit-hardening` (worktree
`.claude/worktrees/dealer-kit`, ports 3040 FE / 8040 BE) carries the post-merge audit
fix wave, all committed and test-verified, NOT yet pushed:

| Commit | What |
|---|---|
| `6b009f792` | Self-review verdict document |
| `b2ba383d4` | Merge origin/main, adopting PR #57's canonical migration graph (single alembic head `322_merge_dealer_kit_customers`; the stale `319_..and..`/`320_..page..` files deleted) |
| `1dcbb7f79` | AC-G3 fix: brand-level visibility filter in `collection_service.resolve_tiles_bulk` (the audit's one true leak) |
| `84b461f0f` | Docs honesty pass, 7 edits (AC-B5 superseded, AC-L2/G5/H3 corrected, design-doc destaled, ledger jsdom excuse killed, B2 caveat into the edition plan) |
| `0ad01fee1` | FE mechanical: artboard pulled from palette, buildDataGridParams in brochureImageService, search on TileDesignsList + BundlesList, SearchableSelect in RoomDesigner |
| `d1862211d` | AC-L11: Edition transitions audited, plus two pre-existing shared `audit_service` defects fixed (non-idempotent listener registration; no-op guard that could drop a real change's row) |
| `3fe87b281` | Phase 3 review follow-ups, FE: audit-log filter knows Dealer Kit Edition; whitespace-only search shows the plain empty state (Tile Designs / Bundles / Collections); WallPicker extracted + tested; design-doc risk 5 attributed to PR #57. Reviewer's page-reset finding refuted (tanstack autoResetPageIndex is on by default). |
| `6e9a13908` | Phase 3 review follow-ups, BE (BLOCKER fixed): a "dealer" export is every brand's dealer tier read from `contact_access_types` (`audience_access_codes(db)`), not the bare Sorento `dealer` code, which combined with the G3 filter had silently dropped every CABANA/MOCHA tile from dealer PDFs; brand `[]`/NULL levels = public; audit guard counts many-to-one relationship reassignment; docstring's autoflush claim corrected; AC-G3 scope recorded honestly (bundle/selection paths not gated). |
| `7ce4a734a` | Sidebar duplicate: the b2ba383d4 merge kept both sides' Dealer Kit menu block, so the group rendered twice (second copy expanded to nothing). Deleted the duplicate; config test pins one-group + no-duplicate-titles invariants. Found live during the agent-browser verification pass. |

Verification evidence lives in each commit message. Totals across the wave: 85 edition +
22 audit + 61 resolution-family + 24 resolution + 55 selection/pricing backend tests
green; 441 dealer-kit frontend tests green (was 429); every behavioural fix
mutation-tested with the failing assertion named.

## Blocked or open, in order

1. **Prod rebuild of :3040 + browser check - DONE 2026-08-15.** Built and served on
   :3040 (prod build), verified via agent-browser through the sidebar: block palette
   offers Heading/Text/Image/Products/Bundle and NO Artboard; Tile Designs has a
   working search box (non-match shows the empty state); Bundles has a search box;
   Brochure Images paginates (page 2 shows different rows). The pass also caught a
   live bug: duplicate Dealer Kit sidebar group from the merge - fixed in `7ce4a734a`,
   rebuilt, re-verified (exactly one group). :3040 and :8040 are UP, started
   DETACHED (nohup) because harness background tasks were being reaped machine-wide;
   PID files + logs + restart script live in the session scratchpad
   (`start-stack.sh` is idempotent - reruns only what is down; `fe3040.pid` /
   `be8040.pid` name the processes to kill for shutdown).
2. **Container PDF-export smoke test** (audit blocker AC-I8, pre-deploy gate).
   `CONTAINER-PDF-EXPORT-RUNBOOK.md` names the exact two compose changes: a
   `sorento_network` alias for `frontend_blue`, and `DEALER_KIT_PRINT_BASE_URL` on the
   worker. The image itself is proven; the running-stack path is not.
3. **Push + follow-up PR - DONE 2026-08-15: PR #162** (`feat/dealer-kit-audit-fixes`,
   pushed from this worktree's local `feat/dealer-kit-hardening`; the remote branch of
   that name is PR #57's merged head and was left untouched). Phase 3 review ran
   first (reviewer agent, 11 findings, all addressed or refuted with evidence - see
   `3fe87b281` / `6e9a13908`). NEVER merge - merge to main is the deploy trigger,
   the captain's call.
4. **Captain decisions outstanding** (from the audit): build-or-descope on
   certification badges (Group E, schema-only), asset library UI (Group D), floor-plan
   upload/tracing (AC-R3/R4); the quote handoff (design doc §7.1); whether to converge
   Print Preview onto CatalogueRenderer (AC-H3 parity risk, now documented).

## Standing constraints active in this effort

- Fable orchestrates; execution delegated to sonnet/haiku subagents (firstmate directive
  2026-08-14). TDD with red-first evidence; mutation-test anything behavioural.
- Chrome UNINSTALLED; agent-browser only (`npx -y agent-browser open/snapshot/eval`);
  zero Playwright-driven verification. The committed `e2e/` spec suite stays.
- Never /compact - write a handoff doc (this pattern) instead.
- One pytest at a time on the shared DB (`sorento_ai_automation` - a COPY OF
  PRODUCTION; ZZT-scoped writes only). Other sessions violate this; keep runs small and
  re-run contention-shaped flakes.
- This worktree has NO venv: use
  `/Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend/venv/bin/pytest`.
- Kill only your own PIDs (`lsof -nP -ti :PORT -sTCP:LISTEN`, then verify cwd with
  `lsof -a -p PID -d cwd`). Never a pattern kill.
- Never bare `git stash` (shared stack across worktrees).
- Deploy only with explicit per-deploy permission. Nothing here is deployed.
- No em-dashes or en-dashes in anything written.

## Environment facts worth knowing

- The dev DB's alembic head is `353_project_order_inquiry_rename`, a revision from the
  project-sales worktree's branch that this tree does not carry. Do not run
  `alembic upgrade` from this tree; tests do not need it.
- `sorento_crm_backend/.env` here sets `DEALER_KIT_PRINT_BASE_URL=http://localhost:3040`
  (fixed 2026-08-09; it wrongly said 3020, which is the spec-search worktree's FE with
  no /c/print route - renders die on a print-ready timeout that looks like a broken
  print page).
- `test_dealer_kit_pdf_render.py` needs the stack up on 3040/8040 and defaults to 3040.
- The 8040 backend may need rebooting:
  `cd sorento_crm_backend && venv-path/uvicorn app.main:app --reload --host 0.0.0.0 --port 8040`
  (use the main checkout's venv).
