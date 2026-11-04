#!/usr/bin/env python3
"""Failover drill on throwaway containers (HA-CF-FAILOVER, plan section 5 step F3).

Two Postgres 17 containers (node A primary, node B streaming standby), a fake Cloudflare
Load Balancing API, and the REAL controller (infra/scripts/cf_failover.py) plus adapter
(infra/scripts/ha-pg.sh) running once per node, with every window scaled down to seconds.
Synthetic data only; needs a local Docker daemon and nothing else. Never points at a real host.

    python3 infra/rehearsal/cf_drill.py            # all scenarios, PASS/FAIL per scenario
    python3 infra/rehearsal/cf_drill.py --keep     # leave the containers up afterwards

A monitor samples both nodes every 0.3 s for the whole run; one sample with both writable
fails the drill. A writer inserts into whichever node is primary and checks at the end that
every acknowledged row survived (async replication may lose the last second; reported).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "infra" / "scripts" / "cf_failover.py"
ADAPTER = ROOT / "infra" / "scripts" / "ha-pg.sh"
IMAGE = os.environ.get("DRILL_IMAGE", "postgres:17")
REDIS_IMAGE = "redis:7.4"
HAPROXY_IMAGE = "haproxy:2.9"
PGB_IMAGE = "edoburu/pgbouncer:v1.23.1-p3"
REDIS_USERS = {"admin": "drill-admin", "app": "drill-app", "repl": "drill-repl", "hacheck": "drill-check"}
NET = "drill-link"          # the private link between the two nodes (cut = disconnect from it)


def local_net(n):
    return f"drill-local-{n}"  # one node's own network: its app path never crosses the link
PGDATA = "/var/lib/postgresql/data/pgdata"
NODES = {"a": "crm-a", "b": "crm-b"}
CF_INTERVAL = 2.0

TIMING = {
    "TICK": "1", "CF_CHECK_INTERVAL": "2", "CF_CONSECUTIVE_DOWN": "2",   # fence 8 s
    "FENCE_MARGIN": "6",                                                  # promote 14 s
    "FENCE_HOLD": "20", "APP_SICK_AFTER": "20", "APP_SICK_COOLDOWN": "60",
    "REJOIN_AFTER": "5", "BOTH_STANDBY_AFTER": "4", "MAX_OBS_GAP": "10",
}


def sh(*args, check=True, timeout=120, quiet=False):
    r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {r.returncode}: {r.stderr.strip()[-400:]}")
    return r.stdout.strip()


def peer(n):
    return "b" if n == "a" else "a"


def cname(n):
    return f"drill-{n}"


def psql(n, sql, timeout=10):
    try:
        r = subprocess.run(["docker", "exec", "-u", "postgres", cname(n), "psql", "-XAtq", "-d", "postgres", "-c", sql],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, ""
    return r.returncode, r.stdout.strip()


def role(n):
    rc, out = psql(n, "select pg_is_in_recovery()", timeout=5)
    if rc != 0:
        return "down"
    return {"f": "primary", "t": "standby"}.get(out, "down")


def app_writable(n):
    """The node's app path: its pgbouncer, wherever that points, answers as a writable database."""
    try:
        r = subprocess.run(["docker", "exec", f"drill-probe-{n}", "psql", "-XAtq", "-h", f"drill-pgb-{n}", "-p", "6432",
                            "-U", "postgres", "-d", "postgres", "-c", "select pg_is_in_recovery()"],
                           capture_output=True, text=True, timeout=3)
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0 and r.stdout.strip() == "f"


