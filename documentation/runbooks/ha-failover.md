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

Convention in this runbook: a block headed **READ-ONLY** changes nothing and can run any time; a
block headed **THIS CHANGES PROD** changes the box and runs only in a window the owner has
chosen, with crew on the call. Paste outputs into the private crew folder, never into the repo
or a PR (the checks below print setting NAMES and states, never secret values).

1. **READ-ONLY** pre-checks on node A (any time, about 1 minute):
   ```
   # READ-ONLY: nothing below changes prod.
   cd /opt/sorento-crm2

   # Postgres: version, layout, the HA-relevant settings, size
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -At \
     -c "show server_version" -c "show data_directory" -c "show hba_file" \
     -c "show wal_level" -c "show wal_log_hints" -c "show data_checksums" \
     -c "show archive_mode" -c "show max_wal_senders" -c "show max_replication_slots" \
     -c "show shared_preload_libraries" -c "show max_connections" \
     -c "select pg_size_pretty(sum(pg_database_size(datname))) from pg_database" \
     -c "select count(*) from pg_replication_slots" \
     -c "select rolname from pg_roles where rolreplication"'

   # pg_hba as it is today (rules only, no passwords live here)
   docker compose exec -T db sh -c 'grep -Ev "^[[:space:]]*(#|$)" "$(psql -U "$POSTGRES_USER" -d postgres -Atc "show hba_file")"'

   # The db service: image, volumes, restart policy, env NAMES only (values never printed)
   docker compose config --format json | python3 -c 'import json,sys
   d=json.load(sys.stdin)["services"]["db"]
   print("image:", d.get("image")); print("restart:", d.get("restart"))
   print("volumes:", [v.get("source","")+" -> "+v.get("target","") for v in d.get("volumes",[])])
   print("env names:", sorted((d.get("environment") or {}).keys()))'

   # The compose network the app reaches Postgres on (for <COMPOSE_SUBNET> in pg_hba.conf)
   for n in $(docker inspect "$(docker compose ps -q db)" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'); do
     echo "$n $(docker network inspect "$n" --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}')"
   done

   # Host: disk, memory, CPUs, clock, watchdog module, deploy files and their modes
   df -h / /var/lib/docker 2>/dev/null; free -m; nproc
   timedatectl show -p NTPSynchronized --value
   lsmod | grep -q softdog && echo "softdog loaded" || echo "softdog NOT loaded"
   stat -c '%a %U %n' . .deploy.env .active_color 2>/dev/null
   ls -l backups/pre-migrate 2>/dev/null | tail -3
   ```
   Note the data directory. If it is the volume root (`/var/lib/postgresql/data`), step 4 moves it
   into `pgdata/`. Copy `shared_preload_libraries` into `compose.ha.yml` and today's app lines from
   pg_hba into `templates/postgres/pg_hba.conf`.

1b. **READ-ONLY** A-B round trip (plan section 9b; decides `SYNC_MODE` and the active-active
   option). Run on node A against node B (B still runs n8n; this only sends pings), then the same
   on B against A. Use B's private address once WireGuard exists, its public address until then.
   ```
   # READ-ONLY: nothing below changes prod.
   PEER="<B_ADDRESS>"          # replace; on node B use "<A_ADDRESS>"
   ping -c 100 -i 0.2 "$PEER" | tail -2          # the rtt min/avg/max/mdev line
   # If ICMP is filtered: TCP connect time to SSH, 20 samples, in ms
   python3 -c 'import socket,time,statistics,sys
   h=sys.argv[1]; t=[]
   for _ in range(20):
       s=time.perf_counter(); c=socket.create_connection((h,22),timeout=3); t.append((time.perf_counter()-s)*1000); c.close(); time.sleep(0.2)
   print("tcp connect ms: min %.2f median %.2f max %.2f" % (min(t), statistics.median(t), max(t)))' "$PEER"
   ```
   Record avg/median in plan section 9b. Under 2 ms: `SYNC_MODE=remote_write` becomes the
   recommendation (owner Q5). Each page that runs 30 sequential queries would pay about 30 x the
   round trip if B's app ever used A's database (option 9b).
2. **READ-ONLY** check: a fresh backup exists and restores (`scripts/ops/backup-db.sh`, the weekly restore test).
3. **THIS CHANGES PROD** (no downtime): replication role (owner types the password at the prompt; it never lands in shell history):
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
4. **THIS CHANGES PROD, WINDOW** (about 2-3 minutes of downtime: one Postgres stop and start):
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
5. **THIS CHANGES PROD** (no downtime): install the role watcher and checks: `infra/scripts/` to `/opt/sorento-crm2/infra/scripts/`,
   `/etc/sorento-ha/ha-pg.env` from `infra/templates/ha-pg.env.example`, the role watcher unit,
   `.ha-image-tag` from the running worker's image SHA, `ha-checks.sh` cron with
   `EXPECT_REPLICAS=0`. Load softdog (`infra/templates/host/README.md`) but do not start
   `cf-failover` yet.
