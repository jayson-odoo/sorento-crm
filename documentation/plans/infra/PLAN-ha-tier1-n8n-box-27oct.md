# PLAN: HA plan v2, Tier 1 warm standby on the n8n box (HA-TIER1-N8N-BOX)

Status: plan in review, PR #1915. Track: docs + infra templates + two small backend guards
(health role endpoint, scheduler leader guard). No migration, no auth/RBAC change, no new ingest
surface: small fix track for the code slice.

Supersedes the Tier 1 section of the 14 Oct crew HA plan (crew report `HA-PLAN-14oct.md` and the
owner plan page; neither is in this repo, so section 0 restates what this plan builds on). Tier 0
lanes are cited by PR.

Owner brief (27 Oct): the n8n box (Hostinger KVM 8, already paid, in KL) is mostly idle because
most mechanisms moved into the CRM. Reuse it as the HA node behind a load balancer, moving its
region if that buys real HA. Follow-ups the same afternoon: (1) can both servers serve at the same
time so load is shared; (2) the CRM box is a KVM 4 at 121/200 GB disk, about 24% CPU and 56% memory,
of which about 39 GB is 8 pre-migrate dumps.

Rules for this lane and its follow-ups: no addresses, private hostnames or secrets in the repo
(placeholders only: `<CRM_PUBLIC_HOST>`, `<PRIMARY_WG_IP>`, `<STANDBY_WG_IP>`); no prod access.
"Unverified" marks every fact this sandbox could not check; crew or the owner confirms them.

---

## 0. What the 14 Oct plan said (restated)

- **Tier 0** (cheap, this month): close the prod edge, verified backups with an alarm and a
  restore test, an outside monitor, a Cloudflare switch script, n8n to CRM over a private path,
  a deploy memory guard and rollback.
- **Tier 1** (warm standby): a second box with a Postgres streaming replica and a WAL archive
  (PITR); a Cloudflare Load Balancing pool with health checks; workers and the scheduler stopped
  on the standby until promotion (APScheduler `BackgroundScheduler` is single-node); a webhook
  buffer (respond.io drops webhook events after about 3 minutes of retries); the OpenAI key's IP
  allowlist extended to the standby; prod infra (compose, nginx/Caddy) in a private git repo as
  the prerequisite. Originally priced on a new DigitalOcean SGP1 box.
- v2 change: the standby is the existing n8n KVM 8, not a new box.

## 1. Tier 0 status today

Repo side: all six Tier 0 lanes are merged. Whether each was APPLIED on prod is not visible from
the repo: crew confirms each "applied?" cell.

| Item | Lane / PR | Repo artefacts | Applied on prod? |
|---|---|---|---|
| Edge lockdown (DB/Redis/MCP not on public interfaces, `TRUSTED_PROXIES`) | HA-SEC-EDGE #1688 (closed 14 Oct) | `documentation/runbooks/prod-edge-lockdown.md`, `documentation/plans/security/PLAN-prod-edge-lockdown-14oct.md` | unverified |
| Outside monitor, heartbeats, Cloudflare switch | HA-MONITOR #1692 (16 Oct) | `documentation/runbooks/monitoring.md`, `documentation/runbooks/n8n-heartbeat-workflow.json` (exported `active: false`, line 114), `scripts/ops/cf-proxy.py`, `HC_SCHEDULER_URL` job `healthchecks_scheduler_ping` (`sorento_crm_backend/app/scheduler/task_scheduler.py:950-954`), `GET /api/v1/health` (`sorento_crm_backend/app/main.py:685`) | unverified (heartbeat workflow import and Uptime Kuma monitors are owner steps) |
| Verified backups: alarm, restore test, n8n + shared DBs | HA-BACKUP-CHECK #1695 (16 Oct) | `scripts/ops/backup-db.sh`, `scripts/ops/restore-test.sh`, `documentation/runbooks/backups.md` | unverified (cron swap to the repo script, `HC_BACKUP_URL`) |
| n8n to CRM private path (tailnet) | HA-N8N-PRIVATE-PATH #1694 (16 Oct) | `documentation/runbooks/n8n-private-path.md` (failover = one `.env` line, lines 641-663) | unverified (closing public 6432/8765 rules is 48 h after the switch) |
| Deploy memory guard, migration timeouts, pre-migrate snapshot, rollback | HA-MEM-DEPLOY-GUARD #1693 (16 Oct) | `scripts/blue_green_deploy.sh` (snapshot 320-345), `.github/workflows/rollback.yml`, `documentation/runbooks/memory-and-deploy-guards.md` | in use: the 8 pre-migrate dumps on the box are its output |

