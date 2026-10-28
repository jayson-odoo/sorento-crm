# UAC: SPAN-PASS-PROD - one lookup warm per container (shared vector file)

Plan: `PLAN-span-pass-prod-28oct.md`. Owner ruling 28 Oct ~15:4x (via crew): Q2 (a) container-shared vector file +
lock. Paths under `sorento_crm_backend/`.

Why: each gunicorn worker (4 per colour, `gunicorn.conf.py:44`) warms its own per-process cache
(`head/lookup_lists.py:856`) at start-up (`main.py:415`) and on the first turns (`engine.py:1270,1335`), so a start or a
`chatbot_lookup_embedder` label flip sends ~4 x 4,652 texts to the embedding provider at once; one process alone hit
Gemini 429 at ~1.5k texts/min (entity-extract-match AC-S3-13).

## Behaviour (the background warm only: `_vector_embedder.fill`)

- **AC-1** A warm first reads the shared vector file of its embedding model and caches every vector it needs from it; it
  sends the provider only the texts the file does not hold. A second process (simulated: the per-process cache
  cleared) warming the same texts after the first sends ZERO provider requests.
- **AC-2** Warms of one model are serialised across processes by an exclusive file lock held for the whole
  read-embed-write: two warms started at once (two threads, separate lock handles) send each text to the provider once
  in total, not twice.
- **AC-3** After embedding, the warm writes the file atomically (temp file + rename): the vectors it read plus the ones it
  embedded. A reader never sees a half-written file.
- **AC-4** A warm that fails part-way (rate limit after the retries, or any other provider error) still writes the
  chunks it stored before re-raising, so the next warm (this process or another) sends only the rest. The lock is
  always released (including on error).
- **AC-5** The file is per embedding model (the model name is part of the file name): a `gemini-embedding-001` warm never
  reads `text-embedding-3-small` vectors, and the other way round. Within a file, a vector is keyed by the SHA-1 of its
  text (no text is written in clear).
- **AC-6** Vectors read from the file are the stored unit float32 vectors: the meaning scores of a turn are the same as
  with vectors embedded in-process.
- **AC-7** Advisory: a missing, unreadable or corrupt file, a lock or write failure logs a WARNING and the warm goes on
  as today (embeds what it needs); it never fails the warm on its own and never raises out of `warm`.
- **AC-8** Location: env `CHATBOT_LOOKUP_VECTOR_DIR`, default the system temp dir (inside a container: shared by its
  workers, gone when the container is replaced). `off` / `0` / `false` / `no` turns the shared file off (today's
  behaviour, no file, no lock). `tests/conftest.py` points it at a per-test temp dir or turns it off.
- **AC-9** The file holds at most `_CACHE_CAP` vectors; when the merge would exceed it, only the vectors of the texts
  this warm asked for are written.
- **AC-10** The turn path is unchanged: `embed()` (a turn's uncached rows) and `pieces` (a message's pieces) never read
  or write the file and never wait on the lock.
- **AC-11** The finished-warm INFO line also says how many texts came from the shared file:
  `lookup lists warm: N texts cached on <model> in S s (F from the shared file)`.

## Out of scope

Cross-container sharing (blue and green each warm once), a Postgres/Redis vector store (trigger: a measured 429 at one
warm per container), n-gram Gemini floors (Q4 (a)).
