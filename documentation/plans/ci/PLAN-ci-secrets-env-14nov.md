# PLAN: CI-SECRETS-ENV, no secret reachable from a pull_request run (14 Nov 2026)

Status: built, PR open (draft), waiting on the owner's environment setup. Track: small fix (workflow-only, no
migration, no product code), security review required.

UAC: `ci-secrets-env-acceptance-criteria.md` (alongside).

## Problem

Every Actions secret is repository-level and the `production` environment holds none. A `pull_request` run of a
same-repo branch, and a `push` to any branch, execute THAT branch's copy of the workflow file, so whoever can push a
branch can add a step that reads a repo secret. The `if:` lines in main's copy of `deploy.yml` protect nothing.

## Secret map (names only, file:line at the base of this lane)

| Secret | Kind | Used by (job) | Moves to |
| --- | --- | --- | --- |
| DOCKER_USERNAME, DOCKER_PASSWORD | secret | deploy.yml validate-backend (762), validate-mcp (853), build-images (2034), build-and-deploy (2197); rollback.yml rollback (81) | `release-build` AND `production` (both need them); the validate legs drop their login |
| SSH_HOST, SSH_HOST_B, SSH_USER, SSH_PRIVATE_KEY, SSH_KNOWN_HOSTS | secret | deploy.yml build-and-deploy (2225-2315); rollback.yml (102-144) | `production` |
| SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD | secret | deploy.yml build-and-deploy (2381-2404); rollback.yml (203-225) | `production` |
| SMTP_PORT | config (kept a secret: same step reads it with the others) | same | `production` |
| OWNER_EMAIL | config, but personal data: kept a secret so it is masked in logs | same | `production` |
| OUTLINE_API_TOKEN | secret | outline-user-guides-sync.yml sync (90) | `outline-sync` |
| NEXT_PUBLIC_VAPID_PUBLIC_KEY | config (public key, inlined into the browser bundle) | deploy.yml build-images (2083) | repository VARIABLE (`vars.`) |
| APP_PORT | unused (no workflow reads it) | none | delete |

`OUTLINE_BASE_URL` / `OUTLINE_COLLECTION_ID` are read as optional secrets with a default (sync.yml 91-92) and are not
set today; they stay optional in `outline-sync`.

## Change

1. `build-images` declares `environment: release-build` (new; deployment branch policy main only, no reviewer), so it
   still builds before the owner approves `production`.
2. `build-and-deploy` and `rollback` keep `environment: production` (owner approval, main only).
3. `validate-backend` / `validate-mcp` lose their Docker Hub login: they run on a merge-queue entry or a non-lean
   dispatch from any ref, which a main-only environment cannot serve. Pulls there are anonymous (rare runs, gha cache).
4. Outline `sync` declares `environment: outline-sync` (main only, no reviewer) and `if: github.ref == 'refs/heads/main'`.
5. The VAPID key build-arg reads `vars.NEXT_PUBLIC_VAPID_PUBLIC_KEY`.
6. No job that runs on `pull_request` reads any secret (none did on main's copy; the lock now holds for a modified
   copy too, because the environments refuse a non-main ref).

Guard: `sorento_crm_backend/tests/test_workflow_secret_scoping.py` (every `secrets.X` sits in an environment job, each
only in the environment that holds it, environment jobs are main-only, VAPID is a variable).

## Order (owner)

Create the two environments and enter the values -> merge -> verify one release (and one Outline sync) -> delete
the repo-level copies. Until the deletion, the repo copies stay as a fallback (an environment secret overrides a repo
secret of the same name). The exact clicks are in the PR body.

## Follow-up

PR 2 (plan only, owner OK needed): `PLAN-ci-zero-minutes-14nov.md`.
