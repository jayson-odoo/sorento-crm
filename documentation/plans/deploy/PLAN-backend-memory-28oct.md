# Backend memory growth (BACKEND-MEMORY)

Status: in review (2026-10-28), PR #1950 reviewer READY; ships in a release after #3. Track: small fix track (under 300 lines, no migration,
no auth/RBAC, no ingest surface).
Lane: `crew/backend-memory`
UAC: `backend-memory-28oct-acceptance-criteria.md`

## Why

Prod `docker stats --no-stream` (owner, 28 Oct ~10:00 MYT): `backend_blue` 6.635 GiB of
15.62 GiB, db 2.87, frontend_blue 0.77, redis 0.50, worker 0.31, worker_fast 0.12, mcp 0.05.
The blue colour was started fresh by release #2 at 03:40 the same day, so it grew by 2 GB or
more in about 6 hours. Release #3 (run 40616142315) was refused by the deploy memory guard:
"4264 MB available, below DEPLOY_MIN_AVAILABLE_MB=4500" (`scripts/blue_green_deploy.sh:69`,
runbook `documentation/runbooks/memory-and-deploy-guards.md`). The preload target from
`PLAN-deploy-memory-and-ci-speed.md` was under 3 GB per colour.

Owner: no restart of the live backend (downtime). Wants to know why it grows.

## Process model (from code)

- `sorento_crm_backend/start.sh:64` runs `gunicorn app.main:app -c gunicorn.conf.py`.
- `sorento_crm_backend/gunicorn.conf.py:42` `preload_app` on, `:44` `workers = 4`,
  `:46` worker class `app.uvicorn_worker.InboxUvicornWorker`, `:58` `graceful_timeout = 150`.
  No `max_requests`, no `max_requests_jitter`, no threads setting: a worker lives as long as the
  container.
- `app/main.py:329` `startup_event` runs in EACH worker (lifespan), after the fork: it starts the
  chatbot inbox sweeper (`app/tasks/chat_turns.py:208`) and the lookup-vector warm thread
  (`app/tasks/chat_turns.py:223`), so whatever those load is private to each worker, four times.

## Steps

1. Inventory every in-process store that grows (file:line, bound, size at prod scale).
2. Measure locally (gunicorn, preload, 2 workers, dev copy `sorento_prod_1020`): RSS per process
   after warm, then after a replayed GET mix; find what grows and whether it plateaus.
3. Zero-downtime recovery command for the owner (rolling gunicorn worker recycle), with what
   users see.
4. Lasting fix as a PR: red test first, kill test, reviewer.

## Findings (28 Oct, local measurement on a copy of main against the dev copy `sorento_prod_1020`)

macOS swaps (11 GB in use), so RSS is meaningless here; every number is `phys_footprint` (private
dirty plus compressed plus swapped), the closest local proxy for Linux private anon memory. Local
Python is 3.14 on macOS's allocator; prod is Python 3.11 (`sorento_crm_backend/Dockerfile:17`) on
glibc. Treat absolute numbers as indicative and the shape (grows or plateaus) as the finding.

1. **Workers are never recycled.** `gunicorn.conf.py` sets no `max_requests`, so every byte a worker
   ever allocated and glibc did not hand back stays until the container is replaced.
2. **Fresh worker:** master 836 MB (the preloaded app, shared copy-on-write), each worker 263 MB private
   right after start-up, 306-330 MB after its first requests.
3. **GET mix (stock balance, products, orders, sales / outstanding / top-selling reports, incoming
   stock, last cost, current-stock list; 773 requests on 2 workers):** 333 -> 345 MB per worker, then
   flat. One unexplained one-off step of +126 MB per worker under a burst of 429s, then flat at
   471-476 MB for the next 4,000 requests. No growth that tracks request count.
4. **Chat lookup path** (`lookup_lists.shortlist` + `list_resolver.resolve`, fake embedder, no LLM;
   visibility alternating between staff-wide and 1-5 customer dealers): the start-up warm holds
   7,035 texts (5,868 customers, 114 salespeople, 166 categories, ...) = 43 MB of float32 vectors per
   worker (`lookup_lists.py:755`); the first turns add +142 MB (two row matrices `:757`, two
   `_prepared` / `_indexes` sets `:192` `:217`, two resolver indexes `list_resolver.py:232`). Then it
   holds steady: 415-424 MB with 4 threads; 523 MB at 200 turns with 8 threads, back to 422-450 MB by
   800 turns. About 230 MB per worker, about 0.9 GB across 4 workers, bounded by the data, not by time.
   The transient peak per turn (about 100 MB more with 8 threads) is what glibc keeps.
