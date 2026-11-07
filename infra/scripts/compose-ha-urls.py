#!/usr/bin/env python3
"""Make the literal DATABASE_URL / DIRECT_URL values in a compose file overridable per node
(HA-TONIGHT runbook S5.3): `KEY: <literal>` becomes `KEY: '${HA_KEY:-<literal>}'` (list form
`- KEY=<literal>` likewise). A node that does not set HA_DATABASE_URL / HA_DIRECT_URL resolves
exactly the old value; node B sets them in its .env to reach its local replica.

Usage: python3 -I compose-ha-urls.py docker-compose.yml   (rewrites in place; keep a backup)
Prints how many lines changed, never the values. Lines already starting with `${` are left alone.
"""
import re
import sys

path = sys.argv[1]
src = open(path).read().split("\n")
pat = re.compile(r"^(\s*)(-\s*)?(DATABASE_URL|DIRECT_URL)(\s*[:=]\s*)(.*?)\s*$")
changed = 0
out = []
for line in src:
    m = pat.match(line)
    if not m or not m.group(5) or m.group(5).lstrip("'\"").startswith("${"):
        out.append(line)
        continue
    ind, dash, key, sep, val = m.groups()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
        val = val[1:-1]
    if "${" in val or "}" in val:
        sys.exit("STOP: %s on a changed line already uses ${...}; edit it by hand" % key)
    inner = "${HA_%s:-%s}" % (key, val)
    if dash:  # list form: - KEY=value
        out.append("%s%s'%s=%s'" % (ind, dash, key, inner.replace("'", "''")))
    else:
        out.append("%s%s: '%s'" % (ind, key, inner.replace("'", "''")))
    changed += 1
open(path, "w").write("\n".join(out))
print("changed lines:", changed)
