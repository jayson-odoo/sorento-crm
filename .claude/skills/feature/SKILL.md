---
name: feature
description: Run a non-trivial feature through this repo's mandatory pipeline - journey, grill, UAC, plan, tickets, FE mock, BE TDD, review, DoD gate - invoking the mattpocock skills at the slots where they belong. Use when starting any feature, refactor or module that is more than a one-file change.
---

# /feature - the sorento_crm delivery pipeline

`PRINCIPLES.md` defines the mandatory order. This skill executes it, calling the
`mattpocock-skills` plugin as subroutines at the steps where they fit.

**The order is the point.** Skipping or reordering a step is a process violation
(`PRINCIPLES.md` step 0-6). If a step genuinely cannot be done, say so explicitly
and record why in the PR description - do not silently drop it.

## Two rules that override the plugin skills

The plugin was written for a different repo. Where it disagrees with
`PRINCIPLES.md`, `PRINCIPLES.md` wins:

1. **Files are the source of truth; tickets are the queue.** `to-spec` and
   `to-tickets` want to publish the spec into GitHub Issues. Here the contract is
   `documentation/plans/<domain>/<slug>-acceptance-criteria.md` (UAC) plus
   `documentation/plans/<domain>/PLAN-<slug>.md`. Issues link back to those paths.
   An issue that contradicts the UAC loses.
2. **Frontend mock before any backend code.** `implement` drives straight to TDD
   and has no concept of Phase 1. Never hand it the whole feature. Scope it to
   Phase 2, or run the phases yourself.

## Who executes each step (delegation is part of the order)

Every step has a named executor. Running a step in the wrong seat is the same
process violation as skipping it. Deviations are recorded in the PR description.

- **Main session** (strongest model, holds the grill context): steps 0-5
  (journey, grill, UAC, plan, plan review, tickets), all user-in-the-loop
  moments (grilling, `/lavish` markup, browser handoff), and orchestration.
  Planning is NEVER delegated for normal features: the `planner` agent exists
  only for module-sized work needing parallel exploration of independent
  sub-plans.
- **`tester` agent** (sonnet): writes step 7's failing tests BEFORE the coder
  sees the slice - from the UAC, the Phase 1 contract doc, and the captain's
  test list (one line per UAC id: test name + the assertion in words) - with
  no implementation to look at. Confirms each test fails for the right reason
  (missing route/function, not an import typo), then commits the red tests.
  Also runs the end-of-lane browser verification (agent-browser) once the
  coder is green.
- **`coder` agent** (sonnet): steps 6 and 7 implementation, ONE agent kept
  alive for the whole lane - the captain continues it with a message for
  later slices and fix rounds instead of respawning, so context and worktree
  state carry over. Spawn with `isolation: "worktree"` - the user codes
  concurrently in the main checkout, so the coder must never share the
  working tree. Its prompt is ONLY: the PLAN path, the UAC path, the slice id,
  and the phase (1 or 2). The files are the contract; do not paraphrase them
  into the prompt. In Phase 2 the coder makes the tester's red tests green; it
  does not author or delete a test, and a test it believes is wrong is
  reported to the captain, not silently fixed.
- **`reviewer` agent** (opus) + **`security-reviewer` agent** (opus) +
  browser verification (`tester` agent): step 8, run in **parallel**, once per
  lane, not once per slice. `reviewer` runs `/code-review`, optionally
  followed by `/codex-review` (OpenAI model family, second opinion) on risky
  or large diffs, plus a **kill test**: for 2-3 UAC lines, comment out the
  implementing branch, run the test, confirm it goes red - a test that stays
  green is a blocker ("test does not guard AC-x"). `security-reviewer` runs
  only when the diff touches auth, RBAC/permission gating, external ingest,
  file upload/storage, or multi-company scoping.
- **`guide-writer` agent** (sonnet): after review passes, writes/updates the
  Outline user guide for the feature (`documentation/user-guides/`) - the
  repo rule "no feature explanations inside the UI" means the explanation
  lives here, not in the diff.
- Trivial one-file changes may run inline in the main session; say so instead
  of silently absorbing a real slice.

## The pipeline

### Step 0 - Scope check

If the work is module-sized (more than one agent session can hold - e.g. an SCM
milestone, a new after-sales surface), run `/wayfinder` FIRST to chart the
unknowns as investigation tickets. Otherwise skip to step 1.

### Step 1 - Guided journey

Write the journey before any entity, table, endpoint or status graph is named:
who the actor is, where they arrive from, what the first screen shows, what the
system already knows, each step and its single decision, what they hold at the
end, what every other stakeholder is told automatically.

Optimise for the **fewest decisions the user must make**. Anything derivable from
something they already gave us is derived, never asked.

**A plan whose first section is a schema is rejected.** No skill does this step - 
it is manual, and it is the one that protects the rest.

### Step 2 - Grill

- Domain surface involved (new terms, new entities, anything in a glossary) →
  `/grill-with-docs`. It challenges the design against `CONTEXT-MAP.md` and writes
  ADRs into `documentation/adr/` inline.
