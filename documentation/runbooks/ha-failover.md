# HA failover runbook (two nodes, Cloudflare Load Balancing as the witness)

Plan: `documentation/plans/infra/PLAN-ha-cf-failover-04nov.md` (replaces the Patroni + etcd + witness
design of 27 Oct / 1 Nov). Templates and scripts: `infra/`. Placeholders only: no addresses,
hostnames or secrets here. Every step that touches a server is an OWNER command, run in a window
the owner chooses; crew is on the call, never at the keyboard of a prod box.

## What runs where

- Node A: the CRM box (primary today). Node B: the KVM 8, rebuilt after n8n stops (plan
  `PLAN-n8n-decom-ha-01nov.md` stage 6-8). Both in Malaysia, the same files, only
  `/etc/sorento-ha/ha-pg.env` differs (names, peer address, pool ids).
- Postgres streams A -> B over the private link; WAL-G archives from whichever is primary to R2.
- `cf-failover.service` (controller) and `role-watcher.service` on both. Workers and the scheduler
  run only where Postgres is primary.
- Cloudflare LB on the public host: pools `node-a`, `node-b`, steering off (failover order),
  monitor `GET /api/v1/health/role`, DNS-only, TTL 30 s.

**Known limitation**: a Malaysia-wide or provider-wide outage takes both nodes down; only the
disaster restore below helps.

## Phase 1: node A alone (can start now, before node B exists)

Goal: node A on the HA Postgres layout (data in a subdirectory, `wal_log_hints`, WAL archiving to
R2), role watcher and checks installed. The controller is NOT started in this phase: with no peer
and no load balancer its lease would expire and it would fence the only database.

1. Read-only pre-checks (owner, any time):
   ```
   cd /opt/sorento-crm2
   docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -Atc "show data_directory; show wal_log_hints; show archive_mode; show shared_preload_libraries; show server_version"
   docker compose config --format json | python3 -c 'import json,sys; c=json.load(sys.stdin)["services"]["db"]; print(c["image"], c.get("volumes"))'
   ```
   Note the data directory. If it is the volume root (`/var/lib/postgresql/data`), step 4 moves it
   into `pgdata/`. Copy `shared_preload_libraries` into `compose.ha.yml`.
2. A fresh backup exists and restores (`scripts/ops/backup-db.sh`, the weekly restore test).
3. Replication role (owner types the password at the prompt; it never lands in shell history):
   ```
   docker compose exec -it db psql -U "$POSTGRES_USER" -d postgres
     CREATE ROLE replicator WITH REPLICATION LOGIN;
     \password replicator
     GRANT CONNECT ON DATABASE postgres TO replicator;
     GRANT EXECUTE ON FUNCTION pg_catalog.pg_ls_dir(text, boolean, boolean) TO replicator;
     GRANT EXECUTE ON FUNCTION pg_catalog.pg_stat_file(text, boolean) TO replicator;
     GRANT EXECUTE ON FUNCTION pg_catalog.pg_read_binary_file(text) TO replicator;
     GRANT EXECUTE ON FUNCTION pg_catalog.pg_read_binary_file(text, bigint, bigint, boolean) TO replicator;
   ```
   (the grants are what `pg_rewind --source-server` needs from a non-superuser).
