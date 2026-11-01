# Mac mini CI runner (`sorento-mac`)

One self-hosted GitHub Actions runner, `sorento-mac-1` (labels
`self-hosted, Linux, ARM64, sorento-mac`), registered to
`jayson-odoo/sorento-crm` only. Since CI-MAC-ONLY (1 Nov 2026, repo private,
3,000 GitHub-hosted minutes a month) every CI job runs here: the PR gate, the
release tests and shards, `outline-user-guides-sync.yml` and
`never-stuck-nightly.yml` (`runs-on: [self-hosted, sorento-mac]`, no fallback
to GitHub-hosted; a busy or offline runner queues the job). Image builds, the
deploy and `rollback.yml` stay on GitHub-hosted (prod is amd64). See the note
above `jobs:` in `.github/workflows/deploy.yml`.

After pulling a change to `provision.sh` (CI-MAC-ONLY added chromium's
libraries for the never-stuck smoke), run `REGISTER=0 scripts/ci-runner/up.sh`
once.

## Layout

- colima VM `ci`: 4 CPU, 6 GB RAM, 16 GB root disk. No Mac directory is
  mounted and no VM port is forwarded to the Mac.
- The runner is the VM user `runner` (no sudo, not in the docker group) and
  its Docker is rootless, so a job, even in a `--privileged` container, never
  gets root in the VM.
- `ci-guard.nft` (systemd `ci-guard.service`, loaded before the network, and
  the runner does not start without it): everything the runner user opens,
  its rootless Docker's network included, reaches the internet only. The Mac
  (lima's `192.168.5.2` is the Mac's localhost: dev Postgres, lane servers),
  the LAN and the tailnet are dropped, and on the VM itself only loopback
  and DNS are open. The VM's own root processes are not limited; no job runs
  as root.
- A job's Postgres/Redis service containers publish 5432/6379 on the VM's
  localhost. `job-started.sh` empties the runner's Docker at the start of
  every job.
- One runner: a 6 GB VM holds one type-check (4 GB heap) or one xdist shard,
  not two.
- No image builds here: an amd64 build on this arm64 VM is QEMU emulation
  (measured 27 Oct 2026: backend image 5.5 min, frontend `next build`
  OOM-killed in the 6 GB VM). See `documentation/plans/_archive/ci/PLAN-ci-runner-mac-26oct.md`.

## Commands (on the Mac)

```bash
scripts/ci-runner/up.sh                     # install / after an edit here: VM, provision, register once, start
REGISTER=0 scripts/ci-runner/up.sh          # provision only
colima ssh -p ci -- sudo systemctl stop sorento-runner    # stop taking jobs (a running job is cancelled)
colima ssh -p ci -- sudo systemctl start sorento-runner   # take jobs again
colima stop ci                              # stop everything, frees the VM's memory (up to 6 GB)
colima start ci                             # start again; guard, Docker and runner come back by themselves
colima ssh -p ci -- sudo journalctl -u sorento-runner -f  # runner log
gh api repos/jayson-odoo/sorento-crm/actions/runners --jq '.runners[] | [.name, .status, .busy] | @tsv'
```

## More runners on the same Mac (crew decides; not running today)

Today there is ONE runner, so a release's jobs and matrix shards run one after
another (a full-suite release queues about 15-19 jobs; the last full release on
the Mac, run 40745728050, used about 133 runner-minutes). Each extra runner is
**its own colima VM**, never a second runner in the `ci` VM: `job-started.sh`
empties the runner user's whole Docker at every job start (it would kill the
other job's Postgres and Redis), every test job publishes 5432/6379 on the VM's
localhost (the second job's containers would fail to bind), and 6 GB holds one
xdist shard or one tsc, not two.

Cost per extra runner, on the Mac: 4 vCPU, 6 GB RAM (`--memory 6`, held while
the VM is up), 18 GB disk (16 root + 2 data). Check the Mac's headroom first
(`sysctl -n hw.ncpu hw.memsize`; the Mac mini also runs the dev stack: dev
Postgres, lane servers, the one `next dev`). Two runners total = 8 vCPU / 12 GB
for CI, three = 12 vCPU / 18 GB, more vCPUs than a 10-core Mac has, so runs slow
each other down under load. Throughput is roughly runner-minutes / runners: the
133-minute release above takes about 70 min on two runners, about 45 on three.
GitHub-hosted minutes do not change (only build-images and build-and-deploy
bill).

Add runner N (2, 3), from the repo root on the Mac. A copy of `up.sh` that
only renames the VM profile and the runner, so the same provisioning,
firewall, rootless Docker and private-repo check apply. It sits next to
`up.sh` because `up.sh` copies its own directory into the VM; not piped into
`bash -s`, because the script's `colima ssh` calls would read the rest of it
from stdin:

```bash
N=2
cd scripts/ci-runner
sed -e "s/^profile=ci$/profile=ci-$N/" -e "s/sorento-mac-1/sorento-mac-$N/g" up.sh > "up-$N.sh"
bash "up-$N.sh"; rm -f "up-$N.sh"
gh api repos/jayson-odoo/sorento-crm/actions/runners --jq '.runners[] | [.name, .status, (.labels | map(.name) | join(","))] | @tsv'
# expect sorento-mac-N  online  self-hosted,Linux,ARM64,sorento-mac
```

It registers with the same `sorento-mac` label, so jobs spread across every
online runner with no workflow change. Start it at login with its own launchd
agent (the `ci` one starts only the `ci` VM):

```bash
sed -e "s/colima-ci/colima-ci-$N/g" -e "s|<string>ci</string>|<string>ci-$N</string>|" \
  my.foundryx.colima-ci.plist > ~/Library/LaunchAgents/my.foundryx.colima-ci-$N.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/my.foundryx.colima-ci-$N.plist
```

Stop taking jobs without removing it: `colima stop ci-$N` (frees its 6 GB).
Remove for good: delete `sorento-mac-N` under Settings > Actions > Runners,
`launchctl bootout gui/$(id -u)/my.foundryx.colima-ci-$N`, `colima delete ci-$N`.
After a `provision.sh` change, rerun the same two lines with `REGISTER=0 bash
"up-$N.sh"` for each extra VM too.

Start at login: copy `my.foundryx.colima-ci.plist` to `~/Library/LaunchAgents/`
and `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/my.foundryx.colima-ci.plist`.

Remove for good: delete `sorento-mac-1` under the repo's Settings > Actions >
Runners, `launchctl bootout gui/$(id -u)/my.foundryx.colima-ci`, then
`colima delete ci`.
