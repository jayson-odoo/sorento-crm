# Backend memory, round 2 (BACKEND-MEM-2)

Status: investigating (2026-10-30). No code until crew OKs the plan.
Lane: `crew/backend-mem-2` (sandbox branch `claude/backend-mem-investigation-o09ezl`)
Previous round: `PLAN-backend-memory-28oct.md`, PR #1950 (gc.freeze, graceful TTOU).

## Why

Prod 30 Oct ~14:05 MYT (release #8, includes #1950, 4 gunicorn workers): backend_blue 7.95 GiB,
host available 3,005 MB, swap full. Release #9 refused by the deploy memory guard (2,922 MB
available < DEPLOY_MIN_AVAILABLE_MB=4500).

## Findings

(in progress)
