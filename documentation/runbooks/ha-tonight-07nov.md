# HA tonight (7 Nov): manual failover for the current two-node layout

Owner runbook. The owner runs every command; crew and agents never touch prod. Source of every
fact: `documentation/plans/infra/PLAN-ha-b-replica-sync-07nov.md` sections 8-10 (owner's
read-only results). Nothing below holds an address, hostname or secret: fill the placeholders
on your own screen, never in the repo or on the PR.

**What you have at the end of tonight:** B holds an encrypted streaming replica and a STANDBY
copy of the CRM app; a rehearsed, copy-paste MANUAL failover to B (S6); Cloudflare Load Balancing
ready to move users to whichever node is writable (S7). **Not tonight:** automatic failover. The
controller (`cf-failover`) and the role watcher stay disabled until the section 3 PR (R2 sync
record) is merged and drilled. Replication stays ASYNC tonight: with synchronous replication and
no controller, B going down would block every save on A forever. RPO tonight = the replication
lag at the moment A dies (measured 0 bytes behind, under 2 ms).

## Placeholders

| Placeholder | What it is | How to read it |
|---|---|---|
| `<A_PUBLIC_IP>` / `<B_PUBLIC_IP>` | public IPv4 of each node | hPanel |
| `<A_PUBLIC_IF>` / `<B_PUBLIC_IF>` | public interface (often `eth0`) | on A: `ip route get <B_PUBLIC_IP>` prints `dev ...`; on B the same with A |
| `<APP_DB>` / `<APP_DB_USER>` | the CRM database name and app role | A's `.env` `DATABASE_URL` (do not paste it anywhere) |
| `<REPL_PASSWORD>` | `replicator` password | on B: `sudo grep -o "password=[^ ]*" /root/replica-run-new.sh` (on your screen only) |
| `<SHA>` | the 40-hex image SHA A runs now | on A: `docker compose ps --format '{{.Image}}' backend_$(cat .active_color)` |
| `<CRM_HOST>` | the public CRM hostname | Cloudflare DNS |
| `<B_COMPOSE_NET>` | B's CRM compose network | on B: `docker network ls \| grep sorento` |

Tunnel addresses used below (private, safe to keep): A = `10.77.0.1`, B = `10.77.0.2`.

## Progress log (owner runs, crew relays; newest last)

| When (7 Nov, MYT) | Step | Result |
|---|---|---|
| ~22:00 | S2.2 (A pg_hba row for 10.77.0.2) | done |
| ~22:30 | S2.3 first try (alter system) | stopped: `primary_conninfo` comes from the replica's command line |
| ~23:00 | S2.3 recreate | failed (`no pg_hba.conf entry ... 172.18.0.1`), rolled back; replica streaming again over the public path. Suspected cause: B's wg0 address (S2.1 check) |
| ~23:30 | S0 on A | DONE: owner key installed on both nodes (`ssh-copy-id`), drop-in applied, `CONFIG-OK`, key login OK, password login denied |
| ~00:30 | S2.1 fix | B's `wg0.conf` had A's values (Address 10.77.0.1, AllowedIPs 10.77.0.2): B pinged itself. Fixed to 10.77.0.2 / 10.77.0.1; keys and handshake verified; ping about 0.8 ms both ways |
| 8 Nov ~01:50 | S2.3 recreate | DONE: new replica container streams from 10.77.0.1 over wg0; `sorento_crm_replica_old` kept stopped. On the way: the replica authenticates with `passfile=/var/lib/postgresql/data/.pgpass`, whose line names A's PUBLIC address, so the new conninfo got `fe_sendauth: no password supplied`; fixed by a second `.pgpass` line for 10.77.0.1 (password never printed) |
| next | A check (`client_addr = 10.77.0.2`), S0 on B, outside-in firewall check, S5, S6.0 drill | pending |

## The provider firewall (Hostinger, owner screenshot 7 Nov ~22:20)

A and B share ONE Hostinger firewall rule set. It acts before the host, so Docker cannot bypass
it. Rules, in order: accept TCP 22, 443, 80 from any; accept TCP 5432, 27017, 6432, 8765 and UDP
51820 from ONE source, which is **node B's public IP**; then drop everything else.

| Rule | What it opens, on each node | Source it needs | Recommendation |
|---|---|---|---|
| UDP 51820 | WireGuard | **A AND B** (each side sends handshakes and keepalives to the other) | Add A's public IP. Without it, A's packets are dropped at B, so no tunnel. |
| TCP 5432 | A: the CRM Postgres (replication). B: n8n's Postgres | B (B replicates from A over the public address until S2.3 is done) | Remove the rule a day after S2.3 streams over the tunnel: tunnel traffic is inside UDP 51820, so the provider never sees 5432. |
| TCP 6432 | A: pgbouncer (n8n on B reaches the CRM database here). B: host pgbouncer | B | Keep until n8n is retired or moved to the tunnel (`10.77.0.1:6432`), then remove. |
| TCP 8765 | the CRM MCP server (streamable HTTP, bearer token); n8n on B calls it on A | B | Same as 6432: keep for n8n, move to the tunnel, then remove. |
| TCP 27017 | B: n8n's MongoDB. Nothing outside B needs it, and the only allowed source is B itself | none | **Remove the rule.** It does nothing useful. |
| TCP 22 | SSH | see below | Leave open to any for now (see below). |
| everything else | dropped: n8n UI 5678, Redis 6379, the replica port 5434 | none | correct |

**What this already covers:** S1 (A's 5432 from B only) and S3 (B's n8n stores and pgbouncer) are
already enforced at the provider for IPv4. Whether the Hostinger firewall also filters IPv6 is
UNVERIFIED; the outside-in check below tests it. The host rules in S1 and S3 stay as defence in
depth: one shared rule set means a single "any" added later for some other reason re-opens both
nodes, and tunnel traffic (inside 51820) is never filtered by the provider at all. They are no
longer urgent: run S1 and S3 after S2, not before.

**Outside-in check (from a third machine, e.g. a phone hotspot, on no allowlist):**

```bash
for h in <A_PUBLIC_IP> <B_PUBLIC_IP>; do
  for p in 5432 6432 6379 27017 5678 5434 8765; do
    nc -4 -z -w 5 $h $p && echo "$h:$p OPEN <- FAIL" || echo "$h:$p closed"; done
  for p in 22 80 443; do nc -4 -z -w 5 $h $p && echo "$h:$p open (expected)" || echo "$h:$p closed"; done
done
# IPv6, if the nodes have public IPv6 addresses:
for h in <A_PUBLIC_IPV6> <B_PUBLIC_IPV6>; do for p in 5432 6432 6379 27017 8765; do
  nc -6 -z -w 5 $h $p && echo "$h:$p OPEN <- FAIL" || echo "$h:$p closed"; done; done
```

Expected: every database, cache and MCP port `closed` on both nodes; 22, 80 and 443 open. Any
`OPEN <- FAIL` on IPv6 means the provider firewall does not cover IPv6: then S1 and S3 are urgent.

