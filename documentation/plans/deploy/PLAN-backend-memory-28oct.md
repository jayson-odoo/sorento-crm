# Backend memory growth (BACKEND-MEMORY)

Status: investigation (2026-10-28). Track: small fix track expected (no migration, no auth/RBAC,
no ingest surface); confirmed once the fix shape is known.
Lane: `crew/backend-memory`
UAC: `backend-memory-28oct-acceptance-criteria.md` (written with the fix, once the cause is measured)

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

**Conclusion so far:** nothing local grows with time or request count. The measured steady state
per worker is about 0.5-0.75 GB, so a colour should sit near 1 + 4 x 0.7 = 3.8 GB, not 6.6 GB.
The gap fits glibc malloc arena retention: a worker runs many threads (anyio's thread pool for sync
endpoints, the 8-thread direct-turn pool `app/tasks/chat_turns.py:88`, inbox drains, prefetch and
warm threads), glibc gives each thread up to 8 x cores arenas, each arena keeps its high-water mark,
and the chat path allocates 100+ MB of numpy temporaries per turn on whichever thread runs it. That
is UNVERIFIED on prod until the owner's `memreport` shows how much of each worker sits in arenas.

## Zero-downtime recovery today (owner runs; verified locally)

gunicorn's own signals: `TTIN` adds a worker, `TTOU` removes one, and gunicorn always removes the
OLDEST (`gunicorn/arbiter.py:573-576`, sorted by age, SIGTERM). Locally: 2 rounds under steady
traffic, workers 57159 then 57160 retired in age order, private memory 477 -> 307 MB, every request
200. `start.sh:64` `exec`s gunicorn, so it is PID 1 and `docker kill -s` reaches it.

What users see: nothing, normally. The retiring worker stops taking new connections and finishes
what it has (up to 100 s, `app/uvicorn_worker.py:15`); an open staff event stream is closed and the
browser reconnects; inbox drains finish their row (`app/tasks/chat_turns.py:208`). The new worker
answers chat turns with spelling-only lookup matching until its warm finishes (10-70 s), exactly
as after every deploy. Peak memory during a round: one extra fresh worker, about +0.5 GB.

### Owner commands (on the server, from `/opt/sorento-crm2`; steps 0-2 are read-only)

```bash
C=sorento-crm2-backend_blue-1

# 0. PID 1 must be gunicorn; the picture before
docker exec $C cat /proc/1/cmdline | tr '\0' ' '; echo
grep MemAvailable /proc/meminfo; docker stats --no-stream

# 1. Per process: age, private memory, and how much of it sits in glibc malloc arenas
docker exec -i $C python3 - <<'PY'
import os
HEAP = 64 << 20
hz = os.sysconf("SC_CLK_TCK"); up = float(open("/proc/uptime").read().split()[0])
for pid in sorted(int(p) for p in os.listdir("/proc") if p.isdigit()):
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()[:60]
        roll = {f[0].rstrip(":"): int(f[1]) // 1024 for f in (l.split() for l in open(f"/proc/{pid}/smaps_rollup")) if len(f) == 3 and f[2] == "kB"}
        start = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19]) / hz
        maps = []
        for line in open(f"/proc/{pid}/smaps"):
            f = line.split()
            if f and "-" in f[0] and ":" not in f[0]:
                lo, hi = (int(x, 16) for x in f[0].split("-")); maps.append([lo, hi, f[1], len(f) == 5, 0])
            elif maps and f and f[0] == "Rss:":
                maps[-1][4] = int(f[1])
        arenas = arena_kb = 0
        for i, (lo, hi, perms, anon, rss) in enumerate(maps):
            if anon and perms == "rw-p" and lo % HEAP == 0:
                end = maps[i + 1][1] if i + 1 < len(maps) and maps[i + 1][0] == hi and maps[i + 1][2] == "---p" else hi
                if end - lo == HEAP:
                    arenas += 1; arena_kb += rss
    except (OSError, ValueError, IndexError):
        continue
    print(f"pid={pid} age_h={(up - start) / 3600:.1f} rss={roll.get('Rss')}MB pss={roll.get('Pss')}MB private_dirty={roll.get('Private_Dirty')}MB anon={roll.get('Anonymous')}MB malloc_arenas={arenas} arena_rss={arena_kb // 1024}MB {cmd}")
PY
docker exec $C sh -c 'cat /sys/fs/cgroup/memory.stat 2>/dev/null || cat /sys/fs/cgroup/memory/memory.stat' | grep -E '^(total_)?(anon|file|rss|cache|shmem) '

# 2. Requests in the last hour (sizes max_requests)
docker logs --since 1h $C 2>&1 | grep -c ' - Status: '

# 3. Rolling recycle, one worker at a time. Run ONE round, re-run step 1 and check that the new
#    worker is small and MemAvailable rose; then run the other three.
docker kill -s TTIN $C; sleep 90      # a 5th worker boots and warms its lookup vectors
docker kill -s TTOU $C; sleep 160     # the OLDEST worker finishes its requests (<= 150 s) and exits
docker logs --since 5m $C 2>&1 | grep -E 'Booting worker|Shutting down|Finished server process'
grep MemAvailable /proc/meminfo; docker stats --no-stream
```

Stop at any step if the output looks wrong: step 3 changes nothing but which processes serve, and
`docker kill -s TTOU $C` (once) undoes a stray `TTIN`.

## Lasting fix (proposal, waits on the owner's numbers)

- `max_requests` + `max_requests_jitter` in `gunicorn.conf.py` (env `GUNICORN_MAX_REQUESTS`,
  `GUNICORN_MAX_REQUESTS_JITTER`, 0 = off): a worker retires itself after N requests, gracefully,
  through the same path as `TTOU`. Bounds growth whatever the cause. N from the owner's request
  count per hour, sized so each worker recycles every 1-2 hours.
- `MALLOC_ARENA_MAX=2` in the backend image if `memreport` shows the arenas hold most of the
  private memory.
- `fill()` honours `_CACHE_CAP` (one line, red test first).
