# Implementation status — SLA / notifications / KPI / PWA epic

Branch: **`feature/sla-notifications-pwa-epic`** (git worktree at `../sorento_crm-sla-epic`). **Not merged to main.** 15 commits (see `git log --oneline main..HEAD`).

Build order executed (dependency-correct, per your call): **31 → 28 → 29 → 30 → 32 → 33.**

## Per-ticket status

| Ticket | Scope | Automated gates (green now) |
|--------|-------|------------------------------|
| **31** | User↔RespondContact link, E.164 phone + unique, channel prefs, FE picker + toggles | pytest 19 · vitest 3 · tsc clean |
| **28** | Auto-scan tier-progression fix + `_escalate_tracker` + manual escalate endpoint/RBAC + FE button | pytest 12 (+31 existing SLA green) · vitest 2 · tsc clean |
| **29** | WhatsApp delivery channel on escalation + assignment (gated, 24h text/template, best-effort) | pytest 6 |
| **30** | Conversation SLA daily summary via WhatsApp bounded template (per-channel gating, idempotent) | pytest 5 |
| **32** | KPI aggregation service (summary/leaderboard/trend/tasks) + endpoints + RBAC + dashboard FE | pytest 5 · vitest 2 · tsc clean |
| **33** | Web push subscribe/unsubscribe + mirror-in-app + prune; PWA manifest + SW + opt-in control | pytest 4 · vitest 6 · tsc clean |

**My 6 epic backend test files: 51 passed in isolation, 0 failures in the full suite.** Full-suite totals: branch 47 failed / 27 err vs main baseline 48 / 24 — no regressions introduced (the remaining failures are pre-existing `audit_logs`/`lookup_bindings` global-listener flakiness documented in CLAUDE.md, present on main too).

## How to validate (commands)

```bash
cd ../sorento_crm-sla-epic            # the worktree
# backend unit (reuses main venv; app imported from cwd)
sorento_crm_backend $ <main-venv>/python -m pytest tests/test_phone_normalize.py tests/test_user_respond_link.py \
  tests/test_form_sla_manual_escalate.py tests/test_whatsapp_notifications.py \
  tests/test_sla_daily_summary_whatsapp.py tests/test_sla_kpi.py tests/test_web_push.py -q
# frontend
sorento_crm_frontend $ node_modules/.bin/tsc --noEmit
sorento_crm_frontend $ node_modules/.bin/vitest run   # (or the specific *.test.tsx added)
```

## Batched live gates — run on an isolated stack (NOT done autonomously to avoid disturbing your :3000/:8000)

These are real DoD items deferred to a controlled pass; code is complete + unit-proven:

1. **DB migrations** (PG): `alembic upgrade head` applies 234 (user link/prefs/unique phone), 235 (event `trigger`/`triggered_by_id` + clock-reset + `sla.form.escalate` grant-to-all), 236 (`sla.kpi.view` grant to management roles). Verify `\d users`, `\d conversation_sla_event_log`. Migration 234 fails loudly on duplicate normalized phones — resolve any before upgrading.
2. **Backfill**: `python scripts/backfill_user_respond_contact.py` (idempotent).
3. **Browser (Playwright MCP)**: User edit → phone + contact picker (no UUID) + toggles; Account → channel + push controls; Complaint/PR/etc → SLA tab → tracker → Escalate modal (reason required) → tier bumps; KPI Dashboard via sidebar (management only); PWA install + push (Lighthouse installability; iOS A2HS 16.4+).
4. **Worker + Respond.io**: WhatsApp sends run on the `respond_io` queue; need approved templates registered for use-cases `sla_escalation`, `sla_assignment`, `sla_daily_summary` (Meta/Respond ops). Code degrades gracefully without them.
5. **VAPID**: set `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` / `VAPID_SUBJECT` (backend) + `NEXT_PUBLIC_VAPID_PUBLIC_KEY` (FE) for real web push. Replace the favicon icon fallback in `manifest.webmanifest` with 192/512 maskable PNGs.

## Notes / deviations

- SLA routes are mounted under `/api/v1/sla-management/...` (not `/api/v1/sla/...` as some UAC curl snippets say). FE services use the correct paths.
- TCK-33 PWA scope is "install + web push, minimal offline" — the service worker has **no fetch handler** (so `/api/v1/*` is never cached); offline app-shell caching was intentionally not added (per the grilled decision).
- TCK-34 (feature voting, KPI-driven tasks, on-field Meta onboarding, HR module) remains parked backlog — not in scope.
