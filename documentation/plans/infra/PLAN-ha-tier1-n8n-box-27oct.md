# PLAN: HA plan v2, Tier 1 on the n8n box with automatic failover (HA-TIER1-N8N-BOX)

Status: plan + code guards + templates in review, PR #1915. Owner rulings D1-D5 recorded 27 Oct
(section 10); three small items still open (section 10, "Still open"). Track: docs + infra
templates + two small backend guards (health role endpoint, scheduler leader guard). No migration,
no auth/RBAC change, no new ingest surface: small fix track for the code slice.

Supersedes the Tier 1 section of the 14 Oct crew HA plan (crew report `HA-PLAN-14oct.md` and the
owner plan page; neither is in this repo, so section 0 restates what this plan builds on). Tier 0
lanes are cited by PR.

Owner brief (27 Oct): the n8n box (Hostinger KVM 8, already paid, in KL) is mostly idle because
most mechanisms moved into the CRM. Reuse it as the HA node behind a load balancer, moving its
region if that buys real HA. Follow-ups the same afternoon: (1) can both servers serve at the same
time so load is shared; (2) the CRM box is a KVM 4 at 121/200 GB disk, about 24% CPU and 56% memory,
of which about 39 GB is 8 pre-migrate dumps. Rulings the same evening (section 10): active-passive,
standby in INDIA ("in case SEA got problem"), no webhook buffer, Cloudflare LB + R2, and AUTOMATIC
failover: "it should happen automatically, that's the point of HA, I want our system to have 0%
downtime as much as possible by maintaining itself automatically".

Rules for this lane and its follow-ups: no addresses, private hostnames or secrets in the repo
(placeholders only: `<CRM_PUBLIC_HOST>`, `<KL_WG_IP>`, `<IN_WG_IP>`, `<WITNESS_WG_IP>`); no prod
access. "Unverified" marks every fact this sandbox could not check; crew or the owner confirms them.

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
| Outside monitor, heartbeats, Cloudflare switch | HA-MONITOR #1692 (16 Oct) | `documentation/runbooks/monitoring.md`, `documentation/runbooks/n8n-heartbeat-workflow.json` (exported `active: false`, line 114), `scripts/ops/cf-proxy.py`, `HC_SCHEDULER_URL` job `healthchecks_scheduler_ping` (`sorento_crm_backend/app/scheduler/task_scheduler.py:953-960`), `GET /api/v1/health` (`sorento_crm_backend/app/main.py:685`) | unverified (heartbeat workflow import and Uptime Kuma monitors are owner steps) |
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


## 2. Target topology (Tier 1: active-passive, automatic failover)

Three members, three locations, so a majority (2 of 3) always decides who is primary:

```
                 Cloudflare (proxy + Load Balancing, monitor GET /api/v1/health/role)
                    | pool "kl" (preferred)            | pool "in" (fallback)
                    v                                  v
  KL node: CRM box (KVM 4)                     IN node: n8n box (KVM 8, moved to India)
  nginx -> backend colour, frontend            nginx -> backend colour, frontend (warm)
  Patroni + Postgres 17 + pgvector             Patroni + Postgres 17 + pgvector
     (leader today)          ==== async WAL stream ====>   (replica today)
  etcd member 1                                etcd member 2
  role-watcher: workers + scheduler            role-watcher: workers + scheduler
     run only while the local DB leads            run only while the local DB leads
  Redis (local)                                Redis (local), n8n + its Postgres, MCP
         \                                          /
          \______ WAL-G archive (both nodes) ______/----> Cloudflare R2 (off-site, PITR)

                 Witness: small VPS in a THIRD location outside SEA and India
                 etcd member 3 only (no Postgres, no app). Cheap, about 1 vCPU / 1 GB.

  <====== WireGuard mesh (3 peers): etcd 2379-2380, Patroni REST 8008, Postgres 5432, SSH 22 ======>
```

The two CRM nodes are symmetric: same compose, same Patroni config apart from the node name and
address. Which one is primary is decided by Patroni through etcd, never by a config file, so a
failover needs no edit anywhere.

### Why Patroni + etcd (and not pg_auto_failover or a human)

