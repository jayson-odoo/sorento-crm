# PLAN: CI-ZERO-MINUTES, GitHub Actions for build / deploy / rollback only (14 Nov 2026)

Status: plan only, waiting on the owner's OK (no code before it). Track: small fix (workflow + crew-side change, no
product code). Follows `PLAN-ci-secrets-env-14nov.md` (PR 1).

Owner goal (14 Nov): "I don't want to use github CI minutes at all", except build, deploy and rollback.

## Items (minutes from the 14 Nov CI audit, billed per month)

| # | Item | Today | Change | Saves |
| --- | --- | --- | --- | --- |
| 1 | PR gate | `ci` label runs `Changed areas` + `PR gate` (`lean-gate`) on a hosted runner, deploy.yml 364 / 1463 | Crew runs the same fast checks in the lane sandbox it already uses for `scripts/crew-tests.sh` and posts a commit status named `PR gate` on the head sha (precedent: the `release-sweep` status, deploy.yml 418-440) | ~17.3k |
| 2 | `pull_request` trigger | deploy.yml 43-46 (`types: [labeled]`), plus `refuse-ci-full` (2416) | Delete the trigger and the PR-only jobs and branches of `if:` | (part of 1) |
| 3 | Push-to-main alembic job | `check-migration-heads` on `push` (deploy.yml 10-12, 192) | Delete the `push` trigger; the alembic head check already runs in the PR gate (item 1) and in every release's `needs` | ~0.6k |
| 4 | Outline sync cron | `outline-user-guides-sync.yml` every 6 h + on push | Run the pull/push from crew's scheduler on the owner's machine (`scripts/sync_user_guides_outline.py`, same script); keep `workflow_dispatch` as a manual fallback | ~0.4k |
| 5 | tests-sharded | `tests-sharded.yml`, dispatch only | Leave the workflow for emergencies; crew stops dispatching it (the cloud release sweep replaces it) | ~3k |

## Owner actions (needed, crew cannot do them)

1. Ruleset `protect-main-branch`: the required check `PR gate` must accept a commit status from any source (not
   pinned to the GitHub Actions app), or crew's status never satisfies it. Settings > Rules > Rulesets >
   protect-main-branch > Require status checks > `PR gate` > source "Any source".
2. OK the move of the Outline sync token to crew's machine (it leaves GitHub's `outline-sync` environment from PR 1).

## Risks

- A crew-posted status is only as trustworthy as the token that posts it: use a fine-grained token limited to
  `statuses: write` on this repository, held by crew only.
- With no GitHub-run gate, a PR merged while crew is down has no `PR gate` status and cannot merge (fails closed).

## Order

Owner OK -> ruleset source edit -> crew posts `PR gate` statuses alongside the hosted run for one day (both visible) ->
delete the `pull_request` and `push` triggers -> move the Outline schedule -> stop dispatching tests-sharded.
