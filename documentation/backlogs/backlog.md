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
| BL-004 | **Enqueue the flyer read instead of holding the request** - the read is off the event loop but is still 15 to 60 s of foreground work with no progress feedback. When artwork rasterisation lands this becomes an enqueue returning 202 with a row to watch, as the catalogue PDF export already does. | `plans/dealer-kit/PLAN-flyer-read-hardening.md` | Medium | Open |
| BL-005 | **Collapse the two forked link-attachment browsers** - the shared picker now lives at `components/common/LinkAttachmentBrowserDialog.tsx` and is used by five modules, but near-identical forks remain under `master-data-management/products` and `marketing-management/promotions`. | `plans/dealer-kit/PLAN-flyer-read-hardening.md` | Low | Open |
| BL-006 | **A flyer whose mime was lost on import is unpickable** - the from-attachment route accepts NULL / `application/octet-stream`, but the picker filters on the six positive PDF spellings so those rows are never offered. Closing it needs a filename or extension filter on the attachments list, not a wider mime filter, which would list every binary blob in the library. | `plans/dealer-kit/PLAN-flyer-read-hardening.md` | Low | Open |
| BL-007 | **The library flyer read has no committed regression guard** - AC-A10 is met by a reproducible agent-browser evidence run only, because the branch's new Playwright spec was dropped under the standing order that no project carries a playwright trace. Give it a guard when the repo-wide replacement for the e2e specs is decided; the same decision covers the existing dealer-kit specs driving clicks through `dispatchEvent`, which bypasses actionability checks. | `plans/dealer-kit/PLAN-flyer-read-hardening.md` | Medium | Open |
| BL-008 | **Frontend tree is not Prettier-clean** - `sorento_crm_frontend/.prettierrc` now pins the measured prevailing style (single quotes, semis, printWidth 80, trailingComma all, no plugins), but `npm run format:check` still flags 1743 of ~2900 files, so no CI format gate exists. Closing it is a dedicated repo-wide `npm run format` PR (nothing else in it), then a `format:check` step in `.github/workflows/deploy.yml`. Also decide whether the three installed but inert prettier plugins (`@ianvs/prettier-plugin-sort-imports`, `prettier-plugin-organize-imports`, `prettier-plugin-tailwindcss`) are dropped or enabled in that same PR. | (none - tooling chore, PR "chore(frontend): add a Prettier config") | Low | Open |

> Seeded 2026-07-13 from in-flight work at the time of the documentation restructure. Historical
> plans predating this register carry their own inline "Deferred / follow-ups" sections; migrate
> those into rows here as each is next touched (going-forward, not a bulk sweep).
