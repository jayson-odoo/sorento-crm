---
name: feature
description: Run a non-trivial feature through this repo's mandatory pipeline — journey, grill, UAC, plan, tickets, FE mock, BE TDD, review, DoD gate — invoking the mattpocock skills at the slots where they belong. Use when starting any feature, refactor or module that is more than a one-file change.
---

# /feature — the sorento_crm delivery pipeline

`PRINCIPLES.md` defines the mandatory order. This skill executes it, calling the
`mattpocock-skills` plugin as subroutines at the steps where they fit.

**The order is the point.** Skipping or reordering a step is a process violation
(`PRINCIPLES.md` step 0-6). If a step genuinely cannot be done, say so explicitly
and record why in the PR description — do not silently drop it.

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
- **`coder` agent** (Agent tool): steps 6 and 7 implementation. Spawn with
  `isolation: "worktree"` - the user codes concurrently in the main checkout,
  so the coder must never share the working tree. Its prompt is ONLY: the PLAN
  path, the UAC path, the slice id, and the phase (1 or 2). The files are the
  contract; do not paraphrase them into the prompt.
- **`tester` agent** (sonnet): test authoring and running in step 7 when split
  from the coder. Asserts against UAC ids.
- **`reviewer` agent + `/code-review`**: step 8. Optionally follow with
  `/codex-review` (OpenAI model family, second opinion) on risky or large diffs.
- Trivial one-file changes may run inline in the main session; say so instead
  of silently absorbing a real slice.

## The pipeline

### Step 0 — Scope check

If the work is module-sized (more than one agent session can hold — e.g. an SCM
milestone, a new after-sales surface), run `/wayfinder` FIRST to chart the
unknowns as investigation tickets. Otherwise skip to step 1.

### Step 1 — Guided journey

Write the journey before any entity, table, endpoint or status graph is named:
who the actor is, where they arrive from, what the first screen shows, what the
system already knows, each step and its single decision, what they hold at the
end, what every other stakeholder is told automatically.

Optimise for the **fewest decisions the user must make**. Anything derivable from
something they already gave us is derived, never asked.

**A plan whose first section is a schema is rejected.** No skill does this step —
it is manual, and it is the one that protects the rest.

### Step 2 — Grill

- Domain surface involved (new terms, new entities, anything in a glossary) →
  `/grill-with-docs`. It challenges the design against `CONTEXT-MAP.md` and writes
  ADRs into `documentation/adr/` inline.
- Pure UX or flow question, no domain surface → `/grill-me`.

Resolve every branch of the decision tree before writing anything down.

### Step 3 — UAC, then plan

**UAC first — it is the contract.** Write
`documentation/plans/<domain>/<slug>-acceptance-criteria.md`: the journey at the
top as its `Journey` section, then independently-verifiable Given/When/Then ACs,
each with an id, grouped by phase, tagged `[BE]` / `[FE]` / `[E2E]` / `[T]`. Every
AC traces to a step in the journey.

**Then** the plan: `documentation/plans/<domain>/PLAN-<slug>.md`, the design that
fulfils the UAC. No plan ships without its UAC file.

`/to-spec` is useful for drafting both — but redirect its output to these two
files. Do not let it publish the spec as an issue. Its "testing seams" step
(step 2) is worth keeping: agree the seams before Phase 2 starts.

Defer-items go to `documentation/backlogs/backlog.md`.

### Step 4 — Review the plan

Render it with `/lavish` for the user to mark up, then `/grill-me` the plan
itself. Grill before code, always.

### Step 5 — Slice into tickets

`/to-tickets` — tracer-bullet vertical slices with blocking edges, published to
GitHub Issues on `jayson-odoo/sorento-crm`.

Each issue body must link its PLAN and UAC paths. Slice ids stay consistent with
the plan's own numbering (S0, S1, ...). Wide refactors use expand-contract rather
than vertical slices — `to-tickets` knows this shape.