**SSH 22 from any.** Restricting it (your own IP, or Tailscale only) would be safer, but: the
release workflow SSHes into A (and later B) from GitHub-hosted runners, whose addresses change, so
a 22-from-my-IP rule **breaks every release**. And a mistake locks you out of both nodes at once
(shared rule set). If you restrict it, first make sure hPanel's browser terminal/VNC console works
for both nodes (that is the rollback path: it does not go through the firewall), then either add
Tailscale to the deploy workflow or keep 22 open. Recommended for now: keep 22 open, and make sure
password login is off on both (`sudo sshd -T | grep -E '^(passwordauthentication|permitrootlogin)'`
prints `passwordauthentication no` and `permitrootlogin no` or `prohibit-password`). Rollback of
any SSH restriction: hPanel console, then remove the rule in the firewall panel.

## Order, downtime and stop rule

| Step | Node | Changes | App downtime |
|---|---|---|---|
| S0 | A, then B | SSH: keys only, root by key only (found 7 Nov: password login open to the internet) | none |
| S1 | A | host firewall: Postgres 5432 from B only (provider already enforces it; defence in depth, run after S2) | none |
| S2 | A + B | WireGuard tunnel, replication moves onto it | none (B re-connects in seconds) |
| S3 | B | host firewall: n8n stores and pgbouncer (provider already enforces it; defence in depth, run after S2) | none (n8n untouched if the check passes) |
| S4 | A | one Postgres restart: `wal_log_hints`, WAL archive to R2, slot and sender limits | **yes: about 1-2 minutes of 503s on A**, announce it |
| S5 | B | CRM app comes up on B as a STANDBY | none (B has no users) |
| S6 | drill on B only | rehearse the manual failover on a throwaway copy | none |
| S7 | Cloudflare | load balancer and monitor on `/api/v1/health/role` | none if done in the order given |

**Global stop rule:** after every step run its Check. If any check differs from Expected, run
that step's Rollback, stop, and post the output (addresses replaced) on PR #2166. Never start a
step while the previous one is red.

**Standard health check (used by several steps), on A:**

```bash
# READ-ONLY. Replication state as A sees it, and the app's health.
cd /opt/sorento-crm2
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select application_name, state, sync_state, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)
   from pg_stat_replication"
C=$(cat .active_color); P=8000; [ "$C" = green ] && P=8010
curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:$P/api/v1/health
```

Expected: `sorento_crm_replica|streaming|async|0` (the last number may be a few thousand bytes
under load, never growing), then `health 200`.

---

## S0. SSH: keys only (do this FIRST; one node at a time, A then B)

Found 7 Nov: `permitrootlogin yes` and `passwordauthentication yes` on both nodes with 22 open to
any. Releases log in with a KEY (`deploy.yml`: `appleboy/ssh-action` with `secrets.SSH_USER` +
`secrets.SSH_PRIVATE_KEY`; `scripts/ha_release.sh` the same), so they are unaffected;
`prohibit-password` still lets root in with a key.

1. From your Mac: `ssh -o PasswordAuthentication=no -o PreferredAuthentications=publickey <user>@<A_PUBLIC_IP> 'echo KEY-OK'`
   prints `KEY-OK`. If not, `ssh-copy-id <user>@<A_PUBLIC_IP>` first, then repeat. Stop until it works.
2. Keep a SECOND session open on the node until step 4 passes; check the hPanel browser terminal
   gives a shell (rollback path, it bypasses SSH and the firewall).
3. Paste (THIS CHANGES PROD, no restart):

```bash
sudo tee /etc/ssh/sshd_config.d/00-sorento-hardening.conf >/dev/null <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
CONF
sudo sshd -t && echo CONFIG-OK
grep -n '^Include' /etc/ssh/sshd_config
sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication)'
sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd
```

   Expected: `CONFIG-OK`; an `Include /etc/ssh/sshd_config.d/*.conf` line near the top;
   `passwordauthentication no`, `kbdinteractiveauthentication no`, `permitrootlogin without-password`,
   `pubkeyauthentication yes`. (`00-` sorts first: sshd keeps the FIRST value it reads, so it beats
   `50-cloud-init.conf`.)
4. Check from the Mac: the key login prints `KEY-OK`; `ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password <user>@<A_PUBLIC_IP> true`
   prints `Permission denied (publickey).` Then close the second session and repeat on B.

**Rollback** (open session or hPanel terminal): `sudo rm /etc/ssh/sshd_config.d/00-sorento-hardening.conf && sudo sshd -t && (sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd)`.

---

## S1. A: Postgres 5432 from B only (no restart, no app impact)

**Changes:** a `DOCKER-USER` rule drops 5432 on A's public interface unless it comes from B; IPv6
5432 is dropped. A oneshot unit re-applies it after a reboot. The app and pgbouncer reach `db` on
the compose bridge and never enter on the public interface, so they are not touched.

**Paste (node A):**

```bash
# THIS CHANGES PROD (node A).
sudo tee /usr/local/sbin/sorento-edge.sh >/dev/null <<'SH'
#!/bin/sh
set -eu
IF=<A_PUBLIC_IF>; B=<B_PUBLIC_IP>
add()  { iptables  -C "$@" 2>/dev/null || iptables  -I "$@"; }
add6() { ip6tables -C "$@" 2>/dev/null || ip6tables -I "$@"; }
add DOCKER-USER -i "$IF" -p tcp -m conntrack --ctorigdstport 5432 --ctdir ORIGINAL ! -s "$B/32" -j DROP
add6 INPUT -i "$IF" -p tcp --dport 5432 -j DROP
SH
sudo chmod 700 /usr/local/sbin/sorento-edge.sh
sudo tee /etc/systemd/system/sorento-edge.service >/dev/null <<'UNIT'
[Unit]
Description=Sorento edge rules (published DB ports)
After=docker.service
Requires=docker.service
PartOf=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/sorento-edge.sh
[Install]
WantedBy=multi-user.target docker.service
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now sorento-edge.service
```

**Check:**
1. `sudo iptables -S DOCKER-USER | grep 5432` prints one line holding `! -s <B_PUBLIC_IP>/32`, `-i <A_PUBLIC_IF>`, `--ctorigdstport 5432` and `-j DROP` (iptables prints them in its own order).
2. Standard health check: `streaming|async|0` and `health 200`.
3. From a phone hotspot (on no allowlist): `nc -4 -z -w 5 <A_PUBLIC_IP> 5432 && echo OPEN || echo closed` prints `closed`; if A has a public IPv6, `nc -6 -z -w 5 <A_PUBLIC_IPV6> 5432` the same.

**Rollback:**

```bash
sudo systemctl disable --now sorento-edge.service
sudo iptables  -D DOCKER-USER -i <A_PUBLIC_IF> -p tcp -m conntrack --ctorigdstport 5432 --ctdir ORIGINAL ! -s <B_PUBLIC_IP>/32 -j DROP
sudo ip6tables -D INPUT -i <A_PUBLIC_IF> -p tcp --dport 5432 -j DROP
```

**Stop if:** replication is not `streaming` within 1 minute, or `health` is not 200.

---

## S2. WireGuard A<->B, then replication onto the tunnel (no restart)

