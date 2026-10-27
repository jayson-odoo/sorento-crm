# infra/ (templates for the private infra repo)

HA-TIER1-N8N-BOX, plan `documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md`.

These files are TEMPLATES. Prod compose, nginx and Caddy are not in any git repo today (plan
section 1, "Still open"); they belong in a PRIVATE repo, proposed name `sorento-infra`. When that
repo exists, this directory moves there and is deleted here. Nothing in this directory is read by
the app, the CI or `scripts/blue_green_deploy.sh`.

Rules: placeholders only (`<KL_WG_IP>`, `<IN_WG_IP>`, `<WITNESS_WG_IP>`, `<CRM_PUBLIC_HOST>`,
`<R2_BUCKET>`). No addresses, private hostnames, passwords or keys, here or in the private repo:
secrets stay in env files on the boxes.

## Proposed layout of `sorento-infra`

```
sorento-infra/
  README.md                       what runs where, how to apply
  nodes/
    crm/                          the SAME files on both CRM nodes (KL and IN); per-node env only
      docker-compose.yml          captured from the KL box (backend_blue/green, frontend, worker,
                                  worker_fast, db, redis, mcp, pgbouncer)
      compose.ha.yml              from templates/compose.ha.yml
      patroni.yml                 from templates/patroni/patroni.yml
      patroni/Dockerfile          pgvector pg17 + Patroni + WAL-G
      etcd.env.example            from templates/etcd/etcd.env.template
      walg.env.example            from templates/walg.env.example
      .deploy.env.example         names only, no values
      nginx/  caddy/              captured from the box
      systemd/role-watcher.service
    in-extra/                     India box only
      haproxy.cfg                 n8n + MCP follow the primary
      n8n/                        the existing n8n compose, unchanged
    witness/                      shared-service box today, Hetzner EU later (config only)
      compose.witness.yml         etcd only
      etcd.env.example
  wireguard/wg0.conf.template
  scripts/role-watcher.sh  scripts/ha-checks.sh
  runbooks/ha-failover.md         documentation/runbooks/ha-failover.md (witness today, move the witness), then drills
```

## Files here

| File | What |
|---|---|
| `templates/patroni/patroni.yml` | Patroni: TTL/loop timings, `maximum_lag_on_failover`, rewind + re-seed, failsafe, watchdog, archiving, pg_hba |
| `templates/patroni/Dockerfile` | Postgres 17 + pgvector + Patroni + WAL-G image |
| `templates/etcd/etcd.env.template` | etcd member env for the three voters, WAN timeouts |
| `templates/compose.ha.yml` | HA override for both CRM nodes: Patroni `db`, workers behind profile `promoted`, `SKIP_MIGRATIONS`, autoheal, etcd |
| `templates/haproxy/haproxy.cfg` | India box: n8n API and DB traffic to whichever node leads |
| `templates/ha-members.env.example` | the ONE place the three voters are named (witness movable by config) |
| `templates/host/ha-members.nft` | the same addresses for the container firewall |
| `templates/host/docker-user.nft` | container firewall: n8n / shared-service apps cannot reach the control plane |
| `templates/witness/compose.witness.yml` | the witness: etcd only (shared-service box today) |
| `scripts/switchback.sh` | automatic move of the primary back to KL (04:00 MYT, 24 h healthy) |
| `templates/walg.env.example` | WAL-G env names for Cloudflare R2 (values on the box only) |
| `templates/wireguard/wg0.conf.template` | three-member mesh, if the tailnet is not used |
| `templates/systemd/role-watcher.service` | runs the role watcher |
| `scripts/role-watcher.sh` | workers + scheduler only on the Patroni leader |
| `scripts/ha-checks.sh` | disk / etcd / lag / archive / WAL / backup-age checks to Healthchecks.io, prunes old dumps |
| `tests/test_ha_scripts.py` | shell tests with fake curl/docker/etcdctl/df: `python3 -m pytest infra/tests -q` |

The app side is already in this repo: `GET /api/v1/health/role` (Cloudflare LB monitor and the
HAProxy check) and the scheduler leader guard (`sorento_crm_backend/app/scheduler/leader.py`, env
`SCHEDULER_LEADER_DATABASE_URL` = a DIRECT Postgres URL, not pgbouncer).
