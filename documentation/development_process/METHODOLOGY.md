# Development Methodology (detailed how-to)

The governing contract is `PRINCIPLES.md` → Methodology. This document is the expanded reference:
the fused Sorento three-phase loop + the FoundryX shared-service UAC-first / Definition-of-Done /
agents-team governance. On any conflict, `PRINCIPLES.md` wins.

## The order (mandatory, every non-trivial feature)

```
grill-me (FE + BE)  →  UAC file (FIRST)  →  PLAN  →  Phase 1 (FE mock)
                                                   →  Phase 2 (BE + tests, swap mock→real)
                                                   →  Phase 3 (code review)  →  PR
```

### 0. Grill → UAC → plan

- **Grill first.** Run `grill-me` on the design — frontend AND backend — until the full decision
  tree is resolved. Then **grill the plan itself** before writing code (don't implement straight
  from decisions).
- **UAC written FIRST**, before the plan: `documentation/plans/<domain>/<slug>-acceptance-criteria.md`.
  Per-AC id, Given/When/Then, grouped by phase, tagged `[BE]`/`[FE]`/`[E2E]`/`[T]`. This is the
  contract; self-verify FE AND BE against every UAC line end-to-end before handoff.
- **Then the plan** (`PLAN-<slug>.md`) as the design that fulfils the UAC, with a live `Status:`
  line and a decision log. Deferrals → a row in `documentation/backlogs/backlog.md`.

### Phase 1 — Frontend prototype (mock)

UI → hook → service → **mock**. Tune every state (loading / empty / error / partial / success)
with no backend running. Verify in a real browser via Playwright MCP — **navigate by clicking the
sidebar from `/`, never a deep URL** (deep-URL nav hides menu-gating bugs). Document the expected
API contract at the top of the service file or in the plan. NO backend code, NO tests yet (shape
may still shift after prototype review). Reuse shared components — a new variant is a prop on the
shared component, never a parallel one-off.

### Phase 2 — Backend wiring + tests

Build BE (models → migration → schema → service → route) to match the Phase-1 contract exactly.
Then swap the mock for the real `api-client` call — a one-line change at the service boundary.
**Tests land here, never deferred:**

- **vitest** — every new component's states + every new query/mutation hook.
- **pytest** — every new route (happy path + auth denial + validation error) + service-level logic.
- **Playwright E2E** — one spec per user flow, **real clicks**, exercising FE→BE→DB; assert the
  right `/api/v1/*` call fired (`browser_network_requests`). AI/file/portal flows use **real
  committed fixtures** in `e2e/fixtures/`, not stubbed mocks.

Re-verify live against the running stack (3000 / 8000 / worker). Write the **test report**
(`<slug>-test-report.md`) keyed back to the UAC ids: PASS / FAIL / DEFERRED per id.

### Phase 3 — Code review

`/code-review` (or `ultra` for big diffs) → address via `--fix` / `/simplify` → open the PR.
Reviewer runs `documentation/PR-CHECKLIST.md` + the DoD gate + hard-fail rules.

## Definition of Done gate

A slice is NOT done until all pass (full list in `PRINCIPLES.md`): mock swapped to real + verified
on real data · backfill migration for existing rows · new-permission grant sweep · new column
reaches the FE (both manual dict builders) · verified from the user's perspective at 375px AND
1280px on a fresh `rm -rf .next && npm run build`. Tests green ≠ user-verifiable.

## Agents-team orchestration (quality lever as the codebase grows)

Building a slice with a subagent team held quality far better than solo. The Sorento agent roster
(`.claude/agents/`): **planner → coder → tester → reviewer**, looped on findings.

- **Audit first.** An `Explore` agent producing a per-AC gap matrix (backend exists? FE exists /
  mock / missing?) before any coder runs surfaces the mock / backfill / permission gaps early.
- **Every subagent brief MUST embed** the DoD gate + hard-fail rules from `PRINCIPLES.md` — a
  subagent starts with zero project memory; the brief is its only guardrail.
- **Sequential coders on a shared branch** when tasks touch overlapping files (parallel same-tree
  edits race). Worktree isolation only when tasks are file-disjoint.
- **Tester verifies from the USER's perspective** (real clicks, real data, fresh build) and writes
  the AC-id-keyed report — not just green pytest. The reviewer re-checks the DoD gate, not only
  correctness.

## Why this order

- **Prototype first** stops building a backend for a UI the user rejects — UX disagreements surface
  against a clickable mock, not a deployed feature.
- **Tests in Phase 2, not Phase 3** — once the contract is locked, wiring is the right time to pin
  it; tests added after review are rushed.
- **Review last** — reviewing a mocked FE in isolation says nothing about end-to-end data flow.