- Owner ruling D5: failover is automatic. With two nodes that is unsafe (each side of a network cut
  would promote itself); a third voter makes it safe, because only the side that still reaches a
  majority may hold the leader key.
- **Patroni + etcd** (recommended): the most used Postgres HA manager; the leader key in etcd has a
  TTL, the leader must renew it every loop, and a leader that cannot renew it DEMOTES ITSELF before
  the TTL ends, so the old primary fences itself on a network cut. It also restarts a crashed
  Postgres, rejoins an old primary as a replica with `pg_rewind`, and re-seeds it from scratch if
  the rewind fails (section 8b). It runs vanilla Postgres, so the pgvector image just gains the
  Patroni package (template `infra/templates/patroni/Dockerfile`).
- pg_auto_failover (alternative, not chosen): simpler two nodes + one monitor, but the monitor is a
  single Postgres that is itself not HA, and the project is less used; Patroni's self-demotion and
  rewind/re-seed cover more of "maintains itself".
- etcd on all three members (not Consul/ZooKeeper): Patroni's best-supported DCS, one static binary.

### Timings and safety settings (template `infra/templates/patroni/patroni.yml`)

| Setting | Value | Why |
|---|---|---|
| `ttl` | 30 s | leader key lifetime: the longest time a dead primary blocks promotion |
| `loop_wait` | 10 s | how often Patroni checks and renews |
| `retry_timeout` | 10 s | DCS and Postgres retries; `loop_wait + 2 x retry_timeout <= ttl` |
| `maximum_lag_on_failover` | 16 MB | a replica further behind than this is NOT promoted automatically (bounds data loss; section 11 "Still needs a human") |
| `use_pg_rewind` | true | old primary rejoins as a replica without a full copy |
| `remove_data_directory_on_rewind_failure` | true | if rewind fails, Patroni wipes and re-seeds it from the leader automatically |
| `wal_log_hints` | on | required by `pg_rewind` |
| `failsafe_mode` | true | if etcd itself is unreachable (for example the witness AND the etcd on one node are down) but the leader still reaches every Patroni member, it keeps running instead of demoting |
| `watchdog.mode` | `automatic` | Linux softdog: if Patroni itself hangs, the box reboots before the TTL ends, so a frozen old primary cannot keep accepting writes (needs `/dev/watchdog` passed into the container; `required` once proven) |
| `synchronous_mode` | false | async (section 3: India RTT would be paid on every commit) |
| etcd `heartbeat-interval` / `election-timeout` | 300 ms / 3000 ms | WAN between KL, India and the witness |

Detection to promotion: up to `ttl` (30 s) for the old leader key to expire plus a few seconds to
promote. The Cloudflare monitor then needs its interval x consecutive failures to move traffic
(section 5).

### Who runs workers and the scheduler: the role watcher

`infra/scripts/role-watcher.sh` (systemd unit, every 5 s, on both CRM nodes) asks the LOCAL
Patroni (`GET http://127.0.0.1:8008/primary`, 200 only on the leader). Two readings in a row as
leader: `docker compose --profile promoted up -d worker worker_fast`. Two readings as not-leader:
`docker compose stop worker worker_fast`. So after an automatic failover the India node starts
its workers and scheduler within about 10 s of promotion, and the demoted KL node stops its own.
Defence in depth: the scheduler leader guard (section 8) refuses to start on a replica and, with
`SCHEDULER_LEADER_DATABASE_URL`, holds a lock so two schedulers can never run against one primary
even if the watcher misfires.

### Where each client connects

- **App on each node**: its LOCAL Postgres through its local pgbouncer. A node serves users only
  while its own DB leads (the LB checks `/api/v1/health/role`), so it never pays cross-site
  per-statement latency (section 4).
- **n8n and MCP** (India box): `crm-private.internal` resolves to a local HAProxy
  (`infra/templates/haproxy/haproxy.cfg`) with two backends, the local CRM and the KL CRM over the
  tunnel, health-checked on the same `/api/v1/health/role`. So n8n follows the primary with no
  `.env` flip (replaces the manual `CRM_PRIVATE_IP` step of
  `documentation/runbooks/n8n-private-path.md:641-663`). The n8n DB credential `sorento-crm-db`
  points at the same HAProxy's Postgres frontend, checked on Patroni's `/primary`.
