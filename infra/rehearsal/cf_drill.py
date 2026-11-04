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
NET = "drill-link"
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
    r = subprocess.run(["docker", "exec", "-u", "postgres", cname(n), "psql", "-XAtq", "-d", "postgres", "-c", sql],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip()


def role(n):
    rc, out = psql(n, "select pg_is_in_recovery()", timeout=5)
    if rc != 0:
        return "down"
    return {"f": "primary", "t": "standby"}.get(out, "down")


# ---------------------------------------------------------------- fake Cloudflare


class FakeCF:
    """Pool health as Cloudflare would report it: the monitor (a primary answering) checked every
    CF_INTERVAL, unhealthy after 2 failures, healthy after 1 success. Each node's controller calls
    its own URL prefix, so a node whose `net` is off gets no answer (UNKNOWN), like a box cut off."""

    def __init__(self):
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
                    pool = parts[4].replace("pool-", "") if len(parts) > 4 else ""
                    healthy = cf.healthy.get(pool)
                if not ok or healthy is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                body = json.dumps({"success": True, "result": {"pool_id": pool, "pop_health": {
                    "Singapore, SG": {"healthy": healthy, "origins": []}}}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self.monitor, daemon=True).start()

    def monitor(self):
        while not self.stop:
            for n in ("a", "b"):
                with self.lock:
                    reach = self.net[n] and self.app_ok[n]
                ok = reach and role(n) == "primary"
                with self.lock:
                    self.fails[n] = 0 if ok else self.fails[n] + 1
                    self.healthy[n] = ok or (self.healthy[n] and self.fails[n] < 2)
            time.sleep(CF_INTERVAL)

    def set(self, **kw):
        with self.lock:
            for k, v in kw.items():
                if isinstance(v, dict):
                    getattr(self, k).update(v)
                else:
                    setattr(self, k, v)


# ---------------------------------------------------------------- stack


class Stack:
    def __init__(self, workdir: Path, cf: FakeCF):
        self.dir = workdir
        self.cf = cf
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
        }

    def up(self):
        self.down(quiet=True)
        init = self.dir / "init"
        init.mkdir(exist_ok=True)
        (init / "repl.sh").write_text('echo "host replication all all trust" >> "$PGDATA/pg_hba.conf"\n')
        sh("docker", "network", "create", NET)
        for n in ("a", "b"):
            sh("docker", "volume", "create", f"drill-{n}-data")
            sh("docker", "run", "-d", "--name", f"drill-probe-{n}", "--network", NET, IMAGE, "sleep", "infinity")
        sh("docker", "run", "-d", "--name", cname("a"), "--network", NET, "--restart", "no",
           "-v", "drill-a-data:/var/lib/postgresql/data", "-v", f"{init}:/docker-entrypoint-initdb.d:ro",
           *self.pg_args())
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
        self.wait_role("b", "standby", 60)
        self.wait_streaming("b", 60)

    def pg_args(self):
        return ["-e", "POSTGRES_PASSWORD=drill", "-e", f"PGDATA={PGDATA}", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                IMAGE, "-c", "wal_level=replica", "-c", "wal_log_hints=on", "-c", "hot_standby=on",
                "-c", "max_wal_senders=5", "-c", "max_replication_slots=5", "-c", "wal_keep_size=256MB",
                "-c", "max_slot_wal_keep_size=1GB"]

    def down(self, quiet=False):
        for n in list(self.procs):
            self.stop_controller(n)
        for c in ("drill-a", "drill-b", "drill-probe-a", "drill-probe-b"):
            sh("docker", "rm", "-f", c, check=False)
        for v in ("drill-a-data", "drill-b-data"):
            sh("docker", "volume", "rm", "-f", v, check=False)
        sh("docker", "network", "rm", NET, check=False)

    def start_controller(self, n):
        env = {**os.environ, **self.adapter_env(n), **TIMING,
               "PG_CMD": str(ADAPTER),
               "STATE_FILE": str(self.dir / f"state-{n}.json"),
               "CF_API_BASE": f"http://127.0.0.1:{self.cf.port}/node-{n}",
               "CF_ACCOUNT_ID": "drill", "CF_POOL_SELF": f"pool-{n}", "CF_POOL_PEER": f"pool-{peer(n)}",
               "CF_API_TOKEN_FILE": str(self.dir / "token"),
               "ALERT_CMD": f"cat >> {self.dir}/alerts-{n}.log; echo >> {self.dir}/alerts-{n}.log"}
        (self.dir / "token").write_text("drill-token\n")
        log = open(self.dir / f"controller-{n}.log", "a")
        self.procs[n] = subprocess.Popen([sys.executable, str(CONTROLLER)], env=env, stdout=log, stderr=subprocess.STDOUT)

    def stop_controller(self, n):
        p = self.procs.pop(n, None)
        if p:
            p.kill()
            p.wait()

    def cut(self, n):
        for c in (cname(n), f"drill-probe-{n}"):
            sh("docker", "network", "disconnect", "-f", NET, c, check=False)

    def join(self, n):
        for c in (cname(n), f"drill-probe-{n}"):
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
    def __init__(self):
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
            time.sleep(0.3)

    def writer(self):
        while not self.stop:
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
    args = ap.parse_args()
    workdir = Path(tempfile.mkdtemp(prefix="cf-drill-"))
    cf = FakeCF()
    st = Stack(workdir, cf)
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
    st.up()
    watch = Watch()
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
        time.sleep(4)
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

    for name, fn in [
        ("steady state + sync standby", steady),
        ("link cut only", link_cut_only),
        ("Cloudflare API down", cf_api_down),
        ("node A dies", kill_a),
        ("primary isolated (fence before promote)", isolate_primary_b),
        ("app sick 20 s + rewind fails -> re-seed", app_sick_with_reseed),
        ("both nodes reboot", both_reboot),
        ("both reboot, link down", both_reboot_link_down),
    ]:
        scenario(name, fn)

    watch.stop = True
    time.sleep(1)
    final = "a" if role("a") == "primary" else "b"
    rc, out = psql(final, "select id from drill")
    present = {int(x) for x in out.split()} if rc == 0 else set()
    lost = sorted(set(watch.acked) - present)
    results.append(("never two writers", "PASS" if not watch.violations else "FAIL",
                    f"{len(watch.violations)} bad samples {watch.violations[:5]}"))
    results.append(("acknowledged writes kept", "PASS" if not lost else "NOTE",
                    f"{len(watch.acked)} acked, {len(lost)} lost {lost[:10]}"))
    cf.stop = True
    print("\n=== cf-drill results ===")
    for name, res, note in results:
        print(f"{res:5} {name}: {note}")
    print(f"logs: {workdir}")
    if not args.keep:
        st.down()
    return 0 if all(r[1] != "FAIL" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
