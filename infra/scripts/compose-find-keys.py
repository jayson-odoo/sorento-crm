#!/usr/bin/env python3
"""Print WHERE (service and key path, never the value) any string in the resolved compose config
contains one of the given needles (HA-TONIGHT runbook S5.3 check: nothing on node B may still point
at A's database, pgbouncer, public address or public hostname).

Usage: docker compose --profile blue --profile green --profile promoted config --format json \
         | python3 -I compose-find-keys.py '@pgbouncer' '@db:' '<A_PUBLIC_IP>' '<CRM_HOST>'
Prints `FOUND <path>` per hit and `HITS: <n>`; exit 0 either way.
"""
import json
import sys


def walk(node, path, needles, hits):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, path + [str(k)], needles, hits)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str) and "=" in v:
                walk(v.split("=", 1)[1], path + [v.split("=", 1)[0]], needles, hits)
            else:
                walk(v, path + [str(i)], needles, hits)
    elif isinstance(node, str) and any(n in node for n in needles):
        hits.append(".".join(path))


needles = [n for n in sys.argv[1:] if n]
hits = []
walk(json.load(sys.stdin), [], needles, hits)
for p in hits:
    print("FOUND", p)
print("HITS:", len(hits))
