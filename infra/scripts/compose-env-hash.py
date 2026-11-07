#!/usr/bin/env python3
"""Hash what `docker compose config --format json` resolves (stdin); values are never printed.

Default (A/B parity, HA-TONIGHT runbook S5.1): `<service> <ENV KEY> <sha256[:12]>` for every env
key of every CRM service (backend*, frontend*, mcp*, worker*), except DATABASE_URL, DIRECT_URL and
REDIS_URL, which differ per node by design.

--all (proof that an edit changed nothing, runbook S5.1b): every env key of EVERY service with no
skip, plus one hash of each whole service definition and of every other top-level section
(networks, volumes, ...). Run it before and after an edit and diff the two outputs.
Stdlib only.
"""
import hashlib
import json
import sys


def h(v):
    return hashlib.sha256(str(v).encode()).hexdigest()[:12]


def env_of(svc):
    env = svc.get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) if "=" in e else (e, "") for e in env)
    return env


def main(argv):
    full = "--all" in argv
    c = json.load(sys.stdin)
    services = c.get("services", {})
    skip = set() if full else {"DATABASE_URL", "DIRECT_URL", "REDIS_URL"}
    for name in sorted(services):
        if not full and not name.startswith(("backend", "frontend", "mcp", "worker")):
            continue
        env = env_of(services[name])
        for k in sorted(env):
            if k in skip:
                continue
            print(name, k, h(env[k] if env[k] is not None else ""))
        if full:
            print(name, "__service__", h(json.dumps(services[name], sort_keys=True)))
    if full:
        for top in sorted(k for k in c if k not in ("services", "name")):
            print("__top__", top, h(json.dumps(c[top], sort_keys=True)))


if __name__ == "__main__":
    main(sys.argv[1:])
