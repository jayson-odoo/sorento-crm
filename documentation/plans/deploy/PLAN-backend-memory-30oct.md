# Backend memory, round 2 (BACKEND-MEMORY, 30 Oct)

Status: investigating (2026-10-30), no code until crew OKs the plan. Track: TBD.
Lane: `crew/backend-memory` (sandbox branch `claude/backend-memory-investigation-0uuet8`)
Previous round: `PLAN-backend-memory-28oct.md` (#1950, gc.freeze + graceful TTOU, shipped in release #8).

## Why

Prod 30 Oct ~14:05 MYT, release #8 (main b07e71d5bf), 4 gunicorn workers: backend_blue
7.953 GiB, MemAvailable 3005 MB, swap full. Release #9 refused by the deploy memory guard
(2922 MB < DEPLOY_MIN_AVAILABLE_MB=4500).

Findings follow.