6. **THIS CHANGES PROD** (no downtime, disk and network load): first WAL-G base backup: `docker compose exec -T -u postgres db wal-g backup-push "$PGDATA"`;
   `ha-checks.sh` green.

Rollback of phase 1: `COMPOSE_FILE` back to the plain compose and `docker compose up -d db` (the
data directory stays in `pgdata/`, so set `PGDATA` in the plain compose too).

## Phase 2: node B (after n8n is stopped and its 14-day stop has ended): THIS CHANGES PROD

Every step below changes a box (step 2 changes node A without downtime; the rest build node B).

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

## Phase 3: Cloudflare and the controllers: THIS CHANGES PROD

Every step below changes prod: from step 4 on, failover is automatic.

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

## Phase 4: prod drills (owner window; plan section 9a): THIS CHANGES PROD, causes outages

Each drill takes the CRM down or moves it between boxes; run only in an announced window.

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

## Phase AA: active-active app tier (owner 4 Nov; plan section 12; after phase 3)

Both nodes serve the app; one writable database and one Redis master stay on the primary node.
Templates: `infra/templates/active-active/`.

0. **READ-ONLY** checks (any time):
   ```
   # READ-ONLY: nothing below changes prod.
   cd /opt/sorento-crm2
   # Existing files: every attachment must live in object storage, none on a local path.
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<'SQL'
   select coalesce(storage_provider, 'none') as provider, count(*) from attachments group by 1 order by 1;
   select count(*) as not_a_url from attachments where coalesce(file_path, '') <> '' and file_path not like 'http%';
   SQL
   # Which database / Redis host each app service uses today (host:port only, never the password).
   docker compose config --format json | python3 -c 'import json,sys,re
   for n,svc in sorted(json.load(sys.stdin)["services"].items()):
       env=svc.get("environment") or {}
       for k in ("DATABASE_URL","REDIS_URL","SCHEDULER_LEADER_DATABASE_URL"):
           v=env.get(k)
           if v: print(n, k, v.rsplit("@", 1)[-1].split("?", 1)[0])'
   ```
   Expect `not_a_url` = 0 and every provider `s3` or `r2`. Expect every backend-image service's
   `DATABASE_URL` to name `pgbouncer:6432`; a service that names `db` directly must be moved to
   pgbouncer first (`SCHEDULER_LEADER_DATABASE_URL` stays direct: it runs only on the primary).
1. **THIS CHANGES PROD, WINDOW** (about 1-2 minutes per node: Redis and pgbouncer restart, then
   one app colour swap), on BOTH nodes, the primary first:
   - Redis users (`templates/active-active/users.acl`: admin, app, repl, hacheck) and
     `redis.conf` in `/etc/sorento-ha/`, mode 0640 root:999; every password from
     `openssl rand -hex 32` (hex: safe in URLs and HAProxy config); the admin password ONLY in
     `/etc/sorento-ha/redis-admin.env` (`REDISCLI_AUTH=...`, mode 0600 root, the same on both
     nodes), never in the project `.env`. Check (READ-ONLY) that no other service gets it:
     `docker compose config --format json | python3 -c 'import json,sys; print([n for n,s in json.load(sys.stdin)["services"].items() if n != "redis" and "REDISCLI_AUTH" in (s.get("environment") or {})])'`
     must print `[]`;
   - `/etc/sorento-ha/haproxy-redis.cfg` (the hacheck password) mode 0640 root:<HAPROXY_UID>;
     `/etc/sorento-ha/pgbouncer-admin.pgpass` mode 0600 owned by the pgbouncer container uid;
     `/etc/sorento-ha/pgbouncer-hba.conf`; pgbouncer KEEPS prod's
     `pool_mode` (read it first: `SHOW CONFIG` on the pgbouncer admin console; never switch session
     to transaction, the app holds session-level advisory locks); every role that goes through
     pgbouncer today (an analytics read-only URL too, if any) needs its line in
     `pgbouncer-hba.conf`;
   - `infra/templates/host/docker-user-wg.sh` on both nodes, run at boot after Docker (5432 and
     6379 on the private address: only the peer over wg0; only the CRM compose network out over
     wg0);
   - the app lines over the link in `postgres/pg_hba.conf` (template, ACTIVE-ACTIVE block) and
     `select pg_reload_conf()` on the primary;
   - `ha/pgbouncer.ini`; `ha/route/` root-owned 0755 with `route.ini` from `route.ini.initial`
     on the PRIMARY node; the pgbouncer userlist;
   - `COMPOSE_FILE=docker-compose.yml:compose.ha.yml:compose.aa.yml` in `.deploy.env`;
   - app `REDIS_URL` -> `redis://app:<APP_PASSWORD>@redis_proxy:6380/<db>`;
   - `docker compose up -d redis redis_proxy pgbouncer`; then on the STANDBY node let the
     adapter write its route and make its Redis a replica (never by hand):
     `set -a; . /etc/sorento-ha/ha-pg.env; set +a; /opt/sorento-crm2/infra/scripts/ha-pg.sh route peer`;
   - a normal release (both nodes, `scripts/ha_release.sh`) to bring the app colours up on the
     new env.
   Check on each node: the app answers `GET /api/v1/health/role` 200 locally;
   `docker compose exec -T redis redis-cli --user admin role` says master on the primary node,
   slave on the other (the `default` user is off: a plain `redis-cli`, and any `redis-cli ping`
   healthcheck in the prod compose, needs `--user`). Docker must be 28 or later, or add a DROP for
   the 127.0.0.1-published 5432/6379 from non-loopback sources: older Docker lets a neighbour on
   the provider network reach loopback-published ports.
