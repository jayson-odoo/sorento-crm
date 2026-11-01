#!/usr/bin/env bash
# H4a rehearsal (N8N-DECOM-HA): adopt a RUNNING standalone pgvector Postgres 17 into Patroni as
# a one-member cluster, on a THROWAWAY Docker host. Mirrors the owner's H4 steps on prod.
# Plan: documentation/plans/infra/PLAN-n8n-decom-ha-01nov.md section 5 (row H4a).
#
#   DOCKER_CONTEXT=<a context whose name contains ha-rehearsal> infra/rehearsal/run.sh [up|down]
#
# `up` (default) runs everything and exits non-zero if any check fails. `down` removes every
# container, volume, network and image it created, plus its temp dir (certs, env files).
# SYNTHETIC data only. Never point this at a real database or at the CI runner's context.
# shellcheck disable=SC2015,SC2016
set -uo pipefail

P=ha-rehearsal
NET=$P-net
# Under $HOME: bind mounts must be visible to the Docker host (Colima shares $HOME, not $TMPDIR).
WORK="$HOME/.cache/$P-work"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPL="$HERE/../templates"
SCRIPTS="$HERE/../scripts"

PG_IMAGE="${PG_IMAGE:-pgvector/pgvector:pg17}"
ETCD_IMAGE="${ETCD_IMAGE:-quay.io/coreos/etcd:v3.5.17}"
# The Dockerfile downloads the amd64 WAL-G build, so every Postgres container runs amd64 (slow
# but correct under emulation on an arm64 host). Override only if the Dockerfile changes.
PLATFORM="${REHEARSAL_PLATFORM:-linux/amd64}"
OUTAGE_MAX_S="${OUTAGE_MAX_S:-180}"
DB=rehearsal

die() { echo "ha-rehearsal: $*" >&2; exit 2; }

# ---- 0. Context guard: nothing below runs unless this passes -------------------------------
ctx="${DOCKER_CONTEXT:-}"
[ -n "$ctx" ] || die "set DOCKER_CONTEXT to a context whose name contains 'ha-rehearsal'"
case "$ctx" in colima-ci|default) die "refusing to run on context '$ctx'" ;; esac
case "$ctx" in *ha-rehearsal*) ;; *) die "context '$ctx' does not contain 'ha-rehearsal'" ;; esac
[ -z "${DOCKER_HOST:-}" ] || die "unset DOCKER_HOST (it overrides the context)"
REAL_DOCKER="$(command -v docker)" || die "docker not found"
d() { "$REAL_DOCKER" --context "$ctx" "$@"; }
d context inspect "$ctx" >/dev/null 2>&1 || die "docker context '$ctx' does not exist"

cmd="${1:-up}"

# ---- down ----------------------------------------------------------------------------------
if [ "$cmd" = down ]; then
  # shellcheck disable=SC2086
  ids=$(d ps -aq --filter "label=$P") ; [ -z "$ids" ] || d rm -f $ids >/dev/null
  for v in $(d volume ls -q --filter "label=$P"); do d volume rm -f "$v" >/dev/null; done
  d network inspect "$NET" >/dev/null 2>&1 && d network rm "$NET" >/dev/null
  d image inspect "$P-patroni:test" >/dev/null 2>&1 && d image rm -f "$P-patroni:test" >/dev/null
  case "$(basename "$WORK")" in "$P"*) rm -rf "$WORK" ;; esac
  echo "ha-rehearsal: removed"
  exit 0
fi
[ "$cmd" = up ] || die "usage: run.sh [up|down]"

d network inspect "$NET" >/dev/null 2>&1 && die "leftovers exist: run 'run.sh down' first"
[ -z "$(d ps -aq --filter "label=$P")" ] || die "leftovers exist: run 'run.sh down' first"
command -v openssl >/dev/null || die "openssl not found"
command -v python3 >/dev/null || die "python3 not found (ha-checks.sh needs it)"