5. **Bug, no effect today:** the warm path `fill()` (`lookup_lists.py:809`) never checks
   `_CACHE_CAP` = 20000 (`:89`); only `embed()` does (`:796`). 7,035 < 20,000, so nothing today.
6. Other bounded stores (inventory by a read-only subagent): `_rbac_cache` up to 50,000 entries
   (`user_service.py:1384`, ~15-25 MB), `_COMPILED` up to 20,000 (`product_spec_rules.py:211`),
   `_EMBED_CACHE` LRU 512 (`project_registration_service.py:115`, ~25 MB), all capped.

7. **Copy-on-write un-sharing by the garbage collector (measured, the likely main cause).** After
   `import app.main` the master holds 3,460,480 GC-tracked objects. A forked child (a worker) that
   runs one full `gc.collect()` takes 87,217 page faults, about 1.4 GB of pages touched, and pauses
   1.67 s: a full collection writes into the header of every tracked object, so each page that holds
   one is copied out of the shared preload into the worker's private memory. With `gc.freeze()` in
   the parent before the fork, the same collection takes 32 faults and 0.00 s (scratch script
   `gc_freeze_faults.py`, recorded in the PR). A worker runs its first full collection only once
   enough new long-lived objects pile up (CPython runs one when they reach 25% of the long-lived
   total), so each worker un-shares the preloaded heap in steps over hours, and four workers end
   up with four private copies. That matches the shape on prod (6.6 GiB six hours after a fresh
   start) and the size: master about 1 GB + 4 x (0.3 own + 0.6-0.8 copied + 0.23 chat lookup) is
   about 5.5-6.3 GB. macOS pages are 16 KB and Linux pages 4 KB, so the prod number will be
   smaller than 1.4 GB per worker; owner step 1 (`Shared_*` against `Private_Dirty` per worker)
   confirms it. `gc.freeze` appears nowhere in the backend today.

**Conclusion (local):** nothing grows with request count. The leading cause was (7): each
worker's garbage collector un-shares the preloaded app heap. Superseded in part by the prod
numbers below.

## Prod numbers (owner steps 0-2, 28 Oct 11:2x) and what they change

PID 1 is gunicorn. MemAvailable 3,681 MB (guard 4,500). backend_blue 7.305 GiB; cgroup anon
7,421 MiB, file 45 MB (no page cache in play). 2,617 requests in the last hour (0.73 a second).
**Prod runs 8 workers** (`WORKERS=8` in the prod env; the 10 Sep decision was 4,
`PLAN-deploy-memory-and-ci-speed.md:42`).

| process | age | rss | shared_dirty | private_dirty | [heap] | arenas |
|---|---|---|---|---|---|---|
| master (pid 1) | 7.7 h | 470 | 223 | 230 | 15 | 0 MB |
| 7 workers | 7.7 h | 916-1264 | 208-216 | 679-1030 | 72-121 | 0-15 MB |
| 1 worker (replaced ~10:30) | 0.9 h | 1144 | 215 | 905 | 69 | 4 MB |

- **Not a leak, warm-up.** A 0.9 h worker is as big as the 7.7 h ones, so a worker reaches its
  size within its first hour. Recycling (`max_requests`) cannot beat that, and at about 327
  requests per worker per hour a limit of 5,000 would recycle each worker once a day:
  `max_requests` is dropped from this PR.
- **malloc arenas are negligible** (15 MB at most): no `MALLOC_ARENA_MAX`.
- **The preload copy is real:** the master's 230 MB `private_dirty` are pages every worker has
  already copied, so about 8 x 230 = 1.8 GB of the colour is duplicated preload; each worker
  still shares only about 212 MB of it. `gc.freeze()` stops the share the collector causes
  (finding 7). Pages that request code writes refcounts into are still copied. Estimate 0.8-1.6 GB
  saved at 8 workers (UNVERIFIED until measured on prod after release).
