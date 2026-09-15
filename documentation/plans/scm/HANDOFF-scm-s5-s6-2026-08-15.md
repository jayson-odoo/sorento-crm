# Handoff: SCM S5 + S6 state, 2026-08-15 (machine degraded mid-push)

Self-contained state document per the no-compact handoff rule. A fresh session can resume
from this file alone.

## Where everything is

| Slice | Branch | Worktree | Commit | State |
|---|---|---|---|---|
| S1+S2 agent master + dup lines | feat/scm-order-import-feedback | scm-import-feedback | pushed | PR #143 green, awaiting merge |
| S3+S4 async + standard modal | feat/scm-import-async | scm-import-async | 52dc35c98 pushed | PR #147 open (stacked on #143), CI runs after #143 merges |
| S5 PO/SPO structured history | feat/scm-po-spo-history | scm-s5-history | d9dafb630 LOCAL ONLY | committed, UNPUSHED (DNS broken) |
| S6 sales-agent screen | feat/scm-agent-master-ui | scm-s6-agents | 4f9d33457 LOCAL ONLY | committed, UNPUSHED (DNS broken) |

S5 and S6 both branch off feat/scm-import-async at 52dc35c98. PR chain when pushable:
S5 -> base feat/scm-import-async; S6 -> base feat/scm-import-async. Merge order:
143 -> 147 -> (148/149 in either order). Every merge deploys; merging is the captain's gate.

## What blocked the push (machine, not code)

macOS services degraded progressively during the evening (uptime ~6 days, load avg peaked 40):
sysmond gone, intermittent process-list failures, local user-name resolution broken (whoami
prints bare 501, plain psql fails; workaround: connect via TCP URL
postgresql://tehjayson@localhost:5432/...), and finally getaddrinfo broken for curl/git
(dscacheutil still resolves; curl/git cannot). Chrome/agent-browser cannot launch AT ALL
(instant silent exit 0) - this predates the DNS failure and blocked the S6 prod-build browser
pass. Almost certainly one root cause; a reboot is the likely fix and is the captain's call.
Note: openclaw-gateway process appeared around the same window at 100%+ CPU - unknown, flag it.

After reboot: push both branches, open the two PRs (bodies below), re-run the S6 browser pass.

## S5 summary (for the PR body)

Structured 27-column PO/SPO export accepted alongside the banded report; detection by row
shape; anchored SPO- prefix routes rows to scm_spo_history / scm_po_history source systems in
purchase_orders, closed/fully-received. Landing in spo_allocations rejected on 4 measured
grounds (PLAN amendment 10). Review BLOCKER fixed + mutation-proven: outstanding importer's
_closed_line revive path now excludes HISTORY_SOURCE_SYSTEMS (new module
app/services/scm/history_sources.py) on both PO and SO bindings - without it a later
outstanding upload could flip 2023 history lines into live supply (po_ordered_v). Currency-only
creditor folding; ambiguous creditor names report unmatched; migration 358 data-only alias
seed (single head, bootstrap_env replay); unit_cost NULL by design; Agent column on this book
is the creditor's shorthand, never fed to sales_agents. 27 new tests, 331 passed across
touched suites; full-file probe 27,192 rows -> 868 PO + 619 SPO in 20s, zero unmapped headers.
Known-open: PO list shows both source systems as "import" (PLAN amendment 20, future filter);
HistorySummary count tiles do not show the PO/SPO split (FE, deliberately out of this BE slice).

## S6 summary (for the PR body)

Minimal screen at master-data-management/sales-agents built at the SAME surface as the
unmerged AutoCount mirror page (same route file/paths/verbs/permission slugs; MirrorReadService
byte-identical; MirrorAnnotationUpdate + person_label(max 100) + demand_class with
extra=forbid kept; source literal widened for 'import'). Class write annotates the clicked row
via assert_demand_class, NOT the code-keyed set_demand_class (per-company unique means a
namesake shared row exists; mutation-proven). useSalesAgent/getSalesAgent/MirrorAnnotationPayload
kept so autocount's [id] page compiles on merge; four duplicate hunks + resolutions in PLAN
amendments 10-16. 16 pytest + 16 vitest green; S1 agent suites re-run green (31) on a
bootstrap_env scratch.

Verification done: dev-build real browser (pre-Chrome-breakage): sidebar entry renders under
Product Management after UoM, page reachable, list renders real rows (codes, Not set, Import,
Active), edit buttons present. Live API on the 8014 stack (real dev DB): list serialises
source=import rows with both new fields; PATCH happy 200 / refused-vocab 400 with allowed-list
message / extra key 422 / overlong label 422 max_length / revert 200; PATCH 401 under API-key
principal (edit is JWT-gated), GET 200. NOT done: prod-build browser modal round-trip
(Chrome cannot launch on this machine) - re-run after reboot, disclose in PR until then.

## Verification stacks (all pointed at dev DB sorento_ai_automation)

- 8013/3013: S3+S4 (scm-import-async), FE prod build, worker on redis db 8. Captain-facing.
- 8014/3014: S6 (scm-s6-agents), FE prod build on 3014 (next start), backend 8014.
- 8012/3012: captain's customer-audit stack (PR #146). Not mine to touch.
- Scratch DBs: sorento_s5_scratch, sorento_s6_scratch, sorento_s6_mig (bootstrap_env-built),
  sorento_customer_import_test. Redis dbs: 8 mine, 9 S5, 10 S6, 12 another lane.
- Worktree .env files are all local-only (untracked); scratch backups: scm-import-async has
  .env.pytest, scm-s6-agents has .env.pytest.s6, scm-s5-history has its own .env (scratch).

## Open items beyond push

- PRs #143 #146 #147 green/await captain merge. Deploy = merge; captain's gate.
- The 150 full-dir scm failures on S5's branch are the documented no-seed-data families
  (m0-m8, policy_config); every touched file passes. No strict base-branch baseline run was
  done (would need a throwaway checkout; do it if anyone doubts).
- Captain still to fill 38 demand_class values - now possible via the S6 screen once merged.
- Tickets to file when GitHub reachable: audit-logs RBAC gate; worker-audit + Complaint/Product
  CREATE hole; HistoryUploadDialog vitest flake (seen twice).
- Cleanup eventually: verification stacks, gitignored PII copies (.playwright-mcp/dealer-so.xlsx),
  scratch DBs, Playwright MCP leftovers in .playwright-mcp/ (tool retired per captain).