# ---- result bookkeeping --------------------------------------------------------------------
NAMES=(); RESULTS=(); EVID=()
record() { NAMES+=("$1"); RESULTS+=("$2"); EVID+=("$3"); printf '%-4s %s: %s\n' "$2" "$1" "$3"; }
pass() { record "$1" PASS "$2"; }
fail() { record "$1" FAIL "$2"; }
must() { "$@" || die "step failed: $*"; }
waitfor() { # waitfor SECONDS cmd...
  local t=$1 end; shift; end=$((SECONDS + t))
  while [ "$SECONDS" -lt "$end" ]; do "$@" >/dev/null 2>&1 && return 0; sleep 1; done
  return 1
}
rand() { openssl rand -hex 12; }

mkdir -p "$WORK/pki" "$WORK/ca-private" "$WORK/shim"
PKI="$WORK/pki"
SUPERPW=$(rand); REPLPW=$(rand); REWPW=$(rand)
ETCD_ROOTPW=$(rand); ETCD_PATRONIPW=$(rand); ETCD_HCPW=$(rand)
SODIUM=$(openssl rand -hex 32)
LBL=(--label "$P=1")

must d network create "${LBL[@]}" "$NET" >/dev/null
for v in pgdata walg etcd-a etcd-w; do must d volume create "${LBL[@]}" "$P-$v" >/dev/null; done
SUBNET=$(d network inspect "$NET" --format '{{(index .IPAM.Config 0).Subnet}}')
echo "ha-rehearsal: context=$ctx network=$NET subnet=$SUBNET"

# ---- 2a. Throwaway CA + certs (ca.key stays out of every container, as in prod) -------------
mint() { # mint NAME CN SAN-or-empty
  local n=$1 ext="$WORK/$1.ext" subj="/CN=$2"
  [ -n "$2" ] || subj="/O=$P-$1"
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$PKI/$n.key" 2>/dev/null || die "openssl genpkey"
  openssl req -new -key "$PKI/$n.key" -subj "$subj" -out "$WORK/$n.csr" || die "openssl req"
  { [ -z "$3" ] || echo "subjectAltName=$3"; echo "extendedKeyUsage=serverAuth,clientAuth"; } > "$ext"
  openssl x509 -req -in "$WORK/$n.csr" -CA "$PKI/ca.crt" -CAkey "$WORK/ca-private/ca.key" \
    -CAcreateserial -days 2 -extfile "$ext" -out "$PKI/$n.crt" 2>/dev/null || die "openssl x509 $n"
  chmod 644 "$PKI/$n.key"
}
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$WORK/ca-private/ca.key" 2>/dev/null || die "ca key"
openssl req -new -key "$WORK/ca-private/ca.key" -subj "/CN=$P-ca" -out "$WORK/ca.csr" || die "ca csr"
printf 'basicConstraints=critical,CA:TRUE\nkeyUsage=keyCertSign,cRLSign\n' > "$WORK/ca.ext"
openssl x509 -req -in "$WORK/ca.csr" -signkey "$WORK/ca-private/ca.key" -days 2 -extfile "$WORK/ca.ext" -out "$PKI/ca.crt" 2>/dev/null || die "ca cert"
SAN="DNS:$P-etcd-a,DNS:$P-etcd-b,DNS:$P-etcd-w,DNS:localhost,IP:127.0.0.1"
mint server server "$SAN"; mint peer peer "$SAN"       # one shared cert per kind (prod: one per member)
# Patroni cert has NO CN: it speaks the HTTP gateway, which rejects a client cert with a CN (finding)
mint patroni "" ""; mint healthcheck healthcheck ""

# ---- 2b. etcd env rendered FROM the template ------------------------------------------------
render_etcd_env() { # render_etcd_env MEMBER-NAME HOST
  grep -v '^[[:space:]]*#' "$TPL/etcd/etcd.env.template" | grep -v '^[[:space:]]*$' | sed \
    -e "s|<THIS_WG_IP>|$2|g" -e "s|<A_WG_IP>|$P-etcd-a|g" \
    -e "s|<WITNESS_WG_IP>|$P-etcd-w|g" -e 's|\${WITNESS_NAME}|witness|g' -e 's|<WITNESS_NAME>|witness|g' \
    -e "s|<HEALTHCHECK_PASSWORD>|$ETCD_HCPW|" -e "s|^ETCD_NAME=.*|ETCD_NAME=$1|" \
    -e 's|^ETCD_LISTEN_PEER_URLS=.*|ETCD_LISTEN_PEER_URLS=https://0.0.0.0:2380|' \
    -e 's|^ETCD_LISTEN_CLIENT_URLS=.*|ETCD_LISTEN_CLIENT_URLS=https://0.0.0.0:2379|'  # etcd binds IPs only
}
render_etcd_env crm-a "$P-etcd-a" > "$WORK/etcd-a.env"
render_etcd_env witness "$P-etcd-w" > "$WORK/etcd-w.env"
if grep -h '[<>]' "$WORK"/etcd-?.env; then die "unrendered placeholder in etcd env"; fi

