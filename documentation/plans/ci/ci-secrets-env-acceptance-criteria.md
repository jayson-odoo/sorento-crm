# UAC: CI-SECRETS-ENV (14 Nov 2026)

Plan: `PLAN-ci-secrets-env-14nov.md`.

1. Every `secrets.X` in `.github/workflows/*.yml`, other than `GITHUB_TOKEN`, is read only by a job that declares an
   environment (`production`, `release-build` or `outline-sync`).
2. SSH_*, SMTP_*, OWNER_EMAIL are read only under `production`; DOCKER_* only under `production` or `release-build`;
   OUTLINE_* only under `outline-sync`.
3. Every job that declares an environment runs only on `refs/heads/main`; in a workflow with a `pull_request` trigger
   it also requires `workflow_dispatch`. No workflow uses `pull_request_target`.
4. `NEXT_PUBLIC_VAPID_PUBLIC_KEY` reaches the frontend build as a repository variable, not a secret.
5. A release (`deploy.yml` dispatch on main) builds, waits for the owner's `production` approval, deploys and mails as
   before; a rollback does the same; the Outline sync runs on push/schedule/dispatch from main.
6. After the owner deletes the repo-level copies, a branch with a modified workflow that echoes `secrets.SSH_PRIVATE_KEY`
   on `pull_request` or `push` gets an empty value, and a job of it that names `environment: production` or
   `release-build` is refused by the branch policy.
7. actionlint reports nothing new on the changed workflows.
