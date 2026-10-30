# PLAN: Embeddings page perf (EMBED-PAGE-PERF)

Status: in progress (small fix track)

## Problem
Owner, 30 Oct on prod: System > Configuration > Embeddings, the Records tab sits empty while
`GET /api/v1/system/embeddings/overview` loads (`sorento_crm_backend/app/api/v1/system/embeddings.py:117`).

## Approach
Measure each query in the overview on seeded data (~25k documents/chunks), then fix the slow
ones with the simplest correct change (query shape / index). Red-first test pins the query shape.
