# UAC: DEPLOY-SKIP-SNAPSHOT

1. DB at the new image's head: deploy log shows `no pending migrations: snapshot skipped`, no pg_dump runs, no dump file is written, the deploy completes with both memory guards and the Postgres check.
2. A migration pending (DB behind, a second head, an extra stamped row): snapshot taken before the new colour starts.
3. The heads read or the alembic_version read fails, is empty, or prints anything that is not a revision id: snapshot taken before the new colour starts.
4. A failed snapshot on a release with pending migrations still stops the deploy before the new colour starts.
5. HA mode reads alembic_version as OS and DB user postgres.

Tests: `sorento_crm_backend/tests/test_blue_green_deploy_guards.py`, section "DEPLOY-SKIP-SNAPSHOT".
