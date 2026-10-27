# infra/ (templates for the private infra repo)

HA-TIER1-N8N-BOX, plan `documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md`.

These files are TEMPLATES. Prod compose, nginx and Caddy are not in any git repo today (plan
section 1, "Still open"); they belong in a PRIVATE repo, proposed name `sorento-infra`. When that
repo exists, this directory moves there and is deleted here. Nothing in this directory is read by
the app, the CI or `scripts/blue_green_deploy.sh`.

Rules: placeholders only (`<PRIMARY_WG_IP>`, `<STANDBY_WG_IP>`, `<CRM_PUBLIC_HOST>`,
`<R2_BUCKET>`). No addresses, private hostnames, passwords or keys, here or in the private repo:
secrets stay in env files on the boxes.

## Proposed layout of `sorento-infra`

```
sorento-infra/
  README.md                       what runs where, how to apply
  nodes/
    primary/                      CRM box (KVM 4)
      docker-compose.yml          captured from the box (backend_blue/green, frontend, worker,
                                  worker_fast, db, redis, mcp, pgbouncer)
      .deploy.env.example         names only, no values
      nginx/  caddy/              captured from the box
      postgres/primary.conf       from templates/postgres/primary.conf
      postgres/pg_hba.conf        from templates/postgres/pg_hba.conf.template
    standby/                      n8n box (KVM 8)
      docker-compose.yml          same services as primary
      compose.standby.yml         from templates/compose.standby.yml
      postgres/standby.conf       from templates/postgres/standby.conf
      n8n/                        the existing n8n compose, unchanged
  wireguard/wg0.conf.template
  scripts/promote-standby.sh
  runbooks/failover.md            plan section 2 "Failover", "Failback", "Drills"
```

## Files here

| File | What |
|---|---|
| `templates/postgres/primary.conf` | WAL level, archiving with WAL-G, slot cap, `archive_timeout` |
| `templates/postgres/standby.conf` | hot standby settings, `primary_conninfo` over the tunnel |
| `templates/postgres/pg_hba.conf.template` | replication only from the standby's tunnel address |
| `templates/walg.env.example` | WAL-G env names for Cloudflare R2 (values on the box only) |
| `templates/compose.standby.yml` | standby override: workers + scheduler behind profile `promoted` |
| `templates/wireguard/wg0.conf.template` | two-node tunnel, if the tailnet is not used |
| `scripts/promote-standby.sh` | the one promotion command (human runs it after fencing) |

The app side is already in this repo: `GET /api/v1/health/role` (Cloudflare LB monitor) and the
scheduler leader guard (`sorento_crm_backend/app/scheduler/leader.py`, env
`SCHEDULER_LEADER_DATABASE_URL` = a DIRECT Postgres URL, not pgbouncer).
