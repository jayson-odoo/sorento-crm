# Handoff: chatbot media endpoint

**Branch:** `fm/multimodal-crm-endpoint` (worktree `/Users/tehjayson/.treehouse/sorento-crm-732336/4/sorento-crm`)
**Merge base:** `db607931` (tip of `main` at branch time)
**Head at time of writing:** `658c6dc0`
**Status file:** `/Users/tehjayson/Documents/foundryx/firstmate/state/multimodal-crm-endpoint.status`
**Design contract:** `documentation/plans/ideation/PLAN-chatbot-media-endpoint.md`

Nothing is pushed. Nothing is merged. Merging is explicitly not this task's job.

This document exists so the work can be picked up without replaying the transcript. It replaces
`/compact`, which is banned: if context runs tight, update this file and report blocked with its path.

## What the slice is

One CRM endpoint that gates, meters and performs voice transcription and image recognition for
chatbot contacts. n8n calls it once and waits. CRM half only, the n8n repo is out of scope.

The wire is synchronous, the execution is not: the handler commits the usage ledger inline, enqueues
to RQ, and awaits the result by polling through `asyncio.to_thread`.

## Where the work stands

Phases 0 through 2 are done and committed. Phase 3 review ran, produced three blockers, and all three
are fixed and committed. Section 16 of the PLAN records every finding and its resolution, including
the ones deliberately accepted as-is and why.

The three blockers, in short:

- **B1, the voice quota was never enforced.** `media_access_service.py` checked
  `settings.image_degraded_model` for both modalities, so a voice contact over quota fell into a
  degrade branch that had no voice model to degrade to. Fixed by giving voice its own
  `media_voice_degraded_model`, defaulting to NULL, and wiring `job.tier` into `_extract_voice`.
  Image ships seeded because its tiers were measured (PLAN 14.1); voice ships unseeded because they
  were not. NULL means hard refusal, not silent degradation.
- **B2, the settings error state was unreachable.** `isLoading || !draft` was evaluated before
  `isError`, so the error Alert could never render. Fixed, and the coder improved on the brief by
  guarding as `isError && !draft` so a failed background refetch does not discard operator edits.
- **B3, no frontend tests on a slice with four [FE] acceptance criteria.** 25 vitest tests added
  across `page.test.tsx` and `ContactMediaAccessSection.test.tsx`. The B2 regression was
  mutation-tested: revert `page.tsx` to the buggy ordering, watch the test fail with the exact
  symptom, restore, confirm zero diff.

PLAN section 16.7 records a self-correction worth keeping: 16.1 justified the NULL default as being
"one setting away", but at the time no UI control existed, so the claim was false when written. A
control was added (`446b9c36`) to make it true.

## Regression attribution: SETTLED, zero regressions

**Result: 119 failures are pre-existing, 4 are branch-only and none of them can be this branch's
doing, 0 are baseline-only.** The 35 files that own the 123 branch failures were run on branch
(`123 failed, 355 passed`) and on `db607931` (`119 failed, 359 passed`), same database, same
invocation, collected 478 on both sides.

Each of the 4 branch-only failures was run down to cause. All four exercise code that is
byte-identical between the two commits (`git diff db607931..HEAD` empty for `app/services/scm/`,
`audit_service.py` and the audit route, `ticket_intake_service.py`, and for the four test files
themselves), so causation is impossible except through shared state. Two are golden-set SCM tests
where 4 of the same 6 SKUs already fail at the merge base; one reads its own row back from an audit
endpoint that pages at 50 while every other lane writes to the same table; one expects a raise in a
file whose sibling tests already fail identically on both sides.

They are flaky tests inside already-failing suites, not clean passes. The supportable claim is the
narrow one: this branch did not cause them.

The baseline had to be chunked into 6 runs to survive machine memory pressure while the branch ran
as one invocation. That asymmetry only inflates the branch-only count (more isolation makes baseline
tests more likely to pass), so it cannot hide a real regression.

The full write-up is in `documentation/plans/ideation/PR-BODY-chatbot-media-endpoint.md`.

## How that attribution was reached (method, kept for the next person)

The branch full-suite number is `123 failed, 6038 passed, 9 skipped, 13 xfailed` and it has been
reproduced twice independently. The question that remains is how many of those 123 this branch caused.

Artifacts live in the session scratchpad under `.../scratchpad/testrun/`:

| File | What it is |
|------|------------|
| `branch_full.log` | full serial suite on branch, complete |
| `branch_failed_ids.txt` | the 123 FAILED lines |
| `branch_failed_clean.txt` | same, `- reason` suffixes stripped, sorted, for diffing |
| `targeted_files.txt` | the 35 unique files those 123 ids live in |
| `branch_targeted.log` | those 35 files on branch: `123 failed, 355 passed` |
| `baseline_full.log` | **discarded.** 196 errors, a broken environment, not a result |
| `baseline_targeted.log` | the run that closes this out |

What is already established:

- All 123 reproduce with only their 35 files selected, so they are deterministic rather than
  ordering or contention artifacts.
- No media test appears among the 123.
- All 35 files exist at `db607931`, so the baseline selection has no missing-file skew.
- The failure texts read like the documented "CI database has no data" class in CLAUDE.md
  (`assert 4 == 1`, `assert 0 == 1`, SCM golden sets), which points at pre-existing data dependence.

The baseline run that closed this out was the same 35 files, same invocation, same database, in the
baseline worktree:

```
cd <scratchpad>/baseline_worktree/sorento_crm_backend    # already checked out at db607931
DATABASE_URL=postgresql://sorento_crm:...@localhost:5432/sorento_ai_automation \
  venv/bin/python -m pytest $(tr '\n' ' ' < <testrun>/targeted_files.txt) -q -p no:randomly \
  > <testrun>/baseline_targeted.log 2>&1
```

