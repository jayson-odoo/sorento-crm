# BACKEND-MEMORY acceptance criteria

Plan: `PLAN-backend-memory-28oct.md`. Tests named per criterion.

- **BM-1** gunicorn freezes the preloaded heap before every fork (`gc.freeze()` in `pre_fork`), so a
  worker's garbage collector never walks, and never un-shares, the objects it inherited.
  `tests/test_gunicorn_conf.py::test_pre_fork_freezes_the_preloaded_heap`
- **BM-2** a worker retires itself after `max_requests` requests plus a random jitter of at least
  half the limit by default; both from the env, `GUNICORN_MAX_REQUESTS=0` turns it off.
  `tests/test_gunicorn_conf.py::test_max_requests_recycles_workers_by_default`,
  `::test_max_requests_env_override_and_zero_turns_recycling_off`,
  `::test_default_jitter_spreads_retirements_over_half_the_limit`
- **BM-3** the limit reaches the uvicorn server inside our worker class, and the 100 s graceful
  shutdown is kept. `tests/test_gunicorn_conf.py::test_the_worker_hands_the_request_limit_to_uvicorn`
- **BM-4** a self-retiring worker stops the inbox drains when its shutdown starts, before waiting on
  connections. `tests/test_uvicorn_worker.py::test_shutdown_stops_the_inbox_before_waiting_on_connections`
- **BM-5** through that shutdown gunicorn keeps hearing the worker's heartbeat while the drains
  wait runs off the event loop, never past `graceful_timeout`, and never while the loop itself is
  wedged. `tests/test_uvicorn_worker.py::test_the_heartbeat_keeps_going_through_the_drains_wait`,
  `::test_a_wedged_event_loop_gets_no_heartbeat`, `::test_the_heartbeat_stops_at_its_bound`,
  `::test_the_worker_serves_through_the_draining_server`
- **BM-6** the lookup warm honours `_CACHE_CAP` as the turn path does.
  `tests/chatbot/test_lookup_warm_retry.py::test_the_warm_honours_the_cache_cap`
- **BM-7** (evidence, not a test) on a local gunicorn with `GUNICORN_MAX_REQUESTS` small and
  connections held mid-request, workers retire with no `WORKER TIMEOUT` line (main's worker
  class: 2).