Still open after Tier 0 (all carried into Tier 1 below):

1. RPO is still 24 h (nightly `pg_dump`, `documentation/plans/ops/PLAN-ha-backup-check-14oct.md`
   "Problem"). WAL archiving is the fix.
2. Prod infra (prod compose, nginx, Caddy, the `.deploy.env` shape) is not in any git repo: the
   repo's `sorento_crm/docker-compose.yml` is the dev stack (`postgres:15-alpine`, no colours), and
   the compose that sets `ENABLE_SCHEDULER` for the `worker` container is not in this repo.
3. No second node, so every host failure is a full outage until a rebuild from the nightly dump.
4. Disk on the CRM box: 121/200 GB with about 39 GB in `backups/pre-migrate/` (section 7).

## 2. Target topology (Tier 1, active-passive)

```
                 Cloudflare (proxy + Load Balancing, HTTP health checks)
                    | pool "primary" (weight 1)      | pool "standby" (fallback only)
                    v                                v
  CRM box (KVM 4, primary)                   n8n box (KVM 8, standby + n8n)
  nginx -> backend colour, frontend          nginx -> backend colour, frontend (warm, idle)
  worker + worker_fast + scheduler (ON)      worker / worker_fast / scheduler: OFF until promotion
  Postgres 17 + pgvector  PRIMARY  ==WAL==>  Postgres 17 + pgvector  HOT STANDBY (read-only)
  Redis (queues, locks, rate limits)         Redis (empty, local; used only after promotion)
  MCP                                        MCP (local, reads via the standby's backend)
       \                                     n8n + its own Postgres (unchanged)
        \___ WAL-G archive (base backups + WAL segments) ___> off-site object storage (R2)
  <====== WireGuard (or the existing tailnet) between the two boxes: 5432 + 22 only ======>
```

- **Primary**: everything that runs today, unchanged, plus `archive_mode=on` and a replication
  slot for the standby.
- **Standby**: one backend colour and the frontend running against the LOCAL hot-standby replica,
  so every page that only reads would render, but the LB sends it no traffic while the primary
  is healthy (section 5). Workers, worker_fast and the scheduler are stopped (compose profile
  `promoted`, template in `infra/templates/compose.standby.yml`). The leader guard (section 8)
  makes it impossible for the scheduler to run against a replica even if someone starts it.
- **n8n** stays where it is, on the standby box (section 6).

### Resources on the KVM 8