**Changes:** a `wg0` tunnel between the nodes (UDP 51820, peer only); A's pg_hba gains a row for
B's tunnel address (reload); B's replica re-points `primary_conninfo` at `10.77.0.1` (reload). The
whole database stops crossing the internet in clear text.

### S2.1 Tunnel (both nodes)

**hPanel first:** the shared Hostinger rule for `51820/udp` must list BOTH nodes' public IPs (it
lists only B today). Without A's IP, A's handshakes are dropped at B and the tunnel never comes up.

**Paste (node A), then the same on node B with the values swapped as marked:**

```bash
# THIS CHANGES PROD (A; on B swap the marked values).
sudo apt-get install -y wireguard
sudo sh -c 'umask 077; [ -s /etc/wireguard/private.key ] || wg genkey > /etc/wireguard/private.key; wg pubkey < /etc/wireguard/private.key > /etc/wireguard/public.key'
sudo cat /etc/wireguard/public.key     # copy this to the OTHER node by hand (a public key, safe)
```

Then on each node write the config with the other node's public key:

```bash
# THIS CHANGES PROD. A: SELF=10.77.0.1 PEER=10.77.0.2 PEER_IP=<B_PUBLIC_IP>
#                    B: SELF=10.77.0.2 PEER=10.77.0.1 PEER_IP=<A_PUBLIC_IP>
SELF=10.77.0.1; PEER=10.77.0.2; PEER_IP=<B_PUBLIC_IP>; PEER_PUB='<PEER_PUBLIC_KEY>'
sudo sh -c "umask 077; cat > /etc/wireguard/wg0.conf" <<EOF
[Interface]
Address = $SELF/32
ListenPort = 51820
PostUp = wg set %i private-key /etc/wireguard/private.key

[Peer]
PublicKey = $PEER_PUB
Endpoint = $PEER_IP:51820
AllowedIPs = $PEER/32
PersistentKeepalive = 25
EOF
sudo systemctl enable --now wg-quick@wg0
# 51820/udp from the peer only, kept with the other edge rules:
echo "add INPUT -i \"\$IF\" -p udp --dport 51820 ! -s $PEER_IP/32 -j DROP" | sudo tee -a /usr/local/sbin/sorento-edge.sh
[ -f /etc/systemd/system/sorento-edge.service ] && sudo systemctl restart sorento-edge.service   # A: applies it now
```

(B gets `sorento-edge.sh` in S3. If you run S2 on B first, the `tee -a` creates a file without the
header: run S3's block afterwards, which rewrites it whole and includes the 51820 line.)

**Check (each node):**
1. `sudo wg show wg0 latest-handshakes` shows a timestamp under 2 minutes old.
2. On A: `ping -c 20 -q 10.77.0.2` gives `0% packet loss` and an avg **between 0.2 and 2 ms**. On B: `ping -c 20 -q 10.77.0.1` the same.
   An avg under about 0.1 ms means the node is pinging ITSELF (it was given the other node's address): stop.
3. On each node `ip route get <peer tunnel address>` prints `<peer> dev wg0 src <own tunnel address>`, never `local <peer> dev lo`.
4. `sudo wg show wg0` lists exactly one peer, whose public key is the OTHER node's `public.key`.

**Rollback:** `sudo systemctl disable --now wg-quick@wg0` on both (nothing uses the tunnel yet).

**Stop if:** no handshake after 2 minutes (check the hPanel rule and the public keys).

**Also check on B (7 Nov lesson):** `ip -br addr show wg0` prints `10.77.0.2/32` and
`ip route get 10.77.0.1` prints `10.77.0.1 dev wg0`, NOT `local 10.77.0.1`. If B carries A's
address, B's own Docker DNAT sends the replica's connection to n8n's Postgres 15 on B (published
on `0.0.0.0:5432`), which answers `pg_isready` and then refuses `replicator` from `172.18.0.1`:
the S2.3 failure seen on 7 Nov.

### S2.2 A: allow B's tunnel address to replicate (pg_hba reload, keeps a backup)

```bash
# THIS CHANGES PROD (node A). No restart.
cd /opt/sorento-crm2
docker compose exec -T -u postgres db sh -c 'f="$PGDATA/pg_hba.conf"; cp -n "$f" "$f.bak-07nov" &&
  grep -q "^host replication replicator 10.77.0.2/32" "$f" ||
  sed -i "/^host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+all/i host replication replicator 10.77.0.2/32 scram-sha-256" "$f"'
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc "select pg_reload_conf()"
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select line_number, error from pg_hba_file_rules where error is not null"
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select line_number, type, database, user_name, address from pg_hba_file_rules where address = '10.77.0.2'"
```

**Expected:** `t`; then nothing (no error rows); then one row `N|host|{replication}|{replicator}|10.77.0.2`.

**Rollback:** `docker compose exec -T -u postgres db sh -c 'cp "$PGDATA/pg_hba.conf.bak-07nov" "$PGDATA/pg_hba.conf"'` and the reload line.

### S2.3 B: move the replica onto the tunnel (replica recreate, about 10-30 s, no user impact)

On B, `primary_conninfo` and `primary_slot_name` are passed on the replica container's command
line (`-c ...`; owner check 7 Nov: `pg_settings.source = command line`), so `alter system` cannot
change them. The container is recreated with the same image id, volume, ports, env and args, and
only `host=` changed to `10.77.0.1`. A is untouched; the slot holds WAL while the replica is down.

**0. Prerequisite (READ-ONLY, B and A):** on A note `sudo iptables -t nat -L DOCKER -v -n | grep 'dpt:5432'`
(the pkts count), run B's `pg_isready` below, read the count again: it must have grown by 1
(proof the connection reached A, not B's own n8n Postgres). On B: `sudo wg show wg0 latest-handshakes` fresh;
`ping -c 5 -q 10.77.0.1` 0% loss; `docker exec sorento_crm_replica pg_isready -h 10.77.0.1 -p 5432`
prints `accepting connections` (the container reaches A through the tunnel, NATed to 10.77.0.2,
the address S2.2 allowed). Stop if not.

**1. Generate (B, changes nothing running).** Copy `infra/scripts/replica-recreate-gen.py` from the
branch to B as `/root/replica-gen.py` (mode 600), then:

```bash
sudo sh -c 'umask 077; docker inspect sorento_crm_replica | python3 -I /root/replica-gen.py 10.77.0.1'
```

Expected: `WARNINGS: 0`; the masked `old:` / `new:` lines differ only in `host=`; the NEW RUN line
keeps `-p 127.0.0.1:5433:5432/tcp`, the data volume, `primary_slot_name`, and a `sha256:` image.
Stop on any `STOP:` or `WARNING`. The `old:` line shows A's public IP: mask it before posting.

**2. Recreate (THIS CHANGES PROD, B only):**

```bash
docker stop -t 60 sorento_crm_replica &&
docker rename sorento_crm_replica sorento_crm_replica_old &&
docker update --restart no sorento_crm_replica_old &&
sudo sh /root/replica-run-new.sh &&
sleep 15 &&
docker exec sorento_crm_replica psql -U postgres -d postgres -Atc \
  "select pg_is_in_recovery(), status, sender_host, sender_port from pg_stat_wal_receiver"
```

Expected on B: `t|streaming|10.77.0.1|5432` (re-run the last line if empty; up to about 30 s).

**Check, on A (superuser):**

```bash
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select application_name, client_addr, state from pg_stat_replication"
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select slot_name, active, wal_status from pg_replication_slots"
```

**Expected:** `sorento_crm_replica|10.77.0.2|streaming`, `sorento_crm_replica_slot|t|reserved`, then
the standard health check.

**Rollback (B):** `docker rm -f sorento_crm_replica && docker rename sorento_crm_replica_old sorento_crm_replica && docker update --restart unless-stopped sorento_crm_replica && docker start sorento_crm_replica`
(use the restart policy step 1 printed). `/root/replica-run-old.sh` rebuilds the original if the
`_old` container is ever lost.

**Stop if:** not `streaming` from `10.77.0.1` within 2 minutes, or `docker logs --tail 30
sorento_crm_replica` shows `FATAL` (`no pg_hba.conf entry for host "10.77.0.2"` = S2.2's row is
missing on A): roll back, then post.

**Password source (7 Nov lesson):** the replica may authenticate with `passfile=` (a `.pgpass` in its
data directory) instead of `password=` in the conninfo. `.pgpass` lines are host-specific, so a new
`host=` needs its own line, or the new container logs `fe_sendauth: no password supplied`. Fix
without printing the password (B):

```bash
docker exec -u postgres sorento_crm_replica sh -c 'f=/var/lib/postgresql/data/.pgpass; grep -q "^10.77.0.1:" "$f" ||
  { grep -m1 "^[^#]*:5432:[^:]*:replicator:" "$f" | sed "s/^[^:]*:/10.77.0.1:/" >> "$f"; }; chmod 600 "$f"; cut -d: -f1-4 "$f"'
```

Expected: the printed lines (no passwords) include `10.77.0.1:5432:<db>:replicator`.

Afterwards: keep `sorento_crm_replica_old` until the next day, then `docker rm` it (data is in the
volume); `sudo shred -u /root/replica-run-old.sh /root/replica-run-new.sh` (they hold the
password). S5.2 later recreates the container once more from the NEW container's settings (same
script pattern), adding the compose network and the 5434 port.

### S2.4 Later (after a day of streaming over the tunnel; not tonight)

**When:** 24 hours of `client_addr = 10.77.0.2` with no reconnects to the public address (8 Nov
~02:00 started the clock, so earliest 9 Nov ~02:00), AND `sorento_crm_replica_old` removed (its
rollback path uses the public address). Then, in this order: (1) remove the TCP 5432 rule in the
Hostinger firewall; (2) the host rule change below; (3) delete A's pg_hba row for B's PUBLIC
address and reload; (4) on B remove the `.pgpass` line for A's public address. Check after each:
replication still `streaming` from `10.77.0.2`.

In A's `sorento-edge.sh` remove `! -s "$B/32"` from the 5432 line (5432 closed on the public
interface to everyone). First `sudo systemctl restart sorento-edge` (it inserts the broad DROP on
top), THEN delete the old narrower rule by hand (the script only adds; this order never leaves
5432 open):
`sudo iptables -D DOCKER-USER -i <A_PUBLIC_IF> -p tcp -m conntrack --ctorigdstport 5432 --ctdir ORIGINAL ! -s <B_PUBLIC_IP>/32 -j DROP`,
then delete the pg_hba row for B's
PUBLIC address and reload. Check: replication still `streaming` from `10.77.0.2`.

