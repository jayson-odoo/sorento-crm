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
- **Known limit**: if the shared-service box sits in the same region or data centre as the KL
  CRM box, a KL region outage takes out 2 of the 3 voters at once and India will NOT take over
  automatically; it waits as a healthy replica until a human forces the promotion
  (`patronictl failover --candidate in --force`, after confirming KL is really down). Its own
  deploys and reboots also pause automatic failover while they last. Moving the witness (below)
  removes both.

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
