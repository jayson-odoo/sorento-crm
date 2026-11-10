# UAC: HA failover with Cloudflare LB as witness (HA-CF-FAILOVER)

Plan: `PLAN-ha-cf-failover-04nov.md` (rules P1-P4, S1-S3, D1-D2 in section 3). Owner answers in
its section 8. Every criterion names how it is proven: unit (`infra/tests/test_cf_failover.py`,
pure decisions), shell (`infra/tests/test_ha_scripts.py`, fake binaries), drill
(`infra/rehearsal/cf_drill.py`, two throwaway Postgres 17 containers + a fake Cloudflare API).

## Never two writers
1. A standby promotes only when, continuously for `PROMOTE_AFTER`, Cloudflare reports the peer UNHEALTHY, it is not streaming, and the peer's Postgres is unreachable. Any one missing: no promotion. (unit, drill: kill A)
2. An UNKNOWN Cloudflare answer (API down, error) never counts toward promotion. (unit, drill: CF API down)
3. A standby further than `MAX_LAG` behind the peer's last seen position never promotes, and alerts. (unit)
4. A primary fences itself (Postgres stopped first, `standby.signal` written, then the workers; at most 60 s) when for `FENCE_AFTER` Cloudflare has not reported it healthy AND the peer has not streamed from it. (unit, drill: isolate A). A fence that does not take is retried every tick and the watchdog is no longer petted; neither a failed fence nor a `down` reading renews the lease. (unit, loop test)
5. The controller refuses to start when `PROMOTE_AFTER < FENCE_AFTER + FENCE_MARGIN`. (unit)
6. A Postgres that is down and not fenced (boot, crash, watchdog reboot) is started as a standby, never writable. (unit, drill)
7. Link cut alone (Cloudflare sees A healthy): A keeps writing, B never promotes. (unit, drill)
8. In every drill, at no sample do both nodes report `pg_is_in_recovery() = false`. (drill)

## Self-maintaining (owner: automatic)
9. Q3: a primary Cloudflare reports UNHEALTHY for `APP_SICK_AFTER` (default 900 s, config) while the peer streams fences itself and alerts; the standby then promotes by rule 1. At most one such fence per node per `APP_SICK_COOLDOWN`. (unit, drill)
10. Q4: a node whose peer is primary and which has not streamed from it for `REJOIN_AFTER` rewinds onto it; if the rewind fails it moves its data directory aside (kept `RESEED_KEEP_DAYS` = 7, then pruned) and re-seeds with `pg_basebackup`; an alert goes out. (unit, drill: A returns after failover)
11. A fenced node starts again as a standby after `FENCE_HOLD` when the peer is a standby, or the peer is unreachable and Cloudflare-unhealthy for `PROMOTE_AFTER`; immediately rejoins when the peer is primary. (unit)
12. Both nodes standby and reachable for `BOTH_STANDBY_AFTER`: exactly the one with the higher WAL position (tie: lower name) promotes. (unit, drill: both restart)
13. Q5: with `SYNC_MODE=remote_write` the primary sets `synchronous_standby_names` to the peer while it streams and to empty the tick it stops; with `SYNC_MODE=off` it keeps it empty. (unit, drill)
14. Q1: the Cloudflare interval and failure count are config values; `FENCE_AFTER` and `PROMOTE_AFTER` derive from them unless set. (unit)

## Same code, same config on both nodes
15. A release deploys the same image SHA to both nodes, the primary first; migrations run only on the primary; the standby's deploy runs with `SKIP_MIGRATIONS=1`, takes no snapshot and touches no workers, and waits until the replicated `alembic_version` holds the new image's heads before switching colour. (shell)
16. The deploy finds each host's role itself; with no second host configured the release behaves exactly as today. (shell)
17. Workers and the scheduler run only where the local Postgres is primary (role watcher reads the local role, no Patroni). (shell)
18. `ha-checks.sh` alerts on: two primaries or none, no replica streaming, lag, stale/failing WAL archive, clock not NTP-synced, env files that differ between nodes (names only, never values). (shell)

## Outside the repo (owner, reviewed commands)
19. Cloudflare LB: steering off, pools node-a / node-b, monitor `GET /api/v1/health/role` expecting 200 with the public Host header, DNS-only TTL 30 s. After a drill the LB answers with node B and does not move back when A returns.
20. The measured failover time of the prod drill is recorded in the plan (expected 8-11 min on 60 s checks).
