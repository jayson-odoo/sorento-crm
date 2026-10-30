# PLAN: CI-RUNNER-MAC (bring the Mac mini runner back for a private repo)

Status: Done. Owner approved; RUNNER_TESTS=mac + RUNNER_FAST=mac set 26 Oct 17:14Z; releases dispatch with `-f runner=github` unless crew says otherwise. Proof run 40359349579 green on sorento-mac-1. Track: small fix track (infra:
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
   (build-images deploy.yml:1866 and build-and-deploy deploy.yml:1991 both require
   `refs/heads/main`, so a branch dispatch runs tests only).
6. Report: what can move, wall time vs GitHub, billed minutes left, risks, the exact var flips.

Crew flips repo vars after the owner OKs; this lane never sets RUNNER_* and never dispatches on main.

## Findings (27 Oct 2026)

Repo went private 27 Oct ~00:25 (`gh api` -> `"private":true`). VM `ci` rebuilt with `up.sh`
at the same size, `sorento-mac-1` re-registered (`--replace`) and online, guard checked (runner
user: Mac `192.168.5.2:5432` blocked, `api.github.com` 200).

### Which jobs can run on sorento-mac

| Job | deploy.yml | On the Mac? |
| --- | --- | --- |
| Single alembic head, PII guard, Changed areas, ci-full refusal, CI gate | 180, 220, 351, 2198, 2243 | yes, `RUNNER_FAST=mac` |
| PR gate / Release tests (`lean-gate`), backend + SCM shards, vitest, type-check | 1431, 1152, 910, 1727, 1792 | yes, `RUNNER_TESTS=mac` |
| Validate backend / MCP imports | 708, 798 | no (hard-coded; full runs only, 707/797) |
| Build and push images | 1867 | no: amd64 only (1926/1941/1954) |
| build-and-deploy | 1996 | no: hard-coded, and needs SSH/Docker Hub/SMTP secrets |

Mac-routable jobs may hold no secret but the job token
(`sorento_crm_backend/tests/test_ci_runner_routing.py:238`), so moving the deploy is a policy
change, not a var flip.

### Image build on arm64

Prod is amd64: images are pushed `linux/amd64` only and the server runs them. On the arm64 VM
an amd64 build is QEMU user emulation:

- JS CPU proxy (node:20-alpine): 1.6 s native vs 12.4 s amd64 = 7.7x slower.
- backend image amd64, no cache: 327 s (GitHub builds all three in 7-9 min).
- frontend image amd64: `npm ci` 72 s, then `next build` OOM-killed at 424 s
  (`dmesg`: node anon-rss 4.9 GB). Not buildable in a 6 GiB VM.

### VM size and memory

4 CPU / 6 GiB unchanged: the floor is tsc's pinned 4096 MB heap (deploy.yml:1688) plus the job's
Postgres/Redis service containers; xdist stays 2 workers (PLAN-ci-mac-cap-18oct.md). One runner,
one job at a time; a second runner would need another 6 GiB the Mac does not have.

Mac swap (`sysctl vm.swapusage`, used): 6.08 GB VM off (00:06) -> 8.8-10.2 GB while the VM
built images -> 8.9-10.5 GB during the proof run (VM peak 2.6 GB used; other lanes moved too)
-> 13.4 GB at ~00:45 with the VM idle. The VM never hands touched memory back: its
`com.apple.Virtualization.VirtualMachine` process holds a 6,160 MB `phys_footprint` (`footprint
-p`) while the guest reports 650 MB used. Budget the full 6 GiB as a fixed cost while the VM is
up; `colima stop ci` (or a restart) is the only way to give it back.

### Proof run

Run 40359349579: `gh workflow run deploy.yml --ref crew/ci-runner-mac -f runner=mac`, success.
Every job that ran was on `sorento-mac-1`: Single alembic head 0.7 min, Changed areas 0.5 min,
Release tests 7.4 min (lean: core tier + the batch since release 36f571df3b). Wall 9 min
(16:27:46-16:36:39Z). Zero GitHub-hosted jobs; build-images and build-and-deploy skipped (not main).

Mac history (14-19 Oct, RUNNER_TESTS=mac): PR gate median 5 min, max 19 (257 runs); Release tests
8-19 min (11 runs). GitHub-hosted public 4-vCPU (23-27 Oct): PR gate median 4, max 35 (52 runs);
a lean release billed 41-46 min (Release tests 14-19, build 8-9, deploy 15-17).

### What to flip

- Tests + every fast gate to the Mac (no code change):
  `gh variable set RUNNER_TESTS --body mac --repo jayson-odoo/sorento-crm` and
  `gh variable set RUNNER_FAST --body mac --repo jayson-odoo/sorento-crm`.
  A lean release then bills only build-images (~8-9) + build-and-deploy (~15-17).
- A full-suite release puts 22 jobs on the Mac (2 fast gates, 3 SCM shards, 11 backend shards,
  5 vitest shards, the type-check; matrices at deploy.yml:917, 1182, 1748), run in series on one
  runner (~3 h; run 39126899668), and puts validate-backend/validate-mcp (708/798) back on
  GitHub-hosted. A release goes full on its own, without `full_suite=true`, when there is no
  earlier release or the lookup fails (504-505), the batch reaches the 300-file compare cap
  (557-560), or it touches tests/conftest.py or tests/_pg_fixture.py (564-566). Stop passing
  `full_suite=true`; for a full run, dispatch with `-f runner=github` (overrides both vars for
  that run: 406, 413-414, 418 and the fast-gate `runs-on` at 180/220/351/2198/2243; pinned by
  tests/test_ci_runner_routing.py:125, :164).
- build-images and build-and-deploy on the Mac need a workflow change, the routing pin tests
  changed, and the owner's OK to put SSH/Docker Hub/SMTP secrets on the Mac; a release whose
  frontend tree changed still cannot build its frontend image here (OOM above).
