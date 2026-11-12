# infra/ (templates for the private infra repo)

HA-CF-FAILOVER, plan `documentation/plans/infra/PLAN-ha-cf-failover-04nov.md` (replaces the
Patroni/etcd design of `PLAN-ha-tier1-n8n-box-27oct.md` and `PLAN-n8n-decom-ha-01nov.md` section 5:
two nodes, no witness server, Cloudflare Load Balancing as the third vote).

These files are TEMPLATES. Prod compose, nginx and Caddy are not in any git repo today; they belong
in a PRIVATE repo, proposed name `sorento-infra`. When that repo exists, this directory moves there
and is deleted here. Nothing in this directory is read by the app or the CI.

Rules: placeholders only (`<PEER_WG_IP>`, `<CF_ACCOUNT_ID>`, `<R2_BUCKET>`, ...). No addresses,
private hostnames, passwords or keys, here or in the private repo: secrets stay in files on the boxes.

## Files here

| File | What |
|---|---|
| `scripts/cf_failover.py` | the failover controller: pure `decide()` (rules P1-P4, S1-S3, D1-D2) + the loop (Cloudflare pool health API, watchdog, state file, alerts) |
| `scripts/ha-pg.sh` | the only thing that touches Postgres: observe, role, fence, promote, start-standby, rejoin (pg_rewind, else re-seed), set-sync, prune |
| `scripts/role-watcher.sh` | workers + scheduler only where the local Postgres is primary; `--no-recreate`, tag from `.ha-image-tag`, skips while the deploy lock is held |
| `scripts/ha-checks.sh` | disk, exactly one primary, NTP clock, shared config identical on both nodes (hashes), standby lag, WAL archive, base backup age, to Healthchecks.io |
| `templates/compose.ha.yml` | HA override for both nodes: plain Postgres `db` (`restart: "no"`), workers behind profile `promoted`, `SKIP_MIGRATIONS`, autoheal |
| `templates/postgres/Dockerfile` | Postgres 17 + pgvector + WAL-G |
| `templates/postgres/pg_hba.ha.conf` | the replication lines (peer's private address only) |
| `templates/ha-pg.env.example` | `/etc/sorento-ha/ha-pg.env`: per-node names, commands, Cloudflare pools, timings |
| `templates/systemd/cf-failover.service`, `role-watcher.service` | the two services |
| `templates/host/README.md` | softdog for the controller's watchdog |
| `templates/walg.env.example` | WAL-G env names for Cloudflare R2 |
| `templates/wireguard/wg0.conf.template` | two-node private link, if the tailnet is not used |
| `rehearsal/cf_drill.py` | the drill: two throwaway Postgres 17 containers, a fake Cloudflare API, the real controller on each |
| `tests/` | `python3 -m pytest infra/tests -q` (controller decisions + a two-node world model; shell tests with fakes) |

The app side is in this repo: `GET /api/v1/health/role` (the Cloudflare LB monitor) and the
scheduler leader guard (`sorento_crm_backend/app/scheduler/leader.py`, env
`SCHEDULER_LEADER_DATABASE_URL` = a DIRECT Postgres URL, not pgbouncer).
