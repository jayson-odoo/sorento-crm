# Backend memory, round 2 (BACKEND-MEM-2)

Status: investigation done (2026-10-30), fix plan awaiting crew OK. No code yet. Track: small fix
track per slice (each under 300 lines, no migration, no auth/RBAC, no ingest surface).
Lane: `crew/backend-mem-2` (sandbox branch `claude/backend-mem-investigation-o09ezl`), PR #2007.
Previous round: `PLAN-backend-memory-28oct.md`, PR #1950 (gc.freeze, graceful TTOU).

## Why

Prod 30 Oct ~14:05 MYT (release #8 = main b07e71d5bf, includes #1950, 4 gunicorn workers):
backend_blue 7.95 GiB, host available 3,005 MB, swap 6,138/6,143 MB used. Release #9 refused by
the deploy memory guard (2,922 MB available < `DEPLOY_MIN_AVAILABLE_MB=4500`,
`scripts/blue_green_deploy.sh:69`). On 28 Oct, before #1950, the same colour was 7.3 GiB at 8
workers (about 0.9 GB per worker). Now it is about the same total at 4 workers: about 1.8-1.9 GB
per worker. Per-worker memory doubled between 28 and 30 Oct.

## What changed between the 28 Oct measurement and release #8

All in prod (`git merge-base --is-ancestor <sha> b07e71d5bf`):

| PR | merged | memory effect |
|---|---|---|
| #1950 BACKEND-MEMORY | 28 Oct | `gc.freeze()` in `pre_fork` (`gunicorn.conf.py:83-90`). Keeps the preload shared. Still right. |
| #1951 API-NONBLOCKING | 29 Oct | about 940 handlers `async def` -> `def`. They now run in anyio's threadpool, 40 threads per worker (default limiter, never overridden: no `total_tokens` / `CapacityLimiter` in `app/`). Before, a blocking `async def` held the event loop, so a worker ran ONE heavy request at a time. Now up to 40 at once. |
| #1959 SPAN-PASS-PROD, #1967 LOOKUP-EMBED-CENTRAL | 28-30 Oct | the lookup warm now loads every `lookup_word` vector from Postgres in each worker (`lookup_word_store.py:228-252`, called from `lookup_lists.py:961`). |

#1982 (AGENTIC-P1) is NOT in release #8.

## Process model (unchanged)

`start.sh:64` -> `gunicorn -c gunicorn.conf.py`: `preload_app` on (`:52`), `WORKERS` (prod 4,
`:54`), `timeout 120`, `graceful_timeout 150`. **No `max_requests` / `max_requests_jitter`**: a
worker lives as long as the container, so its memory high-water mark is kept for days.
`app/main.py:410,416` start the inbox sweeper and the lookup warm in EACH worker after the fork.

## Findings (local measurement, 30 Oct)

Setup: this sandbox, Python 3.13 + glibc (prod: Python 3.11 on Debian glibc,
`Dockerfile:2,17`), a throwaway Postgres 16 + pgvector with 15,000 products, 166 categories and
7,035 `lookup_word` vectors (1536-d, the prod count from the 28 Oct plan). Number = the process's
`Private_Dirty` (what a worker does not share). Scripts in the PR thread (scratch, not committed).

### 1. Concurrency of heavy handlers sets the high-water mark, and #1951 raised it from 1 to 40

Same 72 operations (a 15k-row JSON list and a 15k-row xlsx export, alternating), only the number
of threads running them at once changes. One process, app preloaded (638 MB private at start):

| threads at once | private after 24 / 48 / 72 ops | kept |
|---|---|---|
| 1 (what a worker did before #1951) | 800 / 800 / 788 | +150-160 MB |
| 4 | RESULT_C4 | |
| 8 | RESULT_C8 | |
| 24 (40-thread pool, as now) | 1,526 / 1,806 / 1,731 | +900-1,170 MB |
| 24 with `MALLOC_ARENA_MAX=2` | 1,618 / 1,770 / 1,793 (4th batch 1,898) | no better |
| 24 with `malloc_trim(0)` after each batch | RESULT_C24T | |
| 4 with `malloc_trim(0)` | RESULT_C4T | |

Not a leak: it plateaus. It is the peak of concurrent transient work, and CPython's allocator plus
glibc keep that peak (freed memory sits in partly used pools and heap holes and is not given back).
So a worker's size is "the most heavy requests it ever ran at once" times "their transient size",
held until the worker dies, which (no `max_requests`) is the next deploy. Malloc arenas are not the
cause (`MALLOC_ARENA_MAX=2` changes nothing), so that knob is not in the plan.

Heavy `def` handlers that now overlap in one worker: xlsx/CSV exports (e.g.
`inventory/stock.py:440` balance export, `inventory/stock_position.py:52`), the sales and
outstanding reports, PDF renders (WeasyPrint, `app/services/pdf_render.py`), uploads parsed in
the handler, and the sync chat turn (`app/api/v1/external/chat.py:173` `def chat_turn`), which
builds the lookup rows twice per turn (`chatbot/engine.py:1265`, `:1325`).

### 2. The lookup warm's store load: +231 MB kept, +621 MB peak, per worker, at every boot

`lookup_word_store.load_lookup_vectors` (`lookup_word_store.py:228`) runs `.all()` (`:242`) over
every current `lookup_word` chunk, and pgvector's SQLAlchemy type turns each vector's text into a
list of 1536 Python floats (`pgvector/vector.py:88`, `[float(v) for v in value[1:-1].split(',')]`):
7,035 x 1536 = 10.8 million float objects alive at once before `np.stack`.

| load | kept after | peak during |
|---|---|---|
| today, `.all()` (on a thread, as the warm runs it) | +231 MB (43 MB of it is the vectors) | +621 MB |
| today, `MALLOC_ARENA_MAX=2` | +342 MB | +611 MB |
| today, then `malloc_trim(0)` | +185 MB | |
| prototype: `yield_per(500)`, each batch to float32 at once | +113 MB | +123 MB |

Every worker runs it at start-up (`app/main.py:416` -> `engine.py:1342` `start_lookup_warm`), so
a new colour's 4 workers peak about +2.5 GB together, during exactly the deploy overlap the guard
protects. It also runs again whenever a turn's rows hold a text the cache does not have
(`lookup_lists.py:1115` `is_cached` false -> `warm` -> `fill` -> full reload at `:961`), e.g.
after a new customer or category, until that text is embedded; an embed failure (no key, rate
limit) leaves the text missing, so the next turn reloads all 7,035 vectors again.

On top, per worker, the turn-time stores measured on 28 Oct: two row matrices (`_matrices`,
`lookup_lists.py:896`, `_MATRIX_SETS = 2`; +86 MB measured here for two 7k-text sets), two
`_prepared` / `_indexes` sets (`:178`, `:203`), the resolver index (`list_resolver.py:232`):
about 230 MB per worker on 28 Oct, about 0.9 GB across 4 workers.

### 3. Copy-on-write loss on Python 3.11 (smaller, partly fixed by #1950)

`gc.freeze()` stops the collector touching the preload. Python 3.11 still writes a refcount into
every object a request touches, so the pages a worker uses are copied anyway; 3.12+ makes most of
those objects immortal. Upper bound: the master's preload, about 0.5 GB per worker on prod
(master rss 470 MB on 28 Oct; 735 MB locally on 3.13). This is the smallest of the three and the
most expensive to fix (a Python upgrade), so it is not in this plan.

### Bounded caches (checked, not a cause)

Each capped or keyed by a small domain: `product_image_service._url_cache` 4,096
(`:319`), `dealer_kit/public_cache` 32 entries of ~400 KB (`:37`), `storage_router._signed_cache`
4,096 (`:246`), `llm_provider._OPENAI_CLIENTS` 32 (`:412`), `product_spec_preview._JOBS` 20
(`:34`), `lookup_lists._pieces` 512 (`:900`), `_cache` 20,000 vectors (`:69`, about 123 MB at the
cap; 7,035 today = 43 MB), `audit_service` table caches (keyed by table). No product/contact cache
holds rows across requests.

### Rough budget of one prod worker today (about 1.8-1.9 GB)

| part | MB |
|---|---|
| fresh worker after start-up (28 Oct) | about 300 |
| preload pages copied by refcount writes (3) | up to about 250-500 |
| lookup warm kept (2) + turn-time lookup stores | about 230 + about 230 |
| high-water of concurrent heavy handlers (1) | about 500-1,000, depends on the busiest moment since the deploy |

## Fix plan (slices, smallest first)

Each slice is red-first and measured with the same harness before and after.

**S1 (S): stream the lookup store load.** `load_lookup_vectors` reads with `yield_per(500)` and
turns each batch into float32 before the next (prototype above). Expected per worker: -118 MB kept,
peak -500 MB; a new colour's boot peak drops by about 2 GB. Also: `fill` loads from the store only
the first time (or when the store has texts the cache lacks), not on every missing-text warm.
~60 lines + test.

**S2 (S): `max_requests` with jitter, plus the inbox stop on a request-limit exit.** Bounds how
long a worker keeps a high-water mark. At about 650 requests per worker per hour (2,617/h on 28
Oct across 8 workers, now 4), `max_requests = 2000`, `max_requests_jitter = 500` recycles each
worker every 2.5-4 h, staggered, one at a time. #1950 dropped it because the 28 Oct numbers showed
no growth over time; the #1951 high-water shape is different (it climbs with each busier moment).
The retiring worker needs #1950's graceful drain on this exit path too (the 28 Oct plan notes the
request-limit exit has no signal, so `inbox_queue.begin_shutdown` must run from the worker's own
exit). Depends on S1, or every recycle re-pays the +621 MB warm peak. ~40 lines + test.

**S3 (S): `malloc_trim(0)` after heavy work.** A worker-local call (ctypes, glibc only, no-op
elsewhere) at the end of the export / report / PDF handlers, or once a minute from the existing
sweeper thread when the worker is idle. Expected from the table above: RESULT_TRIM_EFFECT.
~30 lines + test.

**S4 (M): cap concurrent heavy handlers per worker.** A small semaphore (e.g. 2) around exports,
reports and PDF renders only, NOT the global anyio limiter: `def chat_turn` also runs in that pool
and waits on the LLM for 10-60 s, so a global cap would queue chat behind exports. Expected:
the high-water mark falls toward the CONC=RESULT_CAP row. Only if S2+S3 leave a worker over budget.

**Not planned, with the trigger:** share the lookup vectors across workers (one float32 matrix in a
file `np.load(mmap_mode="r")`, page cache instead of 4 private copies, about -130 MB per worker
after S1). Trigger: workers go back up to 8. Python 3.12 upgrade for immortal objects: trigger is
a prod measurement after S1-S3 showing copied preload above 400 MB per worker.

## Expected per worker after

| | today | after S1 | after S1+S2+S3 |
|---|---|---|---|
| one worker, steady | about 1.85 GB | about 1.7 GB | RESULT_AFTER |
| colour (4 workers + master) | 7.95 GiB | about 7.4 GB | RESULT_COLOUR |
| new colour boot peak | about 3.5-4 GB | about 1.5-2 GB | same |

## Deploy guard threshold

`DEPLOY_MIN_AVAILABLE_MB=4500` is right for TODAY's code: a new colour boots a master (about 0.7
GB) plus 4 workers each paying the +621 MB warm peak at the same moment (about 2.5 GB), plus the
pre-migration `pg_dump`. Lowering it now would invite the 10 Sep OOM. After S1 the boot peak is
about 1.5-2 GB; re-measure the new colour's peak on prod (one `docker stats` sample every 2 s over
the first 2 minutes of a deploy) and set the guard to that peak plus about 1.5 GB of headroom
(likely about 3,500). The guard is not the problem: the old colour holding about 8 GB is.

## Owner check that would confirm (read-only, on the prod host)

PLAN-backend-memory-28oct.md "Owner commands" step 1 (per process private_dirty, heap, arenas,
age), plus thread count per worker (`ls /proc/<pid>/task | wc -l`). Expected if this plan is
right: 4 workers at about 1.6-2.0 GB private each, `[heap]` large, arenas small, 40+ threads.
