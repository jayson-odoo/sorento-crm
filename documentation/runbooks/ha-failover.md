# HA failover runbook (Tier 1, Patroni + etcd)

Plan: `documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md`. Templates: `infra/`. This file
grows with the drills (plan section 12); today it holds the witness sections. Placeholders only:
no addresses, hostnames or secrets here.

## Where the three voters are today

Owner ruling 27 Oct about 23:55: everything stays in Malaysia for now.

- Node A: the CRM box (primary today).
- Node B: the n8n KVM 8, also in Malaysia (standby; it keeps running n8n).
- Witness: the shared-service box (`chat.foundryx.my`), Malaysia: etcd only,
  `infra/templates/witness/compose.witness.yml` in its own directory next to that box's own
  stack, joined to the WireGuard mesh; `infra/templates/host/docker-user.nft` loaded there too,
  with every one of its app networks in `<N8N_SUBNETS>`; checks with `ETCD_ONLY=1 PROJECT_DIR=<witness
  dir> COMPOSE_FILES="-f compose.witness.yml" infra/scripts/ha-checks.sh` every 5 minutes.

**Known limitation**: all three are in Malaysia (provider not confirmed; hPanel suggests Hostinger
for the two VPSs). Any ONE box failing is handled automatically. A Malaysia-wide or provider-wide
outage takes all three down together: nothing is left to fail over to, and the CRM is down until
Malaysia returns, or until the disaster restore below. Plan section 10 has the case table.

## Forced promotion when two voters are down

When the primary AND the witness are both down (for example node A dies while the shared-service
box is mid-deploy) and the other node is a healthy replica, Patroni may not promote it: there is no
majority. If waiting for the witness to return is not acceptable:

1. Confirm both are really down (`scripts/ops/cf-proxy.py status` rules out Cloudflare; the boxes
   do not answer over the tunnel or from outside).
2. Fence first. In Cloudflare, disable the dead primary's pool. In hPanel, Stop the dead primary
   if the panel answers; if not, on the surviving node firewall the tunnel to it and to the
   witness (`nft add rule inet sorento_ha_guard input ip saddr { <DEAD_NODE_WG_IP>,
   <WITNESS_WG_IP> } drop`, and the same in `forward`), so they cannot rejoin the old cluster.
3. On the surviving node: stop etcd, start it ONCE with `--force-new-cluster` (same data dir;
   it becomes a one-member cluster keeping the data), then normally.
4. Patroni there promotes itself once the old leader key expires (or `patronictl failover
   --candidate <survivor> --force`, which works now that etcd answers). Check
   `curl -s localhost:8008/primary` is 200 and `/api/v1/health/role` is 200.
5. When the others return: keep them fenced; wipe their etcd data dirs; re-add them one at a time
   (`etcdctl member add ... --learner`, start with `ETCD_INITIAL_CLUSTER_STATE=existing`,
   `member promote`); start the old primary's Patroni (it rejoins as a replica via `pg_rewind` or
   re-seed). Lift the fence and re-enable its pool only when `patronictl list` shows exactly one
   leader.

Writes that reached the old primary but not the survivor (normally under a second) are lost.

## Disaster restore (Malaysia-wide outage)

All three voters are down; there is no standby to promote. Only if the outage is long enough to
justify it (owner's call): provision a VPS in another region from the infra repo, restore the
newest WAL-G base backup plus WAL from R2 (`wal-g backup-fetch`, then recovery to the latest
point: RPO about 60 s, `archive_timeout`), start it as a single-node Patroni cluster with its own
etcd, point Cloudflare at it (`scripts/ops/cf-proxy.py` or the LB pool), and add its egress
address to the OpenAI allowlist. Hours, not minutes. When Malaysia returns, the old nodes are
rebuilt as replicas of the new primary (fenced first, as above).

## Move the witness

Config only, no downtime, quorum kept the whole time (etcd learner: the new member does not
vote until it is promoted). This is how the witness leaves Malaysia later; the standby can move
region the same way (Hostinger "Change location", then Patroni seeds a fresh replica; plan
section 3). Example: shared-service box (`witness-ss`) to a Hetzner EU VPS
(`witness-hz`).

1. New box: WireGuard peer added on it, on node A and node B (the old witness stays for now);
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
7. On node A and node B: edit `/etc/sorento-ha/ha-members.env` (`WITNESS_NAME`, `WITNESS_WG_IP`,
   `PATRONI_ETCD3_HOSTS`) and `/etc/sorento-ha/ha-members.nft`, reload nft
   (`nft -f docker-user.nft`). Patroni discovers etcd members from the cluster itself, so no
   Patroni restart is needed (the new env applies at its next planned restart; unverified, the
   step-8 check proves it).
8. Check: `patronictl list` shows the leader and the replica unchanged; `etcdctl member list`
   shows crm-a, crm-b, witness-hz; `ha-checks.sh` green on all three; then plan drill 5 (stop the new
   witness: nothing changes, an alert fires).
