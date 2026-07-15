# Backlog Register

Deferred work, with linkage back to the plan that spawned it. Add a row when a plan consciously
defers something (hardening, follow-up, migration, prod backfill); close it when a later plan
picks it up. One register, single source of truth — do not scatter TODOs across plan docs.

Format: `ID · Title · Source plan · Priority · Status`. IDs are `BL-<NNN>`, monotonic.

| ID | Title | Source plan | Priority | Status |
|----|-------|-------------|----------|--------|
| BL-001 | **Run the import-tracking master-ref upsert backfill in prod** — the DO-import path fix (customer/transporter FK upsert) is merged but the idempotent JOIN-based backfill script has only run against the local prod-copy DB, not real prod. | `plans/PLAN-import-tracking-master-ref-upsert-backfill.md` | High | Open |
| BL-002 | **Security-cluster Phase 2 (authz / B)** — Phase 1 (bounded bugs C1–C4 + rate-limit A) landed on `fix/phase1-bounded-bugs`, unmerged. Phase 2 = the authz hardening (B), blocked on verifying the n8n `EXTERNAL_API_KEY_ACT_AS_USER_ID` act-as role has exactly the grants it needs. | `plans/PLAN-fix-security-cluster.md` | High | Open |
| BL-003 | **Form-SLA duplicate `sla_assigned` WhatsApp** — double send traced to `_active_tracker` ignoring `team_set_code` + stages sharing one `policy_id`. Fix pending a grill on the correct scoping. | `plans/PLAN-form-sla-dup-shared-policy.md` (to author) | Medium | Open |

> Seeded 2026-07-13 from in-flight work at the time of the documentation restructure. Historical
> plans predating this register carry their own inline "Deferred / follow-ups" sections; migrate
> those into rows here as each is next touched (going-forward, not a bulk sweep).