- Pure UX or flow question, no domain surface → `/grill-me`.
- Design brief: for every surface touched, its density, how often the actor hits it per day
  (the frequency gate in `documentation/reference/DESIGN-LANGUAGE.md`), and an explicit list of
  what must NOT animate.

Resolve every branch of the decision tree before writing anything down.

### Step 3 - UAC, then plan

**UAC first - it is the contract.** Write
`documentation/plans/<domain>/<slug>-acceptance-criteria.md`: the journey at the
top as its `Journey` section, then independently-verifiable Given/When/Then ACs,
each with an id, grouped by phase, tagged `[BE]` / `[FE]` / `[E2E]` / `[T]` / `[UX]`. Every
AC traces to a step in the journey. Run `find-animation-opportunities` read-only on the
current surface; its capped list becomes `[UX]` ACs (each measurable: breakpoint, duration
token, reduced-motion, pressed state, empty state) or an explicit no-motion list in the plan.

**Then** the plan: `documentation/plans/<domain>/PLAN-<slug>.md`, the design that
fulfils the UAC. No plan ships without its UAC file.

`/to-spec` is useful for drafting both - but redirect its output to these two
files. Do not let it publish the spec as an issue. Its "testing seams" step
(step 2) is worth keeping: agree the seams before Phase 2 starts.

Defer-items go to `documentation/backlogs/backlog.md`.

### Step 4 - Review the plan

Render it with `/lavish` for the user to mark up, then `/grill-me` the plan
itself. Grill before code, always.

### Step 5 - Slice into tickets

`/to-tickets` - tracer-bullet vertical slices with blocking edges, published to
GitHub Issues on `jayson-odoo/sorento-crm`.

Each issue body must link its PLAN and UAC paths. Slice ids stay consistent with
the plan's own numbering (S0, S1, ...). Wide refactors use expand-contract rather
than vertical slices - `to-tickets` knows this shape.

### Step 6 - Phase 1: frontend-first, mocked

UI → hook → service → **mock**. No backend code. No tests yet - the shape may
still shift.

Tune every state: loading, empty, error, partial, success. Reuse before
inventing; a new variant is a prop on the shared component, never a parallel
one-off. Document the expected API contract at the top of the service file.

Verify in a real browser via **agent-browser** (headless;
`npx -y agent-browser@0.27.0 <command>`), navigating by **sidebar clicks from `/`** - 
never a deep URL. Check `console` and `errors`. Screenshot the golden path and the
edge cases. `close` when done. Playwright MCP is retired for verification.

If the open question is "which of these three designs", run `/prototype` before
this step and **throw the result away** - it is not built to this repo's layering
rules and must not become the shipped FE.

Any new motion goes through the `animate` decision gate and uses only `lib/motion.ts` presets
and `config.reui.css` tokens. The coder reads `DESIGN-LANGUAGE.md` before the first UI file.

### Step 7 - Phase 2: backend wiring, test-FIRST, tester before coder

**Tester writes the red tests first.** Before the coder opens the slice, the
`tester` agent gets the UAC, the Phase 1 contract doc, and the captain's test
list (one line per UAC id: test name + the assertion in words), writes the
failing tests with no implementation to look at, confirms each fails for the
right reason (missing route/function, not an import typo), and commits them
as `test(<slug>): red tests for <slice>`.

**Then the coder makes them green**, ONE agent kept alive for the whole lane
(the captain continues it via message for later slices, not a respawn).
Models → migration → schema → service → route, matching the Phase 1 contract
exactly. Then swap the mock for the real `api-client` call at the service
boundary. The coder does not edit or delete a red test without reporting why
to the captain first.

**Red → green → refactor, not test-after.** Implement the minimum to pass,
then refactor green. Applies to every route (happy + auth-denial +
validation), every service branch, and above all to deterministic engines,
whose golden-set numbers are written as failing tests first.

`/tdd` drives this loop. `/implement` may drive a ticket end-to-end **at this
phase only**, and it calls `/tdd` internally.

Tests land here, never deferred to Phase 3: pytest, vitest, and per user flow a
real-clicks FE→BE→DB walk, but **no new Playwright spec**: a recorded
agent-browser evidence run stands in, per CLAUDE.md "Persisted Playwright spec".
Re-verify live against the running stack.

Backend tests run on **Postgres only, never sqlite**.

### Step 8 - Phase 3: review, in parallel

Once the coder is green for the whole lane, run three agents **in parallel**,
once per lane, not once per slice:

- **`reviewer`** (opus): `/code-review` (this repo's own - `ultra` for big
  diffs), plus a **kill test**: for 2-3 UAC lines, comment out the
  implementing branch, run the test, confirm it goes red - a test that stays
  green is a blocker finding ("test does not guard AC-x"). Follow with
  `/simplify` or `--fix` for the findings.
- **`security-reviewer`** (opus): only when the diff touches auth
  (`app/dependencies.py`, NextAuth, JWT), RBAC/permission gating
  (`app/modules/runtime/guards.py`, `app/rbac/permission_registry.py`,
  permission slugs, role grants), external ingest (`app/api/v1/external/*`,
  `app/api/v1/public/*`, webhooks, `X-API-Key`), file upload/presign/storage,
  or multi-company scoping (`CompanyScopedMixin`, raw SQL). Uses the built-in
  `/security-review` checklist. See `.claude/agents/security-reviewer.md` for
  the full trigger list.