---

## S3. B: n8n stores and the host pgbouncer closed to the internet (no restart)

**Changes:** n8n's Postgres 5432, Redis 6379 and MongoDB 27017 (docker-published) and the host
pgbouncer 6432 accept only A on the public interface; IPv6 closed; 51820/udp from A only; B's CRM
replica port for A (5434, used by S5.2 and the rejoin in S6) only over the tunnel.

**First (read-only):** `for p in 5432 6379 27017 6432; do echo "== $p"; sudo conntrack -L -p tcp --orig-port-dst $p 2>/dev/null | grep -oE 'src=[0-9a-f.:]+' | sort | uniq -c | sort -rn | head -5; done`.
**Stop if** any source other than A, loopback or a docker address (172.x) shows up: tell crew.

**Paste (node B):**

```bash
# THIS CHANGES PROD (node B).
sudo tee /usr/local/sbin/sorento-edge.sh >/dev/null <<'SH'
#!/bin/sh
set -eu
IF=<B_PUBLIC_IF>; A=<A_PUBLIC_IP>
add()  { iptables  -C "$@" 2>/dev/null || iptables  -I "$@"; }
add6() { ip6tables -C "$@" 2>/dev/null || ip6tables -I "$@"; }
for p in 5432 6379 27017; do       # n8n Postgres, Redis, MongoDB (docker-published)
  add DOCKER-USER -i "$IF" -p tcp -m conntrack --ctorigdstport $p --ctdir ORIGINAL ! -s "$A/32" -j DROP
  add6 INPUT -i "$IF" -p tcp --dport $p -j DROP
done
add  INPUT -i "$IF" -p tcp --dport 6432 ! -s "$A/32" -j DROP   # host pgbouncer (not docker)
add6 INPUT -i "$IF" -p tcp --dport 6432 -j DROP
add  DOCKER-USER -p tcp -m conntrack --ctorigdstport 5434 --ctdir ORIGINAL ! -i wg0 -j DROP  # CRM replica, tunnel only
add6 INPUT -i "$IF" -p tcp --dport 5434 -j DROP
add  INPUT -i "$IF" -p udp --dport 51820 ! -s "$A/32" -j DROP  # WireGuard from A only
add6 INPUT -i "$IF" -p udp --dport 51820 -j DROP
SH
sudo chmod 700 /usr/local/sbin/sorento-edge.sh
# The same unit as S1:
sudo tee /etc/systemd/system/sorento-edge.service >/dev/null <<'UNIT'
[Unit]
Description=Sorento edge rules (published DB ports)
After=docker.service
Requires=docker.service
PartOf=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/sorento-edge.sh
[Install]
WantedBy=multi-user.target docker.service
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now sorento-edge.service && sudo systemctl restart sorento-edge.service
```

**Check:**
1. `docker exec n8n-main wget -qO- http://127.0.0.1:5678/healthz` prints `{"status":"ok"}`.
2. Run one test workflow in the n8n UI: it succeeds.
3. `docker logs --since 10m n8n-main 2>&1 | grep -ciE 'ECONNREFUSED|ETIMEDOUT'` prints `0`.
4. `sudo wg show wg0 latest-handshakes` still fresh; on A, replication still `streaming` from `10.77.0.2`.
5. Phone hotspot: `for p in 5432 6379 27017 6432 5434; do nc -4 -z -w 5 <B_PUBLIC_IP> $p && echo "$p OPEN" || echo "$p closed"; done` prints five `closed`; repeat with `nc -6` and `<B_PUBLIC_IPV6>` if B has one.

