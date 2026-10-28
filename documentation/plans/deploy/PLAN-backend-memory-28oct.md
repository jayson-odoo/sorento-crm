# Backend memory growth (BACKEND-MEMORY)

Status: in progress (2026-10-28), PR #1950. Track: small fix track (under 300 lines, no migration,
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

**Conclusion:** nothing grows with request count; the growth is time-shaped. The leading cause is
(7): each worker's garbage collector un-shares the preloaded app heap, so preload's saving erodes
over hours. glibc malloc arena retention (many threads per worker, 100+ MB numpy temporaries per
chat turn) may add to it; UNVERIFIED until owner step 1 shows the arena numbers.

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

# 2. Requests in the last hour (sizes max_requests)
docker logs --since 1h $C 2>&1 | grep -c ' - Status: '
```

Reading step 1: the master (pid 1) is the preloaded app. A worker whose `shared_clean +
shared_dirty` is small and whose `private_dirty` is near the master's size has un-shared the
preload (finding 7, fixed by `gc.freeze`). Large `arena_rss` points at malloc arenas instead.

Step 3, a separate yes/no: run it ONLY if step 0's first line contains `gunicorn`, in a quiet hour.
One round, then re-run step 1 and check that MemAvailable rose; then the other three rounds.

```bash
docker kill -s TTIN $C; sleep 90      # a 5th worker boots and warms its lookup vectors
docker kill -s TTOU $C; sleep 160     # the OLDEST worker retires (hard-killed at 60-100 s, see above)
docker logs --since 5m $C 2>&1 | grep -E 'Booting worker|Shutting down|WORKER TIMEOUT|Finished server process'
grep MemAvailable /proc/meminfo; docker stats --no-stream
```

A stray `TTIN` is undone by one `docker kill -s TTOU $C`.

## Lasting fix (this PR)

- `gc.freeze()` in gunicorn's `pre_fork` hook (`gunicorn.conf.py`): the preloaded heap moves to
  the permanent generation before every fork, so a worker's collector never walks it and never
  un-shares it (finding 7). Red-first.
- `max_requests` + `max_requests_jitter` (env `GUNICORN_MAX_REQUESTS` 5000,
  `GUNICORN_MAX_REQUESTS_JITTER` 500; 0 = off): a worker retires after about 5000-5500 requests
  and the master forks a fresh one, which bounds any remaining growth (arenas, caches).
- `DrainingServer` (`app/uvicorn_worker.py`): a self-retiring worker (max_requests or TTOU) gets
  the deploy's graceful shutdown, not the hard kill above: it stops the inbox drains when shutdown
  starts (the request limit sends no signal) and keeps gunicorn's heartbeat going through the
  bounded shutdown, never past `graceful_timeout`, so a hung shutdown is still killed. Chosen over
  raising `timeout` to 210 s or more, which would also leave a genuinely hung worker serving
  errors for 3.5 minutes before it is replaced.
- The warm path `fill()` honours `_CACHE_CAP` (finding 5).
- `MALLOC_ARENA_MAX=2`: only if owner step 1 shows the arenas hold the memory.

Cost of each recycle: the new worker re-embeds the lookup texts (`lookup_lists.py:755-829`, the
cache is per process): 7,035 texts, 213,597 characters, about 53k tokens. On the 20 Oct copy
the embedder prompt has no production label, so it is OpenAI `text-embedding-3-small` in chunks
of 500: 15 requests, about USD 0.001 at list price (USD 0.02 per million tokens). On Gemini it
would be 71 requests of 100, about USD 0.008 (UNVERIFIED list price). The new worker matches by
spelling only for those 10-70 s, on a quarter of the traffic. At 10,000 requests an hour (the
real number comes from owner step 2) each worker recycles about every 2 hours: 48 recycles a day,
about USD 0.05 a day on OpenAI, and about 0.5% of chat turns on spelling-only matching. If that
window ever shows up in chat quality, warm the vectors once in the master before the fork (shared,
no window); not built now, no evidence it is needed.