# ---- 1. Standalone pgvector Postgres 17 with synthetic data --------------------------------
must d pull -q --platform "$PLATFORM" "$PG_IMAGE" >/dev/null
must d pull -q "$ETCD_IMAGE" >/dev/null
must d run -d --name "$P-pg" "${LBL[@]}" --network "$NET" --platform "$PLATFORM" \
  -e POSTGRES_PASSWORD="$SUPERPW" -v "$P-pgdata:/var/lib/postgresql/data" "$PG_IMAGE" \
  -c shared_preload_libraries=pg_stat_statements >/dev/null
pgq() { d exec -u postgres "$P-pg" psql -h 127.0.0.1 -U postgres -d "${2:-$DB}" -v ON_ERROR_STOP=1 -Atc "$1"; }
waitfor 180 d exec "$P-pg" pg_isready -h 127.0.0.1 -U postgres || die "standalone Postgres did not come up"
sleep 2
must d exec -u postgres "$P-pg" psql -h 127.0.0.1 -U postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $DB" >/dev/null
must d exec -i -u postgres "$P-pg" psql -h 127.0.0.1 -U postgres -d "$DB" -v ON_ERROR_STOP=1 -q >/dev/null <<SQL
CREATE EXTENSION vector;
CREATE TABLE items (id serial PRIMARY KEY, label text, emb vector(3));
INSERT INTO items (label, emb) SELECT 'item ' || g, ARRAY[random(), random(), random()]::vector FROM generate_series(1, 5000) g;
CREATE INDEX items_emb_hnsw ON items USING hnsw (emb vector_l2_ops);
CREATE TABLE plain_t (id serial PRIMARY KEY, note text);
INSERT INTO plain_t (note) SELECT 'row ' || g FROM generate_series(1, 500) g;
CREATE TABLE probe (id serial PRIMARY KEY, ts timestamptz DEFAULT now());
-- Plan step 6: roles Patroni's bootstrap would have created, made by hand for an adopted cluster.
CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '$REPLPW';
CREATE ROLE rewinder WITH LOGIN PASSWORD '$REWPW';
GRANT EXECUTE ON FUNCTION pg_catalog.pg_ls_dir(text, boolean, boolean) TO rewinder;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_stat_file(text, boolean) TO rewinder;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_read_binary_file(text) TO rewinder;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_read_binary_file(text, bigint, bigint, boolean) TO rewinder;
SQL
ITEMS0=$(pgq "SELECT count(*) FROM items"); PLAIN0=$(pgq "SELECT count(*) FROM plain_t")
DATADIR=$(pgq "SHOW data_directory" postgres); PRELOAD=$(pgq "SHOW shared_preload_libraries" postgres)
echo "ha-rehearsal: standalone seeded: items=$ITEMS0 plain_t=$PLAIN0 data_directory=$DATADIR preload=$PRELOAD"

# ---- 2c. etcd: node A + witness only (phase A shape, as the template lists them), auth on ------
# Only each etcd's own files, as compose.ha.yml does (never patroni.key, never ca.key).
ETCD_PKI=(); for f in ca.crt peer.crt peer.key server.crt server.key healthcheck.crt healthcheck.key; do
  ETCD_PKI+=(-v "$PKI/$f:/etc/etcd/pki/$f:ro"); done
for m in a w; do
  must d run -d --name "$P-etcd-$m" "${LBL[@]}" --network "$NET" --env-file "$WORK/etcd-$m.env" \
    -v "$P-etcd-$m:/etcd-data" "${ETCD_PKI[@]}" "$ETCD_IMAGE" /usr/local/bin/etcd >/dev/null