**Rollback:** `sudo systemctl disable --now sorento-edge.service`, then each `add`/`add6` line
above run by hand as `sudo iptables -D ...` / `sudo ip6tables -D ...` with the same arguments.

**Stop if:** n8n health fails or a workflow errors: roll back at once.

---

## S4. A restart window (THE ONLY STEP WITH APP DOWNTIME)

**Changes:**
- Reload only (no downtime, run first): `max_slot_wal_keep_size = 20GB` (a dead B can no longer
  fill A's disk; A has about 80 GB free), `wal_sender_timeout = 10s`.
- Restart: `wal_log_hints = on` (without it `pg_rewind` refuses, so every rejoin of an old primary
  is a full ~54 GB copy), `archive_mode = on` with `archive_command = 'wal-g wal-push %p'` and
  `archive_timeout = 60` (point-in-time recovery from R2, which does not exist today: G8).
- A's `db` service switches to the repo's image `infra/templates/postgres/Dockerfile`
  (`pgvector/pgvector:pg17`, the same base A runs today, plus WAL-G v3.0.5 with a pinned sha256),
  because the stock image has no `wal-g`. Same data volume, same major version: no data change.

**Downtime:** the db container is recreated once: about 30-90 s with Postgres down (shutdown
checkpoint + start), during which the app answers 503 and workers retry their jobs. Announce 5
minutes. Pick a quiet time.

**Re-seed:** this restart forces NO re-seed of B: B's slot `sorento_crm_replica_slot` holds its
position, B reconnects by itself within seconds after A is back. What S4 changes is the future: until S4
runs, any failover (S6 for real) forces a full re-seed of A afterwards (~54 GB over the tunnel,
roughly 15-30 minutes, B serving meanwhile); after S4, `pg_rewind` is possible for a clean
switchover. A real crash of A still needs the re-seed if `pg_rewind` reports divergence it cannot
fix. Data checksums stay off (enabling them needs a full offline pass: not worth it tonight).

### S4.1 Reload settings (no downtime)

```bash
# THIS CHANGES PROD (node A). Reload only.
cd /opt/sorento-crm2
docker compose exec -T -u postgres db psql -U postgres -d postgres \
  -c "alter system set max_slot_wal_keep_size = '20GB'" \
  -c "alter system set wal_sender_timeout = '10s'" \
  -c "select pg_reload_conf()"
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select name, setting, unit from pg_settings where name in ('max_slot_wal_keep_size','wal_sender_timeout') order by 1"
```

**Expected:** `max_slot_wal_keep_size|20480|MB` and `wal_sender_timeout|10000|ms`. Standard health check green.
**Rollback:** `alter system reset max_slot_wal_keep_size`, `alter system reset wal_sender_timeout`, reload.

### S4.2 Prepare (no downtime): R2 credentials and the image

```bash
# THIS CHANGES PROD (node A files only; nothing restarts).
# Compose reads env_file on EVERY command, so the deploy user must be able to read it
# (otherwise every later release on A fails). <DEPLOY_GROUP> = the group of the user that runs releases.
sudo install -d -m 750 -g <DEPLOY_GROUP> /etc/sorento-ha
sudo sh -c 'umask 027; cat > /etc/sorento-ha/walg.env' <<'EOF'
WALG_S3_PREFIX=s3://<R2_BUCKET>/sorento-crm-pg17
AWS_ENDPOINT=https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_REGION=auto
AWS_S3_FORCE_PATH_STYLE=true
AWS_ACCESS_KEY_ID=<R2_KEY_ID>
AWS_SECRET_ACCESS_KEY=<R2_SECRET>
WALG_COMPRESSION_METHOD=brotli
PGHOST=/var/run/postgresql
EOF
# Build the image from the repo file (copy infra/templates/postgres/Dockerfile from the branch to A first):
sudo install -d /opt/sorento-crm2/infra/templates/postgres
# (scp the Dockerfile from your Mac into that directory, then:)
cd /opt/sorento-crm2 && docker build -t sorento-pg17-walg:07nov infra/templates/postgres
sudo chgrp <DEPLOY_GROUP> /etc/sorento-ha/walg.env && sudo chmod 640 /etc/sorento-ha/walg.env
docker run --rm --env-file /etc/sorento-ha/walg.env --entrypoint wal-g sorento-pg17-walg:07nov st ls
docker run --rm --entrypoint postgres sorento-pg17-walg:07nov --version    # note the 17.x
```

**Version rule:** a standby should never be OLDER than its primary. B runs 17.11. If the last
line prints a minor newer than 17.11, stop and post it (B's replica image is updated first).

Use a R2 API token scoped to that one bucket, Object Read & Write. The last line lists the
bucket's top level (empty is fine). **Stop if** it prints an auth or endpoint error.

Then edit A's `docker-compose.yml` `db:` service (keep a copy: `cp docker-compose.yml docker-compose.yml.bak-07nov`):

```yaml
  db:
    image: sorento-pg17-walg:07nov          # was pgvector/pgvector:pg17
    env_file: /etc/sorento-ha/walg.env      # new line
    # every other line unchanged
```

`docker compose config -q && echo OK` must print `OK`.

### S4.3 The restart (DOWNTIME STARTS)

First (read-only): `docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc "select name, source from pg_settings where name in ('archive_mode','archive_command','wal_log_hints','archive_timeout')"`.
**Stop if** any row says `command line` (the compose `command:` sets it, so `alter system` would be overridden): post it.

```bash
# THIS CHANGES PROD (node A). App downtime about 1-2 minutes.
cd /opt/sorento-crm2
docker compose exec -T -u postgres db psql -U postgres -d postgres \
  -c "alter system set wal_log_hints = on" \
  -c "alter system set archive_mode = on" \
  -c "alter system set archive_command = 'wal-g wal-push %p'" \
  -c "alter system set archive_timeout = 60" \
  -c "checkpoint"
docker compose stop -t 120 db                # clean shutdown (the default 10 s can kill it mid-checkpoint)
docker compose up -d --no-deps db            # recreates db on the new image, same volume
until docker compose exec -T -u postgres db pg_isready -q; do sleep 2; done; echo "db up"
```

### S4.4 Check (right after)

```bash
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select name, setting from pg_settings where name in ('wal_log_hints','archive_mode','archive_command','archive_timeout') order by 1"
docker compose exec -T -u postgres db psql -U postgres -d postgres -c "select pg_switch_wal()"
sleep 20
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select archived_count, failed_count, last_failed_wal from pg_stat_archiver"
```

**Expected:** `archive_command|wal-g wal-push %p`, `archive_mode|on`, `archive_timeout|60`,
`wal_log_hints|on`; then `archived_count >= 1`, `failed_count = 0`, empty `last_failed_wal`.
Then the standard health check (B `streaming` again, `health 200`). Then the first base backup
(runs in the background on A, no downtime, about 20-40 minutes, some disk and CPU load):

```bash
docker compose exec -d -T -u postgres db sh -c 'wal-g backup-push "$PGDATA" > "$PGDATA/../backup-push.log" 2>&1'
# later: docker compose exec -T -u postgres db wal-g backup-list   -> one row
```

**Rollback:**
- Archive failing (`failed_count` growing): WAL piles up on A until it is fixed. Turn it off at
  once, no restart: `alter system set archive_command = '/bin/true'` + `select pg_reload_conf()`.
  Then post the `docker compose logs --tail 50 db` lines that mention `wal-g` (no keys in them).
- Postgres will not start on the new image: `cp docker-compose.yml.bak-07nov docker-compose.yml`,
  `docker compose up -d --no-deps db`. The `alter system` lines stay but are harmless on the
  stock image except `archive_command` (no wal-g there): run the `/bin/true` line above.

**Stop if:** db not up within 3 minutes (rollback), or B not streaming within 2 minutes after it.

---

## S5. B: the CRM app as a STANDBY (8 sub-steps, no user impact)

**Changes:** the CRM app starts on B for the first time, reading B's local replica (read-only:
nothing on B can write, the chatbot sweeper's claim fails on a replica, so B never sends). No
workers on B. B gets no users until S7/S6. A is untouched.

Needs the branch's `scripts/blue_green_deploy.sh` (#2166, `DB_CONTAINER` support): from your Mac,
`git fetch origin claude/ha-cf-failover-wz466v && git show FETCH_HEAD:scripts/blue_green_deploy.sh > /tmp/bgd.sh`,
then `scp /tmp/bgd.sh <B>:/opt/sorento-crm2/scripts/blue_green_deploy.sh`.

**S5.1 Parity (read-only, both nodes):**

```bash
cd /opt/sorento-crm2
sha256sum docker-compose.yml
grep -vE '^(DATABASE_URL|DIRECT_URL|REDIS_URL)=' .env | sort | sha256sum
for k in FIELD_ENCRYPTION_KEY JWT_SECRET NEXTAUTH_SECRET; do printf '%s ' $k; grep "^$k=" .env | sha256sum | cut -c1-12; done
```

**Expected:** both lines and the three short hashes identical on A and B. **Stop if** not: copy
A's file to B (`scp`), never edit secrets by hand.

**S5.2 Recreate the replica container on B's compose network, with a tunnel-only port for A
(replica restarts for a few seconds; it resumes from its slot).** Run **S5.5 first** (it starts
B's Redis, which creates `<B_COMPOSE_NET>`). Same generator as S2.3, with the host unchanged:

```bash
# Generate (changes nothing running). Needs the current infra/scripts/replica-recreate-gen.py at /root/replica-gen.py.
docker network inspect <B_COMPOSE_NET> >/dev/null && echo NET-OK
sudo sh -c 'umask 077; docker inspect sorento_crm_replica | python3 -I /root/replica-gen.py 10.77.0.1 --network <B_COMPOSE_NET> --publish 0.0.0.0:5434:5432'
```

Expected: `NET-OK`; `WARNINGS: 0`; the old and new `primary_conninfo` lines are identical; the NEW
RUN line now has `--network <B_COMPOSE_NET>`, `-p 127.0.0.1:5433:5432/tcp`, `-p 0.0.0.0:5434:5432`,
the same volume, a `POSTGRES_USER=` env line (the release script needs it), a `sha256:` image.

```bash
# THIS CHANGES PROD (node B). Replica down about 10-30 s.
docker rm sorento_crm_replica_old 2>/dev/null; true     # the S2.3 leftover, only once S2.3 has run a day
docker stop -t 60 sorento_crm_replica &&
docker rename sorento_crm_replica sorento_crm_replica_old &&
docker update --restart no sorento_crm_replica_old &&
sudo sh /root/replica-run-new.sh && sleep 15 &&
docker exec sorento_crm_replica psql -U postgres -d postgres -Atc \
  "select pg_is_in_recovery(), status, sender_host from pg_stat_wal_receiver"
```

(If S2.3 is less than a day old, skip the `docker rm` line and rename the S2.3 leftover first:
`docker rename sorento_crm_replica_old sorento_crm_replica_s23`.)

(5434 is closed to everything but `wg0` by S3 and is not in the Hostinger accept list. Binding
`0.0.0.0` instead of `10.77.0.2` keeps the container starting after a reboot even if the tunnel
is not up yet.)

**Check:** B prints `t|streaming|10.77.0.1`; on A, `client_addr = 10.77.0.2`, `streaming`.
**Rollback:** `docker rm -f sorento_crm_replica && docker rename sorento_crm_replica_old sorento_crm_replica && docker update --restart unless-stopped sorento_crm_replica && docker start sorento_crm_replica`.
Afterwards `sudo shred -u /root/replica-run-old.sh /root/replica-run-new.sh`.

**S5.3 B's `.env` (backup first: `cp .env .env.bak-07nov`):**
- `DATABASE_URL` and `DIRECT_URL`: same user, password and database as A, host `sorento_crm_replica`, port `5432`.
- `REDIS_URL=redis://redis:6379/0` (B's own compose Redis).
- Recommended on both nodes (keeps compose identical): add `SKIP_MIGRATIONS: ${SKIP_MIGRATIONS:-0}` to the backend colours' `environment:`. A's behaviour does not change.

**S5.4 B's `.deploy.env`:**

```bash
cd /opt/sorento-crm2 && (umask 077; printf 'DB_CONTAINER=sorento_crm_replica\nDEPLOY_DB_NAME=<APP_DB>\n' >> .deploy.env)
ls -l .deploy.env      # owned by the deploy user, -rw-------
```

**S5.5 Start only B's Redis, remove the stale workers:**

```bash
# THIS CHANGES PROD (node B). NEVER a bare `docker compose up -d` on B: it would start workers and a compose db.
docker compose up -d --no-deps redis
docker compose rm -f worker worker_fast
```

**S5.6 nginx, sudo and registry on B, as on A:** copy A's nginx site config and its TLS
certificate/key for `<CRM_HOST>` (not the upstreams file: the release writes it), the deploy
user's passwordless `sudo` lines for `install` / `nginx -t` / `nginx -s reload`, and
`docker login` to the image registry. `sudo nginx -t` prints `syntax is ok`.

Also on B (reload, no restart), so the slot A will use after a failover cannot fill B's disk:
`docker exec sorento_crm_replica psql -U postgres -d postgres -c "alter system set max_slot_wal_keep_size = '20GB'" -c "select pg_reload_conf()"`.

**S5.7 Dry run (read-only):**

```bash
./scripts/blue_green_deploy.sh --preflight      # every line PASS
./scripts/blue_green_deploy.sh --role           # prints: standby
```

**S5.8 First start on B with A's current release:**

```bash
# THIS CHANGES PROD (node B only).
IMAGE_TAG=<SHA> ./scripts/blue_green_deploy.sh
```

**Expected:** `Node role: standby`, no snapshot, workers untouched, `Deploy complete`. Then on B:

```bash
C=$(cat .active_color); P=8000; [ "$C" = green ] && P=8010
curl -s -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:$P/api/v1/health        # health 200
curl -s -w ' %{http_code}\n' http://127.0.0.1:$P/api/v1/health/role                      # {"status":"standby","role":"standby"} 503
docker compose ps --format '{{.Service}} {{.State}}' | grep -E '^worker' || echo "no workers"  # no workers
```

**Rollback:** `docker compose stop backend_<colour> frontend_<colour> mcp_<colour>`: B is a
replica only again, as before tonight.

**Stop if:** `--role` does not print `standby` (do not run S5.8), or `health/role` answers 200 on B
(B would be writable: stop B's app at once and post).

---

## S6. MANUAL failover (current layout) and tonight's safe drill

### S6.0 Drill tonight (safe: touches neither A nor B's real replica, no user impact)

Rehearses the exact promote on a throwaway COPY of B's replica, and times it. Uses about 60 GB of
B's disk (B has about 270 GB free) and 15-30 minutes of disk load on B only.

```bash
# DRILL on node B. Creates and later deletes a scratch copy; the real replica only serves the copy.
sudo install -d -o 999 -g 999 -m 700 /var/lib/ha-drill
time docker run --rm -u 999:999 --network container:sorento_crm_replica \
  -v /var/lib/ha-drill:/drill pgvector/pgvector:pg17 \
  pg_basebackup -h 127.0.0.1 -p 5432 -U postgres -D /drill/data -X stream -c fast -R
# Start the copy as a standby that follows the real replica (cascading), on a private port:
docker run -d --name ha_drill_pg -u 999:999 --network container:sorento_crm_replica \
  -v /var/lib/ha-drill/data:/var/lib/postgresql/data pgvector/pgvector:pg17 postgres -c port=5499
sleep 20
D='docker exec ha_drill_pg psql -p 5499 -U postgres -d postgres -Atc'
$D "select pg_is_in_recovery(), (select status from pg_stat_wal_receiver)"   # t|streaming
# THE REHEARSED STEP (the same command S6.2 runs on the real replica):
time $D "select pg_promote(true, 60)"                                         # t, in seconds
$D "select pg_is_in_recovery()"                                               # f
$D "create table ha_drill_probe(x int); insert into ha_drill_probe values (1); select count(*) from ha_drill_probe"  # 1
# Clean up:
docker rm -f ha_drill_pg && sudo rm -rf /var/lib/ha-drill
```

If `pg_basebackup` is refused (no `trust` replication row for 127.0.0.1 in the replica's
pg_hba), stop and post the error line: do not edit B's pg_hba for a drill.

Also rehearse (read-only) the decisions S6.1-S6.4 need:
- `ssh <A> true` works; hPanel login works; you know where "Stop" is for A.
- Cloudflare: you can open the DNS record of `<CRM_HOST>` (or, after S7, the load balancer).
- On B: `docker exec sorento_crm_replica psql -U postgres -d postgres -Atc "select now() - pg_last_xact_replay_timestamp()"` is small (seconds while A is busy).

Write down the two `time` values on PR #2166 (copy and promote durations).

### S6.1 When to fail over (real event)

Fail over only if A cannot serve and will not be back soon: A's `/api/v1/health` not 200 from
outside for 5 minutes AND hPanel shows A stopped / unreachable or you cannot SSH to it. A slow or
sick app on a running A is NOT a reason (restart the app on A instead). The exception is A's
database or disk broken while the box still answers SSH (Postgres will not start, disk full or
read-only, data corruption): then fail over with the "A reachable" branch of step 1.

### S6.2 The steps, in this order (downtime: from A's death until step 4, target under 10 minutes)

**1. Fence A (A must never write again until it rejoins as a standby).**
- A reachable over SSH:

  ```bash
  # THIS CHANGES PROD (node A). Stops A's Postgres and marks it a standby, so any later start is read-only.
  cd /opt/sorento-crm2
  docker compose stop -t 5 worker worker_fast
  docker compose stop -t 10 db
  docker compose run --rm --no-deps -T -u postgres --entrypoint sh db -c 'touch "$PGDATA/standby.signal"'
  docker compose ps db --format '{{.State}}'      # exited
  ```

- A unreachable: hPanel **Stop** A (power off) and confirm hPanel shows it stopped before step 2. Do NOT start it again until S6.4. If hPanel offers
  a recovery/rescue boot, use it later to `touch` `standby.signal` inside the data volume before a
  normal boot (UNVERIFIED that Hostinger offers it on this plan).

**2. Promote B.**

```bash
# THIS CHANGES PROD (node B).
docker exec sorento_crm_replica psql -U postgres -d postgres -Atc "select pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()"   # note both
docker exec sorento_crm_replica psql -U postgres -d postgres -Atc "select pg_promote(true, 60)"     # t
docker exec sorento_crm_replica psql -U postgres -d postgres -Atc "select pg_is_in_recovery()"      # f
cd /opt/sorento-crm2; C=$(cat .active_color); P=8000; [ "$C" = green ] && P=8010
curl -s -w ' %{http_code}\n' http://127.0.0.1:$P/api/v1/health/role                                # {"status":"healthy","role":"primary"} 200
```

**3. Start the workers on B (jobs, scheduler, WhatsApp sends now run here).**

```bash
# THIS CHANGES PROD (node B).
IMAGE_TAG=<SHA> docker compose up -d --no-deps worker worker_fast
docker compose logs --since 2m worker | grep -m1 "APScheduler started in worker process"
```

Jobs that were queued in A's Redis at the moment A died are not on B (B has its own Redis): re-run
any import or export a user started in the last minutes.

**4. Point users at B.**
- With S7 done: Cloudflare marks B healthy within about 2 minutes by itself (B now answers 200 on
  `/api/v1/health/role`). Then at once: **disable pool `node-a`** in the load balancer, so A can
  never get users back when it boots.
  Also set the load balancer's **fallback pool to `node-b`** (it is `node-a` in normal times).
- Without S7: Cloudflare DNS, record `<CRM_HOST>`: change the address from `<A_PUBLIC_IP>` to
  `<B_PUBLIC_IP>` (keep the proxy setting as it is).
- Check from outside: `curl -s https://<CRM_HOST>/api/v1/health/role` gives `"role":"primary"`; sign in, open an order, save a small edit.

**5. n8n.** n8n reaches the CRM database through A's pgbouncer (6432). Until crew gives you the
re-point for B, deactivate the n8n workflows that use the CRM database credential (they fail
against a dead A anyway; this keeps them from writing to A if it comes back before S6.4).

**Never:** promote B while A is still writable (step 1 first), or re-enable `node-a` before A is a standby.

### S6.3 Respond.io / external callers

Webhooks hit `<CRM_HOST>`, so they follow step 4. Send one test WhatsApp and see the reply come
from B (`docker compose logs --since 5m backend_$(cat .active_color)` on B shows the webhook).

### S6.4 Rejoin A as B's standby (later, calm; no user impact; about 15-30 minutes copy)

Until S4 has run, this is a full re-seed. A's old data directory is kept aside, not deleted.

On B first (allow A's tunnel address to replicate; B's pg_hba is a copy of A's):

```bash
# THIS CHANGES PROD (node B). Reload only.
docker exec -u postgres sorento_crm_replica sh -c 'f="$PGDATA/pg_hba.conf"; cp -n "$f" "$f.bak-rejoin" &&
  grep -q "^host replication replicator 10.77.0.1/32" "$f" ||
  sed -i "/^host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+all/i host replication replicator 10.77.0.1/32 scram-sha-256" "$f"'
docker exec sorento_crm_replica psql -U postgres -d postgres -Atc "select pg_reload_conf()"
docker exec sorento_crm_replica psql -U postgres -d postgres -Atc "select pg_create_physical_replication_slot('crm_a', true)"
```

On A. Boot A normally only AFTER `node-a` is disabled in Cloudflare (or the DNS record points at
B). If A was powered off while writable, its `db`, app and workers come back up writable on boot
(restart policy). The VERY FIRST command at the first SSH login on A, before anything else:
`cd /opt/sorento-crm2 && docker compose stop worker worker_fast`, so its workers do not send stale
WhatsApp messages or emails. Then the block below. Anything A wrote after B's promotion is
discarded by this rejoin (its old data directory is kept aside for 7 days for inspection).

```bash
# THIS CHANGES PROD (node A). Stop everything on A, then re-seed its data volume from B.
cd /opt/sorento-crm2
docker compose stop
VOL=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Source}}{{end}}{{end}}' \
      "$(docker compose ps -a -q db)")
echo "$VOL"                       # e.g. /var/lib/docker/volumes/<project>_postgres_data/_data
[ -n "$VOL" ] && sudo test -d "$VOL" || { echo "VOL empty: STOP"; false; } &&
TS=$(date -u +%Y%m%dT%H%M%SZ) &&
sudo mv "$VOL" "$VOL.old-$TS" && sudo install -d -o 999 -g 999 -m 700 "$VOL"   # same filesystem: instant
# Type the replicator password at the prompt (not echoed, not in history or `ps`). -R writes it
# into A's primary_conninfo (as B's own conninfo holds it today), so A can log in after restarts.
read -rs -p "replicator password: " PGPASSWORD; echo; export PGPASSWORD
docker compose run --rm --no-deps -T -u postgres -e PGPASSWORD --entrypoint sh db -c \
  'pg_basebackup -d "host=10.77.0.2 port=5434 user=replicator application_name=crm_a" -D "$PGDATA" -X stream -c fast -S crm_a -R'
unset PGPASSWORD
docker compose up -d --no-deps db
docker compose exec -T -u postgres db psql -U postgres -d postgres -Atc \
  "select pg_is_in_recovery(), (select status from pg_stat_wal_receiver)"     # t|streaming
```

If the copy fails: `sudo rm -rf "$VOL" && sudo mv "$VOL.old-$TS" "$VOL"` puts A's old data back
(still fenced: it has `standby.signal`). The replication password now sits in A's
`postgresql.auto.conf` inside its data directory (mode 600, as on B today). Note: WAL-G base
backups copy that file to R2 too (as they would B's), so the R2 bucket token must stay private. On B, `select application_name, state from pg_stat_replication` shows `crm_a|streaming`.

The copy brings B's `postgresql.auto.conf`, so A loses its S4 settings. Re-apply them on A and
restart A's db (A has no users now, so no downtime): S4.1's two `alter system` lines and S4.3's four,
then `docker compose stop -t 120 db && docker compose up -d --no-deps db`, and re-check `t|streaming`.
(On a standby `archive_mode=on` archives nothing; it starts archiving if A is promoted again.)
If A is abandoned instead: on B `select pg_drop_replication_slot('crm_a')`.

Check B's own setting with `docker exec sorento_crm_replica psql -U postgres -d postgres -Atc "show wal_log_hints"`.
If it prints `off`, switching back from B to A later is also a full re-seed until B's Postgres is
restarted with `wal_log_hints = on` (a few seconds of downtime on B, in a window).
Do NOT start A's app or workers: A is a standby now (`.active_color` services stay stopped until
the two-node release runs it as a standby).

A then stays a standby of B. Users stay on B. Switching back to A is a planned switchover in a
window (the same steps with the roles swapped), not part of tonight.

---

## S7. Cloudflare Load Balancing (dashboard, no downtime if done in this order)

Cloudflare Load Balancing is a paid add-on on the zone (UNVERIFIED price on this account). Check
first: Traffic > Load Balancing is available for the zone.

1. **Monitor** (Traffic > Load Balancing > Manage Monitors > Create):
   type HTTPS, path `/api/v1/health/role`, port 443, expected code `200`, header `Host: <CRM_HOST>`,
   interval 60 s, timeout 5 s, retries 1, follow redirects off, allow insecure off.
2. **Pools** (Manage Pools > Create), one endpoint each, monitor from step 1, health-check region
   Southeast Asia:
   - `node-a`: endpoint `<A_PUBLIC_IP>`, Host header `<CRM_HOST>`, minimum healthy 1.
   - `node-b`: endpoint `<B_PUBLIC_IP>`, Host header `<CRM_HOST>`, minimum healthy 1.
   - Notification: email on health change for both pools.
3. **Wait** until `node-a` shows Healthy and `node-b` shows Unhealthy (correct: B is a standby and
   answers 503). **Stop if** `node-a` is not Healthy: fix that first. Usual causes: the Host
   header, A's nginx not routing `/api/v1/health/role`, or a Cloudflare Origin CA certificate on
   the origin (not publicly trusted: the monitor then needs "allow insecure" on; it affects the
   health probe only).
4. **Load balancer** (Create Load Balancer): hostname `<CRM_HOST>`, proxied (orange) if the DNS
   record is proxied today, session affinity off, steering off (failover order), default pools in
   order `node-a`, `node-b`, **fallback pool `node-a`** (when Cloudflare sees no healthy pool, users
   go to the only node that can be writable, as today; a fallback of `node-b` would send everyone
   to the read-only standby on a single missed health check of A). Save. Cloudflare serves the load balancer
   in front of the existing DNS record of the same name; leave the DNS record in place (it is the
   rollback).
5. **Check:** `curl -s https://<CRM_HOST>/api/v1/health/role` gives `"role":"primary"` (from A);
   sign in works; the load balancer analytics show requests to `node-a`.

**Rollback:** disable (not delete) the load balancer: Cloudflare answers from the DNS record again.

**What S7 does and does not do:** it sends users to whichever node answers 200 on the role check.
It never promotes or fences: that stays manual (S6) until the controller is armed after the
section 3 PR. Because a booting A with its old data would answer 200 again, S6.2 step 4 (disable
`node-a`) is part of every failover.

---

## After tonight (crew relays; owner decides)

1. Merge #2166 (two-node release, `DB_CONTAINER`). Then add GitHub secrets `SSH_HOST_B` and
   `SSH_KNOWN_HOSTS` (both hosts' keys: `ssh-keyscan` output checked against `ssh-keygen -lf
   /etc/ssh/ssh_host_ed25519_key.pub` on each box). From then on every release deploys A, then B.
2. Merge the section 3 PR (R2 sync record, adopted names). Drill it. Only then arm the controller
   and role watcher (`CONTROLLER_ARMED=yes`, `ROLE_WATCHER_ARMED=yes`) and `SYNC_MODE=on_commit`.
