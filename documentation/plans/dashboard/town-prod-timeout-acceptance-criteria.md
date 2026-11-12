# UAC: Town snapshot statement timeout on prod (TOWN-PROD-TIMEOUT)

Plan: `PLAN-town-prod-timeout-09nov.md`.

- **AC-1 [T]** A build inside the tick runs with JIT off for its own transaction, on the primary.
- **AC-2 [T]** The same on the read replica branch.
- **AC-3 [T]** The build still runs with the 5 s statement timeout (existing test unchanged).
- **AC-4 [T]** Figures unchanged: `tests/town/test_town_snapshot_figures.py` green, the town total
  still equals the sales report.
- **AC-5 [M]** On `sorento_prod_1104`, every Sorento build statement runs under the 5 s timeout, with
  per-statement timings and planner costs reported in the crew-done report.
