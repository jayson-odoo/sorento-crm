# HA failover runbook (Tier 1, Patroni + etcd)

Plan: `documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md`. Templates: `infra/`. This file
grows with the drills (plan section 12); today it holds the witness sections. Placeholders only:
no addresses, hostnames or secrets here.

## The witness today: the shared-service box

Owner ruling 27 Oct: the third etcd voter runs on the shared-service box for now.

- Runs: `infra/templates/witness/compose.witness.yml` (etcd only) in its own directory, next to
  that box's own stack, joined to the WireGuard mesh as the third peer.
- Firewall: `infra/templates/host/docker-user.nft` on that box too, with every one of its app
  networks in `<N8N_SUBNETS>`, so none of its containers can reach 2379/2380.
- Checks: `ETCD_ONLY=1 PROJECT_DIR=<witness dir> COMPOSE_FILES="-f compose.witness.yml"
  infra/scripts/ha-checks.sh` every 5 minutes, pinging its own Healthchecks check.
- **Known limitation**: the shared-service box is in MALAYSIA, like the KL CRM box (owner, 27 Oct).
  A Malaysia-wide outage takes out 2 of the 3 voters at once, so India will NOT take over
  automatically: it waits as a healthy replica, every node's `/api/v1/health/role` answers 503,
  and the CRM is down until someone runs the forced promotion below. The same happens if KL dies
  while the shared-service box is mid-deploy or rebooting (then it resolves by itself once that
  box is back). Moving the witness off-region (last section) removes both. Full case table: plan
  section 10, "Known limitation: the witness is in Malaysia".

## Forced promotion when Malaysia is down

Only when KL AND the witness are unreachable and India is a healthy replica. `patronictl
failover` does not work here: it writes to etcd, and etcd has no majority.

1. Confirm: `scripts/ops/cf-proxy.py status` (not a Cloudflare outage), the KL and witness boxes
   unreachable from India over the tunnel and from outside, Hostinger status page.
2. Fence first. In Cloudflare, disable the `kl` pool (so KL cannot take traffic when it comes
   back). In hPanel, Stop the KL VPS and the shared-service box's witness if the panel still
   answers. If it does not: on India, firewall the tunnel to KL and the witness
   (`nft add rule inet sorento_ha_guard input ip saddr { $KL_WG_IP, $WITNESS_WG_IP } drop` and
   the same in `forward`), so they cannot rejoin when the network returns.
3. On India: stop etcd, then start it ONCE with `--force-new-cluster` (same data dir; it becomes a
   one-member cluster keeping the data), then normally. `etcdctl member list` shows only `in`.
4. Patroni on India sees the old leader key expire and promotes itself (or
   `patronictl failover --candidate in --force` now that etcd answers). Check
   `curl -s localhost:8008/primary` is 200, then `/api/v1/health/role` 200; the role watcher
   starts workers; the LB moves traffic to the `in` pool.
5. When Malaysia is back: keep the KL box and the witness FENCED. Wipe KL's and the witness's etcd
   data dirs, re-add them to India's cluster one at a time (`etcdctl member add ... --learner`,
   start with `ETCD_INITIAL_CLUSTER_STATE=existing`, `member promote`), then start KL's Patroni:
   it rejoins as a replica (`pg_rewind` or re-seed). Lift the fence and re-enable the `kl` pool
   only when `patronictl list` shows exactly one leader (India). The 04:00 switchback then moves
   the primary home after 24 h healthy.

Data: writes that reached KL but not India before the outage (normally under a second) are lost,
and are discarded when KL is rewound.

## Move the witness

Config only, no downtime, quorum kept the whole time (etcd learner: the new member does not
vote until it is promoted). Example: shared-service box (`witness-ss`) to a Hetzner EU VPS
(`witness-hz`).

1. New box: WireGuard peer added on it, on KL and on India (the old witness stays for now);
   `docker-user.nft` loaded.
2. Certs, minted OFFLINE with the private CA (`ca.key` never on a box): `peer` and `server`
   with the new `<NEW_WITNESS_WG_IP>` in the SAN, plus `healthcheck`. Copy to `/etc/etcd/pki`.
3. On any current member:
   `etcdctl member add witness-hz --learner --peer-urls=https://<NEW_WITNESS_WG_IP>:2380`
   It prints the `ETCD_INITIAL_CLUSTER` line for the new member.
4. On the new box: `/etc/sorento-ha/ha-members.env` with the new `WITNESS_NAME` /
   `WITNESS_WG_IP`, `etcd.env` with `ETCD_NAME=witness-hz`, the printed
   `ETCD_INITIAL_CLUSTER` and `ETCD_INITIAL_CLUSTER_STATE=existing`; then
   `docker compose -f compose.witness.yml up -d`.
5. Wait until `etcdctl endpoint status --cluster -w table` shows the learner caught up, then
   `etcdctl member promote <new id>`. Four voters now (quorum 3); set `ETCD_MEMBERS=4` on the
   ha-checks crons for these minutes or expect one alert.
6. `etcdctl member remove <witness-ss id>`, then on the shared-service box
   `docker compose -f compose.witness.yml down` and remove its WireGuard peer and certs.
7. On KL and India: edit `/etc/sorento-ha/ha-members.env` (`WITNESS_NAME`, `WITNESS_WG_IP`,
   `PATRONI_ETCD3_HOSTS`) and `/etc/sorento-ha/ha-members.nft`, reload nft
   (`nft -f docker-user.nft`). Patroni discovers etcd members from the cluster itself, so no
   Patroni restart is needed (the new env applies at its next planned restart; unverified, the
   step-8 check proves it).
8. Check: `patronictl list` shows the leader and the replica unchanged; `etcdctl member list`
   shows kl, in, witness-hz; `ha-checks.sh` green on all three; then plan drill 5 (stop the new
   witness: nothing changes, an alert fires).
