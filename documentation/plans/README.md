# Plans — structure & conventions

Every non-trivial feature is planned here before code. Structure adopted from the FoundryX
shared-service model, adapted for Sorento's continuous (non-sprint) delivery.

## The triple (one per feature)

For each feature, in this order:

1. **`<slug>-acceptance-criteria.md`** — the **UAC, written FIRST**. Independently-verifiable
   Given/When/Then list, per-AC id (`AC-<NN>`), grouped by phase, tagged `[BE]` / `[FE]` /
   `[E2E]` / `[T]`. This is the **contract** the feature must satisfy.
2. **`PLAN-<slug>.md`** — the design that *fulfils* the UAC. Carries a `Status:` line kept current
   as work progresses, a decision log, and the phase breakdown.
3. **`<slug>-test-report.md`** — the Phase-2 verification, **keyed back to the UAC ids**
   (PASS / FAIL / DEFERRED per id). Real-click Playwright + pytest + vitest outcomes.

A plan does not ship without its UAC file. A slice is "done" only when its UAC ids pass the
Definition-of-Done gate in `PRINCIPLES.md`.

## Layout

```
documentation/plans/
  README.md                      ← this file
  PLAN-*.md                      ← ~78 historical flat plans (kept as-is; do NOT migrate)
  <domain>/                      ← NEW plans go in a domain cluster
    PLAN-<slug>.md
    <slug>-acceptance-criteria.md
    <slug>-test-report.md
```

**Domain clusters** (create the folder on first use; group by product domain, not by date):
`ai-assistant/`, `sla/`, `procurement/`, `complaints/`, `order-management/`, `resources/`,
`inventory/`, `forms/`, `integrations/`, `system-health/`, `portal/`, `master-data/`.

**Going-forward only.** The ~78 existing flat `PLAN-*.md` at the `plans/` root stay where they
are — they are historical and shipped. No retro-UAC. New work uses the triple in a cluster folder.

## Where things link

- **Deferred work** → log a row in `documentation/backlogs/backlog.md` with a link back to the
  source plan, so it isn't forgotten.
- **Methodology** governing the whole flow → `PRINCIPLES.md` (contract) +
  `documentation/development_process/METHODOLOGY.md` (detailed how-to).
- **Gotchas** discovered while building → `LESSONS-LEARNT.md` (root).
