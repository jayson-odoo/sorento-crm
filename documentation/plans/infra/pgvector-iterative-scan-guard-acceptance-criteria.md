# UAC: pgvector iterative-scan guard

- AC-1: With pgvector >= 0.8, a narrowed non-hot read still issues `SET LOCAL hnsw.iterative_scan = relaxed_order` (existing F-5 tests stay green).
- AC-2: With pgvector < 0.8 (version mocked to 0.7.x), no `iterative_scan` SET is sent, the read returns normally, and later statements in the same transaction succeed.
- AC-3: With no `vector` row in `pg_extension` (or an unparseable version), behaviour matches AC-2.
- AC-4: The version is read once per process; repeated reads do not re-query `pg_extension`.
- AC-5: An unsupported server logs exactly one WARNING per process, not one per query.
- AC-6: Both `EmbeddingReadService.search_current` and `entity_resolver._iterative_scan_for` go through the guard.
