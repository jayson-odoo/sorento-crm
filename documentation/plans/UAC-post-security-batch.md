# UAC - Post-security batch

**Status:** Acceptance contract for `PLAN-post-security-batch.md` (locked scope). Written BEFORE implementation. Every item must pass its criteria - FE and BE - with NO regression, before handoff. Quality is the priority bar.

Legend: each criterion is **Given / When / Then**, testable. **REG** = explicit regression guard.

---

## Item 1 - Remove template/UI leaks (nav + footer)

UAC1.1 - **Given** any authenticated page, **when** the top bar renders, **then** the demo mega-menu entries "Profiles / My Account / Network / Apps" are GONE and a breadcrumb (or nothing) shows in their place. No console errors.
UAC1.2 - **Given** the footer, **when** it renders, **then** there is NO "Docs", "Purchase", "FAQ", or "License" link; **Support** (→`/ticket-management/tickets`) and the copyright remain.
UAC1.3 - **Given** mobile width (~390px) and desktop (~1280px), **then** the header and footer render cleanly (no overflow, no empty broken nav region).
UAC1.4 (REG) - **Given** the top-bar utilities that lived near the mega-menu (⌘⇧K search, Upload-activity, My-downloads, notifications, avatar, AI-assistant FAB), **then** ALL still render and function after the mega-menu removal.
UAC1.5 (REG) - **Given** sidebar navigation, **then** every existing sidebar group/leaf still routes correctly (mega-menu removal must not touch `MENU_SIDEBAR`).
UAC1.6 - Build passes; no new TypeScript/eslint errors; existing vitest suite green.

## Item 5 - Assistant must NOT leak the Outline URL

UAC5.1 - **Given** a "how do I…" question that resolves to a guide, **when** the assistant answers (REAL LLM call), **then** the answer contains NO `doc.foundryx.my` / Outline URL anywhere (body or links). Verified by string-scan of the response.
UAC5.2 - **Given** the same answer, **then** it still cites the in-app route(s) / `?guide_target` deep link and/or inline steps (the help is NOT degraded - links just point in-app, not to Outline).
UAC5.3 - **Given** the guide tool-result passed to the LLM, **then** the Outline `url` field is redacted/removed before the model sees it (model can't echo what it never got).
UAC5.4 (REG) - **Given** existing assistant flows (record-context answers, data-list answers, escalation guidance), **then** they still work; only the Outline URL is stripped. Existing assistant tests green.
UAC5.5 - Manual real-LLM transcript captured in the PR showing before(leaks)/after(clean) for at least 2 guide questions.

## Item 4-classifier - Skip record-classifier when no record open

UAC3c.1 - **Given** a page with NO record context (dashboard/settings/list), **when** the user asks anything, **then** `intent_is_record_class()` LLM call is NOT made (verified by log/counter or unit test), and the answer is produced via the normal path.
UAC3c.2 - **Given** a record detail page, **when** the user asks about the record, **then** the classifier IS called and behavior is IDENTICAL to today.
UAC3c.3 (REG) - No change to what the user can ask on any page; no answer-quality regression on either path. Existing assistant tests green.

## Item 3b - Strictly-keyed tool/guide result cache (within a turn)

UAC3b.1 - **Given** the same tool called twice with identical args within ONE assistant turn, **then** the second call is served from cache (verified by tool-invocation counter).
UAC3b.2 (REG - SECURITY) - **Given** two different users (or two different contacts) and the same tool+args, **then** they NEVER share a cache entry. Cache key MUST include `user_id` + `conversation_id` + `turn_id` + `tool_name` + `args_hash`. A test asserts user A's cached result is not returned to user B.
UAC3b.3 - **Given** a new turn, **then** the cache is empty (turn-scoped; no cross-turn staleness).
UAC3b.4 - Measurable: a repeated-tool question issues fewer live tool calls than before (logged).

## Item 3d - Eval harness (golden questions)

UAC3d.1 - **Given** the example NL questions in the module `data-analysis.md` guides, **then** a runnable harness executes them against the assistant (REAL LLM allowed) and reports per-question: routed tool/category + pass/fail + latency.
UAC3d.2 - Harness asserts routed tool CATEGORY (not exact prose), and is re-runnable to compare before/after any assistant change (regression baseline).
UAC3d.3 - Baseline captured and committed (results snapshot) so future changes can diff against it.

## Item 4 - Novice "what can the system do" + getting-started + publish guides

UAC4.1 - **Given** "what can this system do?" / "what can you help me with?" (REAL LLM), **then** the assistant returns a deterministic, friendly capability overview grouped by module with example questions - sourced from the capability endpoint, NOT hallucinated.
UAC4.2 - **Given** the capability answer, **then** it EXCLUDES admin/internal tools (`internal_admin.*`, skip-tools), shows friendly module names (no machine category codes), and no UUIDs/slugs.
UAC4.3 - **Given** `documentation/user-guides/_shared/getting-started-for-new-users.md`, **then** it exists: zero-knowledge orientation (login, sidebar map, where data lives, how to ask the assistant), house-style.
UAC4.4 - **Given** the Outline sync, **then** ONLY the ready guides (inventory, delivery-orders, product, sla, the new getting-started) publish; commercial guides do NOT.
UAC4.5 (REG - SAFEGUARD) - **Given** the sync script, **then** it RAISES if a held folder (`commercial`) is ever added to the publish allowlist - a test/dry-run proves the guard fires. Discipline alone is insufficient.

## Item 2 - Lookup SQL cleanup (defense-in-depth, optional/lowest)

UAC2.1 - **Given** `lookup_binding_service.py` distinct-values query, **then** it uses SQLAlchemy Core `select(col).where(col.isnot(None)).distinct()` (no f-string), behavior-identical (same rows, NULL filtering).
UAC2.2 (REG) - Existing lookup-binding tests green incl. the `_REGISTRY` test path; an added test attempts an injection-style table/column and confirms it's rejected by metadata validation (unchanged).

---

## Cross-cutting (ALL items)
- **No regression:** full `pytest` (note only the 10 pre-existing unrelated SLA failures + 4 pre-existing rbac sqlite-JSONB errors) and full `vitest` green; FE `npm run build` succeeds.
- **Browser verification:** Item 1 verified at desktop+mobile via Playwright (sidebar→page); Items 4/5 verified with REAL assistant calls.
- **Branch:** `feature/post-security-batch` (separate from `security/audit-hardening-20260629`).
- **Pre-existing not-mine working-tree changes** (`ai_assistant_service.py` `_current_date_directive`, `role-list.tsx`) checkpointed in their own commit first, never folded silently into a feature commit.
- Self-verify FE AND BE against every UAC line end-to-end before reporting done (per standing rule).
