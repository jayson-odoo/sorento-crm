#!/usr/bin/env python3
"""Failover controller with Cloudflare Load Balancing as the witness (HA-CF-FAILOVER).

Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md section 3 (rules P1-P4, S1-S3,
D1-D2). Runs on BOTH CRM nodes as a systemd service (templates/systemd/cf-failover.service).

Two nodes, no witness server: the third vote is the Cloudflare LB's own health view of each
node (monitor `GET /api/v1/health/role`, 200 only where the local Postgres is writable).

- `decide()` is pure (no I/O, no clock) and holds every rule. infra/tests/test_cf_failover.py.
- Section 3 sync record (PLAN-ha-b-replica-sync-07nov.md): P4'/S1' read the R2 record through
  `ha-pg.sh sync-record get|put`. Env: CONTROLLER_ARMED=yes (else exit 3), PEER_APP_NAME, and for
  SYNC_MODE != off R2_ENDPOINT, R2_BUCKET, R2_CREDENTIALS_FILE.
- `main()` observes (infra/scripts/ha-pg.sh observe + the Cloudflare pool health API), calls
  `decide()`, runs the actions through ha-pg.sh, pets the watchdog, persists the state.

Python 3.8+ stdlib only. Never prints a secret: the API token is read from a file and only sent
in the Authorization header.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

ROLES = ("primary", "standby", "down")
FENCE_TIMEOUT = 60  # seconds; FENCE_MARGIN is 180
PEER_ROLES = ("primary", "standby", "unreachable")
CF_STATES = ("healthy", "unhealthy", "unknown")
SYNC_MODES = ("off", "remote_write", "on_commit")
NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    node_name: str
    peer_name: str
    tick: int = 15
    cf_check_interval: int = 60
    cf_consecutive_down: int = 2
    fence_after: int = 240
    fence_margin: int = 180
    promote_after: int = 420
    fence_hold: int = 600
    app_sick_after: int = 900
    app_sick_cooldown: int = 86400
    rejoin_after: int = 120
    both_standby_after: int = 60
    max_lag: int = 16 * 1024 * 1024
    sync_mode: str = "off"
    reseed_keep_days: int = 7
    max_obs_gap: int = 45
    peer_app_name: str = ''

    @classmethod
    def from_env(cls, env) -> "Config":
        def num(key, default):
            raw = env.get(key)
            if raw is None or raw == "":
                return default
            try:
                v = int(raw)
            except ValueError:
                raise ConfigError(f"{key}={raw!r} must be a whole number")
            if v < 0:
                raise ConfigError(f"{key} must not be negative")
            return v

        node = env.get("NODE_NAME", "")
        peer = env.get("PEER_NAME", "")
        for k, v in (("NODE_NAME", node), ("PEER_NAME", peer)):
            if not NAME_RE.match(v):
                raise ConfigError(f"{k} must match {NAME_RE.pattern}")
        pan = env.get("PEER_APP_NAME") or peer
        if not NAME_RE.match(pan):
            raise ConfigError("PEER_APP_NAME bad")
        if node == peer:
            raise ConfigError("PEER_NAME must differ from NODE_NAME")

        tick = num("TICK", 15)
        interval = num("CF_CHECK_INTERVAL", 60)
        down = num("CF_CONSECUTIVE_DOWN", 2)
        margin = num("FENCE_MARGIN", 180)
        fence_after = num("FENCE_AFTER", 2 * interval * down)
        promote_after = num("PROMOTE_AFTER", fence_after + max(margin, 3 * interval))
        fence_hold = num("FENCE_HOLD", promote_after + 180)
        sync_mode = env.get("SYNC_MODE", "off") or "off"

        if tick < 1 or interval < 1 or down < 1:
            raise ConfigError("TICK, CF_CHECK_INTERVAL and CF_CONSECUTIVE_DOWN must be at least 1")
        if promote_after < fence_after + margin:
            raise ConfigError(
                f"PROMOTE_AFTER ({promote_after}) must be at least FENCE_AFTER + FENCE_MARGIN "
                f"({fence_after} + {margin}): the old primary must fence before the standby promotes"
            )
        if fence_hold <= promote_after:
            raise ConfigError(f"FENCE_HOLD ({fence_hold}) must exceed PROMOTE_AFTER ({promote_after})")
        if sync_mode not in SYNC_MODES:
            raise ConfigError(f"SYNC_MODE must be one of {', '.join(SYNC_MODES)}")

        return cls(
            node_name=node, peer_name=peer, tick=tick,
            cf_check_interval=interval, cf_consecutive_down=down,
            fence_after=fence_after, fence_margin=margin, promote_after=promote_after,
            fence_hold=fence_hold,
            app_sick_after=num("APP_SICK_AFTER", 900),
            app_sick_cooldown=num("APP_SICK_COOLDOWN", 86400),
            rejoin_after=num("REJOIN_AFTER", 120),
            both_standby_after=num("BOTH_STANDBY_AFTER", 60),
            max_lag=num("MAX_LAG", 16 * 1024 * 1024),
            sync_mode=sync_mode,
            reseed_keep_days=num("RESEED_KEEP_DAYS", 7),
            peer_app_name=pan,
            max_obs_gap=num("MAX_OBS_GAP", 3 * tick),
        )


@dataclass(frozen=True)
class Obs:
    self_pg: str                 # primary | standby | down
    self_streaming: bool         # primary: the peer streams from it; standby: its WAL receiver streams
    self_lsn: Optional[int]
    peer_pg: str                 # primary | standby | unreachable (over the private link)
    peer_lsn: Optional[int]
    cf_self: str                 # healthy | unhealthy | unknown (Cloudflare's view of this node)
    cf_peer: str                 # same for the peer
    sync_names: str = ""         # synchronous_standby_names on this node, quotes stripped
    peer_slot_ok: bool = True
    rec_mode: str = 'unknown'
    rec_primary: Optional[str] = None
    rec_since: Optional[int] = None


# Windows: seconds a condition has held without a break. Reset when the controller was not
# observing (a gap longer than max_obs_gap, or the clock stepped back): an unobserved stretch
# never counts as "held".
WINDOWS = (
    "cf_self_unhealthy_since", "cf_peer_unhealthy_since", "peer_unreachable_since",
    "not_streaming_since", "both_standby_since",
)
# Event timestamps: shifted, not reset, when the clock steps back, so elapsed times survive.
EVENTS = ("lease_from", "fenced_at", "last_app_sick_fence", "last_rejoin_at")


def initial_state() -> dict:
    return {
        "last_tick": None,
        "lease_from": None,
        "fenced_at": None,
        "fencing": False,
        "last_app_sick_fence": None,
        "last_rejoin_at": None,
        "rejoins_since_stream": 0,
        "last_peer_lsn": None,
        "peer_last_role": None,
        "lag_alerted": False,
        "two_primaries_alerted": False,
        "rec_alerted": False,
        **{k: None for k in WINDOWS},
    }


def decide(state: dict, o: Obs, now: float, c: Config):
    """One tick. Returns (new_state, actions). Actions are tuples:
    ("fence", reason) ("promote",) ("start_standby",) ("rejoin",) ("rejoin", "reseed")
    ("set_sync", names) ("ensure_slot",) ("alert", text)
    """
    s = {**initial_state(), **state}
    acts = []

    fresh = s["last_tick"] is None  # no state file: first tick this controller ever ran
    if not fresh and now < s["last_tick"]:
        # Clock stepped back: keep every elapsed time, drop the windows.
        shift = s["last_tick"] - now
        for k in EVENTS:
            if s[k] is not None:
                s[k] -= shift
        for k in WINDOWS:
            s[k] = None
    elif not fresh and now - s["last_tick"] > c.max_obs_gap:
        for k in WINDOWS:
            s[k] = None
        # The lease is kept: an older lease only makes a primary fence sooner.
    s["last_tick"] = now

    def held(key, cond):
        if not cond:
            s[key] = None
            return None
        if s[key] is None:
            s[key] = now
        return now - s[key]

    def fence(reason):
        # Repeated every tick while this node still reads primary (a fence that failed); the
        # lease is never renewed by a fence, only by Cloudflare, a streaming peer or a promotion.
        acts.append(("fence", reason))
        if not s["fencing"]:
            acts.append(("alert", f"{c.node_name}: fencing itself ({reason})"))
        s["fencing"] = True
        if s["fenced_at"] is None:
            s["fenced_at"] = now
        s["cf_self_unhealthy_since"] = None

    def promote(why):
        acts.append(("promote",))
        acts.append(("alert", f"{c.node_name}: promoted ({why})"))
        s["lease_from"] = now
        s["fenced_at"] = None
        s["fencing"] = False

    cf_peer_down = held("cf_peer_unhealthy_since", o.cf_peer == "unhealthy")
    peer_gone = held("peer_unreachable_since", o.peer_pg == "unreachable")
    if o.peer_pg in ("primary", "standby"):
        s["peer_last_role"] = o.peer_pg
    if o.peer_pg == "primary" and o.peer_lsn is not None:
        s["last_peer_lsn"] = o.peer_lsn

    if o.self_pg == "primary":
        for k in ("not_streaming_since", "both_standby_since"):
            s[k] = None
        s["lag_alerted"] = False
        if o.cf_self == "healthy" or o.self_streaming or (fresh and s["lease_from"] is None):
            s["lease_from"] = now
        sick = held("cf_self_unhealthy_since", o.cf_self == "unhealthy")

        if s["fencing"]:  # a fence did not take: keep trying (the I/O loop stops the watchdog too)
            fence("still writable after a fence")
            return s, acts

        if o.peer_pg == "primary":  # P3
            if not s["two_primaries_alerted"]:
                acts.append(("alert", f"{c.node_name}: TWO PRIMARIES, the peer is writable too"))
                s["two_primaries_alerted"] = True
            if o.cf_self != "healthy":
                fence("two primaries and Cloudflare does not see this node")
                return s, acts
            if o.cf_peer == "healthy" and c.node_name > c.peer_name:
                fence("two primaries both seen by Cloudflare; the higher name yields")
                return s, acts
        else:
            s["two_primaries_alerted"] = False

        if s["lease_from"] is None or now - s["lease_from"] >= c.fence_after:  # P1
            fence(f"lease expired: no Cloudflare-healthy report and no streaming peer for {c.fence_after}s")
            return s, acts
        last_sick = s["last_app_sick_fence"]
        if (sick is not None and sick >= c.app_sick_after and o.self_streaming
                and (last_sick is None or now - last_sick >= c.app_sick_cooldown)):  # P2
            s["last_app_sick_fence"] = now
            fence(f"app sick: Cloudflare-unhealthy for {int(sick)}s with a streaming standby")
            return s, acts

        desired = c.peer_app_name if (c.sync_mode != "off" and o.self_streaming) else ""  # P4
        want = "sync" if desired else "async"
        if o.sync_names != desired:
            if desired:
                acts.append(("set_sync", desired)); acts.append(("sync_record", "sync"))
            else:
                acts.append(("sync_record", "async")); acts.append(("set_sync", ""))
        elif o.rec_mode != "unknown" and (o.rec_mode, o.rec_primary) != (want, c.node_name):
            acts.append(("sync_record", want))
        if not o.peer_slot_ok:  # P5: the standby can only stream into its slot
            acts.append(("ensure_slot",))
        return s, acts

    s["fencing"] = False
    s["cf_self_unhealthy_since"] = None
    s["two_primaries_alerted"] = False

    def rejoin():
        s["last_rejoin_at"] = now
        s["rejoins_since_stream"] += 1
        # A rewind that "worked" but did not bring streaming back: re-seed next time.
        acts.append(("rejoin", "reseed") if s["rejoins_since_stream"] > 1 else ("rejoin",))

    if o.self_pg == "standby":
        s["fenced_at"] = None
        not_streaming = held("not_streaming_since", not o.self_streaming)
        both = held("both_standby_since", o.peer_pg == "standby")
        if o.self_streaming:
            s["rec_alerted"] = False
            s["lag_alerted"] = False
            s["rejoins_since_stream"] = 0

        # S1
        if (cf_peer_down is not None and not_streaming is not None and peer_gone is not None
                and min(cf_peer_down, not_streaming, peer_gone) >= c.promote_after
                and s["peer_last_role"] == "primary"):
            last = s["last_peer_lsn"]
            if last is not None and (o.self_lsn is None or last - o.self_lsn > c.max_lag):
                if not s["lag_alerted"]:
                    behind = "unknown" if o.self_lsn is None else str(last - o.self_lsn)
                    acts.append(("alert", f"{c.node_name}: peer down but this standby is too far behind "
                                          f"({behind} bytes > {c.max_lag}); NOT promoting"))
                    s["lag_alerted"] = True
                return s, acts
            if not (o.rec_mode == "sync" and o.rec_primary == c.peer_name):
                if not s["rec_alerted"]:
                    s["rec_alerted"] = True
                    acts.append(("alert", f"record async since {o.rec_since}" if o.rec_mode == "async" else "sync record could not be read"))
                return s, acts
            promote(f"peer Cloudflare-unhealthy and unreachable for {c.promote_after}s")
            acts.append(("sync_record", "async"))
            return s, acts

        # S2
        if (o.peer_pg == "primary" and not_streaming is not None and not_streaming >= c.rejoin_after
                and (s["last_rejoin_at"] is None or now - s["last_rejoin_at"] >= c.rejoin_after)):
            rejoin()
            return s, acts

        # S3
        if both is not None and both >= c.both_standby_after and o.peer_lsn is not None and o.self_lsn is not None:
            if o.self_lsn > o.peer_lsn or (o.self_lsn == o.peer_lsn and c.node_name < c.peer_name):
                promote("both nodes were standby; this one is ahead")
        return s, acts

    # Postgres down.
    s["not_streaming_since"] = None
    s["both_standby_since"] = None
    if s["fenced_at"] is None:  # D1
        acts.append(("start_standby",))
        return s, acts
    if o.peer_pg == "primary":  # D2
        if s["last_rejoin_at"] is None or now - s["last_rejoin_at"] >= c.rejoin_after:
            rejoin()
            # The rejoin leaves a standby (or, if it failed, a stopped data directory that D1
            # starts read-only). Either way the node is no longer "fenced": a slow standby start
            # that still reads down must not be rejoined again as a re-seed (review round 3).
            s["fenced_at"] = None
        return s, acts
    if now - s["fenced_at"] >= c.fence_hold:
        if o.peer_pg == "standby" or (
            peer_gone is not None and cf_peer_down is not None
            and min(peer_gone, cf_peer_down) >= c.promote_after
        ):
            acts.append(("start_standby",))
    return s, acts


# ---------------------------------------------------------------- I/O (not unit-tested; drill)


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} cf-failover: {msg}", flush=True)


class Watchdog:
    """Pets /dev/watchdog (softdog). Opened only after the first COMPLETE tick, and petted only
    while ticks keep completing (security review S2): a controller that crash-loops or cannot
    observe never keeps the box alive. When it stops petting, the box reboots and Postgres comes
    back as a standby (rule D1). Closed WITHOUT the magic 'V' on a crash; a deliberate stop
    (SIGTERM) disarms it first."""

    def __init__(self, path: str):
        self.path = path
        self.fd = None

    def pet(self) -> None:
        if not self.path:
            return
        if self.fd is None:
            self.fd = os.open(self.path, os.O_WRONLY)
        os.write(self.fd, b"\0")

    def keepalive(self) -> None:
        """Pet only if already armed (used while a long command runs inside a good tick)."""
        if self.fd is not None:
            os.write(self.fd, b"\0")

    def disarm(self) -> None:
        if self.fd is not None:
            os.write(self.fd, b"V")
            os.close(self.fd)
            self.fd = None


def run_cmd(argv, watchdog: Watchdog, timeout: Optional[int], tick: int, keepalive: bool = True):
    """Runs argv in its own process group. Pets the watchdog while it waits only when
    `keepalive` (a re-seed can take an hour); a fence never does, so a fence that hangs ends in
    a reboot. On timeout the WHOLE group is killed: killing only the shell would leave its
    `docker compose stop` running (review B2)."""
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    start = time.monotonic()
    while True:
        try:
            out, _ = p.communicate(timeout=max(1, tick // 2))
            return p.returncode, out or ""
        except subprocess.TimeoutExpired:
            if keepalive:
                watchdog.keepalive()
            if timeout is not None and time.monotonic() - start > timeout:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                out, _ = p.communicate()
                return 124, out or ""


def parse_observe(text: str) -> dict:
    d = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def cf_pool_health(base: str, account: str, pool: str, token: str, timeout: int = 10) -> str:
    """Cloudflare's view of one pool (one endpoint per pool): healthy | unhealthy | unknown.
    GET /accounts/{account}/load_balancers/pools/{pool}/health -> result.pop_health.{region}.healthy.
    Unhealthy only when every reporting region says so; no region, an error, or no answer: unknown."""
    try:
        return _cf_pool_health(base, account, pool, token, timeout)
    except Exception:  # noqa: BLE001 - any surprise in the answer is "unknown", never a crash
        return "unknown"


def _cf_pool_health(base, account, pool, token, timeout):
    if not (base and account and pool and token):
        return "unknown"
    req = urllib.request.Request(
        f"{base.rstrip('/')}/accounts/{account}/load_balancers/pools/{pool}/health",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return "unknown"
    if not isinstance(body, dict) or not body.get("success"):
        return "unknown"
    result = body.get("result")
    pops = result.get("pop_health") if isinstance(result, dict) else None
    if not isinstance(pops, dict):
        return "unknown"
    flags = [v.get("healthy") for v in pops.values() if isinstance(v, dict) and isinstance(v.get("healthy"), bool)]
    if not flags:
        return "unknown"
    if any(flags):
        return "healthy"
    return "unhealthy"


def load_state(path: str) -> dict:
    try:
        with open(path) as f:
            s = json.load(f)
        return s if isinstance(s, dict) else initial_state()
    except (OSError, ValueError):
        return initial_state()


def save_state(path: str, s: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main() -> int:
    env = os.environ
    try:
        c = Config.from_env(env)
    except ConfigError as e:
        log(f"config refused: {e}")
        return 2
    if env.get("CONTROLLER_ARMED") != "yes":
        log("not armed (CONTROLLER_ARMED=yes in ha-pg.env arms it, after the section 3 drill)")
        return 3
    pg_cmd = env.get("PG_CMD", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ha-pg.sh"))
    state_path = env.get("STATE_FILE", "/var/lib/sorento-ha/cf-failover.json")
    alert_cmd = env.get("ALERT_CMD", "")
    cf_base = env.get("CF_API_BASE", "https://api.cloudflare.com/client/v4")
    cf_account = env.get("CF_ACCOUNT_ID", "")
    pool_self, pool_peer = env.get("CF_POOL_SELF", ""), env.get("CF_POOL_PEER", "")
    token_file = env.get("CF_API_TOKEN_FILE", "")
    max_ticks = int(env.get("MAX_TICKS", "0") or 0)
    if not (cf_base.startswith("https://") or cf_base.startswith("http://127.0.0.1")):
        log("config refused: CF_API_BASE must be https:// (http only to 127.0.0.1, for the drill)")
        return 2
    if token_file and os.path.exists(token_file) and os.stat(token_file).st_mode & 0o077:
        log(f"warning: {token_file} is readable by group or others; make it mode 600")
    if c.sync_mode != "off" and not all(env.get(k) for k in ("R2_ENDPOINT", "R2_BUCKET", "R2_CREDENTIALS_FILE")):
        log("config refused: R2")
        return 2
    watchdog = Watchdog(env.get("WATCHDOG_DEVICE", ""))

    def stop(signum, frame):
        watchdog.disarm()
        log("stopped (watchdog disarmed)")
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def alert(text: str) -> None:
        log(f"ALERT {text}")
        if alert_cmd:
            try:
                subprocess.run(["sh", "-c", alert_cmd], input=text, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError) as e:
                log(f"alert command failed: {type(e).__name__}")

    def tick(state: dict, started: float) -> dict:
        """One complete tick: observe, decide, persist, act. Raises on any failure."""
        token = ""
        if token_file:
            try:
                with open(token_file) as f:
                    token = f.read().strip()
            except OSError:
                token = ""
        rc, out = run_cmd([pg_cmd, "observe"], watchdog, 30, c.tick)
        d = parse_observe(out) if rc == 0 else {}

        def lsn(key):
            v = d.get(key, "")
            return int(v) if v.isdigit() else None

        self_pg = d.get("self_pg") if d.get("self_pg") in ROLES else None
        if self_pg is None:
            raise RuntimeError(f"observe failed (rc={rc})")
        rrc, rout = run_cmd([pg_cmd, "sync-record", "get"], watchdog, 15, c.tick)
        rd = parse_observe(rout) if rrc == 0 else {}
        rsince = rd.get("rec_since", "")
        o = Obs(
            rec_mode=rd.get("rec_mode") if rd.get("rec_mode") in ("sync", "async") else "unknown",
            rec_primary=rd.get("rec_primary"), rec_since=int(rsince) if rsince.isdigit() else None,
            self_pg=self_pg,
            self_streaming=d.get("self_streaming") == "t",
            self_lsn=lsn("self_lsn"),
            peer_pg=d.get("peer_pg") if d.get("peer_pg") in PEER_ROLES else "unreachable",
            peer_lsn=lsn("peer_lsn"),
            peer_slot_ok=d.get("peer_slot", "t") != "f",
            cf_self=cf_pool_health(cf_base, cf_account, pool_self, token),
            cf_peer=cf_pool_health(cf_base, cf_account, pool_peer, token),
            sync_names=d.get("sync_names", ""),
        )
        state, actions = decide(state, o, started, c)
        save_state(state_path, state)  # before acting: a crash mid-action keeps the decision's windows
        for a in actions:
            if a[0] == "alert":
                alert(a[1])
                continue
            log(f"action {a[0]} {' '.join(a[1:])} (obs {o})")
            argv = [pg_cmd, a[0].replace("_", "-")] + list(a[1:])
            if a[0] == "sync_record":
                argv = [pg_cmd, "sync-record", "put", a[1]]
                rc, out = run_cmd(argv, watchdog, 30, c.tick)
                if rc != 0:
                    alert("sync record write failed; NOT dropping the sync standby")
                    break
                continue
            if a[0] == "fence":
                # Bounded well inside FENCE_MARGIN, never keeping the box alive while it runs.
                rc, out = run_cmd(argv, watchdog, FENCE_TIMEOUT, c.tick, keepalive=False)
            else:
                rc, out = run_cmd(argv, watchdog, None if a[0] == "rejoin" else 300, c.tick)
            tail = out.strip().splitlines()[-3:]
            if a[0] == "rejoin":
                if rc == 0:
                    alert(f"{c.node_name}: rejoined the primary by pg_rewind, now a standby")
                elif rc == 3:
                    alert(f"{c.node_name}: rewind failed; RE-SEEDED from the primary, old data kept "
                          f"{c.reseed_keep_days} days")
                else:
                    alert(f"{c.node_name}: rejoin failed (rc={rc}): {' | '.join(tail)}")
            elif rc != 0:
                alert(f"{c.node_name}: {a[0]} failed (rc={rc}): {' | '.join(tail)}")
        return state

    log(f"started: node={c.node_name} peer={c.peer_name} fence_after={c.fence_after}s "
        f"promote_after={c.promote_after}s app_sick_after={c.app_sick_after}s sync={c.sync_mode}")
    state = load_state(state_path)
    last_prune = 0.0
    last_ok = time.time()
    self_fenced_on_failure = False
    ticks = 0
    while True:
        started = time.time()
        try:
            state = tick(state, started)
            last_ok = time.time()
            self_fenced_on_failure = False
            if state.get("fencing"):
                # This node still read primary when it decided to fence (or a fence already
                # failed): stop petting, so if the fence does not take, the reboot does (D1).
                log("fence pending: watchdog not petted this tick")
            else:
                watchdog.pet()
        except Exception as e:  # noqa: BLE001 - the loop itself must never die silently
            failing = time.time() - last_ok
            log(f"tick failed ({type(e).__name__}: {str(e)[:200]}); failing for {int(failing)}s")
            if failing < c.fence_after:
                watchdog.keepalive()
            elif not self_fenced_on_failure:
                # The controller cannot hold this node's lease, so it gives it up the same way P1
                # would. If even the fence fails, the watchdog (no longer petted) reboots the box.
                self_fenced_on_failure = True
                alert(f"{c.node_name}: controller failing for {int(failing)}s; fencing this node")
                run_cmd([pg_cmd, "fence"], watchdog, FENCE_TIMEOUT, c.tick, keepalive=False)
        if started - last_prune > 3600:
            last_prune = started
            try:
                run_cmd([pg_cmd, "prune", str(c.reseed_keep_days)], watchdog, 300, c.tick)
            except Exception as e:  # noqa: BLE001
                log(f"prune failed: {type(e).__name__}")
        ticks += 1
        if max_ticks and ticks >= max_ticks:
            watchdog.disarm()
            return 0
        time.sleep(max(0.0, c.tick - (time.time() - started)))


if __name__ == "__main__":
    sys.exit(main())
