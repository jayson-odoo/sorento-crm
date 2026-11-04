# UAC: HA failover with Cloudflare LB as witness (HA-CF-FAILOVER)

Plan: `PLAN-ha-cf-failover-04nov.md`. Draft, final after the owner answers the card.

1. A release deploys the same image SHA to both nodes, the primary first; migrations run only on the primary; the standby's backend starts with `SKIP_MIGRATIONS=1`.
2. At every moment at most one Postgres accepts writes. Drill: kill A, cut the A-B link only, Cloudflare API down, A's controller hung; in none of them do two nodes report `pg_is_in_recovery() = false` at the same time.
3. Node B promotes only when Cloudflare positively reports A unhealthy for `PROMOTE_AFTER` AND B has no WAL stream AND B cannot connect to A's Postgres. An UNKNOWN Cloudflare answer never promotes.
4. Node A fences itself (workers stopped, Postgres stopped) when for `FENCE_AFTER` Cloudflare has not reported it healthy AND B is not streaming from it; `FENCE_AFTER` < `PROMOTE_AFTER` by at least 180 s.
5. A returning old primary never starts writable: it rewinds (or re-seeds, per Q4) and follows the new primary; `/api/v1/health/role` answers 503 on it throughout.
6. Workers, the scheduler and every sender run only on the primary; within 10 s of a promotion they start on the new primary; on the standby `worker` and `worker_fast` are never running for more than one watcher tick.
7. Uploads are readable from both nodes with no copy step (S3/R2 objects).
8. The env-hash check reports any env file whose content differs between the nodes, naming the file, never a value.
9. Cloudflare LB: steering off (failover order), monitor `GET /api/v1/health/role` expecting 200; after a drill the LB answers with node B's address and does not move back when A returns.
10. Measured failover time in the drill is recorded in the plan (expected 8-11 min on 60 s checks).