done
ectl_pre() { d exec -e ETCDCTL_USER= "$P-etcd-a" etcdctl "$@"; }                  # before auth is on
waitfor 90 ectl_pre endpoint health --cluster || die "etcd did not become healthy"
# Order from the template: users and roles first, then `auth enable`, all BEFORE Patroni starts.
must ectl_pre user add root --new-user-password="$ETCD_ROOTPW" >/dev/null
must ectl_pre user add patroni --new-user-password="$ETCD_PATRONIPW" >/dev/null
must ectl_pre role add patroni >/dev/null
must ectl_pre role grant-permission patroni --prefix=true readwrite /sorento/ >/dev/null
must ectl_pre user grant-role patroni patroni >/dev/null
must ectl_pre user add healthcheck --new-user-password="$ETCD_HCPW" >/dev/null
must ectl_pre auth enable >/dev/null
echo "ha-rehearsal: etcd members started: crm-a, witness; auth enabled"

# ---- render patroni.yml and the env files FROM the templates ---------------------------------
sed -e "s|<PROD_SHARED_PRELOAD_LIBRARIES>|$PRELOAD|" -e "s|<PROD_DATA_DIRECTORY>|$DATADIR|" \
    -e 's|<A_WG_IP>|127.0.0.1|g' -e 's|<B_WG_IP>|127.0.0.1|g' \
    -e 's|<APP_DB_USER>|rehearsal_app|g' -e 's|<PGBOUNCER_AUTH_USER>|rehearsal_pgb|g' \
    -e "s|<CRM_COMPOSE_SUBNET_24>|$SUBNET|g" "$TPL/patroni/patroni.yml" > "$WORK/patroni.yml"
if grep -v '^[[:space:]]*#' "$WORK/patroni.yml" | grep '<'; then die "unrendered placeholder in patroni.yml"; fi
cat > "$WORK/patroni.env" <<ENV
PATRONI_NAME=rehearsal-a
PATRONI_RESTAPI_CONNECT_ADDRESS=$P-patroni:8008
PATRONI_POSTGRESQL_CONNECT_ADDRESS=$P-patroni:5432
PATRONI_RESTAPI_USERNAME=patroni-admin
PATRONI_RESTAPI_PASSWORD=$(rand)
PATRONI_ETCD3_HOSTS='$P-etcd-a:2379','$P-etcd-w:2379'
PATRONI_ETCD3_USERNAME=patroni
PATRONI_ETCD3_PASSWORD=$ETCD_PATRONIPW
PATRONI_SUPERUSER_PASSWORD=$SUPERPW
PATRONI_REPLICATION_PASSWORD=$REPLPW
PATRONI_REWIND_PASSWORD=$REWPW
ENV
{ # WAL-G env: only the template's non-S3 lines apply; the bucket is a local directory here.
  echo "WALG_FILE_PREFIX=/walg-archive"
  grep -E '^(WALG_COMPRESSION_METHOD|PGHOST)=' "$TPL/walg.env.example"
  echo "WALG_LIBSODIUM_KEY=$SODIUM"; echo "WALG_LIBSODIUM_KEY_TRANSFORM=hex"
} > "$WORK/walg.env"

# ---- build the Patroni image from the template Dockerfile ------------------------------------
must d build -q --platform "$PLATFORM" -t "$P-patroni:test" "${LBL[@]}" \
  "$TPL/patroni" >/dev/null
# WAL-G archive volume must be writable by the postgres user (uid of the image).
must d run --rm --platform "$PLATFORM" -u 0 -v "$P-walg:/walg-archive" --entrypoint chown \
  "$P-patroni:test" postgres:postgres /walg-archive

# ---- 3. Cut over: stop standalone cleanly, start Patroni on the SAME data directory ----------
T0=$SECONDS
must d stop -t 120 "$P-pg" >/dev/null
CTL=$(d run --rm --platform "$PLATFORM" -u postgres -v "$P-pgdata:$DATADIR" --entrypoint pg_controldata \
  "$P-patroni:test" "$DATADIR" 2>&1 | grep 'cluster state')
