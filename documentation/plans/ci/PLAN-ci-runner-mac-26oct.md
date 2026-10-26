# PLAN: CI-RUNNER-MAC (bring the Mac mini runner back for a private repo)

Status: In progress (measure + rebuild + one test-only run). Track: small fix track (infra:
`scripts/ci-runner/`, no app code, no migration, no auth/RBAC, no ingest).

## Why

Owner, 26 Oct 2026 ~23:58: "I am switching the repo to private so can we fully use mac mini
runner to deploy?". A private repo bills GitHub-hosted minutes; a full-suite release was ~470
billed minutes (deploy.yml:60, release 38099410256).

## Facts (measured 26 Oct 2026)

- Repo `jayson-odoo/sorento-crm` is public (`gh api repos/...` -> `"private":false`).
  `scripts/ci-runner/up.sh:24` refuses to register a runner on a public repo.
- Runner `sorento-mac-1` (self-hosted, Linux, ARM64, sorento-mac) registered, offline.
  colima profile `ci` gone (`colima list`: no instance).
- Repo vars: `RUNNER_FAST=github`, `RUNNER_TESTS=github`.
- The last eight releases ran `full_suite=true` (release 40335490445 `Changed areas` log:
  `FULL_SUITE: true`): 26 jobs, ~208 job-minutes before per-job rounding.
- Mac: 16 GB, 10 CPU; swap 6.2 / 7.0 GB used, compressor 4.4 GB, load 8.2 with four crew test
  copies up (ports 3101/3104/3105/3110).

## Steps

1. Map every deploy.yml job to "can run on sorento-mac" or not, with file:line.
2. Prod CPU arch from the image manifest on Docker Hub (no ssh); cost of an amd64 build on arm64.
3. Size the VM against the Mac's measured memory; record `sysctl vm.swapusage` before/after.
4. Rebuild the VM with `up.sh` at that size; register once the repo is private (the guard stays).
5. One test-only run: `gh workflow run deploy.yml --ref crew/ci-runner-mac -f runner=mac`
   (build-images deploy.yml:1866 and build-and-deploy deploy.yml:1990 both require
   `refs/heads/main`, so a branch dispatch runs tests only).
6. Report: what can move, wall time vs GitHub, billed minutes left, risks, the exact var flips.

Crew flips repo vars after the owner OKs; this lane never sets RUNNER_* and never dispatches on main.
