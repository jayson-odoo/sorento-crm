# PLAN: LOOKUP-WARM-STORM - lookup-list warm must not storm fresh workers

Status: built, in review (small fix track, URGENT hotfix; no migration, no auth/RBAC change, no new ingest surface)

## Incident

Prod, 30 Oct ~17:15-17:22 MYT. The owner HUP'd gunicorn at ~16:45 (workers respawned), then release #9
(257b6967eb, without #2007's `max_requests`) deployed a fresh colour at ~16:50. The API timed out for about
10 minutes: backend CPU 120%, DB idle. The log was flooded with
`lookup lists warm: 7067 texts cached on gemini-embedding-001 in 17.5-21.8 s (6788 from the shared file)`
plus many `batchEmbedContents` calls. It recovered on its own.

## What was measured (sandbox: Postgres 16 + pgvector, Redis, 6,788 seeded `lookup_word` vectors, fake Gemini 1 s per call)

1. **The GIL-starvation chain does not reproduce.** A single-process `load_lookup_vectors` over 6,788 rows took
   3.1 s wall / 2.7 s CPU, and a 10 ms ticker thread alongside it stalled at most 38 ms. A warm cannot hold the
   heartbeat off for 120 s on its own.
2. **The log line reproduces exactly**, from real gunicorn, 4 workers, `gunicorn.conf.py` unchanged:
   `7067 texts cached ... (6788 from the shared file)` per fresh worker, plus 3 provider calls each. On one core
   (`taskset -c 0`, close to prod's 120%) each warm took 13.6-14.0 s, near prod's 17.5-21.8 s.
3. **Spec-key texts were never stored.** `engine.start_lookup_warm` warms `load_rows + list_resolver.spec_key_rows`
   (engine.py:1358-1364), but `sync_lookup_words` built documents from `load_rows` only, and `write_back` writes
   only texts a document already holds. So every fresh worker sent the 279 spec-key texts to Gemini.
4. **The load's CPU was pgvector's text parse.** cProfile: `pgvector.Vector._from_text` was 1.66 s of 2.4 s.
   Reading `vector_send(embedding)` (binary) and decoding with numpy: 0.19 s CPU against 1.67 s, bit-identical.
5. **A retiring worker hangs on exit (new finding, independent of the warm).** PyMuPDF 2.0 (PyPI 19 Oct;
   `requirements.txt` had an unpinned `PyMuPDF>=1.24`, the Dockerfile has no lock) builds an onnxruntime layout
   model at `import fitz` (flyer_extraction.py:63 -> pymupdf/__init__.py:343 -> layout `activate()`). Under
   `preload_app` the master owns that thread pool. A forked worker that exits runs onnxruntime's exit handler,
   which joins a thread only the master has (gdb: `__run_exit_handlers -> onnxruntime_pybind11_state.so ->
   std::thread::join -> futex wait`). The worker logs "Worker exiting", hangs until `WORKER TIMEOUT` (120 s)
   SIGABRTs it, and only then is its replacement booted. It hung in 3 of 9 bench runs on 2.0 and 0 of 8 on 1.28.2.
   In one run all 4 workers were stuck in that state for about 90 s with nothing serving. A HUP or a deploy stop
   retires every worker at once.

Not confirmed from prod: whether prod's pool emptied through (5) after the 16:45 HUP, or through OOM respawns
(#9 still had the +621 MB per-worker warm peak that #2007 removed). Crew asked the owner for the log grep.

## Fix

1. `sync_lookup_words` also keeps documents for `list_resolver.spec_key_rows(active_registry(db))`
   (lookup_word_store.py), so the 10-minute `lookup_words_sync` stores them and a fresh worker embeds 0 texts.
2. `load_lookup_vectors` reads `func.vector_send(embedding)` and decodes it with `np.frombuffer` (`_from_binary`).
3. `warm()` records, per model, the texts a failed or partial warm left uncached (`_gave_up`). A later warm that
   would only retry those texts is skipped for `WARM_RETRY_AFTER` (900 s); a text it never tried warms at once.
4. `PyMuPDF>=1.24,<2` in requirements.txt, guarded by
   `tests/test_gunicorn_conf.py::test_importing_pymupdf_starts_no_native_thread_pool_in_the_preloading_master`.
   The app never uses the layout model.

Not built, with the condition that would justify building it:

- **Delaying the start-up warm, or yielding between load batches:** with fixes 1-4, /health stayed under 0.5 s
  on one core through 14 recycles. Build it if a measured warm again pushes /health past 1 s.
- **One worker at a time embedding from the network (advisory lock):** a fresh worker now embeds nothing from
  the network once the sync has run. The remaining window is at most 10 minutes after a spec-registry change
  (279 texts, 3 calls per fresh worker, once per 900 s per worker). Build it if the store must be re-embedded
  from scratch (model switch) while the API serves.

## Proof (4 workers, one core, `GUNICORN_MAX_REQUESTS=100` so recycles and warms land while /health is polled every 100 ms for 180 s)

| | before (main + PyMuPDF 2.0, spec keys not stored) | after (this branch) |
|---|---|---|
| warm per fresh worker | 5.4-14.4 s | 0.4-1.2 s |
| provider calls | 27 | 0 |
| recycles / WORKER TIMEOUT | 5 / 4 | 14 / 0 |
| /health p99 / max | 179 ms / 7,220 ms | 75 ms / 469 ms |
| /health failures | 3 | 0 |

Plain boot, no recycling, one core: warm 13.6-14.0 s -> 1.2-1.4 s, /health max 1,068 ms -> 399 ms.

Tests: tests/chatbot/test_lookup_warm_storm.py (5, red first), the guard test above, plus the lookup / embedding /
span / list_resolver suites (48 files) and the gunicorn / uvicorn worker / heavy-work tests.