must d run -d --name "$P-patroni" "${LBL[@]}" --network "$NET" --platform "$PLATFORM" \
  --env-file "$WORK/patroni.env" --env-file "$WORK/walg.env" \
  -v "$P-pgdata:$DATADIR" -v "$P-walg:/walg-archive" -v "$WORK/patroni.yml:/etc/patroni/patroni.yml:ro" \
  -v "$PKI/ca.crt:/etc/etcd/pki/ca.crt:ro" -v "$PKI/patroni.crt:/etc/etcd/pki/patroni.crt:ro" \
  -v "$PKI/patroni.key:/etc/etcd/pki/patroni.key:ro" -p 127.0.0.1::8008 "$P-patroni:test" >/dev/null
pq() { d exec "$P-patroni" psql -U postgres -d "${2:-$DB}" -v ON_ERROR_STOP=1 -Atc "$1"; }
write_ok() { pq "INSERT INTO probe DEFAULT VALUES" >/dev/null; }
wait_write() { waitfor "${1:-120}" write_ok; }
if wait_write 600; then OUTAGE=$((SECONDS - T0)); else OUTAGE=-1; fi
HPORT=$(d port "$P-patroni" 8008/tcp | head -1 | sed 's/.*://')

# ---- 4. Checks -------------------------------------------------------------------------------
if [ "$OUTAGE" -ge 0 ] && [ "$OUTAGE" -le "$OUTAGE_MAX_S" ]; then
  pass "outage" "stop to first write ${OUTAGE}s (limit ${OUTAGE_MAX_S}s); standalone was left: $CTL"
else fail "outage" "first write after ${OUTAGE}s (limit ${OUTAGE_MAX_S}s; -1 = never); $CTL"; fi

ITEMS1=$(pq "SELECT count(*) FROM items" 2>/dev/null); PLAIN1=$(pq "SELECT count(*) FROM plain_t" 2>/dev/null)
if [ "$ITEMS1" = "$ITEMS0" ] && [ "$PLAIN1" = "$PLAIN0" ]; then
  pass "row counts" "items $ITEMS0 -> $ITEMS1, plain_t $PLAIN0 -> $PLAIN1 (index still used: $(pq "SELECT count(*) FROM pg_indexes WHERE indexname='items_emb_hnsw'" 2>/dev/null))"
else fail "row counts" "items $ITEMS0 -> ${ITEMS1:-?}, plain_t $PLAIN0 -> ${PLAIN1:-?}"; fi

