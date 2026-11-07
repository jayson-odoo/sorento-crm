#!/usr/bin/env python3
"""Print the .env lines node B needs so its app reads the LOCAL replica (HA-TONIGHT runbook S5.3):
HA_DATABASE_URL / HA_DIRECT_URL = A's resolved URLs with host:port swapped for
sorento_crm_replica:5432, and REDIS_URL=redis://redis:6379/0 (B's own Redis).

Usage (node B, after A's compose was copied there and BEFORE any HA_ line exists in .env):
  docker compose --profile blue --profile green config --format json \
    | python3 -I ha-env-for-replica.py >> .env
Writes nothing itself and prints the passwords only into that redirect; on a terminal it refuses.
"""
import json
import os
import re
import sys

if os.isatty(1):
    sys.exit("STOP: redirect the output into .env; it contains the database password")
c = json.load(sys.stdin)
svc = next((s for s in sorted(c.get("services", {})) if s.startswith("backend")), None)
if svc is None:
    sys.exit("STOP: no backend service in the compose config")
env = c["services"][svc].get("environment") or {}
out = []
for key in ("DATABASE_URL", "DIRECT_URL"):
    # compose prints a literal "$" as "$$" (its escape); .env single-quoted values are literal.
    val = (env.get(key) or "").replace("$$", "$")
    new, n = re.subn(r"@[^@/:]+(:\d+)?/", "@sorento_crm_replica:5432/", val, count=1)
    if n != 1 or "'" in new:
        sys.exit("STOP: %s has no single @host:port/ part (or holds a quote); set it by hand" % key)
    if "sorento_crm_replica" in val:
        sys.exit("STOP: %s already points at the replica; nothing to add" % key)
    out.append("HA_%s='%s'" % (key, new))
out.append("REDIS_URL=redis://redis:6379/0")
sys.stdout.write("\n" + "\n".join(out) + "\n")
sys.stderr.write("wrote: HA_DATABASE_URL, HA_DIRECT_URL (host sorento_crm_replica:5432), REDIS_URL\n")
