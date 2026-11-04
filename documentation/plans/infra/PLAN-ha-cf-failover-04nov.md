# PLAN: HA failover with Cloudflare Load Balancing as the witness (HA-CF-FAILOVER)

Status: Review (base, PR #2166); active-active app tier in build on the follow-up PR #2170 (section 12). Card answered 4 Nov (section 8). F1-F4 built (controller, adapter, drill, templates, two-node release); security + correctness review round 1 fixed (section 11); owner options in section 9. F5-F8 are owner phases (runbook).
Track: full (prod infra, size L), LEAD pattern. Nothing in this lane touches production: every prod
step goes to the owner as reviewed commands.

Builds on HA plan v2 (`PLAN-ha-tier1-n8n-box-27oct.md`, PR #1915) and the n8n retirement plan
(`PLAN-n8n-decom-ha-01nov.md`, PRs #2063, #2065). Rules as there: no addresses, hostnames, keys or
staff names in the repo; UNVERIFIED marks every fact not checked from the repo.

## 0. Owner rulings this plan applies

- Active-passive warm standby; both boxes in Malaysia; AUTOMATIC failover; no switchback
  preference, "the load balancer at Cloudflare decides" (1 Nov, Q4).
- NEW 4 Nov 14:45: **no witness server**. "Cloudflare load balancing will act as witnesser to check
  the status of each endpoints." Owner buys Cloudflare Basic Load Balancing: USD 5/month, 2
  endpoints, 1 check region, health check every 60 s, traffic steering off.
- Node A = CRM box, node B = the n8n KVM 8 box (rebuilt from a fresh OS after n8n stops, 1 Nov Q3).

## 1. What the new ruling breaks in the current design

The 1 Nov design is Patroni + a 3-voter etcd (node A, node B, witness) (`PLAN-n8n-decom-ha-01nov.md:204-210`,
`infra/templates/patroni/patroni.yml:25-48`). With no witness there are 2 voters: etcd quorum is 2 of
2, so losing EITHER node stops all automatic promotion. That is worse than no HA for the case HA
exists for (node A dies: node B alone has no quorum and can never promote). Patroni cannot be told
to use Cloudflare as its quorum. So:

- **Drop Patroni and etcd** for this 2-node setup. Use plain Postgres streaming replication
  (A -> B), WAL-G archiving to R2, and a small failover controller of our own on each node
  (`infra/scripts/cf_failover.py`, section 3) that uses the Cloudflare LB health API as the
  third vote. Prod was never adopted into Patroni (H4 is still an owner window that has not run,
  `PLAN-n8n-decom-ha-01nov.md:184`), so nothing on prod has to be undone.
- Kept from the earlier work: `GET /api/v1/health/role` (`sorento_crm_backend/app/main.py:737-762`),
  the scheduler leader guard (`app/scheduler/leader.py:53-91`), the role watcher idea
  (`infra/scripts/role-watcher.sh`, re-pointed from Patroni's `/primary` to the local Postgres role),
  the deploy's HA preflight (`scripts/blue_green_deploy.sh:65-80`, `:233-245`), WAL-G to R2
  (`infra/templates/walg.env.example`), the host prep (`infra/templates/host/`).
- Retired (deleted in the build PR): `templates/patroni/`, `templates/etcd/`,
  `templates/witness/`, `templates/ha-members.env.example`, the witness parts of
  `templates/host/*.nft`, the etcd service in `templates/compose.ha.yml:66-76`, `infra/rehearsal/`
  (rewritten for the new controller), etcd checks in `infra/scripts/ha-checks.sh`.

## 2. How the two boxes stay synchronised (the owner's question)

| # | What | How, with evidence |
|---|---|---|
| 1 | App code | One release, one image tag, both boxes. Today the release ships one SHA-tagged image set (`.github/workflows/deploy.yml:2197-2204` promotes `<svc>-${GITHUB_SHA}`) and runs `IMAGE_TAG=<sha> blue_green_deploy.sh` on ONE host (`deploy.yml:2206-2247`, `secrets.SSH_HOST`). Change: a second host secret and the same two steps against node B, PRIMARY FIRST (migrations run only there), standby second with `SKIP_MIGRATIONS=1` and no snapshot/worker steps (`templates/compose.ha.yml:43-52` already passes `SKIP_MIGRATIONS`). The deploy asks each host its role (`/api/v1/health/role` locally), so "primary first" follows whichever box leads. Migrations stay expand-only, so the standby's old colour can run against a schema one release ahead for the minutes between the two steps. A failover in the middle fails the deploy; re-run it. |
| 2 | Database | Postgres 17 streaming replication A -> B (async; `synchronous_commit` remote_write once measured RTT < 2 ms, Q5), replication slot on the primary with `max_slot_wal_keep_size` (`patroni.yml:61` value carried over) so a dead standby never fills the primary's disk. WAL-G archive to R2 from whichever node is primary (`archive_mode=on`, `archive_command`, `archive_timeout=60`, carried from `patroni.yml:62-64`). Promotion only by the controller (section 3). Never two writable DBs: the old primary FENCES ITSELF before the standby may promote, and comes back read-only (`pg_rewind`, else re-seed with `pg_basebackup`). Needs `wal_log_hints=on` (pre-flight 1 Nov: off, `PLAN-n8n-decom-ha-01nov.md:179`): one restart of node A's Postgres in an owner window. |
| 3 | Files / uploads | Already shared: every upload is an object in S3 or R2, routed per row (`app/services/storage_router.py:7`, `:108`, `:311`; CLAUDE.md "Storage routing"). The only local volume the backend writes is `backend_logs` (`sorento_crm/docker-compose.yml:74-77`), not business data. Pre-migrate dumps (`blue_green_deploy.sh:442`) stay per node; the PITR copy is WAL-G in R2. Nothing to sync. UNVERIFIED: the prod compose (not in git) mounts nothing else; the build PR checks it from the captured compose. |
| 4 | Config / secrets | Same `.env`, `.deploy.env`, compose, nginx on both, one copy each in the private infra repo (`infra/README.md:14-37`), per-node only: the node name and its WireGuard address. `FIELD_ENCRYPTION_KEY`, `JWT_SECRET`, `NEXTAUTH_SECRET` MUST be byte-identical (encrypted secrets and sessions break otherwise; CLAUDE.md "Env quick reference"). A check script compares hashes of the env files across the link (prints only names that differ, never values) and runs in `ha-checks.sh` daily. |
| 5 | Schedulers, workers, senders | No Celery here: jobs are RQ queues (`worker.py`) plus one APScheduler in the `worker` container (`worker.py:82`, `app/main.py:432`). Both start ONLY on the primary: the role watcher starts `worker` + `worker_fast` (compose profile `promoted`, `templates/compose.ha.yml:57-64`) only where the local Postgres is not in recovery, stops them every tick elsewhere (`role-watcher.sh:99-129`); the scheduler refuses on a replica and holds an advisory lock (`leader.py:53-91`). WhatsApp (respond.io) sends run on the `respond_io` RQ queue (`app/tasks/respond_io_tasks.py`), so only on the primary. The chatbot inbox sweeper runs in every API process (`app/main.py:416-421`) but claims each turn with a DB write before it sends (`app/services/chatbot/inbox_queue.py:558-571`, send stamped at `:728` before the POST at `:731`): on the read-only standby the claim fails, so it never sends. Email: `app/services/notification_email.py` is called from request handlers and jobs; the standby gets no traffic from the LB and has no workers. FE `services/send-email.ts` only runs on a request. The n8n-replacement jobs (PRs A-G of the decom plan) are scheduler or RQ jobs, so they inherit this. On promotion the role watcher starts the workers within `INTERVAL x CONFIRM` = 10 s. |
| 6 | Redis / queues | Redis stays local per node, not replicated (v2 decision, `PLAN-ha-tier1-n8n-box-27oct.md:179-183`, `:339-345`). At failover the dead node's queued RQ jobs are lost: import rows left queued/processing are failed by the orphan reconcile (`app/scheduler/task_scheduler.py:82-86`) for a retry; chatbot turns are Postgres rows and are drained again by node B; staff sessions are Postgres rows (`user_sessions`), so users stay signed in. Redis-only state that resets: rate-limit counters, the per-contact drain mutex (safe: only one node sends). |
| 7 | Cloudflare LB | Section 4. |
| 8 | Blocked vs buildable now | Section 6. |

## 3. The failover controller (`cf-failover`), Cloudflare as the third vote

`infra/scripts/cf_failover.py` (Python 3 stdlib only), the same on both nodes, a systemd service
beside the role watcher. The decisions are one pure function (`decide(state, observation, now,
config)`), unit-tested without Postgres or Cloudflare; every side effect goes through one adapter,
`infra/scripts/ha-pg.sh` (role, LSNs, streaming, peer role, promote, fence, start as standby,
rewind or re-seed, synchronous standby names, prune), which the container drill exercises for real.

Each tick (`TICK`, 15 s) it observes:

1. **CF**: the Cloudflare API's view of each pool (`GET .../load_balancers/pools/{id}/health`,
   token scoped to Load Balancing: Read on this account only). Per node: healthy, unhealthy, or
   UNKNOWN (API unreachable, error, no answer for the pool).
2. **Peer**: the other node's Postgres over the private link: primary, standby or unreachable,
   and its WAL position.
3. **Self**: the local Postgres: primary, standby or down; streaming (primary: the peer is in
   `pg_stat_replication` as `streaming`; standby: `pg_stat_wal_receiver` is `streaming`); WAL
   position; current `synchronous_standby_names`.

Windows are seconds of continuous state (state file survives a controller restart), never tick
counts. Clocks are NTP-synced (`ha-checks.sh` alerts otherwise). Config, all env, defaults derived
from the Cloudflare check so a faster plan needs one change:

| Name | Default | Meaning |
|---|---|---|
| `CF_CHECK_INTERVAL`, `CF_CONSECUTIVE_DOWN` | 60 s, 2 | what the LB monitor is set to (owner Q1) |
| `FENCE_AFTER` | `2 x interval x down` = 240 s | primary's lease |
| `PROMOTE_AFTER` | `FENCE_AFTER + max(180, 3 x interval)` = 420 s | standby's wait; refused at start unless >= `FENCE_AFTER + FENCE_MARGIN` (180 s) |
| `APP_SICK_AFTER` | 900 s | Q3: Cloudflare-unhealthy primary with a healthy standby fences itself |
| `APP_SICK_COOLDOWN` | 86400 s | at most one app-sick fence per node per day (no ping-pong on a broken monitor) |
| `FENCE_HOLD` | `PROMOTE_AFTER + 180` = 600 s | a fenced node stays down this long unless the peer is primary |
| `REJOIN_AFTER` | 120 s | standby not streaming from a reachable primary this long: rewind / re-seed |
| `BOTH_STANDBY_AFTER` | 60 s | both nodes standby and reachable: the one further ahead promotes |
| `MAX_LAG` | 16 MB | a standby further behind the primary's last seen position never promotes |
| `SYNC_MODE` | `off` | Q5: `remote_write` once A-B RTT < 2 ms |
| `RESEED_KEEP_DAYS` | 7 | Q4: moved-aside data directories older than this are deleted |

**Rules.** Primary (P), standby (S), Postgres down (D):

- **P1 lease**: writable while Cloudflare reported it healthy within `FENCE_AFTER` OR the peer is
  streaming from it now. Both false for `FENCE_AFTER`: **fence** = stop Postgres FIRST (workers
  cannot write without it), write `standby.signal` (any later start, even a manual one, is
  read-only), then stop the workers with a 5 s grace; bounded at 60 s, well inside the 180 s
  margin. The lease is renewed ONLY by a Cloudflare-healthy report, a streaming peer, this
  controller's own promotion, or the first tick it ever runs; never by a fence or a `down`
  reading. A primary that still reads primary after a fence re-fences every tick and stops
  petting the watchdog, so a fence that does not take ends in a reboot (review B1, B2).
- **P2 app sick (Q3)**: Cloudflare positively reports it UNHEALTHY for `APP_SICK_AFTER` while the
  peer streams from it (a standby is there to take over) and it has not app-sick-fenced in
  `APP_SICK_COOLDOWN`: fence, alert. During those 15 minutes autoheal restarts unhealthy containers
  (`templates/compose.ha.yml:13`).
- **P3 two primaries** (never expected): alert; fence itself unless Cloudflare reports it healthy;
  if Cloudflare reports BOTH healthy, the node with the higher name fences.
- **P4 sync standby (Q5)**: with `SYNC_MODE` on, `synchronous_standby_names` = the peer while it
  streams, empty the moment it stops; with it off, always empty. Set only on change.
- **P5 slot**: the primary recreates the peer's replication slot whenever it is missing or lost
  (`max_slot_wal_keep_size`), so the standby can always stream into it.
- **S1 promote**: all of these held continuously for `PROMOTE_AFTER`: Cloudflare positively reports
  the peer UNHEALTHY (UNKNOWN never counts, so a Cloudflare API outage never promotes); this node
  is not streaming; the peer's Postgres is unreachable. And this node's WAL position is within
  `MAX_LAG` of the peer's last seen position (else alert, no promotion). Then `pg_promote()`,
  create the peer's replication slot, alert.
- **S2 rejoin**: the peer is primary and this node has not streamed from it for `REJOIN_AFTER`:
  `pg_rewind` onto the peer; if that fails, move the data directory aside and `pg_basebackup`
  (Q4), alert. A second rejoin with no streaming in between goes straight to the re-seed. A failed
  copy deletes the partial directory and puts the old one back.
- **S3 both standby**: both reachable and in recovery for `BOTH_STANDBY_AFTER` (after a double
  reboot or a crash): the node with the higher WAL position promotes; on a tie the lower node name.
  The rule is deterministic, so exactly one wins.
- **D1 not fenced** (boot, crash, watchdog reboot): start Postgres AS A STANDBY, always. A node
  never comes up writable by itself; S1 or S3 decide who writes.
- **D2 fenced**: peer primary: rejoin (S2's path), then standby. Otherwise wait `FENCE_HOLD`, then
  start as a standby if the peer is a standby (S3 then picks) or the peer is unreachable and
  Cloudflare has reported it unhealthy for `PROMOTE_AFTER` (S1 then applies).

Why there can never be two writable databases: S1 needs `PROMOTE_AFTER` of "Cloudflare says the
peer is unhealthy, no stream, peer unreachable". Over that time the peer's P1 lease conditions
were also false (no Cloudflare-healthy report, nobody streaming), and `PROMOTE_AFTER` exceeds
`FENCE_AFTER` by at least 180 s, so the peer fenced itself first. That rests on the peer's
controller running: a hung controller stops petting the watchdog (softdog, `templates/host/`) and
the box reboots, and D1 brings it back read-only. Every other path that starts Postgres starts it
as a standby.

| Fault | What happens |
|---|---|
| Node A box dead / network dead | CF: A unhealthy; B: no link. A is gone (or fences after 240 s if only its network died). B promotes 420 s after Cloudflare first reports A down. |
| Link A-B cut, both reachable from Cloudflare | CF says A healthy, so A keeps writing and B never promotes. Alert (no replica). |
| Cloudflare API down | UNKNOWN: B never promotes. A keeps writing while B streams; if the link is also down, A fences after 240 s (safe side: outage, no split brain), and after `FENCE_HOLD` and the link back, S3 hands the write role to the node further ahead. |
| A's app down, DB fine (Q3) | autoheal restarts it; still Cloudflare-unhealthy after 15 min: A fences (P2), B promotes 420 s later. |
| Cloudflare monitor misconfigured | at most one app-sick failover per node per day, alerting each time; never two writers. |
| Both nodes reboot (power) | D1: both come up standby; S3: the one further ahead promotes after 60 s. |
| A comes back after a failover | D2 / S2: rewind or re-seed, follows B. No switchback. |

### 3c. The old primary comes back

D2 then S2: it never starts writable. It rewinds onto the new primary's timeline
(`pg_rewind --source-server ... --write-recovery-conf`); if the rewind fails, the data directory
is moved aside to `<PGDATA>.old-<UTC timestamp>` in the same volume (not deleted; kept
`RESEED_KEEP_DAYS`, 7) and `pg_basebackup -R` copies the primary; an alert goes out either way
(Q4). Commits the old primary acknowledged but never streamed are discarded by the rewind (async:
normally under a second; at most `MAX_LAG`; with `SYNC_MODE=remote_write` none while both ran).
Disk: a re-seed holds two copies of the database for up to 7 days (about 54 GB each today,
`PLAN-n8n-decom-ha-01nov.md:179`); `ha-checks.sh` alerts on disk and the owner can prune early.

## 4. Cloudflare LB configuration

- One load balancer on the public host (`fe-sorento...`; the only public CRM hostname found in the
  repo, `deploy.yml:2150`; the API is behind the same host's nginx). Two pools, one endpoint each:
  `node-a`, `node-b`. **Steering off = failover order**, not round robin and not random: the standby is
  read-only and must never get traffic while the primary is healthy. Default pool order A, B;
  fallback pool B. Because only the primary answers 200, the order is only a tie-break.
- Monitor: HTTPS `GET /api/v1/health/role`, expect 200, Host header = the public host, interval
  60 s (bought plan), retries 1, timeout 5 s, consecutive down 2, consecutive up 1. `/health` is
  answered by nginx itself, so the monitor must use the `/api/v1/...` path (`PLAN-ha-tier1-n8n-box-27oct.md:379-381`).
- After a failover node A answers 503 (stopped, then replica) so traffic never flaps back.
- **DNS-only (grey cloud)**, as the owner chose on 3 Nov: the LB answers DNS with the healthy
  node's address, TTL 30 s (UNVERIFIED: the LB's DNS-only TTL is set on the LB, 30 s is the
  documented default). Clients and resolvers that cache longer keep hitting A until they re-resolve.
  Each node must then hold its OWN valid TLS certificate for the public host: node B cannot pass an
  HTTP-01 challenge while DNS points at A, so both nodes use a DNS-01 challenge (Cloudflare API token,
  Zone DNS: Edit on this zone only) or the owner copies the cert. Proxied (orange) would move traffic
  without waiting on DNS caches and hide origin addresses, but the owner turned it off on purpose:
  Q2 asks whether to keep DNS-only.
- **Expected failover time (node A dies), 60 s checks, DNS-only:** Cloudflare marks A unhealthy
  after 2 failed checks, 60-120 s; B promotes `PROMOTE_AFTER` (420 s) after the first unhealthy
  report; Cloudflare marks B healthy at its next check, 0-60 s; DNS caches expire, 30 s+. Total
  about **8-11 minutes**. The 420 s is the safety margin that 60 s checks force (the primary must be
  sure it is fenced before the standby can be sure). With 15 s checks (add-on) the windows shrink
  to 60/240 s (the 180 s fence margin is a floor) and the total to about 5 minutes (corrected 4 Nov; the card said 3-4). respond.io retries webhooks for about 3
  minutes; messages from the gap are backfilled by the chat-history reconcile
  (`app/scheduler/task_scheduler.py:347`, `PLAN-n8n-decom-ha-01nov.md:55`) once node B runs the
  scheduler. Q1 asks which interval.

## 5. PR-sized steps

| # | Step | Who | Blocked on n8n leaving B? | Size |
|---|---|---|---|---|
| F1 | This plan + UAC; delete the Patroni/etcd/witness templates and rehearsal; amend the 1 Nov plan section 5 and `documentation/runbooks/ha-failover.md` | lane | no | S |
| F2 | `infra/scripts/cf_failover.py` + `ha-pg.sh` (+ watchdog pet) and tests with fake curl/psql/pg_ctl (pattern of `infra/tests/test_ha_scripts.py`); role watcher reads the local Postgres role instead of Patroni's `/primary`; `compose.ha.yml` back to the stock Postgres image with replication settings | lane | no | M |
| F3 | Drill on two throwaway containers in CI-less local docker (`infra/rehearsal/`): fake Cloudflare API (a tiny HTTP stub the drill flips), primary + standby Postgres 17, synthetic data. Drills: kill A, cut link only, CF API down, A returns (rewind), app-down-DB-up, controller hung (fence by watchdog simulated) | lane | no | M |
| F4 | Deploy to two hosts: `deploy.yml` second host, role-aware order, standby with `SKIP_MIGRATIONS=1`; `blue_green_deploy.sh` standby mode (no snapshot, no workers); env-hash check in `ha-checks.sh` | lane | no (node B secret added later) | M |
| F5 | Node A prep in an owner window: `wal_log_hints=on`, `archive_mode=on` + WAL-G to R2, replication user + slot, pg_hba for B's link address, softdog. One Postgres restart (about 1 minute) | owner commands | no | 0.5 d |
| F6 | Node B: fresh OS, edge rules, WireGuard to A, CRM compose, `pg_basebackup` from A, controller + role watcher, TLS cert by DNS-01 | owner commands | **yes** (n8n stopped, 14-day stop over, Q3 of 1 Nov) | 1 d |
| F7 | Cloudflare LB + monitor + API tokens (read LB, DNS-01) | owner | yes (needs B serving) | 0.5 d |
| F8 | Prod drills (planned kill of A in a window, link cut, A return) | owner + crew | yes | 1 d |

Can start now: F1-F4 (repo only), F5 (node A only, an owner window). The prod drill waits for B.
F2-F3 make the controller provable before any prod box runs it.

## 6. Risks

- **Clock and controller trust**: the fence-before-promote order rests on both controllers running
  and NTP. Watchdog + `ha-checks.sh` clock check + the 180 s margin. Drilled in F3.
- **Failover is slow on 60 s checks** (about 8-11 min). Faster needs the paid check interval.
- **DNS caching** beyond TTL (some resolvers, long-lived clients) keeps sending to A after a
  failover; A is fenced, so those requests fail rather than write to the wrong DB.
- **Async replication** loses the last un-streamed commits of a crashed primary (normally < 1 s).
- **Malaysia-wide outage**: both nodes down; off-site restore from R2 by a human (v2 section 11).
- Cloudflare LB behaviour figures (DNS-only TTL, all-pools-down fallback) are UNVERIFIED from this
  sandbox; F7 checks them on the dashboard.

## 7. Owner card (posted as `crew-ask` on the lane PR, 4 Nov)

Q1-Q5 below; answers recorded in section 8.

1. Health check interval: (a) 60 s as bought, failover about 8-11 min; (b) 15 s add-on, about 3-4 min. Rec (a) now, (b) later if the drill time is too slow.
2. Cloudflare mode: (a) stay DNS-only (3 Nov), TTL 30 s, each node its own cert by DNS-01; (b) proxied. Rec (a), owner's own choice; failed-over clients only need re-resolving.
3. App down on A but DB fine and B can still see A: (a) after 15 min of Cloudflare-unhealthy A fences itself and B promotes; (b) never automatic, page the owner, autoheal only. Rec (b): a DB move for an app fault adds risk with no gain, the same image runs on B.
4. Old primary returns and rewind fails: (a) automatic re-seed from the new primary (`pg_basebackup`, A's old data moved aside, not deleted); (b) stay stopped and page the owner. Rec (a), with the old data kept 7 days.
5. Replication: (a) async now, synchronous (remote_write) once the measured A-B RTT is under 2 ms; (b) async only. Rec (a): closes the "last second of commits" loss on a fast link; the controller drops the standby from `synchronous_standby_names` the moment it stops streaming, so a dead standby never blocks writes on the primary.

## 8. Owner answers (crew, 4 Nov, from the owner rulings of 27 Oct, 1 Nov, 4 Nov)

Standing rulings: AUTOMATIC failover, self-maintaining, never propose manual promotion as the
default, re-seed the old primary automatically.

- **Q1 (a) 60 s checks** (owner, 4 Nov). The interval and the failure count stay config values
  (`CF_CHECK_INTERVAL`, `CF_CONSECUTIVE_DOWN`) and every window derives from them. The owner expected
  "instant" failover because the LB routes between the 2 endpoints; section 9 answers that.
- **Q2 (a)** DNS-only, TTL 30 s, a DNS-01 certificate on each node.
- **Q3 (a), not the recommendation (b)**: automatic. For 15 minutes autoheal restarts containers;
  if A is still Cloudflare-unhealthy after that, A fences itself and B promotes. 15 minutes is a
  config value (`APP_SICK_AFTER`). Rule P2.
- **Q4 (a)** automatic re-seed with `pg_basebackup`, old data moved aside and kept 7 days, alert.
- **Q5 (a)** async now; `remote_write` synchronous once measured RTT < 2 ms; the standby is
  dropped from `synchronous_standby_names` the moment it stops streaming. Rule P4.

## 9. What the owner sees, and two options (owner follow-ups, 4 Nov)

### 9a. Today vs after this plan, per failure case

Today everything (frontend, backend, workers, Postgres, Redis) runs on box A; box B runs n8n.
After this plan both boxes run the same stack; only the box whose Postgres is primary runs workers
and the scheduler, and Cloudflare sends every user to that box.

| Case | Today | After this plan (60 s checks, DNS-only) |
|---|---|---|
| App crash on A (backend or frontend container, DB fine) | autoheal / Docker restarts it, about 30-60 s of errors; a deploy is already zero-downtime blue/green (`scripts/blue_green_deploy.sh`) | the same restart first. If A is STILL Cloudflare-unhealthy after 15 min (`APP_SICK_AFTER`), A fences itself and B promotes about 7 min later: users are on B about 22-23 min after the fault. Option 9b would make this case cost nothing |
| Whole box A down (power, kernel, host, network) | the CRM is down until the box is back or someone restores from backup (hours) | down for about 8-11 min: Cloudflare marks A down (1-2 min), B promotes (7 min after that), Cloudflare marks B up (up to 1 min), DNS caches expire (30 s+). Drill: B primary 17 s after A died on the 1 s / 2 s scaled timings. Option 9c serves read-only pages during those minutes |
| A comes back | n/a | A starts read-only, rewinds onto B (or re-seeds, keeping its old data 7 days) and follows B. Users stay on B. No switchback, no human step |
| Only the A-B link breaks | n/a | nothing changes for users; alert |
| Cloudflare API down | n/a | nothing changes; no failover can start while it is down; alert |

### 9b. Option: active-active APP tier, one primary database

Both boxes run the app and Cloudflare sends users to both (steering "random" instead of "off");
B's app reads and writes the primary database on A over the private link. An app crash or a bad
container on one box then needs no database move at all.

What it really takes (evidence):

- **Health check**: the monitor moves from `/api/v1/health/role` (503 on B by design,
  `sorento_crm_backend/app/main.py:737-762`) to `/api/v1/health` (app + its DB connection,
  `main.py:707-733`), so both boxes can be healthy at once.
- **DB and Redis must follow the primary on BOTH boxes**: the API enqueues RQ jobs into its own
  Redis (imports, respond.io sends, catalogue renders; CLAUDE.md "Worker is required"), and
  workers run only on the primary box. A job enqueued on B's local Redis would never run. So B's
  app needs A's Redis AND A's Postgres over the link, and the controller must re-point both boxes'
  pgbouncer and Redis URL at a promotion (a new moving part: today nothing re-points).
- **Chatbot sweeper**: it runs in every API process (`main.py:416-421`) and orders a contact's
  turns with a Redis mutex (`chatbot:drain:{contact}`, `app/services/chatbot/inbox_queue.py:382`). With B's API writing to
  the primary, two sweepers on two Redis instances could send one contact's replies out of order;
  the sweeper must be gated to the primary box (or share A's Redis).
- **Sessions/auth**: already fine: staff sessions are Postgres rows (`app/services/user_session_service.py:92-127`),
  NextAuth cookies need only the same `NEXTAUTH_SECRET`; uploads are in S3/R2. No sticky sessions.
- **Background jobs**: unchanged, primary only (role watcher, `leader.py`).
- **Page times on B**: every query from B's app crosses the link. Extra time per page = sequential
  DB (and Redis) round trips x A-B RTT. The RTT is NOT measured yet (node B still runs n8n); owner
  command, read-only: `ping -c 100 <B private address>` from A (or the public address until
  WireGuard exists). For scale: a page doing 30 sequential queries costs +30 ms at 1 ms RTT
  (same data centre), +150 ms at 5 ms (two Malaysian data centres). Half the users (those Cloudflare
  sends to B) pay it on every page; writes pay it too.
- **"Instant" needs proxied mode.** In DNS-only (the owner's 3 Nov choice) Cloudflare only hands
  out an address; a browser that resolved box A keeps using it until its cache expires. With A's
  app down, those users get errors until Cloudflare marks A down (2 x 60 s) plus the 30 s TTL:
  up to about 2.5 min, active-active or not. Only in PROXIED mode does Cloudflare itself connect to
  the box and, on a connection failure, retry the request on the other endpoint at once (Cloudflare
  "zero-downtime failover" / adaptive routing; documented for proxied load balancers only,
  UNVERIFIED from this sandbox: https://developers.cloudflare.com/load-balancing/understand-basics/adaptive-routing/).
  It does not retry an HTTP 500 from a running but broken app.

**Recommendation: NO for now.** Effort about 3-5 lane-days (re-pointing DB + Redis on promotion,
sweeper gating, monitor change, a second drill set), plus a permanent latency cost on half the
traffic, and in DNS-only it still is not instant (about 2.5 min for users pinned to the bad box).
The app-crash case today is already covered by autoheal (about 1 min) and blue/green deploys.
Trigger to revisit: the owner switches the record to proxied (then the retry makes app faults
near-instant), or the measured RTT is under 1 ms and app-level outages show up in the incident log.

### 9c. Option: read-only pages during the promotion gap (whole-box loss)

While A is down and B has not promoted yet (about 7-9 minutes), Cloudflare has no healthy pool
and answers with the fallback pool, B (Cloudflare's documented behaviour, UNVERIFIED here). B's
app already runs against its hot-standby replica, so lookups and lists work today; every save
fails with Postgres' read-only error and the user sees a generic error.

What a clear "saving paused" mode needs:

1. Backend: one exception handler mapping Postgres SQLSTATE 25006 (`read_only_sql_transaction`)
   to HTTP 503 `{"code": "saving_paused"}` (next to the global handlers in `app/main.py`).
2. Backend: the session touch commits on a 10-minute throttle (`user_session_service.py:115-127`);
   on a replica that commit fails and would sign every user out during the gap. Skip the touch
   (rollback, carry on) on a read-only error. Login itself writes a session row, so NEW sign-ins
   still fail during the gap (shown as "saving paused").
3. Frontend: `lib/api-client` turns `saving_paused` into one banner, "Saving is paused, back in a
   few minutes", instead of per-form errors.
4. Inbound webhooks (respond.io) get the 503 and retry for about 3 minutes; later messages are
   backfilled by the chat-history reconcile once B is primary (section 4).
5. Tests: pytest for the handler + session touch against a read-only transaction; vitest for the
   banner; one drill step.

**Recommendation: YES.** About 1 lane-day (small fix track: no migration, no auth model change,
under 300 lines), and it turns 7-9 minutes of "the CRM is broken" into "you can look things up,
saving is paused". Trigger-free: it helps from the day node B exists. Separate lane after this one.

## 10. Drill results (container drill, 4 Nov)

`python3 infra/rehearsal/cf_drill.py`: two throwaway Postgres 17 containers, a fake Cloudflare API,
the real controller and adapter on each node, windows scaled to seconds (tick 1 s, check 2 s,
fence 8 s, promote 14 s, app-sick 20 s). Result on this branch after review round 1:

| Scenario | Result |
|---|---|
| steady state + sync standby | PASS: A primary, B streaming, `synchronous_standby_names` = crm-b |
| link cut only | PASS: no failover; sync standby dropped within `wal_sender_timeout`, writes kept working |
| Cloudflare API down | PASS: no failover |
| node A dies | PASS: B primary 18 s after A died; A came back read-only and follows B |
| primary isolated | PASS: B fenced itself at 11 s, A promoted at 18 s (fence first), B rewound and follows |
| app sick + damaged data | PASS: A fenced at 25 s, B primary at 40 s, rewind failed, A re-seeded, old data kept aside |
| both nodes reboot | PASS: one writer back, the other follows |
| both reboot, link down | PASS: only the former standby took over; the other rejoined |
| never two writers | PASS: 0 of about 1000 samples |
| acknowledged writes | NOTE: 14 of 304 lost, all written to the ISOLATED primary in the drill (its writer reaches the box through Docker, not the network) during the seconds before it fenced; a real isolated box has no users, only its own workers |

Finding for prod: with `SYNC_MODE=remote_write`, a cut link sends no reset, so the primary keeps
waiting on the dead standby until `wal_sender_timeout` (default 60 s): writes stall that long before
P4 drops the standby. Prod sets `wal_sender_timeout` and `wal_receiver_timeout` to 10 s.

## 11. Review round 1 (4 Nov)

Security review: B1 the pg_hba catch-all (superuser reachable over the link) replaced by a full
`templates/postgres/pg_hba.conf` mounted outside PGDATA (S1: a rewind no longer copies the peer's);
S2 watchdog armed only by completed ticks and a failing controller fences its own node; S3 the
two-node release pins SSH host keys (secret `SSH_KNOWN_HOSTS`); nits N1, N3, N4.
Correctness review: B1 a failed fence or a `down` reading no longer renews the lease; B2 the fence
stops Postgres first, is bounded at 60 s, kills its whole process group and never pets the
watchdog; should-fix: `standby.signal` on fence, clock steps back keep elapsed time, peer query
timeouts, P5 slot, rejoin escalation and failed re-seed cleanup, P3 tie-break. Tests for each, in
`infra/tests/` (the two-node world model now also fails fences at random and models the watchdog).

Review round 2 (verification of round 1): one blocker left and fixed: `ha-pg.sh observe` printed
`down` when `exec psql` failed with the container still running, so a primary whose Docker exec
wedged while cut off took the D1 path and never fenced; it now prints `unknown` (a failed tick:
fence after `FENCE_AFTER`, else the watchdog). Also: the runbook's manual promotion stops the
controller first (a controller fences a node it did not promote), a warning never to stop the
controller on the primary alone, a test for the fence retry, and the two-node release checks the
public URL from the runner. Reviewer kill tests on the B1 lease rule all went red.

Review round 3 (the observe change after round 2): "no response" from `pg_isready` now reads
`unknown` (an overloaded but writable primary times out pg_isready; reading it as down brought
the round-2 blocker back); "rejecting connections" reads `down` only when `pg_controldata` says
the cluster is in crash or archive recovery or starting up (a smart shutdown also rejects new
connections while old sessions keep committing: `unknown`); a D2 rejoin clears `fenced_at`, so a
slow standby start that reads down is not rejoined again as a full re-seed.


## 12. Active-active app tier (owner decision 4 Nov about 17:15, follow-up PR #2170)

Owner: "i want active active". This overrides section 9b's "no" for the APP tier only. There is
still exactly ONE writable database and ONE Redis master. Built for DNS-only, the owner's 3 Nov
choice; section 12d gives the proxied numbers for the owner.

**Ruling interaction, no card needed.** Requirement (6), "a node whose app is unhealthy drops out
of the pool with NO DB failover", supersedes Q3 (a), the app-sick failover. In active-active mode
P2 is off: `APP_SICK_AFTER` defaults to 0, and the controller refuses to start with any other
value. The reason: the other node now serves the same database, so moving the database fixes
nothing for an app fault.

### 12a. How each requirement is met

| # | Requirement | How (evidence) |
|---|---|---|
| 1 | Both nodes serve behind the LB; health check per node | ONE Cloudflare pool with both nodes as origins (steering inside the pool: random; LB-level steering stays "off", one pool). The monitor stays `GET /api/v1/health/role` (`sorento_crm_backend/app/main.py:737-762`): 200 only when THIS node's app reaches a writable database. Cloudflare checks it per origin. The controller reads its own origin's health from the pool health API (`CF_ORIGIN_SELF` / `CF_ORIGIN_PEER`, `infra/scripts/cf_failover.py` `cf_pool_health`; the per-origin shape is UNVERIFIED, phase 3 checks it) |
| 2 | One writable DB, each backend reaches the CURRENT primary through a local endpoint that follows the role | Each node's pgbouncer is its app's only database endpoint. Rule **R1** (`decide()`): on the primary node the target is `local`; on the other node it is `peer`, and only while the peer answers as primary, never a guess. `ha-pg.sh route` rewrites `route/route.ini` (a `%include` in `templates/active-active/pgbouncer.ini`), then runs pgbouncer `RELOAD` and `KILL` + `RESUME` of the app database, so every client and server connection reconnects through the new target in ANY pool mode. In session mode the app's pooled connections are never released, so `RECONNECT` alone would leave a connection pinned to a running standby (review round 2). A route change never moves away from the writable primary, so the dropped connections were doing no useful writes. `server_login_retry = 2`, because pgbouncer otherwise refuses clients for 15 s after the old primary's failed logins. pgbouncer KEEPS prod's `pool_mode`: the app holds session-level advisory locks that transaction pooling would break (security F1). A route repair that only fixes Redis's role does not touch pgbouncer. An unreadable Redis ROLE alerts |
| 3 | One Redis, used by both nodes; jobs/schedulers/senders only on the primary | The primary node's Redis is the master; the other node's is its replica (the same `route` switches roles, Redis FIRST so a returning node never writes to its stale Redis). Each node's app reaches Redis only through a local HAProxy (`templates/active-active/haproxy-redis.cfg`) that sends every connection to whichever Redis answers `role:master`. So one queue, one set of locks (the chatbot drain mutex `chatbot:drain:{contact}`, `app/services/chatbot/inbox_queue.py:382`), one idempotency store (`app/middleware/idempotency_middleware.py`), one rate-limit store. Workers + scheduler: role watcher, unchanged (`infra/scripts/role-watcher.sh`; `app/scheduler/leader.py:53-91`). The chatbot sweeper runs in both nodes' API processes but claims each turn with a database write before it sends (`inbox_queue.py:558-571`, send `:731`) and serialises per contact through the shared Redis mutex: no double sends |
| 4 | Uploads/files shared, existing files included | Already object storage. Every attachment row names `s3` or `r2` (`app/services/storage_router.py:108`, `:311`). Imports carry a storage key, not a local path (`app/tasks/import_tasks.py:642`, download `:730`). Exports upload their result (`app/tasks/export_tasks.py`, 15 storage calls, no local file). Temp files exist only inside a single task (`attachment_bulk_download_task.py:81`, `dealer_kit_export_tasks.py:97`). The only local volume is `backend_logs`. Existing files: a read-only owner query (runbook phase AA, step 0) confirms no row points at a local path |
| 5 | Sessions/auth on either node | Staff sessions are Postgres rows resolved per request (`app/services/user_session_service.py:92-127`), now in the one primary. NextAuth's cookie needs only the same `NEXTAUTH_SECRET` on both (the env hash check in `ha-checks.sh` alerts on drift). No sticky sessions. Per-process caches already exist across gunicorn workers and blue/green colours, so a second node adds no new class of staleness |
| 6 | Unhealthy app leaves the pool, NO DB failover; only a primary DB/box loss promotes | P2 off (above). An app fault on the primary node: Cloudflare marks its origin down, but the standby still streams, so the P1 lease holds and S1 never fires. Drill: app down on A, then on B: no fence, no promotion, the other node served |
| 7 | Added latency for pages served from B | Section 12c (measured) |
| 8 | DNS-only vs proxied | Section 12d |

### 12b. What changes in the failure picture (DNS-only, 60 s checks)

| Case | Active-passive (sections 3, 9a) | Active-active |
|---|---|---|
| App crash on one node | autoheal; after 15 min the DB fails over (Q3) | that origin leaves the pool after 2 checks (60-120 s). Users whose DNS answer named it see errors until then plus up to 30 s TTL; everyone else is unaffected. No DB move |
| Whole primary box down | about 8-11 min to B | the same promotion path (the DB is gone): about 8-11 min until B is primary. B's own origin is unhealthy meanwhile, because its app cannot reach the dead primary. After promotion R1 points B's pgbouncer at itself and B's Redis becomes master |
| Whole standby box down | nothing (it had no users) | its origin leaves the pool (60-120 s + TTL for users pinned to it); no DB effect |
| Link A-B cut | nothing | the standby node's origin leaves the pool (its app cannot reach the primary); no failover |
| Old primary returns | rejoins as standby | rejoins as standby, R1 routes it at the new primary, and it serves again |

Redis, accepted risks (review):
- **Async replication.** Redis replication is asynchronous: a primary-box loss drops the
  jobs, idempotency keys and rate-limit counters written in its last moments. A POST retried
  after a failover may run twice. Job rows that were queued or processing are failed by the
  orphan reconcile for a retry (section 2 row 6).
- **Two masters for up to one tick.** A Redis that restarts (host reboot, container recreate)
  comes back a MASTER, because no `replicaof` is persisted. Until the controller's next tick
  repairs it from Redis's real ROLE (R1 checks the role, not only the route file), the HAProxy on
  that node prefers it: up to one tick (15 s) of split Redis on the standby node. The same holds
  for a fenced old primary's Redis until its next tick.
- **Job pickles.** RQ jobs are pickled (`app/services/queue_service.py:52-57`), so anyone who can
  push to the master's queues runs code on the primary's workers. Before active-active only node
  A's own containers could reach A's Redis; now node B's containers can too. The ACL (`users.acl`)
  takes away reconfiguration and wiping, not pushing jobs. Accepted residual risk, bounded by the
  DOCKER-USER rules (only the CRM compose network crosses the link).

Constraint the drill found: a newly promoted primary's lease starts at the promotion, so its
origin must turn Cloudflare-healthy within `FENCE_AFTER`. In prod that is 240 s, against a route
switch (one tick, 15 s) plus `server_login_retry` (2 s) plus one Cloudflare check (up to 60 s).

### 12c. Measured: added latency for requests served from node B

`infra/rehearsal/measure_roundtrips.py` signs in for real and counts every round trip to Postgres
(statements, psycopg2's implicit BEGIN, COMMIT/ROLLBACK, the pool's pre-ping on checkout) and to
Redis, per request: each one crosses the link when node B serves. The run was on a throwaway
database built by `scripts.bootstrap_env` + `scripts.seed_never_stuck_smoke`, 4 Nov, warm second
calls, admin persona, Redis reachable. It is a LOWER bound:
- list endpoints that run per-row queries cost more on real data;
- a NEW server connection over the link (after a re-point or `server_lifetime`) adds TCP plus
  SCRAM round trips once.
Re-run it on a staging copy for prod-shaped numbers. (The first table, before review, missed
BEGIN/COMMIT/pre-ping and read about 3 too low per request.)

| Request | HTTP | SQL | Redis | local ms | +ms at 0.5 ms RTT | +ms at 1 ms RTT | +ms at 2 ms RTT | +ms at 5 ms RTT |
|---|---|---|---|---|---|---|---|---|
| `/api/v1/health/role` | 200 | 4 | 0 | 8 | 2 | 4 | 8 | 20 |
| `/api/v1/my-requests/me` | 403 | 10 | 0 | 19 | 5 | 10 | 20 | 50 |
| `/api/v1/notifications/coverage/for-me` | 200 | 12 | 0 | 23 | 6 | 12 | 24 | 60 |
| `/api/v1/order-management/customers/?page=1&limit=20` | 200 | 16 | 0 | 41 | 8 | 16 | 32 | 80 |
| `/api/v1/order-management/customers/select` | 200 | 15 | 0 | 34 | 8 | 15 | 30 | 75 |
| `/api/v1/order-management/orders/?page=1&limit=20` | 200 | 12 | 0 | 37 | 6 | 12 | 24 | 60 |
| `/api/v1/order-management/orders/analytics` | 422 | 10 | 0 | 19 | 5 | 10 | 20 | 50 |
| `/api/v1/master-data/products?page=1&limit=20` | 200 | 12 | 0 | 32 | 6 | 12 | 24 | 60 |
| `/api/v1/complaints-management/complaints/?page=1&limit=20` | 200 | 12 | 0 | 29 | 6 | 12 | 24 | 60 |
| `/api/v1/forms-management/forms/?page=1&limit=20` | 200 | 12 | 0 | 32 | 6 | 12 | 24 | 60 |
| `/api/v1/inventory/stock-position?page=1&limit=20` | 200 | 17 | 0 | 41 | 8 | 17 | 34 | 85 |
| `/api/v1/inventory/stock/dashboard` | 200 | 15 | 0 | 42 | 8 | 15 | 30 | 75 |
| `/api/v1/procurement/purchase-requests?page=1&limit=20` | 200 | 12 | 0 | 29 | 6 | 12 | 24 | 60 |
| `/api/v1/procurement/grn/?page=1&limit=20` | 200 | 12 | 0 | 29 | 6 | 12 | 24 | 60 |
| `/api/v1/incoming-stock/list?page=1&limit=20` | 200 | 10 | 0 | 22 | 5 | 10 | 20 | 50 |

Reading it:
- A typical authenticated GET makes 10-17 SEQUENTIAL database round trips (median 12). About 10
  are per-request overhead: transaction, session, permissions, company scope, module guard.
  GETs make no Redis round trips.
- Added latency per request served from B: about 12 ms at 1 ms RTT, 24 ms at 2 ms, 60 ms at 5 ms;
  the slowest here (17) adds 17 / 34 / 85 ms.
- A page that fires its API calls in parallel pays roughly its slowest call.
- Requests Cloudflare sends to the primary node pay nothing.
- The A-B RTT itself is still unmeasured: runbook phase 1 step 1b, read-only. Under 2 ms (same
  data centre): +12-35 ms on half the requests, below what a user notices. Above 5 ms: consider
  sending a larger share to the primary node.
- Writes add their idempotency Redis calls (`app/middleware/idempotency_middleware.py`).

### 12d. DNS-only (built) vs proxied (owner's choice), when one node dies or its app breaks

| | DNS-only, TTL 30 s, 60 s checks (built) | Proxied |
|---|---|---|
| A dead node (or link to it) | Cloudflare marks the origin down after 2 checks: 60-120 s. Clients that resolved it keep using it until their DNS cache expires (TTL 30 s, some resolvers longer). Worst case about 150 s of errors for those clients, about half of all users with random steering | Cloudflare connects to the origin itself and, on a connection failure (521/522/523), retries the OTHER origin at once ("zero-downtime failover", proxied only; UNVERIFIED from this sandbox): about 0 s of errors, then the monitor removes it |
| A running but broken app (HTTP 500) | the same 60-150 s | not retried (it is an HTTP answer, not a connection failure): 60-120 s until the monitor removes it |
| Primary database or box lost | 8-11 min (promotion), both modes alike: no node can write until the fenced promotion | same |

Built for DNS-only. Switching to proxied is a Cloudflare setting (orange cloud on the LB
hostname), with no code change. It also hides the origin addresses; per-node certificates remain
valid (Cloudflare to origin: Full (strict)).

### 12e. Drill (`python3 infra/rehearsal/cf_drill.py --mode aa`, 4 Nov, after review round 2)

Each node runs:
- Postgres 17;
- pgbouncer in SESSION mode (prod keeps its mode; session is the hard case), with the route
  include and TCP timeouts;
- Redis (the template's config + ACL users, no persisted replicaof);
- HAProxy for Redis (checks as `hacheck`).

All of it sits on the node's own network; node-local hops use names that exist only there. The
link is a separate network. The fake Cloudflare checks each node's APP PATH (through its
pgbouncer) as two origins of one pool, each check on its own. Each node also runs a long-lived
session client modelled on the app's SQLAlchemy pool: it stays on a connection that only
returns read-only errors, and reconnects only when the connection is lost. The real controller
and adapter run on each node, with scaled timings.

| Scenario | Result |
|---|---|
| steady state | PASS: both origins healthy; writes through B's app land on A; one Redis shared (set on A, read on B); the app's Redis user gets NOPERM for REPLICAOF, FLUSHALL, SWAPDB, CONFIG, SHUTDOWN; both long-lived sessions write |
| app down on A only | PASS: A out of the pool and back; no fence, no promotion; B kept serving writes |
| app down on B only | PASS: same, mirrored |
| link cut only | PASS: B left the pool (no route to the primary), no failover; back after the link returned |
| primary box dies | PASS: B primary 20 s after A died, serving at 22 s; B routes local and its Redis is master; B's long-lived session writes into B; A came back read-only and serves again through B |
| both nodes reboot while B is primary | PASS: one writer. Both Redis restarted as masters and R1 repaired the standby's from its real role. A, routed at B, wins the both-standby tie and promotes while B stays a running standby: A's long-lived session, pinned to B, is moved off it and writes into A (the round-2 case). KILL TEST: the same drill with the re-point limited to RELOAD (no KILL + RESUME) FAILS this scenario, so the drill guards the fix |
| primary isolated | PASS: the isolated primary fenced (11 s) before the other promoted (20 s); both serving again, both long-lived sessions writing |
| never two writers | PASS: 0 two-Postgres samples ("never two writers" is the Postgres check) |
| Redis two masters | NOTE: 15 samples (0.3 s each, about 4 s in all), all right after a Redis restart, each repaired within a tick (12b) |
| acknowledged writes | NOTE: 2 of 357 lost, written through the ISOLATED primary's own app path in the seconds before it fenced (the drill reaches it through Docker; a real isolated box has no users) |

Drill findings fixed in the build:
- Round 1: pgbouncer re-point after `RELOAD` (`RECONNECT`); `server_login_retry = 2`; Redis role
  switched before pgbouncer.
- Round 2: `KILL` + `RESUME` instead of `RECONNECT`, so session mode is covered; pgbouncer TCP
  keepalive and `tcp_user_timeout`, so a cut link drops server connections in about 10 s
  instead of hanging app requests for the kernel's 15 minutes.
- Drill fidelity: names that resolved to the link address made a link cut also cut node-local
  paths, so node-local hops now use local-only aliases; the old long-lived client never
  reconnected, unlike the app's pool.

`--mode ap` keeps the active-passive scenarios.