LIST=$(d exec "$P-patroni" /opt/patroni/bin/patronictl -c /etc/patroni/patroni.yml list -f json 2>&1)
LEADERS=$(printf '%s' "$LIST" | python3 -c 'import json,sys
try: print(sum(1 for m in json.load(sys.stdin) if m.get("Role") == "Leader"))
except Exception: print(-1)')
[ "$LEADERS" = 1 ] && pass "one leader" "patronictl list: 1 Leader" || fail "one leader" "leaders=$LEADERS; $(printf '%s' "$LIST" | head -c 300)"

REC=$(pq "SELECT pg_is_in_recovery()" postgres 2>/dev/null)
[ "$REC" = f ] && pass "not in recovery" "pg_is_in_recovery() = f" || fail "not in recovery" "pg_is_in_recovery() = ${REC:-?}"

ARC0=$(pq "SELECT archived_count FROM pg_stat_archiver" postgres 2>/dev/null || echo 0)
pq "SELECT pg_switch_wal()" postgres >/dev/null 2>&1; pq "INSERT INTO probe DEFAULT VALUES" >/dev/null 2>&1
arc_up() { [ "$(pq "SELECT archived_count FROM pg_stat_archiver" postgres)" -gt "${ARC0:-0}" ]; }
if waitfor 90 arc_up && [ "$(pq "SELECT failed_count FROM pg_stat_archiver" postgres)" = 0 ]; then
  pass "WAL archiving" "archived_count $ARC0 -> $(pq "SELECT archived_count FROM pg_stat_archiver" postgres), failed_count 0"
else fail "WAL archiving" "archived_count $ARC0 -> $(pq "SELECT archived_count || ' failed ' || failed_count FROM pg_stat_archiver" postgres 2>&1)"; fi

BK=$(d exec "$P-patroni" sh -c 'wal-g backup-push "$PGDATA"' 2>&1); BKRC=$?
BKN=$(d exec "$P-patroni" wal-g backup-list 2>&1 | grep -c base_)
[ "$BKRC" = 0 ] && [ "$BKN" -ge 1 ] && pass "wal-g backup-push" "rc 0, $BKN base backup(s) listed" || fail "wal-g backup-push" "rc $BKRC; $(printf '%s' "$BK" | tail -3)"

# PITR: 100 rows, note the time, 100 more rows; restore the base backup + WAL to the note.
pq "INSERT INTO plain_t (note) SELECT 'pre ' || g FROM generate_series(1, 100) g" >/dev/null 2>&1
sleep 2
TARGET=$(pq "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US') || '+00'" postgres)
WANT=$(pq "SELECT count(*) FROM plain_t"); sleep 2
pq "INSERT INTO plain_t (note) SELECT 'post ' || g FROM generate_series(1, 100) g" >/dev/null 2>&1
LAST0=$(pq "SELECT last_archived_wal FROM pg_stat_archiver" postgres)
pq "SELECT pg_switch_wal()" postgres >/dev/null 2>&1
arc_moved() { [ "$(pq "SELECT last_archived_wal FROM pg_stat_archiver" postgres)" != "$LAST0" ]; }
waitfor 90 arc_moved
must d run -d --name "$P-restore" "${LBL[@]}" --platform "$PLATFORM" --env-file "$WORK/walg.env" \
  -v "$P-walg:/walg-archive" --entrypoint sleep "$P-patroni:test" infinity >/dev/null
rx() { d exec "$P-restore" sh -c "$1"; }
rx 'mkdir -m 700 /tmp/restore && wal-g backup-fetch /tmp/restore LATEST' >/dev/null 2>&1; FRC=$?
rx 'touch /tmp/restore/recovery.signal' >/dev/null 2>&1
d exec -i "$P-restore" sh -c 'cat >> /tmp/restore/postgresql.auto.conf' <<CONF
restore_command = 'wal-g wal-fetch %f %p'
recovery_target_time = '$TARGET'
recovery_target_action = 'promote'
archive_mode = 'off'
listen_addresses = ''
unix_socket_directories = '/tmp'
hba_file = '/tmp/restore/pg_hba.conf'
ident_file = '/tmp/restore/pg_ident.conf'
CONF
rx 'pg_ctl -D /tmp/restore -l /tmp/restore.log -w -t 300 start' >/dev/null 2>&1
rq() { d exec "$P-restore" psql -h /tmp -U postgres -d "${2:-$DB}" -Atc "$1"; }
promoted() { [ "$(rq 'SELECT pg_is_in_recovery()' postgres)" = f ]; }
if [ "$FRC" = 0 ] && waitfor 180 promoted; then
  GOT=$(rq "SELECT count(*) FROM plain_t"); GOTI=$(rq "SELECT count(*) FROM items")
  [ "$GOT" = "$WANT" ] && [ "$GOTI" = "$ITEMS0" ] \
    && pass "PITR" "restored to $TARGET: plain_t $GOT (= $WANT at that time, $(pq "SELECT count(*) FROM plain_t") now), items $GOTI" \
    || fail "PITR" "restored to $TARGET: plain_t $GOT want $WANT, items $GOTI want $ITEMS0"
else fail "PITR" "backup-fetch rc $FRC or restore did not finish; $(rx 'tail -5 /tmp/restore.log' 2>&1)"; fi
d rm -f "$P-restore" >/dev/null

# Postgres crash: kill -9 the postmaster; Patroni must restart it.
PID0=$(d exec "$P-patroni" sh -c 'head -1 "$PGDATA/postmaster.pid"' 2>/dev/null)
d exec "$P-patroni" sh -c 'kill -9 "$(head -1 "$PGDATA/postmaster.pid")"' >/dev/null 2>&1
sleep 2
if wait_write 120; then
  PID1=$(d exec "$P-patroni" sh -c 'head -1 "$PGDATA/postmaster.pid"' 2>/dev/null)
  [ "$PID1" != "$PID0" ] && pass "crash restart" "postmaster $PID0 killed, new postmaster $PID1, write ok" \
    || fail "crash restart" "write ok but postmaster pid unchanged ($PID0)"
else fail "crash restart" "no successful write within 120s of kill -9"; fi

# etcd loss: stop ONE of the two running members (quorum gone); the node must stay primary.
d stop -t 30 "$P-etcd-w" >/dev/null
BAD=""; for i in 1 2 3 4 5 6 7; do   # 70 s: past the 30 s leader TTL plus two loop_wait periods
  sleep 10
  code=$(d exec "$P-patroni" curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8008/primary 2>/dev/null)
  write_ok 2>/dev/null || BAD="$BAD write@${i}0s"
  [ "$code" = 200 ] || BAD="$BAD primary=$code@${i}0s"
done
FS=$(d logs "$P-patroni" 2>&1 | grep -ci failsafe)
[ -z "$BAD" ] && pass "etcd loss (failsafe)" "witness etcd stopped; /primary 200 and writes ok for 70 s ($FS failsafe log lines)" \
  || fail "etcd loss (failsafe)" "witness etcd stopped; problems:$BAD"
must d start "$P-etcd-w" >/dev/null
etcd_two() { [ "$(d exec "$P-etcd-a" etcdctl endpoint health --cluster 2>&1 | grep -c 'is healthy')" -ge 2 ]; }
waitfor 90 etcd_two || echo "ha-rehearsal: warning, etcd did not return to 2 healthy members"
leader_back() { [ "$(d exec "$P-patroni" curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8008/primary)" = 200 ]; }
waitfor 90 leader_back
pq "SELECT pg_switch_wal()" postgres >/dev/null 2>&1; pq "INSERT INTO probe DEFAULT VALUES" >/dev/null 2>&1
sleep 5

# ha-checks.sh against the rehearsal: a docker shim maps `docker compose exec -T etcd|db ...`.
cat > "$WORK/shim/docker" <<SHIM
#!/usr/bin/env bash
[ "\$1" = compose ] || exec "$REAL_DOCKER" --context "$ctx" "\$@"
while [ "\$#" -gt 0 ] && [ "\$1" != exec ]; do shift; done
shift; [ "\$1" = -T ] && shift
svc=\$1; shift
case "\$svc" in etcd) c=$P-etcd-a ;; db) c=$P-patroni ;; *) exit 2 ;; esac
exec "$REAL_DOCKER" --context "$ctx" exec "\$c" "\$@"
SHIM
chmod +x "$WORK/shim/docker"
# Disk checks are meaningless against the host disk, so they are switched off (>100%).
HC=$(PATH="$WORK/shim:$PATH" PROJECT_DIR="$WORK" HC_URL='' SNAPSHOT_DIR="$WORK/none" EXPECT_REPLICAS=0 ETCD_MEMBERS=2 \
  ALERT_AT_PCT=101 PRUNE_AT_PCT=101 \
  PATRONI_URL="http://127.0.0.1:$HPORT/primary" PATRONI_CLUSTER_URL="http://127.0.0.1:$HPORT/cluster" \
  bash "$SCRIPTS/ha-checks.sh" 2>&1); HCRC=$?
[ "$HCRC" = 0 ] && pass "ha-checks.sh" "$(printf '%s' "$HC" | tr '\n' ' ')" || fail "ha-checks.sh" "$(printf '%s' "$HC" | tr '\n' ' ')"

# ---- 5. Summary ---------------------------------------------------------------------------------
echo; echo "=== ha-rehearsal summary ==="
FAILS=0
for i in "${!NAMES[@]}"; do
  printf '%-4s %s\n' "${RESULTS[$i]}" "${NAMES[$i]}"
  [ "${RESULTS[$i]}" = PASS ] || FAILS=$((FAILS + 1))
done
echo "outage (stop to first write): ${OUTAGE}s"
echo "$FAILS failed. Leave it up to inspect, then: DOCKER_CONTEXT=$ctx $0 down"
[ "$FAILS" = 0 ]
