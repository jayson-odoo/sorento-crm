#!/usr/bin/env python3
"""Database and Redis round trips per API request (HA-CF-FAILOVER active-active, plan 12 / 9b).

In active-active a page served from node B pays one A-B round trip for every SQL statement its
API calls run (B's pgbouncer forwards to the primary on A) and for every Redis command. This
counts both, per request, with a real sign-in, so the added latency is

    added_ms_per_request = (sql_statements + redis_round_trips) x RTT_ms

Runs ONLY against a throwaway local database named *_smoke or *_ci (built with
scripts.bootstrap_env + scripts.seed_never_stuck_smoke), never a dev prod-copy:

    cd sorento_crm_backend
    DATABASE_URL=postgresql://.../sorento_latency_smoke DIRECT_URL=... SORENTO_ENV_FILE=.env.ci-tests \\
      venv/bin/python ../infra/rehearsal/measure_roundtrips.py --seed /tmp/lat-seed.json

An empty database gives a LOWER bound: list endpoints that run one query per row run more on
real data. Re-run it on a staging copy for prod-shaped numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from urllib.parse import urlparse

ENDPOINTS = [
    # Picked from the app's own GET routes (no path parameters): the screens staff open most.
    "/api/v1/health/role",
    "/api/v1/my-requests/me",
    "/api/v1/notifications/coverage/for-me",
    "/api/v1/order-management/customers/?page=1&limit=20",
    "/api/v1/order-management/customers/select",
    "/api/v1/order-management/orders/?page=1&limit=20",
    "/api/v1/order-management/orders/analytics",
    "/api/v1/master-data/products?page=1&limit=20",
    "/api/v1/complaints-management/complaints/?page=1&limit=20",
    "/api/v1/forms-management/forms/?page=1&limit=20",
    "/api/v1/inventory/stock-position?page=1&limit=20",
    "/api/v1/inventory/stock/dashboard",
    "/api/v1/procurement/purchase-requests?page=1&limit=20",
    "/api/v1/procurement/grn/?page=1&limit=20",
    "/api/v1/incoming-stock/list?page=1&limit=20",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True, help="the JSON scripts.seed_never_stuck_smoke wrote")
    ap.add_argument("--rtt", type=float, nargs="*", default=[0.5, 1.0, 2.0, 5.0], help="RTTs (ms) to tabulate")
    args = ap.parse_args()
    db = os.environ.get("DATABASE_URL", "")
    name = urlparse(db).path.lstrip("/")
    if urlparse(db).hostname not in ("localhost", "127.0.0.1") or not (name.endswith("_smoke") or name.endswith("_ci")):
        print("refused: DATABASE_URL must be a LOCAL *_smoke or *_ci database")
        return 2

    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    import redis.client

    counts = {"sql": 0, "redis": 0}

    @event.listens_for(Engine, "before_cursor_execute")
    def _sql(*_a, **_k):  # noqa: ANN001
        counts["sql"] += 1

    orig_exec = redis.client.Redis.execute_command
    orig_pipe = redis.client.Pipeline.execute

    def _redis_exec(self, *a, **k):  # noqa: ANN001
        counts["redis"] += 1
        return orig_exec(self, *a, **k)

    def _redis_pipe(self, *a, **k):  # noqa: ANN001
        counts["redis"] += 1  # one round trip for the whole pipeline
        return orig_pipe(self, *a, **k)

    redis.client.Redis.execute_command = _redis_exec
    redis.client.Pipeline.execute = _redis_pipe

    from fastapi.testclient import TestClient
    from app.main import app

    seed = json.load(open(args.seed))
    admin = seed["personas"]["admin"]
    rows = []
    with TestClient(app) as client:
        r = client.post("/api/v1/auth/login", json={"email": admin["email"], "password": seed["password"]})
        if r.status_code != 200:
            print(f"sign-in failed: {r.status_code} {r.text[:200]}")
            return 1
        token = r.json().get("apiToken") or r.json().get("access_token") or r.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}
        for path in ENDPOINTS:
            client.get(path, headers=headers)  # warm: caches, lazy imports
            samples = []
            for _ in range(3):
                counts["sql"] = counts["redis"] = 0
                t0 = time.perf_counter()
                resp = client.get(path, headers=headers)
                ms = (time.perf_counter() - t0) * 1000
                samples.append((counts["sql"], counts["redis"], ms, resp.status_code))
            sql = statistics.median(s[0] for s in samples)
            red = statistics.median(s[1] for s in samples)
            local_ms = statistics.median(s[2] for s in samples)
            rows.append((path, samples[-1][3], int(sql), int(red), local_ms))

    hdr = "| Request | HTTP | SQL | Redis | local ms | " + " | ".join(f"+ms at {r:g} ms RTT" for r in args.rtt) + " |"
    print(hdr)
    print("|" + "---|" * (5 + len(args.rtt)))
    for path, code, sql, red, ms in rows:
        added = " | ".join(f"{(sql + red) * r:.0f}" for r in args.rtt)
        print(f"| `{path}` | {code} | {sql} | {red} | {ms:.0f} | {added} |")
    ok = [r for r in rows if r[1] == 200]
    if ok:
        trips = [r[2] + r[3] for r in ok]
        print(f"\n200-answers: {len(ok)} of {len(rows)}; round trips per request median {statistics.median(trips):g}, max {max(trips)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