- **browser verification** (`tester` agent, agent-browser): end-of-lane, once,
  not per slice.

Design pass: `emil-design-eng` review table (Before / After / Why) on every UI diff;
`review-animations` only when the diff touches motion. Hard-fails listed in
`DESIGN-LANGUAGE.md`.

`reviewer` runs `documentation/reference/PR-CHECKLIST.md` plus the DoD gate.
Fix round: the SAME coder takes reviewer + security findings; the captain
adjudicates only findings that add a layer (registry, abstraction, config
surface) per PRINCIPLES "Simplest thing that works". After review passes, the
`guide-writer` agent writes/updates the Outline user guide.

### Step 9 - Definition of Done gate

A slice is not done until all pass (`PRINCIPLES.md`):

1. Mock swapped to real, verified showing real data
2. Existing rows backfilled
3. New permission → grant sweep for provisioned roles
4. New DB column reaches the FE (**both** manual dict builders)
5. Verified from the user's perspective - real sidebar clicks, real data, at
   **375px AND 1280px**

### Step 10 - Ship

Branch per feature; merge only after review. The user codes concurrently in the
main checkout - run `git status` before ANY branch or commit operation and never
assume the tree is clean. Hand off on the **dev server** (`npm run dev`), never a
prod build: that is the standing rule in `CLAUDE.md` "Frontend dev loop", and it
supersedes the older prod-build habit this step used to carry.

### Step 11 - Reclaim the worktree

A slice is not closed until its build cache is gone. A `.next` directory reaches
2-3G per worktree and never shrinks, so idle lanes quietly cost tens of gigabytes.
It is regenerable, so it must not outlive the work.

Once the PR is merged (or the lane is abandoned), from the primary checkout run:

```bash
./scripts/worktree-gc.sh                     # dry run, see what would go
./scripts/worktree-gc.sh --apply             # drop .next in every idle worktree
./scripts/worktree-gc.sh --apply --merged    # also remove clean worktrees whose
                                             # HEAD is already in origin/main
git worktree prune
```

The script skips any worktree running `next dev`, never kills a process, and
never removes a worktree that is dirty or not yet in `origin/main`. Add `--deep`
to also drop `node_modules` and `venv` from lanes you are done with.

## Skill map (quick reference)

| step | skill | executor |
| ---- | ----- | -------- |
| 0 scope unknown | `/wayfinder` | main session |
| 1 journey | manual - no skill | main session |
| 2 grill | `/grill-with-docs` (domain) or `/grill-me` (flow) | main session (user in loop) |
| 2b terms shifting | `/domain-modeling` | main session |
| 3 UAC + plan | `/to-spec`, output redirected to files | main session (plan mode) |
| 3 UAC design ACs | `find-animation-opportunities` (read-only) | main session |
| 4 plan review | `/lavish` then `/grill-me` | main session (user in loop) |
| 5 tickets | `/to-tickets` | main session |
| 6 design options | `/prototype` (throwaway, before Phase 1) | main session |
| 6 Phase 1 FE mock | - | `coder` agent, worktree |
| 6 new motion | `animate` (decision gate) | `coder` agent, worktree |
| 7 red tests | UAC + contract + captain's test list, no implementation | `tester` agent, before the coder |
| 7 TDD | `/tdd`, or `/implement` scoped to Phase 2 | `coder` agent, worktree (same agent for the whole lane) |
| 8 review | `/code-review` (this repo's) + kill test, then optional `/codex-review` | `reviewer` agent, parallel with security-reviewer + browser verification |
| 8 security review | built-in `/security-review` checklist | `security-reviewer` agent, parallel with reviewer |
| 8 browser verification | agent-browser, once per lane | `tester` agent, parallel with reviewer |
| 8 review design | `emil-design-eng`, `review-animations` (motion diffs only) | `reviewer` agent |
| 8 user guide | Outline sync (`documentation/user-guides/README.md`, `SYNC.md`) | `guide-writer` agent, after review |
| new FE dependency | `pick-ui-library` | `coder` agent, worktree |
| bugs | `/triage` then `/diagnosing-bugs` | `triage` agent (inbound issues) + main session |
| periodic | `/improve-codebase-architecture`, `/codebase-design`, `improve-animations` | main session |
| context full mid-slice | `/handoff` then `/clear` then `/resume-handoff` | main session (user types `/clear`) |
| context research | `/research` | main session |

## Related

- `PRINCIPLES.md` - the binding contract this skill executes
- `documentation/reference/DESIGN-LANGUAGE.md` - tokens, motion presets, primitives roster
- `CLAUDE.md` - repo conventions, dev sessions, architecture
- `LESSONS-LEARNT.md` - the gotcha log (88 entries); read before debugging anything non-obvious
- `CONTEXT-MAP.md` - glossaries
- `documentation/agents/` - issue tracker, triage labels, domain doc rules,
  session handoff (`/handoff` + `/resume-handoff`, the autocompact replacement)