- **Redis**: local per node. On failover the dead node's queued RQ jobs are lost; import rows left
  `queued` or `processing` are settled by the existing orphan reconcile
  (`sorento_crm_backend/app/scheduler/task_scheduler.py:79-86`); chatbot turns live in Postgres
  (`chatbot.turns`, `sorento_crm_backend/app/services/chatbot/inbox_queue.py:1-15`) and are drained
  again by the new node; staff sessions are Postgres rows, so users stay signed in.

### Resources

KVM 8 per Hostinger's plan table: 8 vCPU, 32 GB RAM, 400 GB NVMe, 32 TB bandwidth
([vpsbenchmarks](https://vpsbenchmarks.com/hosters/hostinger/plans/kvm-8),
[hostinger.com/vps-hosting](https://www.hostinger.com/vps-hosting); the page could not be fetched
from this sandbox, crew confirms in hPanel). Same family as the CRM box: KVM 4 = 4 vCPU / 16 GB /
200 GB, matching the owner's screenshot.

| Component on the KVM 8 | Memory | Source |
|---|---|---|
| One backend colour (4 gunicorn workers) | ~4.7 GB | measured 10 Sep, `documentation/plans/deploy/PLAN-deploy-memory-and-ci-speed.md:15` |
| Frontend | ~0.7 GB | same line |
| Postgres replica (`shared_buffers` sized like prod) | ~2 GB | prod db 2.0 GB, same line |
| Redis (idle) + MCP | ~0.6 GB | same line (redis 0.53 GB) |
| Patroni + etcd + HAProxy | ~0.3 GB | estimate |
| Subtotal (the "~9 GB per colour" of the 14 Oct report) | ~8.5-9.5 GB | |
| Blue/green overlap during a deploy | +5.4 GB | `PLAN-deploy-memory-and-ci-speed.md:18` |
| Workers after promotion | +0.3 GB | same line |
| n8n + its Postgres | unverified (crew: `docker stats` on the n8n box) | |

Fits 32 GB with a wide margin even if n8n uses 4-6 GB. After a failover the India node is BIGGER
than today's primary. The KL node gains only Patroni + etcd (~0.3 GB) on its 16 GB. Witness: etcd
alone, under 0.5 GB.

### Network

- WireGuard full mesh between the three members (`infra/templates/wireguard/wg0.conf.template`),
  or the tailnet from HA-N8N-PRIVATE-PATH if applied (WireGuard underneath).
- Over the tunnel only: etcd 2379/2380 (all three), Patroni REST 8008 and Postgres 5432 (the two
  CRM nodes), SSH 22. Nothing of this on a public interface.
- Public on the two CRM nodes: 80/443 limited to Cloudflare ranges (the HA-SEC-EDGE rules), 22
  key-only. The India node needs the same edge rules before it joins the LB. Witness: 22 + the
  WireGuard UDP port only.

### Replication and PITR

- **Postgres 17 + pgvector** on both nodes, the same image tag (prod uses `pgvector/pgvector:pg17`
  or `postgres:17`, `documentation/runbooks/backups.md:121`; crew confirms the tag). Physical
  streaming replication copies pgvector indexes as-is.
- Patroni seeds the India replica itself (`pg_basebackup` from the leader) when it first joins, and
  manages a permanent replication slot per member with `max_slot_wal_keep_size = 20GB`, so a dead
  replica can never fill the leader's disk.
- **WAL-G** to a dedicated Cloudflare R2 bucket from whichever node leads (archive settings live in
  the Patroni config, so they move with the leader): `archive_command = 'wal-g wal-push %p'`,
  `archive_timeout = 60`, nightly `wal-g backup-push` from the leader (cron on both nodes, the
  script exits on a replica), retention 7 full + WAL. Replicas use `wal-g wal-fetch` as their
  `restore_command` fallback. Credentials only in each node's env.
- The nightly `pg_dump` to Drive (`scripts/ops/backup-db.sh`) stays as the logical copy; the
  restore test (`scripts/ops/restore-test.sh`) gains a WAL-G PITR leg.

### Failback

Automatic for the database: when the KL node comes back, Patroni rejoins it as a replica of the
India leader (`pg_rewind`, or a full re-seed if that fails). It is not automatically promoted back
(that would flap). Moving the primary back to KL, which is closer to users (section 3), is one
`patronictl switchover` in a quiet window: a 5-15 s write pause, no data loss. Whether that runs on
a schedule or by hand is open item O3 (section 10).

## 3. Location (owner ruling D2: India)

- **Primary stays where the CRM box is** (Malaysia per the owner's KL remark; the exact data
  centre is unverified from the repo, crew reads hPanel, VPS, Overview, "Location").
- **Standby: Hostinger VPS, location "India" = Mumbai.** Hostinger's support page lists India among
  the VPS locations in Asia (with Indonesia and Malaysia), and Hostinger's own blog announced its
  Mumbai data centre; that the VPS location is that Mumbai site comes from third-party reviews
  ([Hostinger server locations](https://www.hostinger.com/support/1583267-where-are-hostinger-servers-located/),
  [Hostinger India VPS review](https://hostadvice.com/hosting-company/hostinger-reviews/hostinger-india-hosting-review/)).
  Unverified until the hPanel "Change location" dialog shows it.
- **Witness: outside SEA and India**, so an SEA-wide problem leaves India + witness = a majority and
  India promotes; an India problem leaves KL + witness; a witness problem changes nothing. A witness
  in Singapore or Jakarta would fail exactly the case the owner named, so not there. Recommended:
  Europe (Hostinger KVM 1 in a European location, same account and billing; or Hetzner, an
  independent provider, so one provider's account or billing problem cannot take two of three
  voters). Open item O1.

### Latency and what users feel

| Path | Expected RTT | Status |
|---|---|---|
| KL node to India node | 60-100 ms | unverified; public tables put Yangon to Mumbai at about 127 ms ([WonderNetwork](https://wondernetwork.com/pings/Yangon/Mumbai)) and SEA routes to Mumbai usually go via Singapore. Crew measures: `mtr -rwc 100 <IN_WG_IP>` from the KL box over the tunnel, right after the move |
| KL or India to a European witness | 150-250 ms | unverified; only etcd votes cross it, the timeouts in section 2 allow for it |
| Malaysian user to Cloudflare | unchanged | the POP is local whichever origin serves |

Async replication lag at that RTT: WAL leaves the primary as it is written, so the replica is about
half an RTT plus replay behind, normally well under a second at our write rate; bulk imports and
migrations can push it to seconds. Patroni will not promote a replica more than 16 MB behind
(section 2). Synchronous replication (RPO 0) would add the full RTT to every commit, and some
requests commit several times, so it stays off (trigger to revisit: a lost-write incident).

What users feel after a failover to India:

- **During the failover**: about 1-2 minutes of errors or timeouts (section 11 RTO). Staff stay
  signed in (sessions are Postgres rows). A save in flight at that moment fails and has to be
  retried. Writes from the last moment before the crash that had not reached the replica (normally
  under a second) are lost.
- **After it**: every request pays one extra Cloudflare-to-origin RTT, about 60-100 ms (Cloudflare
  keeps warm connections to the origin, so no extra TLS handshakes). Database work is local on the
  India node, so Stock Debt's 45-150 statements cost the same as today. A page that makes 3-5
  sequential API calls feels about 0.2-0.5 s slower. The bot gets slightly faster: n8n and the CRM
  are then on the same box.
- **While KL is primary (normal)**: n8n on the India box reaches the CRM over the tunnel, about
  60-100 ms per call instead of today's same-site hop; a chatbot turn makes a few such calls, so
  about 0.2-0.5 s per turn. Accepted cost of putting the standby where an SEA problem cannot reach
  it; it disappears when the direct-ingress gap plan moves the sends into the CRM (section 6).

Owner clicks: hPanel, VPS (the n8n one), Settings, "Change location", India. Take an n8n backup
first; the VPS gets a NEW public address (whether the disk carries over is unverified), so update
the n8n DNS record, any respond.io webhook URL that names the n8n host by address, and the
allowlists in section 9. Move BEFORE seeding the replica.

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
  reconcile lock at `sorento_crm_backend/app/tasks/chat_reconcile_tasks.py:20`, rate limits). The
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
  (failover order): pool `kl` first, pool `in` as fallback. One endpoint per pool.
- Monitor: HTTPS `GET /api/v1/health/role`, expect 200, `Host` header = the public host, 2
  consecutive failures. `/health` on the public host is answered by nginx itself
  (`sorento_crm_backend/app/main.py:688-690`), so the monitor must use the `/api/v1/...` path.
- The endpoint answers 200 only where the local DB leads, so exactly one pool is healthy at a time
  and the LB follows Patroni by itself: no API call, no DNS edit, no human. When the old primary
  comes back it is a replica (503), so traffic does not flap back.
- Interval: 60 s on the base add-on; shorter intervals cost more (unverified, owner confirms on the
  dashboard). With 60 s x 2 failures the LB can take up to about 2 minutes after promotion to move
  traffic; with 15 s, about 30 s. Open item O2.
- `scripts/ops/cf-proxy.py` (HA-MONITOR) stays the escape for "Cloudflare itself is down"; with the
  LB in place its runbook step must point the DNS-only record at whichever node leads
  (`patronictl list` names it).
- Price (unverified, third-party figures): from $5/month for 2 endpoints with 60 s checks, plus about
  $0.50 per 500k DNS queries; faster checks and more check regions cost more
  ([Cloudflare LB](https://developers.cloudflare.com/use-cases/performance/load-balancing)).

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

With the KVM 8 in India, n8n's calls into the KL primary cross the tunnel (section 3, about
0.2-0.5 s per bot turn) and its CRM endpoint follows the primary through the local HAProxy
(section 2).

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

Witness: etcd data only, under 1 GB; the smallest VPS disk is plenty. Both CRM nodes need the same
headroom, since either can lead: the KL column applies to the India node while it leads.

With D unknown, the CRM box stays under about 60 GB + D after the cap, versus 121 GB today; the KVM
8 needs about 30 GB + D + n8n, a fraction of 400 GB.

## 8. What this PR ships (no prod access needed)

1. **`GET /api/v1/health/role`** (unauthenticated, like `/api/v1/health`; `sorento_crm_backend/app/main.py`):
   200 `{"status":"healthy","role":"primary"}` when the DB answers and `pg_is_in_recovery()` is
   false; 503 `{"status":"standby","role":"standby","replay_lag_seconds":N}` on a replica; 503
   `{"status":"unhealthy","role":"unknown"}` when the DB is unreachable. The LB monitor (section 5),
   the n8n HAProxy check (section 2) and the lag number Phase B would use. No host, no error text.
2. **Scheduler leader guard** (`sorento_crm_backend/app/scheduler/leader.py`, called first in
   `start_scheduler`, `sorento_crm_backend/app/scheduler/task_scheduler.py`):
   - Always: the database must be writable (`pg_is_in_recovery()` false), else
     `SchedulerNotLeader` and no job is registered. The worker already exits non-zero when the
     scheduler fails to start (`sorento_crm_backend/worker.py:81-96`), so a scheduler started on a
     replica fails visibly instead of running against it.
   - When `SCHEDULER_LEADER_DATABASE_URL` is set: also a session-level Postgres advisory lock on
     its own connection for the life of the process, so a second scheduler against the same
     primary refuses. That URL must reach Postgres DIRECTLY: through a transaction-mode pgbouncer
     the lock would sit on a pooled server connection that outlives the worker, and the next
     worker (every deploy recreates it) could never start, or would re-enter the lock beside the
     first. Unset = no lock. Set it on the `worker` container of BOTH nodes.
   - The lock lives as long as its session: the 10 s scheduler heartbeat checks the held
     connection and exits the process if it is gone (a Postgres restart or a Patroni demotion),
     so the restarted worker takes the lock again or refuses.
   - What changes on prod at merge: only the standby check. It opens one DB connection when the
     scheduler starts, so a DB that does not answer at that moment now exits the worker (restart
     loop until it answers) where before the scheduler started and failed per tick.
   - Tests: `sorento_crm_backend/tests/test_scheduler_leader.py`,
     `sorento_crm_backend/tests/test_api_v1_health_role.py`.
3. **Infra templates** under `infra/` (README there), placeholders only; they move to the private
   infra repo when it exists:
   - `templates/patroni/patroni.yml` (both CRM nodes, values from env) and
     `templates/patroni/Dockerfile` (pgvector pg17 + Patroni + WAL-G).
   - `templates/etcd/etcd.env.template` (all three members, WAN timeouts).
   - `templates/compose.ha.yml` (Patroni replaces the `db` service; workers behind profile
     `promoted`; `SKIP_MIGRATIONS=1` on the backend colours of a node that is not leading).
   - `templates/haproxy/haproxy.cfg` (n8n and MCP on the India box follow the primary).
   - `templates/walg.env.example`, `templates/wireguard/wg0.conf.template` (three-peer mesh).
   - `scripts/role-watcher.sh` + `templates/systemd/role-watcher.service` (+ shell test
     `infra/tests/test_role_watcher.sh`): workers and scheduler run only on the leader.
   - `scripts/ha-checks.sh` (+ shell test `infra/tests/test_ha_checks.sh`): disk, WAL, lag, members,
     backup age, pinging Healthchecks; prunes old pre-migrate dumps when disk is high.

Follow-ups named, not built: `SNAPSHOT_KEEP_COUNT` in `scripts/blue_green_deploy.sh` (section 7);
the release deploying both nodes with migrations only on the leader (section 11); phase B read
offload on its trigger (section 4).

## 8b. Self-healing (owner: "maintaining itself automatically")

| Failure | What heals it, with no human | Where |
|---|---|---|
| Primary box or its Postgres dies | Patroni promotes the India replica after the leader key expires (about 30-40 s); the role watcher starts workers + scheduler there; the LB moves traffic; HAProxy moves n8n | section 2, 5 |
| Network cut isolates the primary | it cannot renew the leader key and demotes itself before the TTL ends; the side with the majority promotes | Patroni |
| Patroni itself hangs on the primary | watchdog reboots the box before the TTL ends | `watchdog` in `patroni.yml` |
| Postgres crashes but the box is fine | Patroni restarts it in place (failover only if it stays down past the TTL) | Patroni |
| Old primary comes back | rejoins as a replica with `pg_rewind`; if that fails it is wiped and re-seeded from the leader | `use_pg_rewind`, `remove_data_directory_on_rewind_failure` |
| Replica fell out of its slot window | catches up from the WAL-G archive (`restore_command`), else re-seeds | `patroni.yml` |
| A container exits | `restart: unless-stopped` (as today) | compose |
| A container is up but unhealthy (backend `/health` 503, frontend down) | `autoheal` sidecar restarts containers whose healthcheck fails | `compose.ha.yml` |
| Scheduler lost its lock (Postgres restart, demotion) | worker exits, restarts, re-takes or refuses | section 8 |
| Disk filling with pre-migrate dumps | `ha-checks.sh` keeps the newest 2 when disk use passes 85%, and alerts | `infra/scripts/ha-checks.sh` |
| WAL piling up, replica lagging, member missing, base backup older than 26 h, archive stalled | `ha-checks.sh` alerts through Healthchecks.io (outside our servers, as HA-MONITOR) | same |
| Witness dies | nothing to heal: KL + India are still a majority; `ha-checks.sh` alerts | etcd |

## 9. Owner-side steps (crew/owner apply; nothing here touches prod from the lane)

1. Private infra repo `sorento-infra` (layout in `infra/README.md`; the templates move there).
   Prod compose, nginx, Caddy, `.deploy.env.example` captured from the box. No secrets.
2. Move the KVM 8 to India (section 3). Buy the witness VPS (O1).
3. WireGuard mesh between the three (or confirm the tailnet reaches all three).
4. R2 bucket + scoped token for WAL-G.
5. etcd on all three members; check `etcdctl endpoint health --cluster` shows 3 healthy.
6. Adopt the prod Postgres into Patroni (Patroni's documented "convert a standalone" path: same
   data directory, Patroni takes the leader key) in one planned window, about 1-2 minutes of
   downtime for the restart that also turns on `wal_log_hints` and archiving.
7. Start the India node: Patroni seeds the replica itself; the role watcher keeps its workers off.
8. Allowlists: add the India box's egress address to the OpenAI API key's IP allowlist (OpenAI
   dashboard, project / API keys, allowed IPs), and to any other provider with one (Respond.io API,
   AutoCount: crew checks). Without this a failover works but the bot fails.
9. Cloudflare: buy Load Balancing, create the monitor + pools `kl`, `in` + the LB (section 5).
10. Healthchecks.io checks for `ha-checks.sh` on both CRM nodes and the witness.
11. Drills 1-3 of section 12 before calling Tier 1 done.

## 10. Decisions

Owner rulings, 27 Oct about 19:35 (recorded verbatim where quoted):

- **D1 Topology: (a) active-passive** warm standby now; read offload (Phase B) later on its trigger.
- **D2 Region: India** for the standby, "in case SEA got problem". Section 3.
- **D3 Webhook buffer: (a) none for Tier 1.** Automatic failover puts the usual outage inside
  respond.io's roughly 3-minute retry window (section 11 RTO); anything missed is backfilled by the
  CRM's `chat_history_reconcile`. Revisit a Cloudflare Worker + Queue if a drill shows lost events.
- **D4 Spend: (a) Cloudflare LB + R2 WAL archive.** Plus the witness the automatic failover needs
  (section 11 costs).
- **D5 Promotion: automatic**, "it should happen automatically, that's the point of HA, I want our
  system to have 0% downtime as much as possible by maintaining itself automatically". The
  split-brain risk is solved with a third voter (witness) + Patroni's self-demotion + watchdog
  (section 2), not by a human.

Still open (one crew-ask on the PR):

- **O1 Witness host**: (a) Hetzner smallest cloud VPS in Germany or Finland, about EUR 4-5/month,
  independent provider; (b) Hostinger KVM 1 in a European location, about $5-7/month (promo,
  renewal higher), same account. Recommend (a): a Hostinger account, billing or platform problem
  then cannot take two of the three voters. Prices unverified.
- **O2 LB check interval**: (a) 60 s base, traffic moves up to about 2 minutes after promotion;
  (b) the faster interval add-on (15 s or less), about 30 s. Recommend (b) if it is under $10/month
  extra: it is the largest single piece of the outage.
- **O3 Moving the primary back to KL after a failover**: (a) automatic, a scheduled
  `patronictl switchover` at 03:00 MYT once KL has been a healthy, caught-up replica for 24 h;
  (b) a human runs the same command. Recommend (a): about a 5-15 s write pause at night, no data
  loss, and it removes the last routine human step.

## 11. Costs, effort, RTO/RPO, what still needs a human, risks

### Cost per month (on top of the two Hostinger boxes already paid)

| Item | Per month | Status |
|---|---|---|
| Cloudflare Load Balancing, 2 endpoints, 60 s checks | about $5 | unverified |
| Faster checks (O2 b) | about $5-10 more | unverified |
| Witness VPS (O1) | about $5-7 | unverified |
| R2 for WAL-G: 7 compressed fulls + WAL, about 50-150 GB at $0.015/GB (10 GB free); about 50-100k writes, inside the free million | about $1-3 | depends on DB size D, unverified |
| India region for the KVM 8 | $0 expected | unverified (Hostinger may charge for a location change) |
| **Total** | **about $11-25** | |

### Effort

| Slice | Who | Lane-days |
|---|---|---|
| This plan + code guards + templates (PR #1915) | lane | 1.5 |
| Private infra repo, prod compose captured | crew + owner | 0.5 |
| Region move, witness, WireGuard mesh, etcd | owner (clicks) + crew | 1 |
| Patroni image, adopt prod Postgres (planned window), WAL-G | crew with owner at the box | 1.5-2 |
| India node stack, role watcher, HAProxy for n8n, autoheal, ha-checks | lane + crew | 1 |
| Release deploys both nodes; migrations only on the leader | lane | 1-1.5 |
| Cloudflare LB + monitors + drills 1-3 | owner + crew | 1 |
| **Total** | | **about 7.5-8.5** |

### RTO / RPO

| | Today | After Tier 1 |
|---|---|---|
| Unplanned: primary box dies | hours (rebuild from the nightly dump) | about 40 s to promotion, plus the LB move: about 1 minute with 15 s checks, about 2.5 minutes with 60 s checks |
| Planned switchover | n/a | 5-15 s write pause |
| Deploy | zero downtime (blue/green) | unchanged |
| RPO unplanned | up to 24 h | normally under 1 s of commits; at most 16 MB of WAL (else no automatic promotion) |
| RPO from backups (PITR) | 24 h | about 60 s (`archive_timeout`) |

"0% downtime" honestly: deploys and planned moves are already near zero; an unplanned box loss
becomes about 1-2.5 minutes instead of hours. Lower than that needs synchronous replication and
active-active, which section 4 and section 3 rule out for this latency.

### What still needs a human

1. The replica is more than 16 MB behind when the primary dies: Patroni will not promote on its
   own (that would silently lose more than a few seconds). A human picks: wait for the old
   primary, or `patronictl failover --force` and accept the loss. `ha-checks.sh` alerts on lag long
   before this.
2. Two of the three members are down at once (for example KL and the witness): no majority, so no
   automatic promotion, by design. A human confirms and forces it.
3. A member is gone for good (VPS deleted, disk lost): provision a replacement from the infra repo;
   Patroni then re-seeds it on its own.
4. Cloudflare itself is down: `scripts/ops/cf-proxy.py`.
5. Bad data (a wrong migration, a mass delete): a point-in-time restore from WAL-G is always a
   human decision.
6. Approving releases (the `production` environment gate, as today), changing allowlists and DNS
   when an address changes, and O3 if the owner picks (b).

### Risks

- etcd across 150-250 ms links: tuned timeouts (section 2); a flapping link to the witness costs
  nothing while KL and India see each other. Drill 4 tests it.
- Watchdog in containers needs `/dev/watchdog` passed through; until proven, `mode: automatic`
  (best effort) and the TTL demotion are the fence.
- Deploys touch two nodes: the release must deploy both, same image, migrations only on the leader
  (`SKIP_MIGRATIONS=1` elsewhere: `sorento_crm_backend/start.sh` otherwise runs
  `alembic upgrade head` against a read-only replica and the container fails to start).
- Replication slots filling a disk: `max_slot_wal_keep_size`, plus the WAL alert.
- n8n stays a single point of failure for bot sends while it carries them (section 6); it sits on
  the India node, which survives an SEA problem.
- Forgotten allowlists: the failover works but the bot fails. Drill 2 catches it.
- Async replication: a crash can lose the last fraction of a second of commits.

## 12. Drills

| # | When | What | Pass |
|---|---|---|---|
| 1 | before go-live, then monthly | `patronictl switchover` KL to India and back in a quiet window | write pause under 15 s each way; LB follows; workers move; `/api/v1/health/role` 200 on exactly one node |
| 2 | before go-live, then quarterly | hard stop of the KL VPS in hPanel (unplanned failover) | India promoted within 60 s; LB moved within the O2 bound; bot answers a test WhatsApp; OpenAI calls succeed from India; respond.io messages from the gap backfilled by reconcile |
| 3 | after drill 2 | start KL again | it rejoins as a replica with no human step; lag back to under 1 s |
| 4 | before go-live, then quarterly | cut the tunnel on KL only (firewall rule) | KL demotes itself within 30 s; India promotes; never two primaries (`patronictl list`, both role endpoints) |
| 5 | quarterly | stop the witness | nothing changes; alert fires |
| 6 | monthly | `scripts/ops/restore-test.sh` + a WAL-G PITR restore to a chosen minute in a throwaway container | restore finishes; row counts match |
| 7 | monthly | `ha-checks.sh` with a lowered threshold | Healthchecks alert reaches the owner |

Each drill's numbers go into `documentation/runbooks/` (follow-up runbook `ha-failover.md`).
