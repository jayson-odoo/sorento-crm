# PLAN: HA failover with Cloudflare Load Balancing as the witness (HA-CF-FAILOVER)

Status: Plan, CARD posted 4 Nov, waiting on owner answers (section 9). No code before the answers.
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
  (`infra/scripts/cf-failover.sh`, section 3) that uses the Cloudflare LB health API as the
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

One script, the same on both nodes, a systemd service like the role watcher. Each tick (15 s) it
reads three things:

1. **CF**: the Cloudflare API's view of each pool (`GET .../load_balancers/pools/{id}/health`,
   token scoped to Load Balancing: Read on this account only). Result per node: healthy, unhealthy,
   or UNKNOWN (API unreachable, error, stale).
2. **Peer**: can this node reach the other node's Postgres over the private link (WireGuard), and
   is the replica streaming (`pg_stat_replication` on the primary, `pg_stat_wal_receiver` on the standby).
3. **Self**: `pg_is_in_recovery()` on the local Postgres.

Clocks are NTP-synced on both nodes (checked by `ha-checks.sh`); every window is measured in
seconds of continuous state, not in tick counts.

**Primary keeps the right to write (a lease).** The primary stays writable while EITHER Cloudflare
reported it healthy within the last `FENCE_AFTER` (default 240 s) OR the standby is streaming from
it right now (then the standby can see it, so the standby will not promote). When both have been
false for `FENCE_AFTER`, the primary **fences itself**: stops the workers (role watcher), then
stops Postgres (`pg_ctl stop -m fast`), so `/api/v1/health/role` turns 503 and nothing can write.
It does not restart Postgres until the peer is reachable again (section 3c).

**Standby promotes only when all hold, continuously for `PROMOTE_AFTER` (default 420 s =
`FENCE_AFTER` + 180 s margin):** Cloudflare positively reports the primary UNHEALTHY (UNKNOWN never
counts, so a Cloudflare API outage never promotes); the standby's WAL receiver is disconnected; the
standby cannot open a connection to the primary's Postgres over the link; and its last received WAL
position was within `MAX_LAG` (16 MB, as `patroni.yml:41`) of the primary's last reported position.
Then `SELECT pg_promote()`; the role watcher starts the workers; the LB sees 200 and moves traffic.

Why this cannot give two writable DBs: the standby's conditions imply the primary's fence
conditions (Cloudflare unhealthy, no streaming) have held for at least 180 s longer than the
primary needs to fence. The one case it relies on clocks and the primary's own controller running:
a primary whose controller is hung. The watchdog covers that (softdog, `templates/host/`): the
controller pets it, so a hung controller reboots the box, which also stops Postgres, before
`PROMOTE_AFTER` passes. Cases:

| Fault | What happens |
|---|---|
| Node A box dead / network dead | CF: A unhealthy; B: no link. A is gone (or fences if only its network died). B promotes after 420 s. |
| Link A-B cut, both reachable from Cloudflare | CF says A healthy, so A keeps writing and B never promotes. Alert (lag). No outage. |
| Cloudflare API down | UNKNOWN: B never promotes. A keeps writing while B streams; if the link is also down, A fences after 240 s (the safe side: brief outage, no split brain). Alert. |
| A's app down, DB fine | CF: A unhealthy, but B still streams, so no fence and no promotion: autoheal restarts the containers (`templates/compose.ha.yml:13`). Q3 asks whether to fail over after a longer window. |
| Cloudflare monitor misconfigured (A shown unhealthy while fine) | B streams, so nothing happens; alert. A wrong monitor alone never moves the DB. |
| A comes back after a failover | 3c. |

### 3c. The old primary comes back

Its controller starts with Postgres stopped (fenced) and never starts it writable on its own. It
reads the peer: if node B is primary (reachable, not in recovery), it rewinds A onto B's timeline
(`pg_rewind --source-server`), writes `standby.signal` + `primary_conninfo` pointing at B, starts
Postgres as a replica: A is now the standby, B stays primary (no switchback, Q4 of 1 Nov). If the
rewind fails it re-seeds with `pg_basebackup` (Q4 of this card). If the peer cannot be reached it
stays stopped and alerts. Transactions A committed but never streamed before it died are discarded
by the rewind (async: normally under a second; at most `MAX_LAG`).

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
  to about 60/105 s and the total to about 3-4 minutes. respond.io retries webhooks for about 3
  minutes; messages from the gap are backfilled by the chat-history reconcile
  (`app/scheduler/task_scheduler.py:347`, `PLAN-n8n-decom-ha-01nov.md:55`) once node B runs the
  scheduler. Q1 asks which interval.

## 5. PR-sized steps

| # | Step | Who | Blocked on n8n leaving B? | Size |
|---|---|---|---|---|
| F1 | This plan + UAC; delete the Patroni/etcd/witness templates and rehearsal; amend the 1 Nov plan section 5 and `documentation/runbooks/ha-failover.md` | lane | no | S |
| F2 | `infra/scripts/cf-failover.sh` (+ watchdog pet) and tests with fake curl/psql/pg_ctl (pattern of `infra/tests/test_ha_scripts.py`); role watcher reads the local Postgres role instead of Patroni's `/primary`; `compose.ha.yml` back to the stock Postgres image with replication settings | lane | no | M |
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

## 8. Owner answers

(pending)