### Step 6 — Phase 1: frontend-first, mocked

UI → hook → service → **mock**. No backend code. No tests yet — the shape may
still shift.

Tune every state: loading, empty, error, partial, success. Reuse before
inventing; a new variant is a prop on the shared component, never a parallel
one-off. Document the expected API contract at the top of the service file.

Verify in a real browser via Playwright MCP, navigating by **sidebar clicks from
`/`** — never a deep URL. Check `browser_console_messages`. Screenshot the golden
path and the edge cases. `browser_close` when done.

If the open question is "which of these three designs", run `/prototype` before
this step and **throw the result away** — it is not built to this repo's layering
rules and must not become the shipped FE.

### Step 7 — Phase 2: backend wiring, test-FIRST

Models → migration → schema → service → route, matching the Phase 1 contract
exactly. Then swap the mock for the real `api-client` call at the service
boundary.

**Red → green → refactor, not test-after.** Write the failing test, watch it fail
for the right reason, implement the minimum, refactor green. Applies to every
route (happy + auth-denial + validation), every service branch, and above all to
deterministic engines, whose golden-set numbers are written as failing tests
first.

`/tdd` drives this loop. `/implement` may drive a ticket end-to-end **at this
phase only**, and it calls `/tdd` internally.

Tests land here, never deferred to Phase 3: pytest, vitest, one Playwright E2E
per user flow (real clicks, FE→BE→DB). Re-verify live against the running stack.

Backend tests run on **Postgres only, never sqlite**.

### Step 8 — Phase 3: review

`/code-review` (this repo's own — `ultra` for big diffs), then `/simplify` or
`--fix` for the findings. The plugin ships its own `code-review`; prefer this
repo's unless the user asks otherwise.

Reviewer runs `documentation/reference/PR-CHECKLIST.md` plus the DoD gate.

### Step 9 — Definition of Done gate

A slice is not done until all pass (`PRINCIPLES.md`):

1. Mock swapped to real, verified showing real data
2. Existing rows backfilled
3. New permission → grant sweep for provisioned roles
4. New DB column reaches the FE (**both** manual dict builders)
5. Verified from the user's perspective — real sidebar clicks, real data, at
   **375px AND 1280px**

### Step 10 — Ship

Branch per feature; merge only after review. The user codes concurrently in the
main checkout — run `git status` before ANY branch or commit operation and never
assume the tree is clean. Hand off on a **prod build** (`npm run build && npm start`),
never a dev server.

## Skill map (quick reference)

| step | skill | executor |
| ---- | ----- | -------- |
| 0 scope unknown | `/wayfinder` | main session |
| 1 journey | manual — no skill | main session |
| 2 grill | `/grill-with-docs` (domain) or `/grill-me` (flow) | main session (user in loop) |
| 2b terms shifting | `/domain-modeling` | main session |
| 3 UAC + plan | `/to-spec`, output redirected to files | main session (plan mode) |
| 4 plan review | `/lavish` then `/grill-me` | main session (user in loop) |
| 5 tickets | `/to-tickets` | main session |
| 6 design options | `/prototype` (throwaway, before Phase 1) | main session |
| 6 Phase 1 FE mock | — | `coder` agent, worktree |
| 7 TDD | `/tdd`, or `/implement` scoped to Phase 2 | `coder` agent, worktree; tests may split to `tester` |
| 8 review | `/code-review` (this repo's), then optional `/codex-review` | `reviewer` agent + main session |
| bugs | `/triage` then `/diagnosing-bugs` | main session |
| periodic | `/improve-codebase-architecture`, `/codebase-design` | main session |
| context | `/handoff`, `/research` | main session |

## Related

- `PRINCIPLES.md` — the binding contract this skill executes
- `CLAUDE.md` — repo conventions, dev sessions, lessons learned
- `CONTEXT-MAP.md` — glossaries
- `documentation/agents/` — issue tracker, triage labels, domain doc rules