KVM 8 per Hostinger's plan table: 8 vCPU, 32 GB RAM, 400 GB NVMe, 32 TB bandwidth
([vpsbenchmarks](https://vpsbenchmarks.com/hosters/hostinger/plans/kvm-8), Hostinger's own page
[hostinger.com/vps-hosting](https://www.hostinger.com/vps-hosting); the page could not be fetched
from this sandbox, figures from search results, crew confirms in hPanel). Same family as the CRM
box: KVM 4 = 4 vCPU / 16 GB / 200 GB, matching the owner's screenshot.

| Component on the KVM 8 | Memory | Source |
|---|---|---|
| One backend colour (4 gunicorn workers) | ~4.7 GB | measured 10 Sep, `documentation/plans/deploy/PLAN-deploy-memory-and-ci-speed.md:15` |
| Frontend | ~0.7 GB | same line |
| Postgres hot standby (`shared_buffers` sized like prod) | ~2 GB | prod db 2.0 GB, same line |
| Redis (idle) + MCP | ~0.6 GB | same line (redis 0.53 GB) |
| Standby subtotal (the "~9 GB per colour" of the 14 Oct report) | ~8-9 GB | |
| Blue/green overlap during a standby deploy | +5.4 GB | `PLAN-deploy-memory-and-ci-speed.md:18` |
| Workers after promotion | +0.3 GB | same line |
| n8n + its Postgres | unverified (crew: `docker stats` on the n8n box) | |

Steady state about 9 GB plus n8n, peak about 15 GB plus n8n during a deploy: fits 32 GB with a
wide margin even if n8n uses 4-6 GB. CPU: the standby colour is idle; replay of the WAL stream is
single-core and light at our write rate. After a promotion the KVM 8 is BIGGER than today's
primary, so a failed-over CRM runs faster, not slower.

### Network (WireGuard)

- Reuse the tailnet from HA-N8N-PRIVATE-PATH if it is applied (it is WireGuard underneath);
  otherwise a plain WireGuard pair (`infra/templates/wireguard/wg0.conf.template`).
- Over the tunnel only: Postgres 5432 (replication + the optional read offload), SSH 22 for
  promotion. Redis 6379 only if phase C (section 4) is ever built.
- Public on both boxes: 80/443 restricted to Cloudflare ranges (the HA-SEC-EDGE rules), 22
  key-only. The standby needs the same edge rules before it joins the LB pool.
- `pg_hba.conf` on the primary: `hostssl replication replicator <STANDBY_WG_IP>/32 scram-sha-256`
  and nothing on the public interface (template in `infra/templates/postgres/`).

### Replication and PITR

- **Postgres 17 + pgvector** on both nodes, same image tag (prod uses `pgvector/pgvector:pg17` or
  `postgres:17`, `documentation/runbooks/backups.md:121`; crew confirms the exact tag). Physical
  streaming replication copies pgvector indexes as-is; the extension only has to be installed in
  the standby image.
- Standby seeded with `pg_basebackup -R -S standby_kvm8` over the tunnel (about DB-size of
  transfer, once).
- Replication slot with `max_slot_wal_keep_size = 20GB` so a dead standby can never fill the
  primary's disk (the slot is dropped after 20 GB of lag and the standby is re-seeded).
- **WAL-G** (recommended over pgBackRest: one static binary, native S3/R2, fewer moving parts) on
  the primary: `archive_command = 'wal-g wal-push %p'`, `archive_timeout = 60` (RPO bound about 1
  minute even when idle), nightly `wal-g backup-push`, retention 7 full + WAL (`wal-g delete
  retain FULL 7`). Target: a dedicated Cloudflare R2 bucket (the app already uses R2,
  CLAUDE.md "Storage routing"), credentials only in the box's env.
- The nightly `pg_dump` to Drive (`scripts/ops/backup-db.sh`) stays as the logical, portable
  copy; the restore test (`scripts/ops/restore-test.sh`) gains a WAL-G PITR leg later.
- Monitoring: replica lag via the new `/api/v1/health/role` on the standby (reports
  `replay_lag_seconds`), WAL-G `backup-push` pinging a Healthchecks check like the dump does.

### Failover (human first)

Unplanned, primary dead:

1. Outside monitor pages (HA-MONITOR). Owner or crew confirms the primary is really down (not
   Cloudflare: `scripts/ops/cf-proxy.py status`).
2. **Fence the old primary**: Hostinger hPanel "Stop" on the CRM box, or SSH `docker compose
   stop db backend_* worker*` if it still answers. Never promote while the old primary can still
   accept writes.
3. **Promote, one command on the standby**: `infra/scripts/promote-standby.sh` (template in this
   PR): `pg_ctl promote` (via `SELECT pg_promote()`), wait until `pg_is_in_recovery()` is false,
   then `docker compose --profile promoted up -d` (workers, worker_fast, scheduler).
4. Cloudflare LB needs no click: the standby pool's health check is `GET /api/v1/health/role`,
   which answers 200 only when the local DB is writable (section 8), so the pool turns healthy
   on its own seconds after step 3 and the LB fails over to it.
5. n8n on the same box: flip `CRM_PRIVATE_IP` to the local address
   (`documentation/runbooks/n8n-private-path.md:641-663`).
6. OpenAI: the standby's egress address must already be on the key's allowlist (one-time owner
   step, section 9).

RTO: about 10-15 minutes with a human in the loop (page, confirm, fence, promote). RPO: the
streaming lag, normally under a second; at worst the last `archive_timeout` (60 s) if the
standby was also behind.

Planned switchover (maintenance, region move): stop writes on the primary (LB drain), wait for
lag 0, promote, done: RPO 0, about 2 minutes.

Automatic promotion (Patroni + etcd) needs three voters and is NOT in Tier 1: with two boxes it
risks split brain. Trigger to revisit: two unplanned failovers in a quarter, or an RTO target
under 5 minutes.

### Failback

The old primary is now behind and must not rejoin as a primary.

1. Rebuild it as the new standby: `pg_rewind` against the new primary if its timeline diverged
   only slightly, else a fresh `pg_basebackup`.
2. It now replicates from the KVM 8. Run that way as long as convenient (the KVM 8 is the bigger
   box).
3. Optional switch back during a quiet window: the planned switchover above in reverse.

### Drills

- Monthly: restore test (exists) plus a WAL-G PITR restore to a throwaway container at a chosen
  timestamp.
- Quarterly: planned switchover to the standby and back, in a quiet window, with the owner.
- After every infra change: `curl` the role endpoint on both nodes; check the LB shows the right
  pool healthy.

## 3. Location (region)

Facts:

- The n8n KVM 8 is in Kuala Lumpur (owner, 27 Oct).
- The CRM box's data centre is **unverified** from the repo. Crew: hPanel, VPS, Overview,
  "Location". If it is ALSO Malaysia, both nodes share one site: a Hostinger KL outage or network
  event takes both down, so that is not real HA.
- Hostinger VPS regions in Asia per its support page: India, Indonesia, Malaysia; Singapore is
  listed for web/cloud plans but not VPS on one version of the page and listed elsewhere
  ([support article](https://support.hostinger.com/en/articles/1583267-where-are-your-servers-located),
  conflicting versions; crew confirms in the hPanel "Change location" dialog).

Latency (rough public figures, unverified, crew measures with `ping` over the tunnel): KL to
Singapore about 5-10 ms RTT, KL to Jakarta about 15-25 ms, KL to Mumbai about 60-80 ms. Users,
respond.io's webhook senders and Cloudflare all have POPs in KL, Singapore and Jakarta, so the
user-facing hop is dominated by the Cloudflare POP, not the origin, as long as the origin stays
in the region.

Recommendation:

- If the CRM box is in KL: move the KVM 8 OUT of KL. First choice **Singapore** if the hPanel
  dialog offers it for VPS (different site, lowest RTT, best for an eventual read offload);
  second **Indonesia (Jakarta)**. Not India: 60-80 ms makes failed-over latency and any cross-node
  read noticeable.
- If the CRM box is NOT in KL (for example it is already Singapore or India): keep the KVM 8 in
  KL; the two are already different sites.
- Owner clicks: hPanel, VPS (the n8n one), Settings, "Change location" (Hostinger migrates the
  disk; the VPS gets a NEW public address, unverified whether the disk is kept, so take an n8n
  backup first), then update the n8n DNS record and any respond.io webhook URL that points at the
  n8n host by address. Do the move BEFORE seeding the replica.

## 4. Can both servers take load at the same time? (owner question 1)

Short answer: yes for the web tier, later and only for named read-heavy pages; not for the whole
app now, and it is not needed now (the CRM box is at about 24% CPU and 56% memory).

Why not full active-active today:

- **One writable database.** Postgres has one primary. A request served by the KVM 8 that writes
  has to reach the primary over the tunnel, and our handlers are chatty: the Stock Debt page runs
  45-150 statements per request (crew measurement). Every statement pays the round trip:

  | Inter-box RTT | Added time per Stock Debt request (45-150 statements) |
  |---|---|
  | 0.5 ms (same site) | 25-75 ms |
  | 7 ms (KL - Singapore) | 0.3-1.05 s |
  | 20 ms (KL - Jakarta) | 0.9-3.0 s |
  | 70 ms (KL - Mumbai) | 3.2-10.5 s |

  The region that makes HA real (different sites) is exactly what makes cross-node DB access slow.
  So the standby should talk to its LOCAL replica, never chat with the remote primary.
- **Redis is single-node** (RQ queues, the chatbot per-contact drain mutex
  `chatbot:drain:{contact}` at `sorento_crm_backend/app/services/chatbot/inbox_queue.py:444`, the
  reconcile lock at `sorento_crm_backend/app/tasks/chat_reconcile_tasks.py:21`, rate limits). The
  inbox sweeper starts on EVERY API process (`sorento_crm_backend/app/main.py:406-411`): two nodes
  with two Redis instances would each think they hold the per-contact lock and double-send. Active
  -active would have to put both nodes on the primary's Redis over the tunnel, paying RTT per
  Redis call too.
- **Scheduler and workers**: single-node by design (section 8), so the second node would add only
  web capacity.
- What is already fine for active-active: staff sessions are Postgres rows (`user_sessions`,
  CLAUDE.md "Auth boundary"), NextAuth cookies are stateless given the same `NEXTAUTH_SECRET`,
  uploads go to S3/R2 (CLAUDE.md "Storage routing"), so no sticky sessions are needed.

Phased path (recommended):

- **Phase A (Tier 1, this plan): active-passive.** Standby warm, zero traffic. Real HA, no app
  change beyond sections 8-9.
- **Phase B (only on a trigger): read offload of named heavy read-only pages to the standby.**
  The PRIMARY's nginx proxies a short allowlist of read-only GET paths (reports, Stock Debt,
  chatbot catalogue lookups: exact paths chosen from access logs when triggered) to the standby's
  backend over the tunnel. That costs ONE round trip per request, not one per statement, because
  the standby's backend reads its local replica. Lag guard: the standby answers those paths only
  while `/api/v1/health/role` reports `replay_lag_seconds` under a limit (proposed 5 s);
  otherwise nginx's `backup` upstream serves them on the primary. A page that must read its own
  write (save then reload) stays on the primary. Trigger: primary CPU above 60% sustained for a
  week, or one of those pages' p95 over 3 s from load, not from code. Cost: one nginx block and
  the lag check, no LB change.
- **Phase C (not recommended): both nodes take any request.** Only if both boxes are in the same
  site (RTT under 1 ms) AND Phase B is not enough. Needs both nodes on one Redis, every write over
  the tunnel, and gives up the site separation that is the point of Tier 1.

Cloudflare LB note: its "random"/weighted steering CAN split traffic across both pools; the
reason not to is the database, not the LB.

## 5. Cloudflare Load Balancing

- One load balancer on `<CRM_PUBLIC_HOST>` (and the frontend host if separate), steering "off"
  (failover order): pool `primary` (CRM box), fallback pool `standby` (KVM 8).
- Monitor: HTTPS `GET /api/v1/health/role`, expect 200, interval 60 s (the base plan), 2
  consecutive failures, `Host` header set to the public host. `/health` on the public host is
  answered by nginx itself (`sorento_crm_backend/app/main.py:688-690`), so the monitor must use the
  `/api/v1/...` path to reach the app.
- Because `/api/v1/health/role` returns 503 on a read-only replica, the standby pool is unhealthy
  until promotion and the LB never sends users to a database that refuses writes.
- `scripts/ops/cf-proxy.py` (HA-MONITOR) stays the "Cloudflare itself is down" escape: it unproxies
  hosts; with an LB in place the DNS fallback record must point at whichever node is primary
  (runbook step to add when the LB exists).
- Price (unverified, third-party figures; owner confirms on the Cloudflare dashboard): from $5/month
  for 2 origins, 60 s checks, plus about $0.50 per 500k DNS queries; faster checks and more regions
  cost more ([Cloudflare LB](https://developers.cloudflare.com/use-cases/performance/load-balancing)).

## 6. n8n: what still runs there, and keep or retire

From the repo (crew verifies live through the n8n connector; the workflow export repo
`sorento_crm_n8n` is not in this checkout, and the private-path runbook counted about 29 live
workflows, `documentation/runbooks/n8n-private-path.md:15`):

Still in n8n:

- **All customer-facing sends** for the chatbot: chunking, quick replies, 24 h template fallback,
  attachments, assign, comment, contact fields (gap table,
  `documentation/plans/chatbot/PLAN-n8n-to-direct-ingress-gap.md:62-68`). The CRM never sends to
  customers itself on the bot path (D9).
- **Producer / dispatcher / spine and the failover poller** while direct ingress is off: the flag
  `chatbot_direct_ingress_mode` defaults to off
  (`sorento_crm_backend/app/models/user.py:758`, `sorento_crm_backend/app/services/chatbot/direct_ingress.py:133`).
- **SLA scheduled escalation**, a 1-minute n8n schedule calling the CRM
  (`documentation/n8n/sla-scheduled-escalation.workflow.json:6-19`; endpoints
  `sorento_crm_backend/app/api/v1/sla/sla_tracking.py:975`, `:1010`). The CRM scheduler has no
  conversation-SLA scan of its own.
- **Webhooks the CRM calls**: attachment intake (`app/services/attachment_webhook_helper.py:40-121`),
  `respond-send-user` human-intervention flag (`app/services/crm_chat_outbound_webhook.py:241-307`),
  close-convo housekeeping (`app/services/crm_close_convo_webhook.py:150-245`), stock inquiry /
  purchase request revise (`app/services/procurement_service.py:6495-6588`, `:8040-8139`), the
  hourly liveness ping (`app/services/n8n_liveness_service.py:29-63`), chatbot-sender when direct
  ingress is on (`app/services/chatbot/direct_ingress.py:355-437`). Paths under
  `sorento_crm_backend/`.
- **n8n into the CRM**: `/api/v1/external/*` (chat turn, chat-history mirror, media, memory frames,
  SLA tracking, RAG, attachments, and more; mounted at `sorento_crm_backend/app/api/v1/__init__.py:250`)
  and the MCP server (`sorento_crm_mcp/README.md:3`), plus a direct DB credential `sorento-crm-db`
  used by four workflows (`documentation/runbooks/n8n-private-path.md:209`, `:461-462`).

Moved into the CRM already: respond.io webhook direct to the CRM with HMAC
(`app/api/v1/public/respond_webhook.py:334`), the turn engine (`/external/chat/turn`), per-contact
ordering and the CRM-owned inbox queue (`app/services/chatbot/inbox_queue.py:1-15`), media intake,
missed-message reconcile (`chat_history_reconcile`), the ticket-resolved message
(`app/tasks/respond_io_tasks.py:512-514`).

Recommendation: **keep n8n on the KVM 8, unchanged, for Tier 1.** It is small next to 32 GB, it is
still on the bot's send path, and retiring it is its own lane (the direct-ingress gap plan's slices
5-6). Note the HA consequence: the bot's send path depends on n8n, so n8n on the standby box is a
single point of failure for the bot even after Tier 1. That is acceptable because (a) the KVM 8 is
the healthier box and (b) the gap plan already moves sends into the CRM; once that lands, n8n only
carries the SLA escalation schedule and the non-chatbot webhooks, which the CRM scheduler can take
over (trigger: gap plan slice 6 merged).

## 7. Disk sizing (owner question 2)

CRM box today: 200 GB, 121 used, about 39 GB in 8 `backups/pre-migrate/` dumps (owner screenshot;
crew checking the prune rule).

Prune rule as coded: `take_snapshot` deletes dumps older than `SNAPSHOT_KEEP_MINUTES` (default
2880 = 48 h) and only when a NEW snapshot is taken
(`scripts/blue_green_deploy.sh:74-75`, `:332-333`). So 8 dumps on disk means 8 migration deploys
inside 48 hours, or the mtimes were reset (a copy), or the box's `.deploy.env` overrides the window
(crew checks). Each dump is about 4.9 GB. There is no count cap.

Recommended:

- Add `SNAPSHOT_KEEP_COUNT` (default 2) to the prune, in addition to the age rule, so a busy deploy
  day never stacks more than two. Small follow-up in `scripts/blue_green_deploy.sh` + its shell test
  (not in this PR; it is deploy code and HA-MEM-DEPLOY-GUARD's tests own it).
- Once WAL-G PITR is live, the pre-migrate dump is a fast-rollback convenience, not the backup:
  keep 1-2 locally, never copy them around.
- Nothing large on the CRM box beyond its DB: nightly dumps already go to Drive and are deleted
  locally (`documentation/plans/ops/PLAN-ha-backup-check-14oct.md`), WAL archive goes to R2.

| | CRM box (200 GB) | KVM 8 (400 GB) |
|---|---|---|
| OS + Docker images (backend image 3.96 GB, two colours + prune) | ~25 GB | ~25 GB |
| Postgres data (crew: `SELECT pg_size_pretty(pg_database_size(current_database()))`) | D | D (replica) |
| `pg_wal` (`max_wal_size` 4 GB + slot cap 20 GB worst case) | up to 24 GB | ~4 GB |
| Pre-migrate dumps (cap 2 x ~5 GB) | ~10 GB | 0 (not taken on the standby) |
| WAL archive | 0 (off-site R2) | 0 (off-site R2) |
| n8n + its DB + executions | 0 | unverified (crew: `du` on the n8n volume) |

With D unknown, the CRM box stays under about 60 GB + D after the cap, versus 121 GB today; the KVM
8 needs about 30 GB + D + n8n, a fraction of 400 GB.

## 8. Code guards this lane ships (no prod access needed)

1. **`GET /api/v1/health/role`** (unauthenticated, like `/api/v1/health`): 200
   `{"status":"healthy","role":"primary"}` when the DB answers and `pg_is_in_recovery()` is false;
   503 `{"status":"standby","role":"standby","replay_lag_seconds":N}` on a hot standby; 503
   `{"status":"unhealthy"}` when the DB is unreachable. The LB monitor of section 5, and the lag
   number Phase B would use. No host, no error text.
2. **Scheduler leader guard**: `start_scheduler()` first checks the database it is connected to is
   writable (`pg_is_in_recovery()` false) AND takes a session-level Postgres advisory lock on a
   dedicated connection held for the process lifetime. Not writable or lock held by another
   process: the scheduler does not start (the worker logs it and exits non-zero, as it already does
   on a scheduler failure, `sorento_crm_backend/worker.py:81-96`). Uses `DIRECT_URL` when set,
   because a session advisory lock does not survive a transaction-mode pgbouncer.
   Result: two nodes can never both run jobs against one primary, and a scheduler started by mistake
   on the standby refuses to run against the replica.

## 9. Owner-side steps (crew/owner apply; nothing here touches prod from the lane)

1. Private infra repo `sorento-infra` (layout in `infra/README.md` of this PR; the templates under
   `infra/templates/` move there). Prod compose, nginx, Caddy, `.deploy.env.example`. No secrets:
   env files stay on the boxes.
2. Region move of the KVM 8 if section 3 says so.
3. WireGuard (or confirm the tailnet) between the boxes.
4. R2 bucket + scoped token for WAL-G; enable archiving on the primary (one Postgres restart, in a
   quiet window).
5. Seed the replica; start the standby stack without the `promoted` profile.
6. OpenAI: add the KVM 8's egress address to the API key's IP allowlist (OpenAI dashboard, API
   keys / project, allowed IPs). Same for any other provider with an allowlist (Respond.io API,
   AutoCount: crew checks).
7. Cloudflare: buy Load Balancing, create the monitor + two pools + the LB (section 5).
8. Webhook buffer decision (section 10, D3).
9. First drill: planned switchover in a quiet window.

## 10. Decisions for the owner (each with a recommendation)

- **D1 Topology**: (a) active-passive warm standby now, read offload later on a trigger;
  (b) active-active now. **Recommend (a)**: the CRM box is at about 24% CPU, the database has one
  writer, and cross-site per-statement latency makes (b) slower, not faster (section 4).
- **D2 Region for the KVM 8**: (a) keep KL; (b) move to Singapore (or Jakarta if Singapore is not
  offered for VPS). **Recommend (b) if the CRM box is in KL, (a) otherwise**: two boxes in one site
  is not HA.
- **D3 Webhook buffer** (respond.io gives up after about 3 minutes; a human failover is 10-15):
  (a) none, rely on the CRM's missed-message reconcile (`chat_history_reconcile`) to backfill
  history after failover; (b) Hookdeck (managed, pricing unverified); (c) a Cloudflare Worker +
  Queue in front of the webhook URLs (Workers Paid about $5/month, unverified). **Recommend (a) for
  Tier 1, measured in the first drill**: reconcile already exists and backfills missed messages;
  what it cannot do is reply to customers inside the outage, which no buffer fixes either until the
  CRM is back. Revisit (c) if a drill shows lost non-message events (assignments, closes).
- **D4 Spend**: (a) Cloudflare LB about $5-10/month + R2 for WAL about $1-3/month (about 100-200 GB
  stored at $0.015/GB, unverified) = roughly $10/month on top of the boxes you already pay for;
  (b) defer the LB and fail over by DNS with `cf-proxy.py`-style scripting ($0, slower RTO, more
  manual). **Recommend (a)**.
- **D5 Promotion**: (a) human runs the one promote command; (b) automatic. **Recommend (a)** until a
  third voter exists (section 2).

## 11. Effort, RTO/RPO, risks

| Slice | Who | Lane-days |
|---|---|---|
| This plan + code guards + templates (PR #1915) | lane | 1 |
| Private infra repo, prod compose captured from the box | crew + owner | 0.5 |
| Region move + WireGuard | owner (clicks) + crew | 0.5 |
| WAL-G + archiving + replica seed | crew with owner at the box | 1 |
| Standby stack + deploy pipeline deploys both nodes (blue/green on each) | lane | 1-1.5 |
| Cloudflare LB + monitors + first drill | owner + crew | 0.5 |
| Total | | about 4.5-5 |

- RTO: today hours (rebuild from the nightly dump). After Tier 1: 10-15 minutes unplanned, about 2
  minutes planned.
- RPO: today up to 24 h. After Tier 1: under a second normally, at most about 60 s.

Risks:

- Split brain if the old primary is not fenced before promotion: the runbook makes fencing step 2,
  the leader guard stops a double scheduler, and the LB role check stops traffic to a stale primary
  only if that primary's DB was demoted; a revived old primary with a writable DB would pass its
  check, so fencing is mandatory and the old primary's pool is disabled in the LB at failover.
- Deploys now touch two nodes: the release must deploy the standby too (same image), or the
  standby drifts and a failover runs old code. A migration runs once, on the primary; the replica
  receives it through replication, and the standby's backend must be the same release.
- Replication slot filling the primary's disk: capped by `max_slot_wal_keep_size`.
- n8n remains a single point of failure for bot sends (section 6).
- OpenAI / provider allowlists forgotten: failover works but the bot fails. Drill catches it.
- Region move gives the KVM 8 a new address: update DNS and every allowlist that names the old one.