def app_sql(n, sql, timeout=8):
    """A query through node n's app path (its pgbouncer)."""
    try:
        r = subprocess.run(["docker", "exec", f"drill-probe-{n}", "psql", "-XAtq", "-h", f"drill-pgb-{n}", "-p", "6432",
                            "-U", "postgres", "-d", "postgres", "-c", sql], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, ""
    return r.returncode, r.stdout.strip()


def app_redis(n, *cmd):
    """A Redis command through node n's app path (its HAProxy, which picks the master)."""
    try:
        r = subprocess.run(["docker", "exec", "-e", f"REDISCLI_AUTH={REDIS_USERS['app']}", f"drill-redis-{n}", "redis-cli",
                            "--user", "app", "-h", f"drill-rproxy-{n}", "-p", "6380", *cmd], capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        return ""
    return (r.stdout or r.stderr).strip()  # an error reply (NOPERM) is the answer too


def redis_role(n):
    try:
        r = subprocess.run(["docker", "exec", f"drill-redis-{n}", "redis-cli", "--user", "admin", "role"],
                           capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout.split("\n")[0].strip() if r.returncode == 0 else ""


# ---------------------------------------------------------------- fake Cloudflare


class FakeCF:
    """Pool health as Cloudflare would report it: the monitor (a primary answering) checked every
    CF_INTERVAL, unhealthy after 2 failures, healthy after 1 success. Each node's controller calls
    its own URL prefix, so a node whose `net` is off gets no answer (UNKNOWN), like a box cut off."""

    def __init__(self, active_active=False):
        self.aa = active_active
        self.lock = threading.Lock()
        self.api_up = True
        self.net = {"a": True, "b": True}
        self.app_ok = {"a": True, "b": True}
        self.fails = {"a": 0, "b": 0}
        self.healthy = {"a": True, "b": False}
        self.stop = False
        cf = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                parts = self.path.strip("/").split("/")
                caller = parts[0].replace("node-", "")
                with cf.lock:
                    ok = cf.api_up and cf.net.get(caller, False)
                    pool = parts[5].replace("pool-", "") if len(parts) > 5 else ""
                    healthy = True if cf.aa else cf.healthy.get(pool)
                if not ok or healthy is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                if cf.aa:  # one pool, both nodes as origins, each with its own health
                    region = {"healthy": cf.healthy["a"] or cf.healthy["b"], "origins": [
                        {"origin-a": {"healthy": cf.healthy["a"]}}, {"origin-b": {"healthy": cf.healthy["b"]}}]}
                else:
                    region = {"healthy": healthy, "origins": []}
                body = json.dumps({"success": True, "result": {"pool_id": pool, "pop_health": {
                    "Singapore, SG": region}}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self.monitor, daemon=True).start()

    def check(self, n):
        with self.lock:
            reach = self.net[n] and self.app_ok[n]
        # The monitor (`/api/v1/health/role`): 200 only when the node's APP reaches a writable
        # database. Active-passive: its own; active-active: through its pgbouncer.
        ok = reach and (app_writable(n) if self.aa else role(n) == "primary")
        with self.lock:
            self.fails[n] = 0 if ok else self.fails[n] + 1
            self.healthy[n] = ok or (self.healthy[n] and self.fails[n] < 2)

    def monitor(self):
        # Each origin is checked on its own, like Cloudflare: a hanging check of a dead node
        # never delays the check of the live one.
        while not self.stop:
            started = time.time()
            threads = [threading.Thread(target=self.check, args=(n,)) for n in ("a", "b")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            time.sleep(max(0.0, CF_INTERVAL - (time.time() - started)))

    def set(self, **kw):
        with self.lock:
            for k, v in kw.items():
                if isinstance(v, dict):
                    getattr(self, k).update(v)
                else:
                    setattr(self, k, v)


# ---------------------------------------------------------------- stack


class Stack:
    def __init__(self, workdir: Path, cf: FakeCF, active_active=False):
        self.dir = workdir
        self.cf = cf
        self.aa = active_active
        self.procs = {}

    def adapter_env(self, n):
        p = peer(n)
        return {
            "NODE_NAME": NODES[n], "PEER_NAME": NODES[p], "PEER_HOST": cname(p), "REPL_USER": "postgres",
            "PGDATA": PGDATA,
            "PG_EXEC": f"docker exec -u postgres {cname(n)}",
            "PG_RUNNING": f"docker exec {cname(n)} true",
            "PG_START": f"docker start {cname(n)}",
            "PG_STOP": f"docker stop -t 10 {cname(n)}",
            "PG_OFFLINE_SH": f"docker run --rm --network container:drill-probe-{n} -u postgres "
                             f"-v drill-{n}-data:/var/lib/postgresql/data {IMAGE} sh -c",
            "PEER_PSQL": f"docker exec drill-probe-{n} psql",
            "WORKERS_STOP": "true",
            "SYNC_MODE": "remote_write",
            **({
                "ACTIVE_ACTIVE": "1",
                "ROUTE_FILE": str(self.dir / f"route-{n}" / "route.ini"),
                "PGB_LOCAL_HOST": cname(n),
                # RELOAD alone keeps idle server connections to the OLD primary, which hang on a
                # dead host; RECONNECT closes them so the next query opens one to the new target.
                "PGB_RELOAD": f"docker exec drill-pgb-{n} psql -h 127.0.0.1 -p 6432 -U postgres pgbouncer -c RELOAD -c RECONNECT",
                "REDIS_CLI": f"docker exec drill-redis-{n} redis-cli --user admin",
                "PEER_REDIS_HOST": f"drill-redis-{p}",
            } if self.aa else {}),
        }

    def node_containers(self, n):
        extra = [f"drill-pgb-{n}", f"drill-redis-{n}", f"drill-rproxy-{n}"] if self.aa else []
        return [cname(n), f"drill-probe-{n}", *extra]

    def up(self):
        self.down(quiet=True)
        left = sh("docker", "volume", "ls", "-q", "--filter", "name=drill-")
        if left:
            raise RuntimeError(f"leftover drill volumes, remove them first: {left}")
        init = self.dir / "init"
        init.mkdir(exist_ok=True)
        (init / "repl.sh").write_text('echo "host replication all all trust" >> "$PGDATA/pg_hba.conf"\n')
        sh("docker", "network", "create", NET)
        for n in ("a", "b"):
            sh("docker", "network", "create", local_net(n))
            sh("docker", "volume", "create", f"drill-{n}-data")
            sh("docker", "run", "-d", "--name", f"drill-probe-{n}", "--network", NET, IMAGE, "sleep", "infinity")
            sh("docker", "network", "connect", local_net(n), f"drill-probe-{n}")
        sh("docker", "run", "-d", "--name", cname("a"), "--network", NET, "--restart", "no",
           "-v", "drill-a-data:/var/lib/postgresql/data", "-v", f"{init}:/docker-entrypoint-initdb.d:ro",
           *self.pg_args())
        sh("docker", "network", "connect", local_net("a"), cname("a"))
        self.wait_role("a", "primary", 60)
        psql("a", "create table drill(id bigserial primary key, node text, at timestamptz default now())")
        psql("a", "select pg_create_physical_replication_slot('crm_b', true)")
        psql("a", "alter system set primary_conninfo = 'host=drill-b user=postgres application_name=crm-a'")
        psql("a", "alter system set primary_slot_name = 'crm_a'")
        conf = (f"echo \"primary_conninfo = 'host=drill-a user=postgres application_name=crm-b'\" >> {PGDATA}/postgresql.auto.conf"
                f" && echo \"primary_slot_name = 'crm_b'\" >> {PGDATA}/postgresql.auto.conf && touch {PGDATA}/standby.signal")
        sh("docker", "run", "--rm", "--network", NET, "-u", "postgres", "-v", "drill-b-data:/var/lib/postgresql/data",
           IMAGE, "sh", "-c", f"pg_basebackup -h drill-a -U postgres -D {PGDATA} -X stream && {conf}", timeout=300)
        sh("docker", "run", "-d", "--name", cname("b"), "--network", NET, "--restart", "no",
           "-v", "drill-b-data:/var/lib/postgresql/data", *self.pg_args())
        sh("docker", "network", "connect", local_net("b"), cname("b"))
        self.wait_role("b", "standby", 60)
        self.wait_streaming("b", 60)
        if self.aa:
            self.up_app_tier()

    def up_app_tier(self):
        """Per node: pgbouncer (target in route/route.ini), Redis (A master, B its replica) and
        HAProxy sending Redis traffic to whichever is master. Same layout as compose.aa.yml."""
        for n in ("a", "b"):
            p = peer(n)
            rdir = self.dir / f"route-{n}"
            rdir.mkdir(exist_ok=True)
            target = cname(n) if n == "a" else cname("a")
            (rdir / "route.ini").write_text(
                f"; route={'local' if n == 'a' else 'peer'} (written by the drill setup)\n[databases]\n* = host={target} port=5432\n")
            (self.dir / f"pgbouncer-{n}.ini").write_text(
                "%include /etc/pgbouncer/route/route.ini\n\n[pgbouncer]\nlisten_addr = 0.0.0.0\nlisten_port = 6432\n"
                "auth_type = trust\nauth_file = /etc/pgbouncer/userlist.txt\npool_mode = transaction\n"
                "server_lifetime = 30\nserver_check_query = select 1\nadmin_users = postgres\nserver_login_retry = 1\n")
            (self.dir / f"userlist-{n}.txt").write_text('"postgres" ""\n')
            for f in (rdir, self.dir / f"pgbouncer-{n}.ini", self.dir / f"userlist-{n}.txt"):
                os.chmod(f, 0o755 if f.is_dir() else 0o644)
            sh("docker", "run", "-d", "--name", f"drill-pgb-{n}", "--network", local_net(n),
               "-v", f"{self.dir}/pgbouncer-{n}.ini:/etc/pgbouncer/pgbouncer.ini:ro",
               "-v", f"{self.dir}/userlist-{n}.txt:/etc/pgbouncer/userlist.txt:ro",
               "-v", f"{rdir}:/etc/pgbouncer/route:ro", PGB_IMAGE)
            sh("docker", "network", "connect", NET, f"drill-pgb-{n}")
            # The same config + ACL layout as templates/active-active/redis.conf + users.acl.
            (self.dir / f"redis-{n}.conf").write_text(
                f"aclfile /etc/redis/users.acl\nappendonly no\nreplica-read-only yes\nmasteruser repl\n"
                f"masterauth {REDIS_USERS['repl']}\nport 6379\nbind 0.0.0.0\nprotected-mode yes\n"
                )  # no replicaof: as in the template, `ha-pg.sh route peer` makes it a replica
            (self.dir / f"users-{n}.acl").write_text(
                "user default off\n"
                f"user admin on >{REDIS_USERS['admin']} ~* &* +@all\n"
                f"user app on >{REDIS_USERS['app']} ~* &* +@all -@admin -flushall -flushdb\n"
                f"user repl on >{REDIS_USERS['repl']} +psync +replconf +ping\n"
                f"user hacheck on >{REDIS_USERS['hacheck']} +info +ping +quit\n")
            for f in (f"redis-{n}.conf", f"users-{n}.acl"):
                os.chmod(self.dir / f, 0o644)
            sh("docker", "run", "-d", "--name", f"drill-redis-{n}", "--network", NET,
               "-e", f"REDISCLI_AUTH={REDIS_USERS['admin']}",
               "-v", f"{self.dir}/redis-{n}.conf:/usr/local/etc/redis/redis.conf:ro",
               "-v", f"{self.dir}/users-{n}.acl:/etc/redis/users.acl:ro",
               REDIS_IMAGE, "redis-server", "/usr/local/etc/redis/redis.conf")
            sh("docker", "network", "connect", local_net(n), f"drill-redis-{n}")
            (self.dir / f"haproxy-{n}.cfg").write_text(
                "global\n    maxconn 512\ndefaults\n    mode tcp\n    timeout connect 2s\n    timeout client 1h\n"
                "    timeout server 1h\n    timeout check 2s\nresolvers docker\n    nameserver dns 127.0.0.11:53\n"
                "    hold valid 1s\nfrontend redis_in\n    bind 0.0.0.0:6380\n    default_backend redis_master\n"
                "backend redis_master\n    option tcp-check\n    tcp-check connect\n"
                f"    tcp-check send AUTH\\ hacheck\\ {REDIS_USERS['hacheck']}\\r\\n\n    tcp-check expect string +OK\n"
                "    tcp-check send INFO\\ replication\\r\\n\n    tcp-check expect string role:master\n"
                "    tcp-check send QUIT\\r\\n\n    tcp-check expect string +OK\n"
                f"    server local drill-redis-{n}:6379 check inter 1s fall 2 rise 2 resolvers docker init-addr none on-marked-down shutdown-sessions on-marked-up shutdown-backup-sessions\n"
                f"    server peer drill-redis-{p}:6379 check inter 1s fall 2 rise 2 backup resolvers docker init-addr none on-marked-down shutdown-sessions\n")
            os.chmod(self.dir / f"haproxy-{n}.cfg", 0o644)
            sh("docker", "run", "-d", "--name", f"drill-rproxy-{n}", "--network", NET,
               "-v", f"{self.dir}/haproxy-{n}.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro", HAPROXY_IMAGE)
            sh("docker", "network", "connect", local_net(n), f"drill-rproxy-{n}")
        # Node B joins the way the runbook says: `ha-pg.sh route peer` (Redis replica, pgbouncer).
        env = {**os.environ, **self.adapter_env("b")}
        r = subprocess.run([str(ADAPTER), "route", "peer"], env=env, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"route peer on b failed: {r.stderr.strip()[-300:]}")
        end = time.time() + 60
        while time.time() < end and not (app_writable("a") and app_writable("b") and app_redis("b", "ping") == "PONG"):
            time.sleep(1)
        if not (app_writable("a") and app_writable("b")):
            raise RuntimeError("app tier did not come up: " + sh("docker", "logs", "--tail", "20", "drill-pgb-b", check=False))

    def pg_args(self):
        return ["-e", "POSTGRES_PASSWORD=drill", "-e", f"PGDATA={PGDATA}", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                IMAGE, "-c", "wal_level=replica", "-c", "wal_log_hints=on", "-c", "hot_standby=on",
                "-c", "max_wal_senders=5", "-c", "max_replication_slots=5", "-c", "wal_keep_size=256MB",
                "-c", "max_slot_wal_keep_size=1GB",
                # A cut link sends no RST: the primary notices the dead standby only after this,
                # and until then a synchronous commit waits (prod value: plan section 3, P4).
                "-c", "wal_sender_timeout=3s", "-c", "wal_receiver_timeout=3s"]

    def down(self, quiet=False):
        for n in list(self.procs):
            self.stop_controller(n)
        for c in ("drill-a", "drill-b", "drill-probe-a", "drill-probe-b", "drill-pgb-a", "drill-pgb-b",
                  "drill-redis-a", "drill-redis-b", "drill-rproxy-a", "drill-rproxy-b"):
            sh("docker", "rm", "-f", c, check=False)
        for v in ("drill-a-data", "drill-b-data"):
            sh("docker", "volume", "rm", "-f", v, check=False)
        for net in (NET, local_net("a"), local_net("b")):
            sh("docker", "network", "rm", net, check=False)

    def start_controller(self, n):
        env = {**os.environ, **self.adapter_env(n), **TIMING, **({"APP_SICK_AFTER": "0"} if self.aa else {}),
               "PG_CMD": str(ADAPTER),
               "STATE_FILE": str(self.dir / f"state-{n}.json"),
               "CF_API_BASE": f"http://127.0.0.1:{self.cf.port}/node-{n}",
               "CF_ACCOUNT_ID": "drill", "CF_POOL_SELF": f"pool-{n}", "CF_POOL_PEER": f"pool-{peer(n)}",
               **({"CF_POOL_SELF": "pool-shared", "CF_POOL_PEER": "pool-shared",
                   "CF_ORIGIN_SELF": f"origin-{n}", "CF_ORIGIN_PEER": f"origin-{peer(n)}"} if self.aa else {}),
               "CF_API_TOKEN_FILE": str(self.dir / "token"),
               "ALERT_CMD": f"cat >> {self.dir}/alerts-{n}.log; echo >> {self.dir}/alerts-{n}.log"}
        (self.dir / "token").write_text("drill-token\n")
        log = open(self.dir / f"controller-{n}.log", "a")
        self.procs[n] = subprocess.Popen([sys.executable, str(CONTROLLER)], env=env, stdout=log, stderr=subprocess.STDOUT)
        time.sleep(2)
        if self.procs[n].poll() is not None:
            tail = (self.dir / f"controller-{n}.log").read_text().strip().splitlines()[-1:]
            raise SystemExit(f"controller {n} exited at start: {tail}")

    def stop_controller(self, n):
        p = self.procs.pop(n, None)
        if p:
            p.kill()
            p.wait()

    def cut(self, n):
        """Node n loses the private link; its own network (app -> pgbouncer -> local db) stays."""
        for c in self.node_containers(n):
            sh("docker", "network", "disconnect", "-f", NET, c, check=False)

    def join(self, n):
        for c in self.node_containers(n):
            sh("docker", "network", "connect", NET, c, check=False)

    def wait_role(self, n, want, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if role(n) == want:
                return time.time()
            time.sleep(0.3)
        raise AssertionError(f"{cname(n)} not {want} after {timeout}s (is {role(n)})")

    def wait_streaming(self, n, timeout):
        end = time.time() + timeout
        while time.time() < end:
            rc, out = psql(n, "select count(*) from pg_stat_wal_receiver where status = 'streaming'")
            if rc == 0 and out == "1":
                return
            time.sleep(0.5)
        raise AssertionError(f"{cname(n)} not streaming after {timeout}s")

    def alerts(self, n):
        p = self.dir / f"alerts-{n}.log"
        return p.read_text() if p.exists() else ""


# ---------------------------------------------------------------- monitor + writer


class Watch:
    def __init__(self, active_active=False):
        self.aa = active_active
        self.served = {"a": 0, "b": 0}
        self.redis_two_masters = 0
        self.violations = []
        self.acked = []
        self.stop = False
        threading.Thread(target=self.monitor, daemon=True).start()
        threading.Thread(target=self.writer, daemon=True).start()

    def monitor(self):
        while not self.stop:
            ra, rb = role("a"), role("b")
            if ra == "primary" and rb == "primary":
                self.violations.append(time.strftime("%H:%M:%S"))
            if self.aa and redis_role("a") == "master" and redis_role("b") == "master":
                self.redis_two_masters += 1
            time.sleep(0.3)

    def writer(self):
        turn = 0
        while not self.stop:
            if self.aa:
                # Like the load balancer: alternate between the two nodes' app paths; a node
                # whose path fails is skipped, the request goes to the other one.
                order = ("a", "b") if turn % 2 == 0 else ("b", "a")
                turn += 1
                for n in order:
                    rc, out = app_sql(n, f"insert into drill(node) values ('via-{n}') returning id", timeout=5)
                    if rc == 0 and out.isdigit():
                        self.acked.append(int(out))
                        self.served[n] += 1
                        break
            else:
                for n in ("a", "b"):
                    rc, out = psql(n, f"insert into drill(node) values ('{n}') returning id", timeout=5)
                    if rc == 0 and out.isdigit():
                        self.acked.append(int(out))
                        break
            time.sleep(0.3)


# ---------------------------------------------------------------- scenarios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--mode", choices=("aa", "ap"), default="aa",
                    help="aa: active-active app tier (default, owner 4 Nov); ap: active-passive")
    args = ap.parse_args()
    aa = args.mode == "aa"
    workdir = Path(tempfile.mkdtemp(prefix="cf-drill-"))
    cf = FakeCF(active_active=aa)
    st = Stack(workdir, cf, active_active=aa)
    results = []

    def scenario(name, fn):
        t0 = time.time()
        try:
            note = fn() or ""
            results.append((name, "PASS", f"{time.time() - t0:.0f}s {note}"))
        except Exception as e:  # noqa: BLE001
            results.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        print(f"{results[-1][1]} {name}: {results[-1][2]}", flush=True)

    print(f"drill workdir {workdir}", flush=True)
    stray = sh("pgrep", "-f", r"^\S*python\S* \S*infra/scripts/cf_failover\.py$", check=False)
    if stray:
        raise SystemExit(f"a controller from an earlier drill is still running (pids {stray.split()}); stop it first")
    st.up()
    watch = Watch(active_active=aa)
    st.start_controller("a")
    st.start_controller("b")

    def steady():
        time.sleep(12)
        assert role("a") == "primary" and role("b") == "standby"
        st.wait_streaming("b", 10)
        rc, out = psql("a", "show synchronous_standby_names")
        assert out.strip('"') == "crm-b", f"sync names {out!r}"
        return "A primary, B streaming, A sync standby = crm-b"

    def link_cut_only():
        st.cut("b")  # B and its probe off the link; Cloudflare still reaches both
        time.sleep(10)
        rc, out = psql("a", "show synchronous_standby_names")
        assert out == "", f"sync names not dropped: {out!r}"
        rc, _ = psql("a", "insert into drill(node) values ('sync-check')")
        assert rc == 0, "a write blocked while the standby was gone"
        time.sleep(26)
        assert role("a") == "primary" and role("b") == "standby"
        st.join("b")
        st.wait_streaming("b", 30)
        return "no failover; sync standby dropped at once, writes kept working"

    def cf_api_down():
        cf.set(api_up=False)
        time.sleep(30)
        assert role("a") == "primary" and role("b") == "standby"
        cf.set(api_up=True)
        time.sleep(4)
        return "no failover while the Cloudflare API was down"

    def kill_a():
        t0 = time.time()
        st.stop_controller("a")              # the whole box: controller, Postgres, network
        sh("docker", "stop", "-t", "1", cname("a"))
        st.cut("a")
        cf.set(net={"a": False})
        t1 = st.wait_role("b", "primary", 90)
        took = t1 - t0
        cf.set(net={"a": True})
        st.join("a")
        st.start_controller("a")             # box back: D1 starts it as a standby, S2 rejoins
        st.wait_role("a", "standby", 60)
        st.wait_streaming("a", 120)
        assert "promoted" in st.alerts("b")
        return f"B primary {took:.0f}s after A died; A back as a standby following B"

    def isolate_primary_b():
        t0 = time.time()
        st.cut("b")
        cf.set(net={"b": False})
        fenced = None
        end = time.time() + 90
        while time.time() < end and role("a") != "primary":
            if fenced is None and role("b") == "down":
                fenced = time.time()
            time.sleep(0.3)
        t1 = st.wait_role("a", "primary", 5)
        assert fenced is not None and fenced < t1, "B was not fenced before A promoted"
        cf.set(net={"b": True})
        st.join("b")
        st.wait_role("b", "standby", 90)
        st.wait_streaming("b", 120)
        return f"B fenced after {fenced - t0:.0f}s, A promoted after {t1 - t0:.0f}s, B rejoined"

    def app_sick_with_reseed():
        t0 = time.time()
        cf.set(app_ok={"a": False})          # Cloudflare cannot get a 200 from A; link stays up
        end = time.time() + 90
        while time.time() < end and role("a") != "down":
            time.sleep(0.3)
        assert role("a") == "down", "A did not fence itself"
        fenced = time.time() - t0
        # Damage A's data while it is fenced so pg_rewind cannot work: Q4 re-seed path.
        sh("docker", "run", "--rm", "-u", "postgres", "-v", "drill-a-data:/var/lib/postgresql/data", IMAGE,
           "rm", "-f", f"{PGDATA}/global/pg_control")
        t1 = st.wait_role("b", "primary", 90)
        cf.set(app_ok={"a": True})
        st.wait_role("a", "standby", 180)
        st.wait_streaming("a", 120)
        ls = sh("docker", "run", "--rm", "-v", "drill-a-data:/d", IMAGE, "ls", "/d")
        assert "pgdata.old-" in ls, f"old data not kept aside: {ls}"
        assert "RE-SEEDED" in st.alerts("a"), st.alerts("a")
        return f"A fenced after {fenced:.0f}s, B primary after {t1 - t0:.0f}s, A re-seeded, old data kept"

    def both_reboot():
        for n in ("a", "b"):
            st.stop_controller(n)
        for n in ("a", "b"):
            sh("docker", "stop", "-t", "5", cname(n))
        st.start_controller("a")
        st.start_controller("b")
        end = time.time() + 90
        while time.time() < end and "primary" not in (role("a"), role("b")):
            time.sleep(0.3)
        roles = sorted([role("a"), role("b")])
        assert "primary" in roles, roles
        loser = "a" if role("b") == "primary" else "b"
        st.wait_role(loser, "standby", 60)
        st.wait_streaming(loser, 120)
        return f"one writer back ({'b' if loser == 'a' else 'a'}), the other follows"

    def both_reboot_link_down():
        before = "a" if role("a") == "primary" else "b"
        follower = peer(before)
        for n in ("a", "b"):
            st.stop_controller(n)
        for n in ("a", "b"):
            sh("docker", "stop", "-t", "5", cname(n))
        st.cut("a")
        st.cut("b")
        st.start_controller("a")
        st.start_controller("b")
        t1 = st.wait_role(follower, "primary", 90)
        time.sleep(10)
        assert role(before) == "standby", f"old primary is {role(before)}"
        st.join("a")
        st.join("b")
        st.wait_streaming(before, 120)
        return f"only the former standby ({follower}) took over; the other rejoined"

    # ---- active-active scenarios: both nodes serve; the database moves only on a db/box loss.

    def wait_until(cond, timeout, what):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return time.time()
            time.sleep(0.5)
        raise AssertionError(f"not {what} after {timeout}s")

    def routes_follow(primary, only_primary=False):
        """Each live node's endpoints name the one primary: local there, peer on the other node.
        `only_primary` while the other box is dead (its controller is dead with it)."""
        other = peer(primary)
        r = {n: (st.dir / f"route-{n}" / "route.ini").read_text().split()[1] for n in ("a", "b")}
        assert r[primary] == "route=local", r
        assert redis_role(primary) == "master", redis_role(primary)
        if not only_primary:
            assert r[other] == "route=peer", r
            wait_until(lambda: redis_role(other) == "slave", 20, f"{other} Redis a replica")

    def aa_steady():
        time.sleep(8)
        assert role("a") == "primary" and role("b") == "standby"
        assert app_writable("a") and app_writable("b"), "both app paths must reach the primary"
        with cf.lock:
            assert cf.healthy["a"] and cf.healthy["b"], cf.healthy
        routes_follow("a")
        assert app_redis("a", "set", "drill-key", "from-a") == "OK"
        assert app_redis("b", "get", "drill-key") == "from-a", "Redis must be shared through the master"
        # The app's Redis user cannot reconfigure, re-point or wipe Redis (security review S1).
        for cmd in (("replicaof", "no", "one"), ("flushall",), ("config", "set", "maxmemory", "1"), ("shutdown",)):
            out = app_redis("a", *cmd)
            assert "NOPERM" in out, (cmd, out)
        rc, out = psql("a", "select count(*) from drill where node = 'via-b'")
        assert rc == 0 and int(out) > 0, "writes through node B's app must land in A's database"
        return "both origins healthy; B's writes land on A; one Redis shared"

    def aa_app_down(n):
        def fn():
            other = peer(n)
            primary_before = "a" if role("a") == "primary" else "b"
            served = dict(watch.served)
            cf.set(app_ok={n: False})        # node n's app unhealthy; its database untouched
            wait_until(lambda: not cf.healthy[n], 20, f"origin {n} out of the pool")
            time.sleep(40)                   # > fence (8 s) + promote (14 s) + app-sick (20 s, off)
            assert role(primary_before) == "primary" and role(peer(primary_before)) == "standby", "the database moved"
            with cf.lock:
                assert cf.healthy[other], "the other node must stay in the pool"
            assert watch.served[other] > served[other], "the other node must keep serving writes"
            cf.set(app_ok={n: True})
            wait_until(lambda: cf.healthy[n], 20, f"origin {n} back in the pool")
            return f"node {n} out of the pool and back; no fence, no promotion; {other} served"
        return fn

    def aa_link_cut():
        primary = "a" if role("a") == "primary" else "b"
        other = peer(primary)
        st.cut(other)
        wait_until(lambda: not cf.healthy[other], 30, f"{other} out of the pool (no route to the primary)")
        time.sleep(30)
        assert role(primary) == "primary" and role(other) == "standby"
        with cf.lock:
            assert cf.healthy[primary]
        st.join(other)
        wait_until(lambda: cf.healthy[other], 40, f"{other} back in the pool")
        st.wait_streaming(other, 60)
        return f"{other} dropped out while it could not reach the primary; no failover"

    def aa_kill_primary():
        primary = "a" if role("a") == "primary" else "b"
        other = peer(primary)
        t0 = time.time()
        st.stop_controller(primary)          # the whole box: controller, Postgres, its app tier, network
        for c in st.node_containers(primary):
            if c != f"drill-probe-{primary}":
                sh("docker", "stop", "-t", "1", c)
        st.cut(primary)
        cf.set(net={primary: False})
        t1 = st.wait_role(other, "primary", 90)
        wait_until(lambda: cf.healthy[other], 40, f"{other} serving as the new primary")
        t2 = time.time()
        routes_follow(other, only_primary=True)
        cf.set(net={primary: True})
        for c in st.node_containers(primary):
            if c not in (cname(primary), f"drill-probe-{primary}"):
                sh("docker", "start", c)
        st.join(primary)
        st.start_controller(primary)         # D1 starts its Postgres read-only, S2 rejoins, R1 routes
        st.wait_role(primary, "standby", 90)
        st.wait_streaming(primary, 120)
        wait_until(lambda: cf.healthy[primary], 60, f"{primary} back in the pool through {other}'s database")
        routes_follow(other)
        wait_until(lambda: app_redis(primary, "set", "after-failover", "x") == "OK"
                   and app_redis(other, "get", "after-failover") == "x", 20, "one Redis shared after the return")
        return (f"{other} primary {t1 - t0:.0f}s after {primary} died, serving at {t2 - t0:.0f}s; "
                f"{primary} came back read-only and serves again through {other}")

    def aa_isolate_primary():
        primary = "a" if role("a") == "primary" else "b"
        other = peer(primary)
        t0 = time.time()
        st.cut(primary)
        cf.set(net={primary: False})
        fenced = None
        end = time.time() + 90
        while time.time() < end and role(other) != "primary":
            if fenced is None and role(primary) == "down":
                fenced = time.time()
            time.sleep(0.3)
        t1 = st.wait_role(other, "primary", 5)
        assert fenced is not None and fenced < t1, f"{primary} was not fenced before {other} promoted"
        cf.set(net={primary: True})
        st.join(primary)
        st.wait_role(primary, "standby", 90)
        st.wait_streaming(primary, 120)
        wait_until(lambda: cf.healthy[primary] and cf.healthy[other], 60, "both back in the pool")
        routes_follow(other)
        return f"{primary} fenced at {fenced - t0:.0f}s, {other} promoted at {t1 - t0:.0f}s; both serving again"

    def aa_both_reboot():
        for n in ("a", "b"):
            st.stop_controller(n)
        for n in ("a", "b"):
            sh("docker", "stop", "-t", "5", cname(n))
            # Redis restarts with the box and comes back a MASTER on both (no replicaof in its
            # config): R1 must repair the role from what Redis says, not from the route file.
            sh("docker", "restart", "-t", "1", f"drill-redis-{n}")
        st.start_controller("a")
        st.start_controller("b")
        wait_until(lambda: "primary" in (role("a"), role("b")), 90, "a primary")
        p = "a" if role("a") == "primary" else "b"
        st.wait_role(peer(p), "standby", 60)
        st.wait_streaming(peer(p), 120)
        wait_until(lambda: cf.healthy["a"] and cf.healthy["b"], 60, "both in the pool")
        routes_follow(p)
        return f"one writer ({p}), both nodes serving"

    if aa:
        plan = [
            ("aa: steady state, both serving", aa_steady),
            ("aa: app down on A only (no DB failover)", aa_app_down("a")),
            ("aa: app down on B only (no DB failover)", aa_app_down("b")),
            ("aa: link cut only", aa_link_cut),
            ("aa: primary box dies", aa_kill_primary),
            ("aa: primary isolated (fence before promote)", aa_isolate_primary),
            ("aa: both nodes reboot", aa_both_reboot),
        ]
    else:
        plan = [
            ("steady state + sync standby", steady),
            ("link cut only", link_cut_only),
            ("Cloudflare API down", cf_api_down),
            ("node A dies", kill_a),
            ("primary isolated (fence before promote)", isolate_primary_b),
            ("app sick 20 s + rewind fails -> re-seed", app_sick_with_reseed),
            ("both nodes reboot", both_reboot),
            ("both reboot, link down", both_reboot_link_down),
        ]
    for name, fn in plan:
        scenario(name, fn)


    watch.stop = True
    time.sleep(1)
    final = "a" if role("a") == "primary" else "b"
    rc, out = psql(final, "select id from drill")
    present = {int(x) for x in out.split()} if rc == 0 else set()
    lost = sorted(set(watch.acked) - present)
    results.append(("never two writers", "PASS" if not watch.violations else "FAIL",
                    f"{len(watch.violations)} bad samples {watch.violations[:5]}"))
    if aa:
        # Postgres is the "never two writers" check above. Redis: two masters for a moment is
        # expected when a box returns or restarts (its Redis boots a master until R1 fixes the
        # role, one tick); reported, not failed. Plan 12b.
        results.append(("two Redis masters (samples, 0.3 s each)", "NOTE", str(watch.redis_two_masters)))
    results.append(("acknowledged writes kept", "PASS" if not lost else "NOTE",
                    f"{len(watch.acked)} acked, {len(lost)} lost {lost[:10]}"))
    cf.stop = True
    print("\n=== cf-drill results ===")
    for name, res, note in results:
        print(f"{res:5} {name}: {note}")
    print(f"logs: {workdir}")
    # Controllers ALWAYS stop: a leftover one would act on the next run's containers.
    for n in list(st.procs):
        st.stop_controller(n)
    if not args.keep:
        st.down()
    return 0 if all(r[1] != "FAIL" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
