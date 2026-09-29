# PLAN: Pipeline rulings, 24 Sep 2026

Status: small fix track - in review

Docs-only change writing six owner rulings (taken in the main session, 24 Sep 2026) into the
governing process docs, so every future session and agent reads them without re-litigating.
Evidence: the last 35 merged PRs each took 30 min to 6 h from PR-open to merge, with 30 PRs
open at once (26 ready), 89 worktrees, 78 handoff files and 13 memory items waiting on a merge
go - the queue and the per-lane ceremony are the cost, not coding or review. No code, no tests,
no migration, no browser pass (nothing in the app changed).

## Rulings

- R1: Track is chosen by the diff, not by feel - under ~300 changed lines, no migration, no
  auth/RBAC/permission change, no new external ingest surface IS the small fix track.
- R2: `security-reviewer` runs only when the diff touches its surface (auth, RBAC, external
  ingest, uploads, multi-company scoping); otherwise skipped and the PR body says so.
- R3: `guide-writer` is retired from the per-lane pipeline; Outline updates run on-request or
  as a weekly batch instead.
- R4: Every PR body carries `Track: small-fix | full` and `Plan created: <ISO timestamp>` so
  lane duration is measurable alongside CI's own PR-open-to-merge time.
- R5: Post-merge cleanup (worktree removal, `.next` reclaim, private `*_ci` DB + redis index
  drop) is pre-authorised for the captain, subject to the two standing guards (grep `.env*`
  before `DROP DATABASE`; never touch a live process's cwd the captain did not start).
- R6: Model routing stands (orchestrator Fable, `coder`/`tester`/`triage` Sonnet,
  `reviewer`/`security-reviewer`/`planner` Opus) - noted as unchanged despite the `opus` alias
  now resolving to Opus 5.5 at `medium` effort.

## Files changed

`PRINCIPLES.md`, `CLAUDE.md`, `.claude/skills/feature/SKILL.md`, `.claude/agents/guide-writer.md`,
`documentation/reference/PR-CHECKLIST.md`.