4. WINDOW (about 2-3 minutes of downtime: one Postgres stop and start):
   ```
   docker compose stop worker worker_fast
   docker compose stop db
   # only if step 1 showed the volume root: move the data into pgdata/ (same filesystem, instant)
   docker run --rm -v <POSTGRES_VOLUME>:/v <SAME_PG_IMAGE> sh -c \
     'cd /v && mkdir pgdata && find . -mindepth 1 -maxdepth 1 ! -name pgdata -exec mv {} pgdata/ \; && chown postgres:postgres pgdata && chmod 700 pgdata'
   # stage compose.ha.yml (templates/compose.ha.yml, image built from templates/postgres/Dockerfile),
   # postgres/pg_hba.conf (templates/postgres/pg_hba.conf: copy the app/pgbouncer lines from
   # today's pg_hba first, pin <COMPOSE_SUBNET> in docker-compose.yml), walg.env,
   # and in .deploy.env: COMPOSE_FILE=docker-compose.yml:compose.ha.yml
   # PHASE 1 ONLY: in compose.ha.yml set db `restart: unless-stopped` (no controller yet to start it)
   docker compose up -d db
   docker compose exec -T -u postgres db psql -U postgres -Atc "show data_directory; show wal_log_hints; show archive_mode"
   ```
   Expect `/var/lib/postgresql/data/pgdata`, `on`, `on`, and `show hba_file` =
   `/etc/postgresql/pg_hba.conf`. Check the app signs in (pg_hba allows it) and that
   `psql -h <A_WG_IP> -U postgres` from another host is REJECTED. Then `docker compose up -d worker worker_fast`
   and check the app.
5. Install the role watcher and checks: `infra/scripts/` to `/opt/sorento-crm2/infra/scripts/`,
   `/etc/sorento-ha/ha-pg.env` from `infra/templates/ha-pg.env.example`, the role watcher unit,
   `.ha-image-tag` from the running worker's image SHA, `ha-checks.sh` cron with
   `EXPECT_REPLICAS=0`. Load softdog (`infra/templates/host/README.md`) but do not start
   `cf-failover` yet.
6. First WAL-G base backup: `docker compose exec -T -u postgres db wal-g backup-push "$PGDATA"`;
   `ha-checks.sh` green.

Rollback of phase 1: `COMPOSE_FILE` back to the plain compose and `docker compose up -d db` (the
data directory stays in `pgdata/`, so set `PGDATA` in the plain compose too).

## Phase 2: node B (after n8n is stopped and its 14-day stop has ended)

