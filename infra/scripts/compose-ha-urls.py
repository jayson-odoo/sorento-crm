#!/usr/bin/env python3
"""Make the literal DATABASE_URL / DIRECT_URL / ANALYTICS_RO_DATABASE_URL values in a compose file overridable per node
(HA-TONIGHT runbook S5.1b): `KEY: <literal>` becomes `KEY: '${HA_KEY:-<literal>}'` (list form
`- KEY=<literal>` likewise). A node that does not set HA_DATABASE_URL / HA_DIRECT_URL resolves
exactly the old value; node B sets them in its .env to reach its local replica.

Handles plain, single-quoted and double-quoted values, a quoted list item, and a trailing
`# comment` (kept after the new value). Anything it cannot parse safely is a STOP (exit 1, file
untouched): anchors/aliases, a value that uses ${...} other than the key's own variable
(`KEY: ${KEY:-<url>}` becomes `'${HA_KEY:-${KEY:-<url>}}'`), a double-quoted escape other than
\\" and \\\\, text after a closing quote that is not a comment.

Usage: python3 -I compose-ha-urls.py docker-compose.yml   (rewrites in place; keep a backup)
Prints how many lines changed, never the values. Prove the result with
compose-env-hash.py --all before/after: it must not change on a node without HA_* set.
"""
import re
import sys

KEYS = ("DATABASE_URL", "DIRECT_URL", "ANALYTICS_RO_DATABASE_URL")
MAP = re.compile(r"^(\s*)(%s)(\s*:\s*)(.*)$" % "|".join(KEYS))
LST = re.compile(r"^(\s*)(-\s*)(['\"]?)(%s)=(.*)$" % "|".join(KEYS))


class Stop(Exception):
    pass


def split_quoted(q, rest):
    """rest starts right after the opening quote q. Returns (value, tail after the closing quote)."""
    out, i = [], 0
    while i < len(rest):
        ch = rest[i]
        if q == "'" and ch == "'":
            if rest[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), rest[i + 1:]
        if q == '"' and ch == "\\":
            nxt = rest[i + 1:i + 2]
            if nxt not in ('"', "\\"):
                raise Stop("unsupported escape in a double-quoted value")
            out.append(nxt)
            i += 2
            continue
        if q == '"' and ch == '"':
            return "".join(out), rest[i + 1:]
        out.append(ch)
        i += 1
    raise Stop("unterminated quote")


def comment_of(tail):
    m = re.match(r"^\s*(#.*)?$", tail)
    if not m:
        raise Stop("text after the closing quote")
    return (" " + m.group(1)) if m.group(1) else ""


def plain(rest):
    m = re.match(r"^(.*?)(\s+#.*)?$", rest)
    return m.group(1).rstrip(), (" " + m.group(2).strip()) if m.group(2) else ""


def wrap(key, val):
    if not val:
        return None
    # A's compose (owner, 8 Nov): `KEY: ${KEY:-<url>}`. Nest it, so a node without HA_KEY
    # resolves exactly what it did, with or without KEY in its .env. Only the SAME key's own
    # variable, with a plain default (or none); anything else stays a STOP.
    if re.fullmatch(r"\$\{%s(?::?-(?:[^${}]|\$\$)*)?\}" % key, val):
        return "${HA_%s:-%s}" % (key, val)
    if val[0] in "&*!" or "${" in val or "}" in val:
        raise Stop("%s value is an anchor, alias, tag or already uses ${...}; edit it by hand" % key)
    return "${HA_%s:-%s}" % (key, val)


def sq(s):
    return "'" + s.replace("'", "''") + "'"


def rewrite_line(line):
    m = MAP.match(line)
    if m:
        ind, key, sep, rest = m.groups()
        rest = rest.strip()
        if not rest or rest.startswith("#"):
            return line, False
        if rest[0] in "'\"":
            val, tail = split_quoted(rest[0], rest[1:])
            com = comment_of(tail)
        else:
            val, com = plain(rest)
        if val.startswith("${HA_"):
            return line, False
        new = wrap(key, val)
        return ("%s%s: %s%s" % (ind, key, sq(new), com)), True
    m = LST.match(line)
    if m:
        ind, dash, q, key, rest = m.groups()
        if q:
            val, tail = split_quoted(q, rest)
            com = comment_of(tail)
        else:
            val, com = plain(rest)
        if val.startswith("${HA_"):
            return line, False
        new = wrap(key, val)
        if new is None:
            return line, False
        return ("%s%s%s%s" % (ind, dash, sq("%s=%s" % (key, new)), com)), True
    return line, False


def rewrite(text):
    out, n = [], 0
    for line in text.split("\n"):
        new, changed = rewrite_line(line)
        out.append(new)
        n += changed
    return "\n".join(out), n


def main(path):
    text = open(path).read()
    try:
        new, n = rewrite(text)
    except Stop as e:
        sys.exit("STOP: %s (file untouched)" % e)
    open(path, "w").write(new)
    print("changed lines:", n)


if __name__ == "__main__":
    main(sys.argv[1])
