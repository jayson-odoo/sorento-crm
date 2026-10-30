# UAC: Embeddings page perf (EMBED-PAGE-PERF)

- AC-EPP-1: every statement `GET /system/embeddings/overview` runs reads `embedding_chunks` through an
  index only (no heap scan); the counts it returns are unchanged. (`tests/test_embed_page_perf.py`)
- AC-EPP-2: the overview is not re-fetched on a timer while the Lookup words tab shows, nor while the
  browser tab is hidden; it re-fetches every 30 s while Records shows. (`useEmbeddings.poll.test.tsx`)
- AC-EPP-3: Start backfill / Embed missing / Save settings never start a second overview request while
  one is in flight. (`useEmbeddings.poll.test.tsx`)
- AC-EPP-4: on 469k chunks the overview answers in < 1 s cold.
