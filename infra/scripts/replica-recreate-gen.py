#!/usr/bin/env python3
"""Generate run scripts that recreate node B's standalone replica container `sorento_crm_replica`
with ONE change: the host= in its command-line primary_conninfo (HA-TONIGHT runbook S2.3).

Usage (node B, root): docker inspect sorento_crm_replica | python3 -I replica-recreate-gen.py <new host>
Writes /root/replica-run-old.sh and /root/replica-run-new.sh (they hold the password: umask 077,
shred them once done) and prints only a MASKED view. Exits non-zero with STOP: when the container
does not have exactly one primary_conninfo argument with one host=. Prints a WARNING for every
container setting it does not copy. Stdlib only.
"""
import json, re, shlex, sys
c = json.load(sys.stdin)[0]
cfg, hc = c["Config"], c["HostConfig"]
NEW = sys.argv[1]
warn = []
def run(cmd_args):
    a = ["docker", "run", "-d", "--name", "sorento_crm_replica"]
    rp = hc.get("RestartPolicy") or {}
    if rp.get("Name") and rp["Name"] != "no":
        a += ["--restart", rp["Name"] + (":%d" % rp["MaximumRetryCount"] if rp["Name"] == "on-failure" and rp.get("MaximumRetryCount") else "")]
    nm = hc.get("NetworkMode") or "default"
    if nm not in ("default", "bridge"):
        a += ["--network", nm]
    if len((c.get("NetworkSettings") or {}).get("Networks") or {}) > 1:
        warn.append("container is on more than one network")
    for cport, binds in sorted((hc.get("PortBindings") or {}).items()):
        for b in binds or []:
            hp = (b.get("HostIp") + ":" if b.get("HostIp") else "") + b["HostPort"]
            a += ["-p", hp + ":" + cport]
    for m in c.get("Mounts") or []:
        src = m["Name"] if m["Type"] == "volume" else m["Source"]
        a += ["-v", src + ":" + m["Destination"] + ("" if m.get("RW", True) else ":ro")]
    for e in cfg.get("Env") or []:
        a += ["-e", e]
    if cfg.get("User"):
        a += ["--user", cfg["User"]]
    if hc.get("ShmSize") and hc["ShmSize"] != 67108864:
        a += ["--shm-size", str(hc["ShmSize"])]
    for k in ("Memory", "NanoCpus", "CpuQuota", "CpuShares", "PidsLimit"):
        if hc.get(k):
            warn.append("HostConfig.%s=%s is not copied" % (k, hc[k]))
    for k in ("CapAdd", "ExtraHosts", "Devices", "SecurityOpt", "Links", "VolumesFrom"):
        if hc.get(k):
            warn.append("HostConfig.%s is set and not copied" % k)
    lc = hc.get("LogConfig") or {}
    if lc.get("Type") not in (None, "", "json-file") or lc.get("Config"):
        warn.append("custom LogConfig is not copied")
    if cfg.get("Labels") and any(k.startswith("com.docker.compose") for k in cfg["Labels"]):
        warn.append("container was created by docker compose")
    if cfg.get("Entrypoint") and cfg["Entrypoint"] != ["docker-entrypoint.sh"]:
        a += ["--entrypoint", cfg["Entrypoint"][0]]
        if len(cfg["Entrypoint"]) > 1:
            warn.append("multi-word entrypoint")
    a.append(c["Image"])  # exact image id: same version
    a += cmd_args
    return a
old_cmd = list(cfg.get("Cmd") or [])
hits = [i for i, x in enumerate(old_cmd) if x.startswith("primary_conninfo=") or "primary_conninfo=" in x]
if len(hits) != 1:
    sys.exit("STOP: expected exactly one primary_conninfo argument, found %d" % len(hits))
i = hits[0]
new_val, n = re.subn(r"(?<![A-Za-z_])host=[^ '\"]+", "host=" + NEW, old_cmd[i])
new_val, _ = re.subn(r"(?<![A-Za-z_])hostaddr=[^ '\"]+ ?", "", new_val)
new_val, p = re.subn(r"(?<![A-Za-z_])port=[0-9]+", "port=5432", new_val)
if n != 1:
    sys.exit("STOP: expected exactly one host= in primary_conninfo, found %d" % n)
new_cmd = old_cmd[:]; new_cmd[i] = new_val
for name, args in (("old", run(old_cmd)), ("new", run(new_cmd))):
    with open("/root/replica-run-%s.sh" % name if len(sys.argv) < 3 else sys.argv[2] + "/replica-run-%s.sh" % name, "w") as f:
        f.write("#!/bin/sh\nset -e\n" + " ".join(shlex.quote(x) for x in args) + "\n")
def m1(x):
    x = re.sub(r"password=('(?:[^'\\]|\\.)*'|\S+)", "password=***", x)
    return re.sub(r"^([A-Z_]*(PASS|SECRET|KEY|TOKEN)[A-Z_]*=).*$", r"\1***", x, flags=re.S)
def show(args):
    return " ".join(shlex.quote(m1(x)) for x in args)
print("NEW RUN (masked):"); print(show(run(new_cmd)))
print("CHANGED ARG (masked):"); print("  old:", m1(old_cmd[i])); print("  new:", m1(new_cmd[i]))
for w in warn: print("WARNING (stop and post):", w)
print("WARNINGS:", len(warn))