2. **THIS CHANGES PROD** (traffic starts reaching node B): Cloudflare: replace the two pools with
   ONE pool holding both endpoints (same monitor `GET /api/v1/health/role`, 60 s, down 2, up 1);
   LB default pool = that pool, DNS-only TTL 30 s. Note each endpoint's address for the env.
3. **THIS CHANGES PROD**: in `/etc/sorento-ha/ha-pg.env` on both nodes add the active-active
   block (`ACTIVE_ACTIVE=1`, `CF_ORIGIN_SELF`, `CF_ORIGIN_PEER`, `CF_POOL_SELF` = the one pool,
   `ROUTE_FILE`, `PGB_LOCAL_HOST`, `PGB_ADMIN`, `PGB_DATABASES`, `REDIS_CLI`), remove `APP_SICK_AFTER` (it must be
   0) and `CF_POOL_PEER` (the old per-node pool is gone; a different value is refused), then `systemctl restart cf-failover` on the standby node first, then the primary node.
   The logs must show `started: ... app_sick_after=0s` and no action.
4. **THIS CHANGES PROD, causes an outage on one node** (drill, announced window):
   `docker compose stop backend_<active>` on node A. Expect: A's origin leaves the pool within
   about 2 minutes, users keep working through B, no fence and no promotion in either
   controller's log. Start it again; A returns to the pool. Then the same on node B.
5. **READ-ONLY**: measure the A-B round trip (phase 1 step 1b) and record it in plan section 12c.

In active-active a standby that the release cannot reach keeps serving the OLD code to real users
(`scripts/ha_release.sh` fails the run): fix the node or take its endpoint out of the pool until
the next release reaches it.

Rollback of phase AA: Cloudflare back to the two pools in failover order (phase 3), remove
`ACTIVE_ACTIVE` and the active-active block from `ha-pg.env`, restart `cf-failover` on both.
Redis and pgbouncer on the primary node keep working as they are.

## When something looks wrong

- Alert "TWO PRIMARIES": never expected. The controller already fenced the node Cloudflare does
  not see. Check `infra/scripts/ha-pg.sh observe` on both; page crew.
- Alert "too far behind; NOT promoting": the standby lagged more than 16 MB when A died. Nothing
  promotes automatically (it would lose more than allowed). Options: bring A back, or accept the
  loss and promote by hand (**THIS CHANGES PROD**): confirm A is stopped (hPanel), `systemctl stop cf-failover` on B FIRST
  (a running controller fences a node it did not promote itself, within one tick), then
  `docker compose exec -T -u postgres db psql -U postgres -c "select pg_promote()"` on B. Start
  `cf-failover` on B again only once A is back as B's standby.
- **THIS CHANGES PROD**: stop everything automatic: `systemctl stop cf-failover` on BOTH nodes, standby first. Never stop
  it on the primary alone: that switches off the primary's fence while the standby can still
  promote (two writers if the primary is then cut off).

## Disaster restore (Malaysia-wide outage)

Both nodes down. Only if the outage is long enough to justify it (owner's call): provision a VPS
in another region from the infra repo, restore the newest WAL-G base backup plus WAL from R2
(`wal-g backup-fetch`, recovery to the latest point: RPO about 60 s, `archive_timeout`), start it
as a single node (controller not started), point the LB's pools or the DNS record at it
(`scripts/ops/cf-proxy.py`), add its egress address to the OpenAI allowlist. Hours, not minutes.
When Malaysia returns, rebuild A and B as standbys of it (phase 2 steps 2-3).
