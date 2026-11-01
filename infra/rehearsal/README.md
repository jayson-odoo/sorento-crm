# H4a rehearsal: adopt a running Postgres into Patroni

Rehearses, on a throwaway Docker host, what the owner does on prod in H4: a RUNNING standalone
`pgvector/pgvector:pg17` becomes a one-member Patroni cluster (etcd with node A + witness,
WAL-G archiving on). Plan: `documentation/plans/infra/PLAN-n8n-decom-ha-01nov.md` section 5,
row H4a. Synthetic data only; nothing here reads a real database.

## Run

```bash
DOCKER_CONTEXT=<a context whose name contains ha-rehearsal> infra/rehearsal/run.sh      # up
DOCKER_CONTEXT=<same> infra/rehearsal/run.sh down                                         # remove everything
```

The script refuses without such a context, refuses `colima-ci` and `default`, and refuses if
`DOCKER_HOST` is set. Every container, volume and the network carry the `ha-rehearsal` label or
prefix; `down` removes them, the built image and the temp dir (certs, env files, passwords).
Needs `openssl` and `python3` on the machine running the script, and a Docker host that can pull
images and download WAL-G and Patroni during the build. Exit code is non-zero if any check fails.

## What runs, in order

1. Standalone Postgres 17 with `shared_preload_libraries=pg_stat_statements`, the `vector`
   extension, `items` (5000 rows, vector column, hnsw index), `plain_t` (500 rows), a `probe`
   table, and the `replicator` and `rewinder` roles with the GRANTs from v2 step 6.
2. etcd: members `crm-a` and `witness` (the phase A shape; node B is not listed), mTLS
   from a throwaway CA, users and roles from `etcd.env.template`, then `auth enable`.
3. Cut-over: clean stop of the standalone, then the Patroni image (built from the template
   Dockerfile) on the SAME volume, `data_dir` and preload libraries read from the standalone.
   The outage is timed from the stop to the first successful write.

## Checks (each prints PASS or FAIL with evidence)

| Check | Proves |
|---|---|
| outage | the 1-2 minute window holds (limit `OUTAGE_MAX_S`, default 180), and the standalone left a clean shutdown state |
| row counts | the adopted cluster is the old data, not a fresh initdb (the wrong `data_dir` failure) |
| one leader | `patronictl list` shows exactly one Leader |
| not in recovery | `pg_is_in_recovery()` is false |
| WAL archiving | `archived_count` rises after a WAL switch, `failed_count` is 0 |
| wal-g backup-push | a base backup is written and listed |
| PITR | base backup + WAL restored into a throwaway container to a noted time gives the row count at that time, not the later one |
| crash restart | `kill -9` of the postmaster: Patroni restarts it, writes work, new postmaster pid |
| etcd loss (failsafe) | with one of the two running etcd members stopped (quorum lost) for 70 s, `/primary` stays 200 and writes work |
| ha-checks.sh | `EXPECT_REPLICAS=0 ETCD_MEMBERS=2` run against the rehearsal through a small docker shim |

## Where it diverges from the templates

The rehearsal renders the templates and overrides nothing else. Every override, all rehearsal-only:

- Names, not WireGuard addresses: members are container names on one Docker network. The
  `<*_WG_IP>` placeholders become those names (etcd) or `127.0.0.1` (Patroni allowlist, `pg_hba`);
  `<WITNESS_NAME>` becomes `witness`, `ETCD_NAME` is set per member, `<HEALTHCHECK_PASSWORD>` and
  the other secrets are throwaway.
- `ETCD_LISTEN_PEER_URLS` and `ETCD_LISTEN_CLIENT_URLS` are `0.0.0.0` (etcd binds IPs only, and
  container names are not IPs).
- One shared server cert and one shared peer cert cover all member names; prod mints one per member.
- WAL-G writes to a volume (`WALG_FILE_PREFIX`), not R2; the libsodium key is a throwaway with the
  hex transform added. Compression and `PGHOST` come from the template.
- App and pgbouncer `pg_hba` users and the compose subnet are placeholders; nothing connects as them.
- `/dev/watchdog` is not mapped (the watchdog stays in `automatic`, so a missing device is a log line).
- `ha-checks.sh` runs through a docker shim, with `HC_URL` empty, a missing snapshot dir, and disk
  alerts off (they would measure the host disk).
- Containers run `linux/amd64` (the Dockerfile fetches an amd64 WAL-G); slow under emulation.
- Docker bind mounts must be visible to the Docker host, so the temp dir is under `$HOME`.
- The Dockerfile builds with its own pinned versions and checksum; nothing is overridden.

## Findings about the templates (all fixed in the templates; the run proves the fixes)

- `etcd.env.template` had no `ETCDCTL_ENDPOINTS`; etcdctl defaults to plain http, so the TLS-only
  client port broke every etcdctl call. The template now names `https://127.0.0.1:2379`.
- A member that is LISTED in `ETCD_INITIAL_CLUSTER` but never started keeps the etcd cluster
  version at 3.0.0; Patroni 4.0.5 then calls the removed `/v3alpha` API and gets 404 forever
  Phase A bootstraps etcd with node A + witness only (the template now lists just those two); node B
  joins at H6 with `etcdctl member add --learner`, then `member promote`.
- Patroni's etcd client cert must have no CN: the HTTP gateway rejects a client cert with a CN
  ("CommonName ... will be ignored"). Patroni authenticates with the `patroni` etcd user password.
- `etcdctl auth status` is refused ("permission denied") for the role-less healthcheck user, so
  `ha-checks.sh` reported "etcd auth not enabled" on a healthy cluster. It now reads "permission
  denied" (the exact text "etcdserver: permission denied") as auth on; a test covers it.
- `wal-g` without `PGHOST` fell back to TCP 127.0.0.1 and hit the `postgres ... reject` pg_hba
  rule. `walg.env.example` now sets `PGHOST=/var/run/postgresql`.

## Last run

Outage 4 s (stop to first write); PITR restored plain_t 600 (= 600 at the noted time, 700 later)
and items 5000; all 10 checks PASS.
