# PLAN: LOOKUP-WARM-STORM - lookup-list warm must not storm fresh workers

Status: in progress (small fix track, URGENT hotfix; no migration, no auth change)

## Incident

Prod, 30 Oct ~17:15-17:22 MYT, after release #9 (fresh green colour, 4 gunicorn workers): API
timed out ~10 min, backend CPU 120%, DB idle. Log flooded with
`lookup lists warm: 7067 texts cached on gemini-embedding-001 in 17.5-21.8 s (6788 from the shared file)`
plus many `batchEmbedContents` calls. Self-recovered.

## Fix (to be filled with measured facts as the lane proceeds)

1. Spec-key texts persist in the shared vector file too: a fresh worker embeds 0 from the network.
2. The warm is cheap / GIL-friendly: no per-float Python objects on decode; yields between batches.
3. Per-process "tried recently" guard so a failed / partial warm is not retried every turn.
4. Start-up warm runs after the worker serves, at low priority, one worker at a time from network.

## Proof

Boot 4 workers locally on dev-size data, measure warm time, CPU and /health latency during warm.
Target: /health < 1 s throughout, no WORKER TIMEOUT.
