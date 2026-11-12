#!/usr/bin/env python3
"""Write the .env lines node B needs so its app reads the LOCAL replica (HA-TONIGHT runbook S5.3).

--auto COMPOSE_FILE (the runbook's way, 8 Nov): finds every HA_* variable the compose file uses
(compose-ha-urls.py made them: HA_DATABASE_URL, HA_DIRECT_URL, HA_DATABASE_URL_2, ...), asks
`docker compose config` which service and key each one feeds (by setting each to a unique marker
in this process's environment, which beats .env), and writes HA_X='<that key's CURRENT resolved
value with @host:port swapped for @sorento_crm_replica:5432>' plus REDIS_URL=redis://redis:6379/0.
Path, database name and query (?schema=public) are kept. Run it BEFORE commenting out .env lines
that the compose still falls back to, so the current value is the one B resolves today.

Legacy: without --auto, reads `docker compose config --format json` on stdin and writes
HA_DATABASE_URL / HA_DIRECT_URL (+ HA_ANALYTICS_RO_DATABASE_URL when set) from --service
(default: first backend*) with --suffix (e.g. _2).

Prints passwords only into the redirect; refuses a terminal. Stdlib only.
"""
import json
import os
import re
import subprocess
import sys

REPLICA = "@sorento_crm_replica:5432/"


def swap(key, val):
    val = (val or "").replace("$$", "$")  # compose prints a literal "$" as "$$"
    if "sorento_crm_replica" in val:
        sys.exit("STOP: %s already points at the replica; nothing to add" % key)
    new, n = re.subn(r"@[^@/:]+(:\d+)?/", REPLICA, val, count=1)
    if n != 1 or "'" in new:
        sys.exit("STOP: %s has no single @host:port/ part (or holds a quote); set it by hand" % key)
    return new


def env_of(svc):
    env = svc.get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) if "=" in e else (e, "") for e in env)
    return env


def config(cwd, extra_env=None):
    e = dict(os.environ, **(extra_env or {}))
    r = subprocess.run(["docker", "compose", "--profile", "*", "config", "--format", "json"],
                       cwd=cwd, env=e, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        sys.exit("STOP: docker compose config failed: %s" % r.stderr.strip()[:300])
    return json.loads(r.stdout)


def auto(path):
    cwd = os.path.dirname(os.path.abspath(path))
    names = []
    for v in re.findall(r"\$\{(HA_[A-Z0-9_]+):-", open(path).read()):
        if v not in names:
            names.append(v)
    if not names:
        sys.exit("STOP: the compose file uses no HA_* variable; run compose-ha-urls.py on A first")
    if any(os.environ.get(v) for v in names):
        sys.exit("STOP: an HA_* variable is set in this shell; unset it first")
    base = config(cwd)
    marked = config(cwd, {v: "__HAMARK_%s__" % v for v in names})
    out, used = [], []
    for v in names:
        where = [(s, k) for s, d in marked["services"].items() for k, val in env_of(d).items()
                 if val == "__HAMARK_%s__" % v]
        if not where:
            sys.stderr.write("note: %s feeds no service; skipped\n" % v)
            continue
        s, k = sorted(where)[0]
        cur = env_of(base["services"][s]).get(k)
        if any(env_of(base["services"][s2]).get(k2) != cur for s2, k2 in where):
            sys.exit("STOP: %s feeds keys that resolve differently today; set it by hand" % v)
        out.append("%s='%s'" % (v, swap(k, cur)))
        used.append("%s (%s.%s)" % (v, s, k))
    out.append("REDIS_URL=redis://redis:6379/0")
    return out, used


def legacy(args):
    opt = {"--service": None, "--suffix": ""}
    while args:
        k = args.pop(0)
        if k not in opt or not args:
            sys.exit("usage: ha-env-for-replica.py --auto docker-compose.yml | [--service NAME] [--suffix _2]")
        opt[k] = args.pop(0)
    if opt["--suffix"] and not re.fullmatch(r"_[0-9]{1,2}", opt["--suffix"]):
        sys.exit("STOP: --suffix must look like _2")
    c = json.load(sys.stdin)
    svc = opt["--service"] or next((s for s in sorted(c.get("services", {})) if s.startswith("backend")), None)
    if svc is None or svc not in c.get("services", {}):
        sys.exit("STOP: service %s not in the compose config" % svc)
    env = env_of(c["services"][svc])
    out = []
    for key in ("DATABASE_URL", "DIRECT_URL", "ANALYTICS_RO_DATABASE_URL"):
        if key == "ANALYTICS_RO_DATABASE_URL" and not env.get(key):
            continue
        out.append("HA_%s%s='%s'" % (key, opt["--suffix"], swap(key, env.get(key))))
    if not opt["--suffix"]:
        out.append("REDIS_URL=redis://redis:6379/0")
    return out, ["from service %s" % svc]


if __name__ == "__main__":
    if os.isatty(1):
        sys.exit("STOP: redirect the output into a file; it contains the database password")
    argv = sys.argv[1:]
    if argv[:1] == ["--auto"]:
        if len(argv) != 2:
            sys.exit("usage: ha-env-for-replica.py --auto docker-compose.yml")
        lines, used = auto(argv[1])
    else:
        lines, used = legacy(argv)
    sys.stdout.write("\n" + "\n".join(lines) + "\n")
    sys.stderr.write("wrote: %s, REDIS_URL\n" % "; ".join(used) if lines[-1].startswith("REDIS_URL")
                     else "wrote: %s\n" % "; ".join(used))
