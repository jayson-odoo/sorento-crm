# PLAN: node B exists as a replica; deploy both, then LB, then no-data-loss failover (HA-CF-FAILOVER, 7 Nov)

Status: Build (7 Nov). Card answered 7 Nov about 11:00 (section 7): all five recommendations. Step 1 (deploy both on the plain compose) in build; section 3 (sync record) next.
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
