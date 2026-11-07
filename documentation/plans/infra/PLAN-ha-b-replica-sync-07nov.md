# PLAN: node B exists as a replica; deploy both, then LB, then no-data-loss failover (HA-CF-FAILOVER, 7 Nov)

Status: Build (7 Nov evening, HA-TONIGHT). Step 1 built. Tonight: manual runbook `documentation/runbooks/ha-tonight-07nov.md`. Section 3 build contract in section 11, red tests first. Track: full.
Track: full (prod infra). Nothing in this lane touches production: every prod step is an owner
command, and every block in section 5 is READ-ONLY.

Builds on `PLAN-ha-cf-failover-04nov.md` (PR #2166: controller, adapter, drill, two-node release)
and its section 12 (PR #2170: active-active app tier, stacked on #2166). Same rules: no
addresses, hostnames, keys or staff names in the repo; UNVERIFIED marks every fact not checked
from the repo.

## 0. New facts and the owner's order (7 Nov, about 10:30)

- Node B is BUILT. The app runs on the n8n box (KVM 8). Its Postgres is a streaming REPLICA of
  the main database on node A (KVM 4). The 4 Nov plan assumed a fresh rebuild from our templates
  (runbook phase 2). The owner built it himself, so it is not known yet which of our templates it
  follows (section 2, G1).
- The owner's order:
  1. The DEPLOY puts the same new version on BOTH nodes every release. Today `deploy.yml` deploys
     only node A.
  2. Only then is the Cloudflare load balancer switched on: active-active app tier (4 Nov ruling).
     Both nodes serve, there is ONE writable database, and node B's app writes to the primary.
  3. Automatic failover: when node A's database is down, B's replica is promoted WITHOUT data loss
     and WITHOUT conflicting writes (fencing, no split brain, Cloudflare LB health as the witness).

## 1. What #2166 and #2170 already cover

| Owner step | Covered by | Evidence |
|---|---|---|
| 1 deploy both | #2166: `scripts/ha_release.sh` asks each host its role, refuses unless exactly one is primary, deploys the primary first (migrations, snapshot), then each standby in standby mode, then re-checks roles | `scripts/ha_release.sh:33-37` (role per host), `:51-60` (exactly one primary), `:65-67` (primary first), `:73-84` (standbys), `:87-90` (failover during release fails it) |
| | `deploy.yml` runs it only when the secrets `SSH_HOST_B` and `SSH_KNOWN_HOSTS` exist; without them, today's single-host steps run | `.github/workflows/deploy.yml:2193-2224` |
| | standby mode: `SKIP_MIGRATIONS=1`, no snapshot, workers untouched, waits for the replicated alembic head | `scripts/blue_green_deploy.sh:512-521`, `:642` |
| 2 LB, active-active | #2170: one pool with both nodes as origins, per-node pgbouncer that follows the primary (rule R1), Redis replicated with a per-node HAProxy picking the master, P2 app-sick failover off | `PLAN-ha-cf-failover-04nov.md` section 12a (on the #2170 branch), drill 12e |
| 3 automatic failover, no split brain | #2166: `cf_failover.py` rules P1 (lease, fence first), S1 (promote only after `PROMOTE_AFTER` of Cloudflare-unhealthy + no stream + peer unreachable), D1 (a node never starts writable by itself); watchdog | `infra/scripts/cf_failover.py:178` (`decide`), `:312-321` (S1, lag check); drill 8/8 and AA 7/7, never two writers |
| 3 without data loss | NOT covered. See G4 | `cf_failover.py:279` (P4 drops the sync standby the moment it stops streaming, nothing records that), `:59` (`MAX_LAG` 16 MB lets B promote while missing commits) |

## 2. What changes now that B exists, and the gap list

- **G1. B was not built from our templates. Unknown: does it match what the controller expects?**
  The controller and adapter assume:
  - Postgres 17 in the `sorento-pg17` image (WAL-G inside, `templates/postgres/Dockerfile`);
  - B's `application_name` = its node name (`ha-pg.sh:86`). A matches the sync standby and
    "peer streaming" on it (`ha-pg.sh:103`);
  - a replication slot for B on A (`primary_slot_name`, rule P5);
  - the replication user and the `pg_hba.conf` mounted outside PGDATA (`templates/postgres/pg_hba.conf`);
  - the link over WireGuard, not the public internet;
  - the deploy directory `/opt/sorento-crm2` (`ha_release.sh` `REMOTE_DIR`).
  The READ-ONLY checks in section 5 answer all of these. Then either we fit `ha-pg.env` to B as it
  is, or we re-seed B from the template (card Q1).
- **G2. Node A prep (runbook phase 1) state unknown.** Without a slot, A can recycle WAL that B
  still needs: B then falls off and needs a full re-seed. Without `wal_log_hints=on` (off on
  1 Nov, `PLAN-n8n-decom-ha-01nov.md:179`) or data checksums, `pg_rewind` cannot rejoin the old
  primary after a failover, so every rejoin is a full copy (about 54 GB). Both are phase 1 items.
  `wal_log_hints` needs one Postgres restart on A.
- **G3. Two-node deploy needs HA compose mode on BOTH nodes today.** `blue_green_deploy.sh --role`
  answers `single` unless `COMPOSE_FILE` loads `compose.ha.yml` (`blue_green_deploy.sh:77-78`,
  `:119`). `ha_release.sh` then refuses with "not an HA node". Turning on `compose.ha.yml` on A:
  - moves A's db onto the template image and its replication settings, which recreates A's db
    container (a restart);
  - puts the workers behind the `promoted` profile (`compose.ha.yml:89-96`), so the role watcher
    must run on A first or A's workers never start.
  That is steps 2-3 work arriving before step 1. The smaller path: role detection that works on
  the plain compose (read `pg_is_in_recovery()` from the `db` service whatever the compose files
  are; `single` only when the box has no replica relation). Then step 1 needs no restart on A.
  About 40 lines plus tests (card Q2).
- **G4. "No data loss" is not met by the built design.** P4 makes B the sync standby while it
  streams and EMPTIES `synchronous_standby_names` the moment it stops (`cf_failover.py:279`).
  Nothing outside A records that A went async.
  The failure: the link breaks (or B restarts). After `wal_sender_timeout` A drops B and keeps
  committing alone. Later A dies. S1 promotes B after the window, because B's lag check compares
  against the LAST position B SAW (`cf_failover.py:317`), not A's real end. Every commit made
  since the drop is lost, and nothing alerts. Section 3 closes this.
- **G5. Workers and senders on B today: unknown.** The plain compose starts `worker` and
  `worker_fast` with no profile. If B's app or workers write to A's database directly (not to
  B's read-only replica), B's scheduler and RQ senders could run beside A's: double WhatsApp
  sends and double scheduled jobs. The leader lock (`app/scheduler/leader.py:53-91`) guards only
  the APScheduler, not RQ jobs. READ-ONLY check 5.B3 answers it. If they run, stopping them on B
  is the first prod step, before anything else.
- **G6. Active-active pieces on B.** #2170 needs pgbouncer (route include), HAProxy for Redis
  and a Redis replica on both nodes. B's current Redis and DB endpoint are unknown (5.B3).
- **G7. Order of merges.** #2166 (deploy both + dormant controller), then #2170 (active-active),
  then a new PR for section 3. Each PR changes the repo only. The controller is not started on
  prod until section 3 is merged, because step 3 needs "no data loss".

## 3. No data loss: synchronous replication and its trade-off

### 3a. What each setting costs and guarantees

Only a transaction that WROTE something waits for the standby. A read-only transaction (every
GET; psycopg2's BEGIN ... COMMIT with no write) gets no transaction id and never waits. Most
write requests make one COMMIT, so the cost below is paid once per saved form. It is also paid
by the session touch, at most once per user per 10 minutes (`user_session_service.py:115-127`).

| `synchronous_commit` (B listed in `synchronous_standby_names`) | A commit returns when | Added per write commit | Loses acknowledged commits when |
|---|---|---|---|
| `local` / B not listed (async, built today) | A has flushed | 0 | A dies before B received them: normally under 1 s, up to `MAX_LAG` |
| `remote_write` | B has received it and written it to its OS (no fsync) | 1 RTT | A dies AND B's OS crashes at the same moment (one power event on both) |
| `on` | B has flushed it to disk | 1 RTT + B's WAL fsync (VPS NVMe typically 0.2-2 ms, UNVERIFIED: 5.B4 measures it) | never, for any single failure |
| `remote_apply` | B has also replayed it | 1 RTT + fsync + replay | as `on`. Not needed: no app reads from B (active-active routes B's app to the primary) |

At a measured A-B RTT of (not measured yet, 5.AB):

| RTT | `remote_write` per write | `on` per write (fsync 1 ms assumed) | A write from B's app (active-active: B to A, then A to B) |
|---|---|---|---|
| 0.5 ms | +0.5 ms | +1.5 ms | +1 ms sync on top of section 12c's link cost |
| 1 ms | +1 ms | +2 ms | +2 ms |
| 2 ms | +2 ms | +3 ms | +4 ms |
| 5 ms | +5 ms | +6 ms | +10 ms |

Below 5 ms neither is noticeable on a save. Throughput is unaffected at this CRM's write rate:
commits from concurrent requests are flushed and confirmed together.

### 3b. When B is down: writes must not block forever

- `synchronous_standby_names = 'ANY 1 (crm-b)'` means the same as `'crm-b'` with ONE standby.
  "ANY 1" only adds anything once there is a third copy. The fallback must come from the
  controller (P4), not from Postgres. Postgres itself waits forever.
- **Write stall when B dies:**
  - B stops cleanly: about one controller tick (15 s).
  - The link is cut with no reset: `wal_sender_timeout` (10 s in `compose.ha.yml:48`), plus one
    tick, plus the R2 write below. About 25 s worst case.
  During the stall, saves on A wait; nothing is lost and nothing errors unless a client times
  out first.
- **The hole (G4) and the fix: a sync record in R2.** R2 already holds the WAL archive
  (`templates/walg.env.example`). It is an object in an existing bucket, not a server, so it stays
  inside the 4 Nov "no witness server" ruling. The card says this plainly.
  - **P4' drop.** Before the primary empties `synchronous_standby_names`, it PUTs
    `ha/sync-state.json` = `{"mode": "async", "primary": "<node>", "since": <time>}` to R2. Only
    after a confirmed PUT does it drop the standby.
  - **P4' re-add.** When the standby streams again and has caught up, the primary sets it back
    in `synchronous_standby_names`. Then it writes `{"mode": "sync", ...}` (sync first, record
    second, so the record is never more optimistic than Postgres).
  - **S1' promote.** S1 also needs a fresh read of the record showing `mode == sync`, written by
    the peer. R2 unreachable counts as no (like a Cloudflare UNKNOWN).
    - Record `sync`: no acknowledged commit exists that B lacks. B promotes automatically, and
      its first action is to write `{"mode": "async", "primary": "<self>"}` (it has no standby
      yet).
    - Record `async`: B does NOT promote. It pages the owner with the record's `since` time
      (card Q5).
  - **Only the primary writes the record.** The P1 lease means the old primary has fenced
    before the new one promotes, so there is one writer. No conditional PUT is needed.
    Credentials: WAL-G's R2 key already on the node, signed with `curl --aws-sigv4`, so the
    controller stays stdlib-only.
  - **B and R2 both unreachable from A at once:** the PUT cannot confirm, so A keeps waiting
    (writes blocked) until either returns, and alerts at once (card Q4).
- **Result.**
  - Zero acknowledged commits are lost for any SINGLE failure: A dies, B dies, link cut, or R2
    down.
  - Failover stays automatic for every single failure.
  - The only non-automatic case is a double fault: B was already out (async), then A dies.
  - Commits A flushed but never acknowledged before it died are discarded when A rejoins
    (`pg_rewind`). Their clients got an error, not a success, so this is not data loss.
- **Build size:** P4' and S1' in `decide()`, a `sync-record` adapter verb, tests (the two-node
  world model gains "A wrote while async, then died": B must never promote), and drill scenarios
  (B down then A dies; R2 down then B down). About 1.5 lane-days, a new PR after #2170.

### 3c. Recommendation

`synchronous_commit = on` with P4' and S1', if the measured RTT is under about 3 ms and B's fsync
is under about 2 ms. Use `remote_write` if the RTT is 3-10 ms: it differs from `on` only in the
case where both boxes lose power together. Above 10 ms, reconsider. Until section 3 is merged
and switched on, keep `SYNC_MODE=off` and do not start the controller (async with automatic
promotion is exactly the silent-loss path in G4).

## 4. Step order (all prod steps are owner commands, reviewed before they run)

1. Owner runs the READ-ONLY checks in section 5 and pastes the redacted output on the PR.
2. If 5.B3 shows workers or a scheduler running on B: stop them on B (first prod step, owner).
3. Repo: Q2's change (role detection on the plain compose), merge #2166. Owner adds the secrets
   `SSH_HOST_B` + `SSH_KNOWN_HOSTS`. The next release deploys both nodes (owner step 1 done).
4. Node A prep (phase 1, one restart window): slot for B (if missing), `wal_log_hints=on`, WAL-G
   archive to R2, softdog.
5. Merge #2170; active-active pieces on both nodes (runbook phase AA); Cloudflare LB on (owner
   step 2). The controller is still not running: no automatic failover yet, no promotion either.
6. Merge the section 3 PR; controllers on (runbook phase 3); `SYNC_MODE=on`; prod drills
   (phase 4) (owner step 3).

## 5. READ-ONLY prod checks (owner runs them first; nothing below changes prod)

Paste the output with addresses and hostnames replaced by `<A>` / `<B>`. Run each block in the
CRM deploy directory of that node. `DB` is the compose db service (`db` unless yours differs).

### 5.A On node A

```bash
# READ-ONLY: nothing below changes prod.
cd /opt/sorento-crm2 2>/dev/null || echo "deploy dir is not /opt/sorento-crm2: tell us where it is"
echo "compose files: ${COMPOSE_FILE:-<unset>}"; grep -E '^COMPOSE_FILE=' .deploy.env 2>/dev/null
docker compose exec -T -u postgres db psql -U postgres -Atc "select version()"
docker compose exec -T -u postgres db psql -U postgres -c "
select name, setting from pg_settings where name in
 ('wal_level','wal_log_hints','data_checksums','synchronous_standby_names','synchronous_commit',
  'max_wal_senders','max_replication_slots','max_slot_wal_keep_size','wal_keep_size',
  'archive_mode','wal_sender_timeout','hot_standby_feedback','cluster_name') order by name;"
docker compose exec -T -u postgres db psql -U postgres -Atc "select 'archive_command set: '||(current_setting('archive_command') <> '')"
# Replication state and lag (one row per standby).
docker compose exec -T -u postgres db psql -U postgres -c "
select application_name, state, sync_state, write_lag, flush_lag, replay_lag,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)) as replay_behind
from pg_stat_replication;"
docker compose exec -T -u postgres db psql -U postgres -c "
select slot_name, slot_type, active, wal_status,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) as retained
from pg_replication_slots;"
# Which hba lines allow replication (types and users only).
docker compose exec -T -u postgres db psql -U postgres -c "
select type, database, user_name, auth_method from pg_hba_file_rules where 'replication' = any(database);"
# Running version of the app (image tags) and the active colour.
cat .active_color 2>/dev/null; docker compose ps --format '{{.Service}}\t{{.Image}}\t{{.Status}}'
df -h / /var/lib/docker 2>/dev/null; timedatectl | grep -E 'synchronized|NTP'
```

### 5.B On node B

```bash
# READ-ONLY: nothing below changes prod.
cd /opt/sorento-crm2 2>/dev/null || echo "deploy dir is not /opt/sorento-crm2: tell us where it is"
echo "compose files: ${COMPOSE_FILE:-<unset>}"; grep -E '^COMPOSE_FILE=' .deploy.env 2>/dev/null
docker compose exec -T -u postgres db psql -U postgres -Atc "select version()"
# B1: replica state and lag as B sees it.
docker compose exec -T -u postgres db psql -U postgres -c "
select pg_is_in_recovery() as replica,
       pg_last_wal_receive_lsn() as received, pg_last_wal_replay_lsn() as replayed,
       now() - pg_last_xact_replay_timestamp() as last_replayed_commit_age;"
docker compose exec -T -u postgres db psql -U postgres -c "
select status, slot_name, sender_port, latest_end_time, last_msg_receipt_time from pg_stat_wal_receiver;"
docker compose exec -T -u postgres db psql -U postgres -c "
select name, setting from pg_settings where name in
 ('primary_slot_name','hot_standby','hot_standby_feedback','wal_log_hints','data_checksums',
  'cluster_name','wal_receiver_timeout') order by name;"
# B2: is the link the WireGuard interface? (prints interface names only)
ip -brief link | awk '{print $1, $2}'
# B3: what B's app and workers talk to (host part only, never the password), and what runs.
docker compose ps --format '{{.Service}}\t{{.Image}}\t{{.Status}}'; cat .active_color 2>/dev/null
for s in backend_blue backend_green worker worker_fast; do
  docker compose exec -T "$s" python -c "import os,urllib.parse as u
for k in ('DATABASE_URL','REDIS_URL'):
    p=u.urlparse(os.environ.get(k,''));print('$s',k,p.hostname,p.port)" 2>/dev/null
done
docker compose exec -T redis redis-cli info replication 2>/dev/null | grep -E '^role|master_link_status'
# B4: WAL fsync speed on the disk that holds B's data. Not strictly read-only: it writes and
# deletes one scratch file next to PGDATA (no prod data touched), about 20 s of disk load.
docker compose exec -T -u postgres db sh -c 'f="$(dirname "$PGDATA")/fsync.test"; pg_test_fsync -s 2 -f "$f" 2>&1 | grep -A6 "one 8kB write"; rm -f "$f"'
df -h / /var/lib/docker 2>/dev/null; timedatectl | grep -E 'synchronized|NTP'
```

### 5.AB Round trip A-B (from A, then again from B with A's address)

```bash
# READ-ONLY: nothing below changes prod.
ping -c 100 -i 0.2 -q <the other node's private (or public) address> | tail -2
```

What each answer decides: version and image (G1, Q1), slot and `wal_log_hints` (G2, step 4),
`COMPOSE_FILE` (G3, Q2), `sync_state` and lag (section 3 baseline), B3 (G5: stop B's workers
first if they run), B4 + 5.AB (Q3 `on` vs `remote_write`).

## 6. Owner card (crew-ask on PR #2166, 7 Nov)

1. Node B as built: (a) adopt it as it is, fitting `ha-pg.env` and the slot and names to it after
   the checks; (b) re-seed B from our template image (`pg_basebackup`, about 54 GB; B's app paused
   meanwhile). Rec (a) if 5.B shows Postgres 17 with a slot. (b) only if the major version or
   image differs.
2. Deploy both nodes first: (a) a small change so the two-node release reads each node's role
   from today's plain compose. No restart on A; step 1 ships on its own. (b) Merge #2166 as it
   is. Both nodes must first switch to HA compose mode, which recreates A's db container and
   needs the role watcher running before A's workers start. Rec (a): it keeps your order.
3. Sync level: (a) `synchronous_commit=on` (zero loss for any single failure, about +1 RTT +
   1 ms per save); (b) `remote_write` (+1 RTT; loses data only if both boxes lose power at the
   same moment); (c) stay async (loses the last seconds when A dies). Rec (a) if the RTT is under
   3 ms, else (b).
4. B and R2 both unreachable from A at the same time: (a) saves on A wait until either one comes
   back, alert at once (strict no-loss); (b) after 60 s A goes async without the record (saves
   never wait more than 60 s, but a later loss of A could then lose those saves silently).
   Rec (a): it is a double fault, and R2 already carries the WAL archive.
5. A dies while B was already out of sync (a double fault: B was down or cut off first, A kept
   writing alone): (a) no automatic promotion; you are paged with the time B fell out, and you
   choose to wait for A or to promote and accept the loss; (b) automatic promotion after B replays
   what the R2 WAL archive holds (loses up to `archive_timeout`, 60 s). Rec (a): it is the only
   case where "automatic" and "no data loss" conflict, and a single failure never lands here.

## 7. Owner answers (7 Nov about 11:00, verbatim "I am ok with the HA recommendation")

- **Q1 (a)** adopt B as built; re-seed only if the checks show a different Postgres major or image.
- **Q2 (a)** the two-node release reads each node's role from today's plain compose; step 1 ships
  on its own, no restart on A.
- **Q3 (a)** `synchronous_commit=on` if the measured A-B RTT is under 3 ms, else (b) `remote_write`.
- **Q4 (a)** strict: saves on A wait while both B and R2 are unreachable, alert at once.
- **Q5 (a)** no automatic promotion when B was already out of sync: page the owner.

### 7a. Step 1 as built (Q2)

`blue_green_deploy.sh --role` on the plain compose (no `compose.ha.yml`) asks the plain `db`
service `pg_is_in_recovery()` as `$POSTGRES_USER` on the `postgres` database: `t` = standby,
`f` = primary. Any failure or other answer = `single`, which is exactly today's release, so a
single-host release never fails on the new query. A plain standby gets the same standby release
as the HA one (SKIP_MIGRATIONS=1 exported, no snapshot, workers untouched, waits for the
replicated alembic head) but writes no `.ha-image-tag` (no role watcher reads it there).
`ha_release.sh` is unchanged: it refuses unless exactly one host answers primary and every other
answers standby.

Note for the owner: start.sh honours SKIP_MIGRATIONS only if B's compose passes it to the backend
colours (the repo template does not, `sorento_crm/docker-compose.yml`). Either way B never
migrates: the release waits for the replicated head first, so `alembic upgrade head` finds
nothing to do, and any DDL on a replica would fail the new colour's health check, leaving the
old colour serving.

## 8. Section 5 results (owner, 7 Nov about 11:20) and what they change

Facts (addresses and hostnames left out on purpose):
- **Node A.** Deploy dir `/opt/sorento-crm2`, `COMPOSE_FILE` unset (plain compose).
  - Postgres: 17.9 on `pgvector/pgvector:pg17`, the same base as our template (`templates/postgres/Dockerfile:4`).
  - Settings: `wal_level=replica`, `wal_log_hints=off`, `data_checksums=off`, `archive_mode=off` (an `archive_command` is set but never runs), `synchronous_commit=on` with an empty `synchronous_standby_names` (so: async), `wal_sender_timeout=60s`, `max_slot_wal_keep_size=-1`, `wal_keep_size=0`.
  - One standby: `application_name=sorento_crm_replica`, streaming, async, write/flush/replay lag 0.86 / 1.42 / 1.63 ms, 0 bytes behind. Physical slot `sorento_crm_replica_slot`, active.
  - Running: blue colour, workers on `61e9d217`, pgbouncer, redis 7. Disk 58% of 193G. NTP synced.
- **Node B.** Deploy dir `/opt/sorento-crm2`, `COMPOSE_FILE` unset. The compose `db` service is not running there, so the replica runs somewhere else. No WireGuard interface: replication runs over `eth0`. `.active_color` blue. The B3 loop printed nothing. Disk 30% of 387G. NTP synced.

New and changed gaps:
- **G8 No WAL archive.** `archive_mode=off`, so nothing has ever been archived to R2.
  - The PITR copy assumed in the 4 Nov plan (section 2 row 2) does not exist. Recovery today relies on the dumps (`scripts/ops/backup-db.sh`) only.
  - Q5's alternative (b) ("replay the R2 archive") was never available. Q5 (a) stands.
  - The R2 sync record (section 3b, Q4) does not depend on the archive. It needs only an R2 bucket and a key on both nodes.
  - Fix: `archive_mode=on` with WAL-G. That needs a restart, so it goes in the same window as G2.
- **G2 confirmed.** `wal_log_hints` and `data_checksums` are both off, so `pg_rewind` cannot run. Until a restart turns `wal_log_hints` on, every rejoin of an old primary is a full re-seed (about 54 GB; fast over a link with under 1 ms RTT).
- **G9 A dead standby can fill A's disk.** `max_slot_wal_keep_size=-1` lets the slot keep WAL without limit while B is down. Fix: set it to 20GB. That is a reload, no restart.
- **G10 Sync drop stall.** `wal_sender_timeout=60s`: with sync on, a cut link would stall saves for about 75 s before P4 drops B. Fix: set 10s (reload, no restart; `compose.ha.yml:48` value).
- **G11 Names.** The adapter derives the slot from the node name (`ha-pg.sh:55-58`), but B uses `application_name` `sorento_crm_replica` and slot `sorento_crm_replica_slot`.
  - Adopting B (Q1 (a)) needs separate `PEER_APP_NAME` / `PEER_SLOT` config values.
  - Small adapter change plus tests, in the section 3 PR.
- **G12 Security: `host ... trust` lines in A's pg_hba.** Two `host all trust` rows match replication.
  - The `postgres` image ships two such rows for loopback only (`127.0.0.1/32`, `::1/128`). If these are those two, they are reachable only from inside A's db container: low risk.
  - If either has any other CIDR, anyone in that range can copy the whole database without a password. Then it is a blocker to fix before anything else (8c checks it).
- **G13 Replication over eth0, no WireGuard.** The scram rows for `replicator` work over the provider or public network. Two things are unknown:
  - whether the stream uses TLS (8c checks it);
  - whether A's 5432 is reachable from the internet (8c checks it).
  WireGuard (the template's design) or TLS plus a firewall rule limited to B is needed before the controller runs: the controller also sends peer queries over this path.
- **G14 B's database is not the compose `db`.** Step 1 impact:
  - `--role` on B reads `single` (psql fails), so `ha_release.sh` refuses the whole release ("not an HA node", nothing deployed).
  - **Do not add `SSH_HOST_B` until B answers `standby`.** If the replica is a compose service under another name, `DB_SERVICE=<name>` in B's `.deploy.env` is enough (`blue_green_deploy.sh:107`). If it is a host install, step 1 needs a small extra change.
  - 8b finds out which, and also how B's app connects (B3 printed nothing).
- **Q3 resolved by the measurement.** A write_lag of 0.86 ms means the RTT is under 1 ms, so `synchronous_commit=on` per Q3 (a). 8c's ping confirms it.

### 8b. Next READ-ONLY block, node B (finds the replica and the app's connections)

```bash
# READ-ONLY: nothing below changes prod. Passwords are masked before printing.
cd /opt/sorento-crm2
docker compose ls
docker compose config --services
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
ss -ltnp 2>/dev/null | grep -E ':(5432|6432|6379)\b'
systemctl list-units --type=service --all 2>/dev/null | grep -iE 'postgres|pgbouncer|redis'
ps -eo user,args | grep -E '[p]ostgres .*-D|[p]ostmaster' | cut -c1-200
# Every container whose image looks like Postgres: role and version.
for c in $(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /postgres|pgvector|postgis/ {print $1}'); do
  echo "== $c"; docker exec "$c" sh -c 'psql -U "${POSTGRES_USER:-postgres}" -d postgres -Atc "select pg_is_in_recovery(), version(), current_setting(\$\$primary_slot_name\$\$), current_setting(\$\$hot_standby_feedback\$\$)"' 2>&1 | head -3
done
# How every running container reaches Postgres and Redis (scheme, host, port, db; no password).
for c in $(docker ps --format '{{.Names}}'); do
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" \
    | grep -E '^(DATABASE_URL|DIRECT_URL|REDIS_URL)=' \
    | sed -E 's#://[^@/]*@#://***@#' | sed "s#^#$c #"
done
```

### 8c. Next READ-ONLY block, node A (pg_hba with addresses, link, exposure, ping)

```bash
# READ-ONLY: nothing below changes prod.
cd /opt/sorento-crm2
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "
select line_number, type, database, user_name, address, netmask, auth_method
from pg_hba_file_rules order by line_number;"'
# Is the stream encrypted, and from which kind of address (paste only private/public, not the address)?
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "
select r.application_name, r.client_addr, s.ssl, s.version
from pg_stat_replication r left join pg_stat_ssl s using (pid);"'
# Is 5432 published on a public interface?
docker compose port db 5432 2>/dev/null; ss -ltn 2>/dev/null | grep -E ':5432\b'
sudo nft list ruleset 2>/dev/null | grep -nE '5432' | head; sudo ufw status 2>/dev/null | grep -E '5432' 
# Round trip to B (use the address B replicates from, as client_addr above shows).
ping -c 100 -i 0.2 -q <B address> | tail -2
```

When pasting: replace every address with `<A>`, `<B>` or `private` / `public`, and every CIDR
with `loopback`, `docker net`, `private` or `public`.

## 9. 8b/8c results (owner, 7 Nov about 11:45): exposure first

Facts:
- **Node B.**
  - The CRM compose project in `/opt/sorento-crm2` is NOT running; `docker compose ls` lists only n8n.
  - The replica is a standalone container `sorento_crm_replica`: `pgvector/pgvector:pg17`, 17.11 (A runs 17.9; same major, so streaming is fine). In recovery, `primary_slot_name=sorento_crm_replica_slot`, `hot_standby_feedback=off`. Published on `127.0.0.1:5433` only.
  - CRM app: only `sorento_crm_worker` and `sorento_crm_worker_fast`, state Created (never started), old tag `backend-1.0.1`. No backend or frontend.
  - A host `pgbouncer.service` listens on `0.0.0.0:6432` and `[::]:6432`.
  - The n8n stack listens on all interfaces: n8n 5678, Redis 6379, Postgres 15 on 5432, MongoDB 27017.
- **Node A.**
  - db 5432 is published on `0.0.0.0`. The nft DNAT for 5432 accepts any input interface except the compose bridge (11711 packets). 6432 is DNATed to the pgbouncer container's 5432 too.
  - 8c's queries ran as `$POSTGRES_USER`, which is not a superuser here, so:
    - `pg_hba_file_rules` was denied;
    - `pg_stat_replication.client_addr` and `pg_stat_ssl` read empty. They are hidden from non-superusers, so empty does NOT mean "local socket".

**Corrections to "node B is built".** B holds a streaming replica, but no CRM app runs on it (G15).
Step 1 on B would be the FIRST start of B's app, not an update. What B's app connects to is the
active-active design question: A's primary through pgbouncer (#2170), not B's replica.

So:
- step 1 stays repo-ready;
- `SSH_HOST_B` waits until B's compose `.env` is reviewed (DATABASE_URL target, REDIS_URL) and B's
  `DB_SERVICE` question (G14) is settled. The replica is a standalone container, not a compose
  service, so `DB_SERVICE` cannot name it: G14 needs the small extra change (a `DB_CONTAINER`
  knob for `docker exec`) in the next PR.

### 9a. Severity

| # | Finding | Severity | Why |
|---|---|---|---|
| X1 | A: Postgres 5432 on every interface; nft DNAT from any interface | **CRITICAL until 9b proves the trust rows are loopback only; HIGH after** | A `host replication all <wide CIDR> trust` row would let anyone who reaches 5432 copy the whole database (`pg_basebackup`) with no password. Even with loopback-only trust rows, every role with a password can be guessed from the internet (scram, no rate limit) |
| X2 | B: n8n Redis 6379 public | **CRITICAL if `redis-cli ping` answers PONG without a password** | an open Redis on the internet allows data reads and writes and is a common host-takeover path (`CONFIG SET dir`) |
| X3 | B: n8n MongoDB 27017 public | **CRITICAL if it answers without auth** | full read and write of n8n's data |
| X4 | A: pgbouncer 6432 public (DNAT) | HIGH | the 14 Oct finding (`prod-edge-lockdown.md`); only n8n should reach it |
| X5 | B: host pgbouncer 6432 public; n8n Postgres 5432 public | HIGH | password guessing; the target behind B's pgbouncer is unknown, possibly A |
| X6 | replication over eth0, TLS unknown | MEDIUM (HIGH if 9b shows `ssl = f` over a public address) | the whole database crosses the provider network in clear text |
| X7 | B: n8n UI 5678 public | MEDIUM | n8n has its own login; n8n is being retired |

The Hostinger VPS firewall (`prod-edge-lockdown.md` step 1) may already drop some of these in
front of the box. Docker's DNAT does not prove a port is reachable from outside. The outside
connect test in 9b is what decides each severity. Run it first.

### 9b. READ-ONLY block (run before any fix)

On node A:

```bash
# READ-ONLY: nothing below changes prod. Run as the postgres superuser, as block 5.A did.
cd /opt/sorento-crm2
P='docker compose exec -T -u postgres db psql -U postgres -d postgres'
$P -c "select line_number, type, database, user_name, address, netmask, auth_method
       from pg_hba_file_rules order by line_number;"
$P -c "select r.application_name, r.usename, r.client_addr, s.ssl, s.version
       from pg_stat_replication r left join pg_stat_ssl s using (pid);"
# Every non-local client, by address and user (the app arrives from the compose network).
$P -c "select client_addr, usename, count(*) from pg_stat_activity
       where client_addr is not null group by 1, 2 order by 3 desc;"
# Who arrives on the published ports (sources of tracked flows), and the current DOCKER-USER chain.
for p in 5432 6432; do echo "== $p"; sudo conntrack -L -p tcp --orig-port-dst $p 2>/dev/null \
  | grep -oE 'src=[0-9a-f.:]+' | sort | uniq -c | sort -rn | head; done
sudo iptables -S DOCKER-USER 2>/dev/null
ip -brief addr
```

On node B:

```bash
# READ-ONLY: nothing below changes prod. Passwords masked.
docker exec sorento_crm_replica sh -c 'psql -U "${POSTGRES_USER:-postgres}" -d postgres -Atc "show primary_conninfo"' \
  | sed -E 's/password=[^ ]*/password=***/g'
docker inspect -f '{{.HostConfig.NetworkMode}}' sorento_crm_replica
ps -eo args | grep -E '[s]sh .*-[LR]|[a]utossh|[s]tunnel|[s]ocat' | cut -c1-200   # a tunnel to A?
sudo grep -vE '^\s*(;|#|$)' /etc/pgbouncer/pgbouncer.ini | sed -E 's/password=[^ ]*/password=***/g'
sudo ss -tn state established '( sport = :6432 )' | awk 'NR>1 {print $4}' | sed -E 's/:[0-9]+$//' | sort | uniq -c
# n8n stores: does each answer WITHOUT credentials? (PONG / 1 = open; NOAUTH / Unauthorized = protected)
docker exec n8n-redis redis-cli ping
docker exec n8n-mongodb mongosh --quiet --eval 'try { db.adminCommand({listDatabases: 1}).ok } catch (e) { e.codeName }'
for p in 5432 6379 27017 5678 6432; do echo "== $p"; sudo conntrack -L -p tcp --orig-port-dst $p 2>/dev/null \
  | grep -oE 'src=[0-9a-f.:]+' | sort | uniq -c | sort -rn | head -5; done
grep -E '^(DATABASE_URL|DIRECT_URL|REDIS_URL)=' /opt/sorento-crm2/.env 2>/dev/null | sed -E 's#://[^@/]*@#://***@#'
```

From a machine that is on NO allowlist (phone hotspot), one connection attempt per port:

```bash
for p in 5432 6432; do nc -4 -z -w 5 <A public> $p && echo "A $p OPEN <- FAIL" || echo "A $p closed"; done
for p in 5432 6379 27017 5678 6432; do nc -4 -z -w 5 <B public> $p && echo "B $p OPEN <- FAIL" || echo "B $p closed"; done
```

When pasting: keep `client_addr` / `address` as `loopback`, `docker net`, `<B>`, `private` or
`public`. Paste a "trust" row's CIDR class exactly, because the severity depends on it.

### 9c. Fix plan: THIS CHANGES PROD. Reviewed commands for the owner, in order

Docker-published ports bypass ufw, so the rule goes in `DOCKER-USER` (it sees packets after
DNAT; `--ctorigdstport` matches the host port the client dialled). Put each rule on the public
interface (`-i eth0`), so container-to-container traffic is never touched. Every step has its
rollback beside it. Check after every step: replication still `streaming` (block 5.A), the app
healthy (`/api/v1/health`), the outside test closed.

1. **Hostinger firewall first (both nodes, 5 minutes, no restart; the outer guard,
   `prod-edge-lockdown.md` step 1).**
   - A: accept 22/80/443 from any, 5432 from `<B>` only (replication), 6432 from the hosts 9b's
     conntrack shows (n8n), nothing else.
   - B: accept 22 from any, 5678 only if n8n's UI must stay public, nothing else.
   - Rollback: delete the added rules in hPanel.
2. **A, `DOCKER-USER` (immediate, no restart):**
   ```bash
   # THIS CHANGES PROD. 5432: only B may connect from outside. 6432: only the hosts 9b listed.
   sudo iptables -I DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 5432 --ctdir ORIGINAL ! -s <B>/32 -j DROP
   sudo iptables -I DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 6432 --ctdir ORIGINAL ! -s <N8N>/32 -j DROP
   # rollback: the same lines with -D instead of -I
   ```
   Persist: `netfilter-persistent save` if the package is installed. Otherwise add the two rules to
   a oneshot unit `After=docker.service`, as in `n8n-private-path.md:709`. Without persistence a
   reboot reopens the ports.
3. **A, pg_hba (reload, no restart), only if 9b shows a `trust` row wider than loopback:**
   - Delete that row.
   - Keep `local ... trust`, the loopback rows, and `host replication replicator <B>/32 scram-sha-256`.
   - Then: `docker compose exec -T -u postgres db psql -U postgres -c 'select pg_reload_conf()'`.
   - Check: `pg_hba_file_rules` has no `error` column set, and replication reconnects.
   - Rollback: restore the saved copy (`cp` it aside first) and reload.
4. **B, `DOCKER-USER` for the n8n stores (immediate, no restart):** n8n reaches its Postgres,
   Redis and Mongo over its own docker network, so nothing outside needs them unless 9b's
   conntrack shows a source.
   ```bash
   # THIS CHANGES PROD.
   for p in 5432 6379 27017; do
     sudo iptables -I DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport $p --ctdir ORIGINAL -j DROP
   done
   # rollback: the same with -D
   ```
5. **B, host pgbouncer 6432** (not docker, so ufw or `listen_addr` works): after 9b names its
   clients, set `listen_addr = 127.0.0.1` in `/etc/pgbouncer/pgbouncer.ini` (or `127.0.0.1,<private>`)
   and `sudo systemctl reload pgbouncer`. If something outside uses it, use
   `ufw allow from <client> to any port 6432` plus `ufw deny 6432` instead.
   Rollback: restore the ini and reload.
6. **Next restart window on A (with G2 `wal_log_hints`, G8 `archive_mode`):**
   - bind 5432 to loopback plus the private or WireGuard address (`prod-edge-lockdown.md` step 4,
     `"127.0.0.1:5432:5432"`);
   - replication over WireGuard (or `hostssl` with a certificate) so it is encrypted (X6);
   - pin pgbouncer's image (A runs `edoburu/pgbouncer:latest`).

## 10. pg_hba result, the exposure fix and B's first start (owner 7 Nov about 11:55)

**pg_hba facts on A:**
- `trust` only on `local`, `127.0.0.1/32` and `::1/128` (all and replication). These are the image defaults, so the G12 trust risk is LOW.
- Line 128: `host all all all scram-sha-256`.
- Replication: `replicator` with scram from `172.18.0.1/32` (the docker gateway) and from B's PUBLIC address `/32`.
- `pg_stat_ssl` is empty: the replication stream crosses the public internet unencrypted.

**Updated severity:**

| Finding | Severity |
|---|---|
| X1: A 5432 open to the internet, with password logins for any role (line 128) | HIGH |
| X6: replication in clear text over the public internet (the whole database, continuously) | HIGH |
| X2, X3: B's Redis and Mongo | CRITICAL only if 9b shows them answering without credentials, else HIGH |
| X4, X5 | HIGH, unchanged |

Order below: (1) A's 5432, (2) encryption, (3) B's ports, then step 1. Every block is **THIS
CHANGES PROD**, owner-run, with its rollback and its check. `<IF>` = the public interface
(`ip route get <B>` on A prints it as `dev ...`); `<A>` / `<B>` = public addresses.

### 10.1 A: 5432 from B only (no restart, zero app impact)

The app and pgbouncer reach `db` container to container on the compose bridge. Those packets
never enter on `<IF>`, so a rule on `<IF>` cannot touch them. Docker-published ports bypass ufw.
IPv4 is filtered in `DOCKER-USER` (after DNAT; `--ctorigdstport` = the port the client dialled).
If `ss -ltnp | grep ':5432'` shows a `docker-proxy` on `[::]`, IPv6 arrives through that proxy on
`INPUT`, and then reaches Postgres FROM `172.18.0.1`, the gateway row above. So IPv6 is dropped
on `INPUT`.

```bash
# THIS CHANGES PROD (node A). Persistent: a oneshot unit re-applies it after a reboot or a docker restart.
sudo tee /usr/local/sbin/sorento-edge.sh >/dev/null <<'SH'
#!/bin/sh
set -eu
IF=<IF>; B=<B>
add()  { iptables  -C "$@" 2>/dev/null || iptables  -I "$@"; }
add6() { ip6tables -C "$@" 2>/dev/null || ip6tables -I "$@"; }
add DOCKER-USER -i "$IF" -p tcp -m conntrack --ctorigdstport 5432 --ctdir ORIGINAL ! -s "$B/32" -j DROP
add6 INPUT -i "$IF" -p tcp --dport 5432 -j DROP
SH
sudo chmod 700 /usr/local/sbin/sorento-edge.sh
sudo tee /etc/systemd/system/sorento-edge.service >/dev/null <<'UNIT'
[Unit]
Description=Sorento edge rules (published DB ports)
After=docker.service
Requires=docker.service
PartOf=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/sorento-edge.sh
[Install]
WantedBy=multi-user.target docker.service
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now sorento-edge.service
```

Check:
- `sudo iptables -L DOCKER-USER -v -n | grep 5432` shows the rule.
- Block 5.A's `pg_stat_replication` query: still `streaming`, 0 bytes behind.
- `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<active backend port>/api/v1/health` returns 200 (8000 blue, 8010 green).
- From the phone hotspot: `nc -4 -z -w 5 <A> 5432` gives closed (and `-6` closed).

Rollback:

```bash
sudo systemctl disable --now sorento-edge.service
sudo iptables -D DOCKER-USER -i <IF> -p tcp -m conntrack --ctorigdstport 5432 --ctdir ORIGINAL ! -s <B>/32 -j DROP
sudo ip6tables -D INPUT -i <IF> -p tcp --dport 5432 -j DROP
```

6432 on A stays as `prod-edge-lockdown.md` step 1 has it (from n8n only) until n8n retires.

### 10.2 Encrypt replication: WireGuard A<->B (recommended) vs TLS

**Recommendation: WireGuard.** The link will carry more than Postgres replication:
- the controller's peer reads;
- active-active (#2170): B's app reaching A's pgbouncer, and Redis replication, which Postgres TLS
  would leave in clear text.
A's Postgres does not restart. B's replica switches with a reload (`primary_conninfo` is
reloadable since PG 13). TLS (`ssl=on` is also a reload, but it needs a certificate in A's data
directory and a CA on B for `verify-full`) protects only Postgres.

```bash
# THIS CHANGES PROD (both nodes). On each: install, make keys, swap the PUBLIC keys by hand.
sudo apt-get install -y wireguard
sudo sh -c 'umask 077; wg genkey | tee /etc/wireguard/private.key | wg pubkey > /etc/wireguard/public.key'
# /etc/wireguard/wg0.conf from infra/templates/wireguard/wg0.conf.template:
#   A: Address = 10.77.0.1/32, peer AllowedIPs = 10.77.0.2/32, Endpoint = <B>:51820
#   B: Address = 10.77.0.2/32, peer AllowedIPs = 10.77.0.1/32, Endpoint = <A>:51820
sudo chmod 600 /etc/wireguard/wg0.conf && sudo systemctl enable --now wg-quick@wg0
# 51820/udp from the peer only: add  "add INPUT -i \"$IF\" -p udp --dport 51820 ! -s <peer>/32 -j DROP"
# to sorento-edge.sh (and the Hostinger firewall: 51820/udp from the peer), then restart sorento-edge.
sudo wg show wg0 latest-handshakes && ping -c 20 -q 10.77.0.2   # (from A; 10.77.0.1 from B)
```

Then point replication at the tunnel:

```bash
# THIS CHANGES PROD. Node A: let B's tunnel address replicate (pg_hba reload, no restart). Keeps a backup.
cd /opt/sorento-crm2
docker compose exec -T -u postgres db sh -c 'f="$PGDATA/pg_hba.conf"; cp "$f" "$f.bak-07nov" &&
  sed -i "/^host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+all/i host replication replicator 10.77.0.2/32 scram-sha-256" "$f"'
docker compose exec -T -u postgres db psql -U postgres -c "select pg_reload_conf()" \
  -c "select line_number, error from pg_hba_file_rules where error is not null"   # expect 0 rows
# Node B: same conninfo, host changed to the tunnel. `show` prints the password: read it on your screen, never paste it.
docker exec -it sorento_crm_replica psql -U "<replica superuser>" -d postgres -c "show primary_conninfo"
docker exec -it sorento_crm_replica psql -U "<replica superuser>" -d postgres \
  -c "alter system set primary_conninfo = '<the same string with host=10.77.0.1>'" -c "select pg_reload_conf()"
```

Check on A (superuser, block 9b): `client_addr = 10.77.0.2`, `streaming`, 0 bytes behind.

Rollback:
- B: `alter system set primary_conninfo = '<the old string>'` + reload.
- A: `cp "$PGDATA/pg_hba.conf.bak-07nov" "$PGDATA/pg_hba.conf"` + reload.
- Both: `systemctl disable --now wg-quick@wg0`.

Once it has streamed over the tunnel for a day:
- in `sorento-edge.sh` on A, drop the `! -s "$B/32"` part, so 5432 is closed on `<IF>` to everyone;
- delete the pg_hba row for B's public address and reload.
Postgres traffic then never crosses the internet. The 5432 bind to loopback plus the tunnel
address waits for the next restart window (with `wal_log_hints`, `archive_mode`; G2, G8).

### 10.3 B: n8n stores and the host pgbouncer to localhost/A only

n8n reaches its own Postgres, Redis and MongoDB over its docker network, so nothing outside needs
them. Run 9b's conntrack first: if a source other than `<A>` shows up, stop and tell crew.

```bash
# THIS CHANGES PROD (node B). Same unit pattern as 10.1, with this sorento-edge.sh:
sudo tee /usr/local/sbin/sorento-edge.sh >/dev/null <<'SH'
#!/bin/sh
set -eu
IF=<IF>; A=<A>
add()  { iptables  -C "$@" 2>/dev/null || iptables  -I "$@"; }
add6() { ip6tables -C "$@" 2>/dev/null || ip6tables -I "$@"; }
for p in 5432 6379 27017; do       # n8n Postgres, Redis, MongoDB (docker-published)
  add DOCKER-USER -i "$IF" -p tcp -m conntrack --ctorigdstport $p --ctdir ORIGINAL ! -s "$A/32" -j DROP
  add6 INPUT -i "$IF" -p tcp --dport $p -j DROP
done
add  INPUT -i "$IF" -p tcp --dport 6432 ! -s "$A/32" -j DROP   # host pgbouncer (not docker)
add6 INPUT -i "$IF" -p tcp --dport 6432 -j DROP
SH
sudo chmod 700 /usr/local/sbin/sorento-edge.sh
# then the same /etc/systemd/system/sorento-edge.service as 10.1, daemon-reload, enable --now
```

Check:
- n8n works: `docker exec n8n-main wget -qO- http://127.0.0.1:5678/healthz` returns `{"status":"ok"}`.
- Run one test workflow in the n8n UI.
- `docker logs --since 10m n8n-main 2>&1 | grep -ciE 'ECONNREFUSED|ETIMEDOUT'` returns 0.
- Phone hotspot: 5432, 6379, 27017 and 6432 on `<B>` closed, v4 and v6.

Rollback: `systemctl disable --now sorento-edge.service`, then the same `iptables -D ...` /
`ip6tables -D ...` lines.

n8n UI 5678 stays public (n8n has its own login and is being retired). Restrict it in the
Hostinger firewall if no one outside needs it.

### 10.4 Step 1 on B: bring the CRM app up as a STANDBY (workers and scheduler off)

Built in the repo (this branch): `DB_CONTAINER` in `.deploy.env` makes the release reach B's
standalone replica through `docker exec` (`scripts/blue_green_deploy.sh` `db_exec` / `db_cid`).
The name is validated, and `DB_CONTAINER` is refused in HA compose mode. With it, `--role` on B
answers `standby`. B's app reads the local replica: nothing on B can write until step 3 (or
#2170 re-points it), and the chatbot sweeper's claim fails on a replica, so B never sends. The
release never starts workers on a standby. B gets no users until the LB is on.

Owner commands on B, in order (THIS CHANGES PROD, B only; A is untouched):

1. **Parity check (read-only).** `sha256sum docker-compose.yml` on both nodes must match.
   `grep -vE '^(DATABASE_URL|DIRECT_URL|REDIS_URL)=' .env | sha256sum` on both must match.
   `FIELD_ENCRYPTION_KEY`, `JWT_SECRET` and `NEXTAUTH_SECRET` must be identical.
2. **Put the replica on B's compose network** (live, no restart):
   `docker network ls | grep sorento`, then `docker network connect <sorento-crm2 network> sorento_crm_replica`.
   Rollback: `docker network disconnect ...`.
3. **B's `.env`:**
   - `DATABASE_URL` and `DIRECT_URL`: host `sorento_crm_replica`, port `5432`, A's app user and database.
   - `REDIS_URL=redis://redis:6379/0`, B's own compose Redis.
4. **B's `.deploy.env`, mode 600:** `DB_CONTAINER=sorento_crm_replica` and `DEPLOY_DB_NAME=<db>`.
   There is no backend on B to read the name from.
5. **Recommended, both nodes (keeps the compose files identical):** add
   `SKIP_MIGRATIONS: ${SKIP_MIGRATIONS:-0}` to the backend colours' `environment:`. A's release
   behaviour is unchanged. B never migrates even without it (section 7a), but this makes it
   explicit.
6. **Start only B's Redis:** `docker compose up -d redis`.
   - Never run a bare `docker compose up -d` on B: it would start the workers and the compose `db`.
   - Remove the stale never-started workers: `docker compose rm -f worker worker_fast`.
7. **nginx, sudo and registry login on B, as on A:**
   - nginx with A's site config (not the upstreams file; the release writes that);
   - the deploy user's passwordless `sudo install` / `nginx -t` / `nginx -s reload`;
   - `docker login` to the image registry.
8. **Dry run (read-only):** copy `scripts/blue_green_deploy.sh` from this branch to B, then run
   `./scripts/blue_green_deploy.sh --preflight` (all PASS) and `--role` (`standby`).
9. **First start on B, the release A runs now:** `IMAGE_TAG=<A's full 40-hex SHA> ./scripts/blue_green_deploy.sh`.
   - Expect: `Node role: standby`, the replica is already at the head, no snapshot, workers untouched, `Deploy complete`.
   - Check: `/api/v1/health` 200 on B's active port; `/api/v1/health/role` 503 (correct on a replica).
   - Rollback: `docker compose stop backend_<c> frontend_<c> mcp_<c>`, which leaves B a replica only, as today.
10. After #2166 (with this change) is merged: add the secrets `SSH_HOST_B` and `SSH_KNOWN_HOSTS`.
    From then on every release deploys A, then B.

## 11. Section 3 build contract (HA-TONIGHT, 7 Nov evening)

The build spec for section 3b plus G11. Tests are written red from this section first. The
controller and the role watcher stay DISARMED by default: they refuse to run until the owner arms
them after this PR merges and the drill passes (owner ruling 7 Nov ~21:45, "settle the HA today":
tonight is the manual runbook `documentation/runbooks/ha-tonight-07nov.md`, not the controller).

### 11a. Names (G11)

New `ha-pg.env` keys, each optional, validated, with the old behaviour as the default:

| Key | Default | Used for | Check |
|---|---|---|---|
| `SELF_APP_NAME` | `$NODE_NAME` | `application_name` in this node's `primary_conninfo` after a rejoin | `^[a-z0-9_-]{1,32}$` |
| `SELF_SLOT` | `${NODE_NAME//-/_}` | `primary_slot_name` after a rejoin; dropped on promote if stale | `^[a-z0-9_]{1,63}$` |
| `PEER_APP_NAME` | `$PEER_NAME` | `pg_stat_replication.application_name` in observe; `synchronous_standby_names` | `^[a-z0-9_-]{1,32}$` |
| `PEER_SLOT` | `${PEER_NAME//-/_}` | slot observe checks, `ensure-slot` and `promote` create | `^[a-z0-9_]{1,63}$` |

Adopting B as built: A sets `PEER_APP_NAME=sorento_crm_replica`, `PEER_SLOT=sorento_crm_replica_slot`;
B sets `SELF_APP_NAME=sorento_crm_replica`, `SELF_SLOT=sorento_crm_replica_slot`. `Config.from_env`
reads `PEER_APP_NAME` (same default and check) and P4 uses it, not `PEER_NAME`.

### 11b. The sync record (P4' / S1')

Object `ha/sync-state.json` (key overridable as `SYNC_RECORD_KEY`) in the WAL-G R2 bucket:
`{"mode": "sync"|"async", "primary": "<NODE_NAME>", "since": <unix seconds>}`.

Adapter `ha-pg.sh`:
- `sync-record get`: prints `rec_mode=<sync|async>`, `rec_primary=<name>`, `rec_since=<int>` and
  exits 0, or exits non-zero (any HTTP error, timeout, a missing object, a body that is not that
  shape). Parsing is in the adapter with `python3 -c` from stdin (host python3 is already required
  by the controller).
- `sync-record put sync|async`: PUTs the JSON with `primary=$NODE_NAME`, `since=$(date +%s)`, exits
  0 only on HTTP 200.
- Transport: `curl -fsS -m 5 --aws-sigv4 "aws:amz:auto:s3"` to
  `$R2_ENDPOINT/$R2_BUCKET/$SYNC_RECORD_KEY` (path style). The key pair comes from
  `R2_CREDENTIALS_FILE` (mode 600, two lines `AWS_ACCESS_KEY_ID=` / `AWS_SECRET_ACCESS_KEY=`, the same
  values as WAL-G's) and reaches curl as a `-K -` config on stdin, so it never shows in `ps`.
  `R2_ENDPOINT` must start with `https://` (or `http://127.0.0.1` for the drill/tests).
- Missing R2 settings: `get` and `put` exit 2.

Controller (`decide()` stays pure; the record arrives in `Obs`):
- `Obs` gains `rec_mode` (`sync` | `async` | `unknown`; `unknown` = the `get` failed), `rec_primary`
  (`Optional[str]`), `rec_since` (`Optional[int]`). Defaults: `unknown`, `None`, `None`.
- **P4' (primary).** `desired = PEER_APP_NAME if sync_mode != off and self_streaming else ""`.
  - Drop (`sync_names` non-empty, `desired` empty): actions `("sync_record", "async")` THEN
    `("set_sync", "")`, in that order.
  - Add (`sync_names` empty, `desired` non-empty): `("set_sync", desired)` THEN
    `("sync_record", "sync")`.
  - Steady state, names already equal desired: if the record is readable and differs from
    (`"sync" if desired else "async"`, self) emit `("sync_record", that)`. An `unknown` record in
    steady state emits nothing (no alert storm while R2 is down; the next transition retries).
- **I/O loop rule:** a failed `sync_record` action skips every action after it in the same tick
  (so A never drops B without a confirmed record: writes keep waiting, Q4 (a)) and alerts
  `sync record write failed; NOT dropping the sync standby` (once per failure streak is fine,
  every tick is acceptable).
- **S1' (standby).** S1's three windows and the lag check are unchanged. Promotion additionally
  needs `rec_mode == "sync" and rec_primary == PEER_NAME`. Otherwise no promotion and one alert
  per outage (reuse a state flag, reset when streaming again): record `async` names its `since`
  (card Q5 (a)), `unknown` says the record could not be read.
  After the `promote` action, emit `("sync_record", "async")` (the new primary has no standby).
- `SYNC_MODE != off` with no `R2_ENDPOINT`/`R2_BUCKET`/`R2_CREDENTIALS_FILE` in the env: the
  I/O `main()` refuses to start (exit 2). `decide()` does not see env.
- With `SYNC_MODE=off` a standby never promotes automatically (the record never says `sync`).
  This is intended: async plus automatic promotion is the silent-loss path G4.

### 11c. Disarmed by default

- `cf_failover.py main()`: unless `CONTROLLER_ARMED=yes`, log `not armed (CONTROLLER_ARMED=yes
  in ha-pg.env arms it, after the section 3 drill)` and exit 3, before touching the watchdog.
  `cf-failover.service` gains `RestartPreventExitStatus=3` so systemd does not loop it.
- `role-watcher.sh`: same with `ROLE_WATCHER_ARMED=yes`, exit 3; its unit the same line.
- `ha-pg.env.example`: `CONTROLLER_ARMED=no`, `ROLE_WATCHER_ARMED=no`, the four names, the R2
  keys, `SYNC_MODE=on_commit` commented with "only after the drill".
- The drill (`infra/rehearsal/cf_drill.py`) and the loop tests set the arm flags themselves.

### 11d. Tests (red first)

- `test_cf_failover.py`: P4' order on drop and add; steady-state repair; unknown record in steady
  state emits nothing; S1 with record sync from peer promotes then writes async; record async
  never promotes and alerts once with `since`; record unknown never promotes; record sync but
  `rec_primary` = self never promotes; `PEER_APP_NAME` drives `set_sync`; config check on it.
  World model: a shared record object; a fault "B down, A writes alone (async), A dies" never
  promotes B; the random-fault test keeps "never two writers" and adds "never a promotion that
  loses an acknowledged commit" (B's lsn < A's last acknowledged lsn while the record said sync).
- `test_cf_failover_loop.py`: failed `sync_record` skips the following `set_sync`; not armed
  exits 3 without opening the watchdog; `SYNC_MODE=on_commit` without R2 settings exits 2.
- `test_ha_scripts.py`: `sync-record get/put` against a local fake S3 (http.server), credentials
  never on argv (fake curl logs argv), bad body = non-zero, missing settings = exit 2; the four
  names reach observe SQL, `ensure-slot`, `promote` and the standby conf; invalid names exit 2;
  role watcher not armed exits 3.
