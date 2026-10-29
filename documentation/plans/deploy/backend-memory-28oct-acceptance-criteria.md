# BACKEND-MEMORY acceptance criteria

Plan: `PLAN-backend-memory-28oct.md`. Tests named per criterion.

- **BM-1** gunicorn freezes the preloaded heap before every fork (`gc.freeze()` in `pre_fork`), so a
  worker's garbage collector never walks, and never un-shares, the objects it inherited.
  `tests/test_gunicorn_conf.py::test_pre_fork_freezes_the_preloaded_heap`
- **BM-5** a worker retired with `TTOU` keeps gunicorn's heartbeat through its shutdown while the
  drains wait runs off the event loop, never past `graceful_timeout`, and never while the loop
  itself is wedged; gunicorn's worker class serves through that server.
  `tests/test_uvicorn_worker.py::test_the_heartbeat_keeps_going_through_the_drains_wait`,
  `::test_a_wedged_event_loop_gets_no_heartbeat`, `::test_the_heartbeat_stops_at_its_bound`,
  `::test_the_worker_serves_through_the_draining_server`
- **BM-6** the lookup warm honours `_CACHE_CAP` as the turn path does.
  `tests/chatbot/test_lookup_warm_retry.py::test_the_warm_honours_the_cache_cap`
- **BM-7** (evidence, not a test) on a local gunicorn with `--timeout 20` and connections held
  mid-request, a `TTOU` retires the oldest worker with no `WORKER TIMEOUT` line (main's worker
  class: one).

BM-2 to BM-4 (`max_requests`, its jitter, the shutdown's own inbox stop) were dropped after the
owner's prod numbers showed warm-up, not a leak.