It takes about 23 minutes. Then diff `branch_failed_clean.txt` against the baseline FAILED set and
report three sets: failing in both (pre-existing), branch-only (the number that matters),
baseline-only (fixed or flaky). A branch-only id is not reportable as an id: open it, read the
assertion, and say whether it plausibly touches this diff (media endpoint, media settings columns,
migrations 358/359, `queue_service` socket timeouts).

**Why targeted alone is not enough on its own, and why it is enough here.** A test can fail in a full
run and pass in isolation, so a targeted baseline can show "passes on baseline" for something that
also fails on baseline in a full run, manufacturing a regression this branch never caused. That risk
is retired in this case because the branch targeted run reproduced all 123 exactly, which means the
selection is not masking ordering effects on either side.

## Rules that constrain whoever picks this up

- **Do not touch the shared dev database `sorento_ai_automation`** beyond running tests, which roll
  back their own transactions. No dumps, restores, drops, DDL, or `alembic_version` changes. Other
  worktrees use it concurrently. A prior agent ran `pg_dump`/`pg_restore` against it in violation of
  this; the database was verified intact afterwards (283 tables, users 3142, customers 6397,
  orders 30939, `alembic_version` unchanged) and the incident is logged in the status file.
- **Do not reset any user's password to manufacture a browser login.** The local database is a copy
  of production.
- **Never quote a suite number that cannot be attributed.** A contaminated baseline is worse than no
  baseline because it invents regressions.
- Browser verification uses `npx -y agent-browser`. `chrome-devtools-axi` is dead (Chrome
  uninstalled) and Playwright is not to be used.
- Never run `/compact`. Update this file instead.
- **Every FE production build takes a machine-wide lock.** Parallel Next builds drove machine load
  to 80 across the fleet. `flock` does not exist on this macOS box, so use the mkdir spin-wait, and
  the `trap` is mandatory rather than tidiness: a build that dies without releasing the lockdir
  wedges every other lane indefinitely.

  ```bash
  while ! mkdir /tmp/fm-fe-build.lockdir 2>/dev/null; do sleep 30; done
  trap 'rmdir /tmp/fm-fe-build.lockdir 2>/dev/null' EXIT
  npm run build
  ```

  This bites at handoff, since handing off to the user requires a prod build. Vitest and pytest are
  explicitly fine unserialised; do not serialise test runs. If the spin-wait blocks far longer than
  a build should take, check for a live `next build` process before assuming the lockdir is stale.

## Browser sign-off: DONE (2026-08-15)

The captain provided a browser-verification login as `E2E_EMAIL` / `E2E_PASSWORD` in the clone at
`/Users/tehjayson/Documents/foundryx/firstmate/projects/sorento-crm/sorento_crm_frontend/.env.local`
(gitignored, values never printed). Both operator surfaces were signed off against a production
build on this lane's ports (backend 8020, frontend 3021), reached by clicking rather than by deep
URL. The full account is in the PR body under "Browser sign-off of the two operator surfaces",
including the failed-load state, which was verified by stopping the backend.

Practical notes for anyone repeating it:

- Use an isolated browser session (`AGENT_BROWSER_SESSION=<name>`, or `--session`). The default
  session is shared, and another lane's run pulled the page to its own port mid-verification.
- Set the viewport first (`agent-browser set viewport 1400 1600`) and scroll the target into view.
  A click on an element below the fold reports success and does nothing, which reads exactly like a
  dead handler and cost real time before it was pinned down.
- The login helper is `<session scratchpad>/ablogin.sh <url>`. The email input is `name=email`, not
  `type=email`.

## Known unmet, not to be papered over

- **A persisted Playwright spec for the two operator surfaces.** The interactive sign-off is done;
  a committed regression spec is not written.
- **RQ worker end-to-end against the `queue_service` socket-timeout change** is unverified.
- **No corpus re-run through the changed voice path** after the B1 fix.

## Pre-existing defect found, deliberately not fixed

`alembic upgrade head` is broken repo-wide from a true base: no migration creates
`conversation_sla_tracking`, yet three migrations reference it (008, `241_sla_takeover_requests`,
`portal_rev_0001`). Verified by `grep -c "create_table\(['\"]conversation_sla_tracking"` across
`alembic/versions/` returning 0. Migration 008 dates to 2026-01-27 and the merge base is the tip of
main, so this predates the branch by a wide margin. It is hidden in practice because
`tests/_pg_fixture.py` builds schema with `Base.metadata.create_all()`. Out of scope here (300+
migrations), and not filed as an issue because filing is outward-facing and firstmate's call.

This branch's own four migrations were verified for real, not assumed: schema built at merge base,
stamped `885010d94677`, all four run forward, DDL and seeds and grants checked by direct query, all
four downgraded, then re-upgraded and re-verified. 193 media tests then passed against
migration-produced DDL rather than `create_all` DDL.

## What is left

1. ~~Write the PR description.~~ Done: `documentation/plans/ideation/PR-BODY-chatbot-media-endpoint.md`,
   covering all four things the definition of done requires it to state - the measured
   `lock:{contact}` decision and its evidence, spine resume (checked, and the answer is no), the
   corpus results, and the entity-hint question (answered, Option A, not outstanding).
2. Append `done: {summary}` to the status file.
3. Run `/no-mistakes`. Avoid `--yes`, which would bypass firstmate's authority check.
4. Do not merge.

Opening the PR itself is left to firstmate rather than done here: it is outward-facing, and the body
is ready to paste. `gh-axi` is the tool if firstmate wants this seat to do it.

An ask-user finding is never this seat's to answer. Escalate to firstmate and stop.