1. Fresh OS, Docker, edge rules, WireGuard (`infra/templates/wireguard/`), host psql client
   (`postgresql-client-17`), the same `/opt/sorento-crm2` files as node A (compose, `.env`,
   `.deploy.env`, nginx, `postgres/pg_hba.conf`: byte-identical), its own
   `/etc/sorento-ha/ha-pg.env` (NODE_NAME=crm-b, PEER_HOST = A's private address), `pgpass` files
   and `/etc/sorento-ha/alert.curl` (mode 600).
2. On node A: `SELECT pg_create_physical_replication_slot('crm_b', true);` and
   `ALTER SYSTEM SET primary_conninfo = 'host=<B_WG_IP> user=replicator application_name=crm-a';`
   `ALTER SYSTEM SET primary_slot_name = 'crm_a';` (both ignored while A is primary; used if it
   ever becomes a standby).
3. Seed node B (copies the whole database; about 54 GB, tens of minutes; A keeps serving):
   ```
   docker compose run --rm --no-deps -T -u postgres --entrypoint sh db -c \
     "pg_basebackup -h <A_WG_IP> -U replicator -D /var/lib/postgresql/data/pgdata -X stream -c fast \
      && echo \"primary_conninfo = 'host=<A_WG_IP> user=replicator application_name=crm-b'\" >> /var/lib/postgresql/data/pgdata/postgresql.auto.conf \
      && echo \"primary_slot_name = 'crm_b'\" >> /var/lib/postgresql/data/pgdata/postgresql.auto.conf \
      && touch /var/lib/postgresql/data/pgdata/standby.signal"
   docker compose start db   # or up -d db the first time
   ```
   Check on A: `select application_name, state from pg_stat_replication;` shows `crm-b streaming`.
4. App on B: the first two-node release (below) brings the colours up with `SKIP_MIGRATIONS=1`.
   TLS for the public host on B by DNS-01 (Cloudflare token: Zone, DNS: Edit, this zone only).
   Role watcher on B (it keeps the workers stopped there).
5. Allowlists for B's egress address (OpenAI and any provider with one).
6. GitHub: add secrets `SSH_HOST_B` (and B's deploy key) and `SSH_KNOWN_HOSTS` (both hosts'
   public keys: `ssh-keyscan <host>` output, compared with `ssh-keygen -lf
   /etc/ssh/ssh_host_ed25519_key.pub` run on each box). From the next release on, `deploy.yml`
   runs `scripts/ha_release.sh`: primary first, then the standby; it refuses a host whose key
   does not match.

## Phase 3: Cloudflare and the controllers

1. Cloudflare (dashboard): monitor HTTPS `GET /api/v1/health/role`, expected 200, Host header =
   the public host, interval 60 s, retries 1, timeout 5 s. Pools `node-a` and `node-b`, one
   endpoint each, that monitor, consecutive down 2, up 1. Load balancer on the public host:
   DNS-only, TTL 30 s, steering off, default pools `node-a`, `node-b`, fallback `node-b`.
2. API token: Account, Load Balancing: Read, this account only; save as
   `/etc/sorento-ha/cf-token` (mode 600) on both nodes; pool ids into each `ha-pg.env`.
3. On node A, switch db back to `restart: "no"` in `compose.ha.yml` (the controller now starts it
   after a reboot, as a standby: rule D1).
4. `systemctl enable --now cf-failover role-watcher` on both nodes. Check the logs show `started:`
   and no action on either; `ha-checks.sh` with `EXPECT_REPLICAS=1` green on both.

Rollback of phase 3: `systemctl stop cf-failover` on both (disarms the watchdog), set the LB's
default pool to `node-a` only. Postgres keeps replicating; nothing promotes.

## Phase 4: prod drills (owner window; plan section 9a)

Record every time measured into the plan, section 10.

1. Link only: `wg-quick down wg0` on B for 5 minutes. Expect: no failover, alert "peer
   unreachable", A keeps serving. `wg-quick up wg0`: B streams again.
2. App crash on A: `docker compose stop backend_<active>` on A. Expect: autoheal does NOT restart
   a stopped container, so Cloudflare marks A down; after 15 min A fences itself, B promotes about
   7 min later. (Shorten `APP_SICK_AFTER` for the drill only if the owner wants.)
3. Whole box A: hPanel Stop on A. Expect users on B in about 8-11 minutes; a test WhatsApp gets
   its reply from B; staff stay signed in.
4. A returns: hPanel Start. Expect A as a standby following B (alert "rejoined" or "RE-SEEDED"),
   users stay on B.

## When something looks wrong

- Alert "TWO PRIMARIES": never expected. The controller already fenced the node Cloudflare does
  not see. Check `infra/scripts/ha-pg.sh observe` on both; page crew.
- Alert "too far behind; NOT promoting": the standby lagged more than 16 MB when A died. Nothing
  promotes automatically (it would lose more than allowed). Options: bring A back, or accept the
  loss and promote by hand: confirm A is stopped (hPanel), `systemctl stop cf-failover` on B FIRST
  (a running controller fences a node it did not promote itself, within one tick), then
  `docker compose exec -T -u postgres db psql -U postgres -c "select pg_promote()"` on B. Start
  `cf-failover` on B again only once A is back as B's standby.
- Stop everything automatic: `systemctl stop cf-failover` on BOTH nodes, standby first. Never stop
  it on the primary alone: that switches off the primary's fence while the standby can still
  promote (two writers if the primary is then cut off).

## Disaster restore (Malaysia-wide outage)

Both nodes down. Only if the outage is long enough to justify it (owner's call): provision a VPS
in another region from the infra repo, restore the newest WAL-G base backup plus WAL from R2
(`wal-g backup-fetch`, recovery to the latest point: RPO about 60 s, `archive_timeout`), start it
as a single node (controller not started), point the LB's pools or the DNS record at it
(`scripts/ops/cf-proxy.py`), add its egress address to the OpenAI allowlist. Hours, not minutes.
When Malaysia returns, rebuild A and B as standbys of it (phase 2 steps 2-3).