- **What a worker builds after the fork** (local, `postfork_harness.py`, Python-traced): start-up
  events +25 MB (boto3/botocore and apscheduler first imported there: 103 + 20 modules, only
  about 3 MB of it), 420 report/list/stock GETs +8 MB (SQLAlchemy's compiled-statement cache),
  the chat lookup path +151 MB (43 MB of row vectors, 105 MB of indexes and caches in
  `app/services/chatbot`). Footprint grew 407 MB over the same steps, so about half is outside
  Python's own accounting (C allocations and memory freed but kept by the allocator).
- **Worker count dominates:** each worker costs about 0.9 GB, so 8 -> 4 frees about 3.6 GB.
  **Owner ruling (28 Oct 13:5x): WORKERS=4**; the owner edits the server compose before release #4.
  Release #3 went live after the owner's TTOU x4. Lane API-NONBLOCKING (#1951) moves the blocking
  `async def` handlers off the event loop so 4 workers carry the load; no file overlap with this PR.

## Zero-downtime recovery today (owner runs)

gunicorn's own signals: `TTIN` adds a worker, `TTOU` removes one, and gunicorn removes the
OLDEST (`gunicorn/arbiter.py:573-576`, sorted by age, SIGTERM). `start.sh:64` `exec`s gunicorn, so
it is PID 1 and `docker kill -s` reaches it, IF the prod compose does not wrap it (step 0 checks).
Locally: 2 rounds under steady traffic, workers retired in age order, private memory 477 -> 307
MB, every request 200 (no long-lived connections were open in that test).

What users see, plainly: the retiring worker is NOT given its full graceful shutdown. gunicorn's
master keeps checking every worker's heartbeat against its 120 s `timeout`
(`gunicorn/arbiter.py:209` calls `murder_workers`, `:488-507`; gunicorn 23.0.0); uvicorn sends that heartbeat only from its main loop
(`uvicorn/server.py:246-250`), not while it shuts down; an open staff event stream holds the
shutdown for the full 100 s (`app/uvicorn_worker.py:15`). So the master hard-kills the retiring
worker with SIGABRT 60-100 s after the TTOU (the last heartbeat can be 60 s old). The inbox drains
stop taking rows at the signal and finish theirs within seconds (`app/tasks/chat_turns.py:178`),
so the usual loss is: staff event streams on that worker drop and the browser reconnects; a slow
sync `/chat/turn` still running on it is cut (n8n sees an error for that turn); expect one
`WORKER TIMEOUT` line per round in the log. The new worker answers chat turns with spelling-only
lookup matching until its warm finishes (10-70 s), as after every deploy. Peak memory during a
round: one extra fresh worker, about +0.5 GB. Run it in a quiet hour.

A recycled worker is forked from today's master without `gc.freeze`, so it un-shares again over
the next hours: the recycle buys the headroom to deploy release #3, it is not the fix.

### Owner commands (on the server, from `/opt/sorento-crm2`; steps 0-2 are read-only)

```bash
cd /opt/sorento-crm2
C=$(docker compose ps -q backend_$(cat .active_color))

# 0. Which process is PID 1 (step 3 needs gunicorn there), and the picture before
docker exec $C cat /proc/1/cmdline | tr '\0' ' '; echo
grep MemAvailable /proc/meminfo; docker stats --no-stream

# 1. Per process (MB): age, shared vs private memory, the [heap] and the glibc malloc arenas
docker exec -i $C python3 - <<'PY'
import os
HEAP = 64 << 20
hz = os.sysconf("SC_CLK_TCK"); up = float(open("/proc/uptime").read().split()[0])
for pid in sorted(int(p) for p in os.listdir("/proc") if p.isdigit()):
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()[:60]
        r = {f[0].rstrip(":"): int(f[1]) // 1024 for f in (l.split() for l in open(f"/proc/{pid}/smaps_rollup")) if len(f) == 3 and f[2] == "kB"}
        start = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19]) / hz
        maps = []  # [lo, hi, perms, anonymous, name, rss_kb, private_dirty_kb]
        for line in open(f"/proc/{pid}/smaps"):
            f = line.split()
            if f and "-" in f[0] and ":" not in f[0]:
                lo, hi = (int(x, 16) for x in f[0].split("-"))
                maps.append([lo, hi, f[1], len(f) == 5, f[5] if len(f) > 5 else "", 0, 0])
            elif maps and f and f[0] in ("Rss:", "Private_Dirty:"):
                maps[-1][5 if f[0] == "Rss:" else 6] = int(f[1])
        heap_pd = sum(m[6] for m in maps if m[4] == "[heap]") // 1024
        arenas = arena_kb = 0
        for i, (lo, hi, perms, anon, name, rss, pd) in enumerate(maps):
            if anon and perms == "rw-p" and lo % HEAP == 0:
                end = maps[i + 1][1] if i + 1 < len(maps) and maps[i + 1][0] == hi and maps[i + 1][2] == "---p" else hi
                if end - lo == HEAP:
                    arenas += 1; arena_kb += rss
    except (OSError, ValueError, IndexError):
        continue
    print(f"pid={pid} age_h={(up - start) / 3600:.1f} rss={r.get('Rss')} pss={r.get('Pss')} shared_clean={r.get('Shared_Clean')} shared_dirty={r.get('Shared_Dirty')} private_dirty={r.get('Private_Dirty')} heap_private_dirty={heap_pd} malloc_arenas={arenas} arena_rss={arena_kb // 1024} (MB) {cmd}")
PY
docker exec $C sh -c 'cat /sys/fs/cgroup/memory.stat 2>/dev/null || cat /sys/fs/cgroup/memory/memory.stat' | grep -E '^(total_)?(anon|file|rss|cache|shmem) '

# 2. Requests in the last hour
docker logs --since 1h $C 2>&1 | grep -c ' - Status: '
```

Reading step 1: the master (pid 1) is the preloaded app. A worker whose `shared_clean +
shared_dirty` is small and whose `private_dirty` is near the master's size has un-shared the
preload (finding 7, fixed by `gc.freeze`). Large `arena_rss` points at malloc arenas instead.

Step 3, a separate yes/no: run it ONLY if step 0's first line contains `gunicorn`, in a quiet hour.
One round, then re-run step 1 and check that MemAvailable rose; then the remaining rounds, one per
worker (prod runs 8). To SHED workers instead (8 -> 6), run only the `TTOU` line, once per worker.

```bash
docker kill -s TTIN $C; sleep 90      # one extra worker boots and warms its lookup vectors
docker kill -s TTOU $C; sleep 160     # the OLDEST worker retires (hard-killed at 60-100 s, see above)
docker logs --since 5m $C 2>&1 | grep -E 'Booting worker|Shutting down|WORKER TIMEOUT|Finished server process'
grep MemAvailable /proc/meminfo; docker stats --no-stream
```

A stray `TTIN` is undone by one `docker kill -s TTOU $C`.

## Lasting fix (this PR)

- `gc.freeze()` in gunicorn's `pre_fork` hook (`gunicorn.conf.py`): the preloaded heap moves to
  the permanent generation before every fork, so a worker's collector never walks it and never
  un-shares it (finding 7, prod: 8 x 230 MB copied). Red-first.
- `DrainingServer` (`app/uvicorn_worker.py`): a worker retired with `TTOU`, the tool for shedding
  workers without a restart, gets the deploy's graceful shutdown instead of the 60-100 s SIGABRT
  above. A task on the event loop keeps gunicorn's heartbeat going through the shutdown, never
  past `graceful_timeout`. It runs on the loop on purpose (review round 1): the drains wait runs
  off the loop (`asyncio.to_thread`, `app/main.py` shutdown_event), so the beats continue through
  it, while a worker whose loop wedges stops beating and is still killed at 120 s. This was chosen
  over raising `timeout` to 210 s or more, which would leave a genuinely hung worker serving
  errors for 3.5 minutes. The inbox already stops at the TTOU's SIGTERM (`app/tasks/chat_turns.py:178`).
- The warm path `fill()` honours `_CACHE_CAP` (finding 5).

Dropped after the prod numbers: `max_requests` and its jitter (no slow leak to bound; at about 327
requests per worker per hour it would not run), and with it the shutdown's own inbox stop (only
the request limit retired a worker without a signal). `MALLOC_ARENA_MAX`: not needed (arenas at 15
MB at most).

Not built, with the trigger that would justify it:

- **Warm the lookup vectors once in the master before the fork** so all workers share them: 43 MB
  of vectors per worker (`lookup_lists.py:755`), about 300 MB at 8 workers, more if the
  widest-set matrix and indexes (`:757`, `:192`, `:217`, `list_resolver.py:232`) are built there
  too. Costs: a boot delay (the warm calls the embedding API, 15 OpenAI requests today), and a
  fork-safety rule (it must finish synchronously before the fork, or a child inherits a held
  `_store_lock`). Trigger: the owner keeps 8 workers and the colour is still over budget after
  this PR ships.
- **Redis for the vectors**: no. Every turn does matrix maths over the whole row set in process;
  fetching 43 MB per turn is worse than holding it.
