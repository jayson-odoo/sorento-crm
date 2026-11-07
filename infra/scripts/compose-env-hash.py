#!/usr/bin/env python3
"""Print <service> <ENV KEY> <sha256[:12] of the value> for every CRM service (backend*, frontend*,
mcp*, worker*) in `docker compose config --format json` read from stdin. Values are never printed.
DATABASE_URL, DIRECT_URL and REDIS_URL are skipped (they differ per node by design). Used by the
HA-TONIGHT runbook S5.1 to prove two nodes resolve the same secrets. Stdlib only."""
import hashlib, json, sys
c = json.load(sys.stdin)
skip = {'DATABASE_URL', 'DIRECT_URL', 'REDIS_URL'}
for svc in sorted(c.get('services', {})):
    if not svc.startswith(('backend', 'frontend', 'mcp', 'worker')):
        continue
    env = c['services'][svc].get('environment') or {}
    if isinstance(env, list):
        env = dict(e.split('=', 1) if '=' in e else (e, '') for e in env)
    for k in sorted(env):
        if k in skip:
            continue
        v = env[k] if env[k] is not None else ''
        print(svc, k, hashlib.sha256(str(v).encode()).hexdigest()[:12])
