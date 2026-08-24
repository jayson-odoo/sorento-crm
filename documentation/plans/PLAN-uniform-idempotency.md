# PLAN - Uniform request idempotency (duplicate-submit / network-slowness backstop)

**Status:** IMPLEMENTED + verified, 2026-06-30 (user-approved: 10s window, allowlist, token-key, wait→409, 2xx-only, `Idempotent-Replay` header). BE middleware + FE `useAction` primitive shipped on branch feat/complaint-do-auto-fulfilment (uncommitted). FE migration of remaining action buttons (approve/reject/process/close/escalate) is incremental - they are already covered by the BE allowlist. Original draft + grill verdicts retained below. Spawned from the form-SLA duplicate-assignment incident (PSSF26-0320): a double "Change to pending approval" click under a slow refetch fired two POSTs 3s apart → duplicate SLA assignment + duplicate WhatsApp. That specific bug is already fixed three ways (`_active_tracker` stage-scope, `set_pending_approval` no-op guard, FE ref-lock + await-refetch). This plan generalizes the defense so the **whole class** of bug - any mutating action replayed under network slowness / double-click / proxy retry / two tabs - cannot recur anywhere.

## Why

Patching individual buttons is whack-a-mole. The root condition is universal: a mutating POST can be delivered more than once for a single user intent (fast double-click before the disable renders, the FE re-enabling on stale data while a refetch lags, client/proxy/Cloudflare re-send on a slow upstream, two stale tabs). Any endpoint with a non-idempotent side effect (SLA emit, notification send, status transition, stock movement, money-like actions) can duplicate. Fix it structurally at the two chokepoints every request already flows through.

## Current state (measured this session)

- **FE single HTTP chokepoint:** `sorento_crm_frontend/lib/api.ts` → `apiFetch(path, init)` wraps `window.fetch`. Every feature service goes through it.
- **BE middleware stack:** `sorento_crm_backend/app/main.py` → `app.add_middleware(LoggingMiddleware)` etc. Clean insertion point.
- **Redis present:** `app/services/queue_service.py` already does `redis.from_url(settings.redis_url)`. Reuse with a separate `decode_responses=True` client for the idempotency cache.
- **Hand-rolled action buttons (no shared primitive):** ~4 today (`setSettingPending`, `setApproving`, `setRejecting`, `setEscalating`/`setFinalizing` …). No `useCreateMutation`/`useActionMutation` shared hook exists yet despite CLAUDE.md mentioning the pattern - action buttons are inline `onClick` with ad-hoc loading state.

## Target - two layers (defense in depth)

### Layer 1 - BE idempotency middleware (the guarantee)
A middleware that dedupes replays of the same action uniformly across **every** mutating endpoint.

- **Scope (revised per grill #1):** opt-in **allowlist** of transition / side-effect endpoints (mutating methods only). NOT global - see grill verdict #1 (global body-hash corrupts identical creates). Allowlist is a path-pattern set, easy to extend.
- **Key (revised per grill #2/#3):** `sha256(session_token : method : path : body_bytes)` - the *fingerprint*; token (not user_id) because middleware runs before auth deps. Body-hash is what collapses a double-click (two gestures). Optional explicit `Idempotency-Key` header → `sha256(session_token : method : path : header_key)` for high-value single-gesture retries.
- **Store:** Redis. Per key store a small record: `{state: in_progress|done, status, headers_subset, body, created_at}`.
- **Flow:**
  1. Compute key. `SET key {in_progress} NX EX <ttl>`.
  2. If `NX` succeeded → first request → run the handler → overwrite key with `{done, status, body}` (same TTL) → return response.
  3. If `NX` failed → a replay:
   - record `done` → return the cached `(status, body)` verbatim, **handler never runs again**.
   - record `in_progress` (first still running) → short bounded wait/poll (e.g. up to ~5s) for it to flip to `done`, then return cached; on timeout return `409 Conflict` (`{code: "duplicate_in_flight"}`).
- **TTL:** two tiers - auto/fingerprint mode short (default **10s**, configurable) so only accidental replays collapse and a legitimate identical re-submit minutes later still runs; explicit `Idempotency-Key` mode longer (default **24h**).
- **Exclusions (allowlist of "always re-runnable"):** endpoints that are legitimately repeatable or stream/large-body - file uploads, bulk imports, presign, export, anything reading a stream. Either skip by path-prefix allowlist or skip when `Content-Type` is multipart/stream or body > N KB. For large-body actions that still need protection, require the explicit header-key mode (don't hash the body).
- **Failure semantics:** if the handler raises / returns 5xx, **do not cache** (delete the key) so the user can retry. Only cache 2xx (and deterministic 4xx? - open question). On Redis outage, **fail open** (process normally; never block writes on a cache miss).
- **Multi-worker safe:** Redis `SET NX` is the cross-process lock; works across uvicorn workers and the API↔worker split.

### Layer 2 - FE shared action primitive
Bake the two UI guards into one reusable unit and migrate the hand-rolled buttons.

- `useAction()` hook (or `<ActionButton>`): synchronous `useRef` in-flight lock (kills same-tick double-fire - React state disable lags a render) + `disabled` while running + **awaits the dependent `invalidateQueries`** so the control re-enables only after the entity reflects the change (closes the stale-view window).
- `apiFetch`: for mutating methods, auto-generate + attach an `Idempotency-Key` per logical action. Open question: per-gesture key (needs the action layer to mint/reuse it on retry) vs let the BE fingerprint-mode handle it and only attach explicit keys for high-value actions.
- Migrate the ~4 existing inline action buttons to the primitive.

### Keep - domain guards as the floor
The transition-only emits (`set_pending` no-op guard) and stage-scoped lookups (`_active_tracker` + `team_set_code`) stay. Middleware is the net above; domain guards are the floor below. Conversation-SLA's idempotent-create and partial-unique-index pattern are the precedent.

## User-acceptance criteria (UAC)

1. A double-click on any mutating action button (fast same-tick OR 3s-apart under slow refetch) results in **exactly one** server-side execution and **one** side effect (one SLA assignment, one notification, one status transition).
2. Two browser tabs both submitting the same action within the window → one execution.
3. A client/proxy retry (same body) within the window → one execution; the retry receives the original response, not an error (unless still in-flight past the wait bound → 409).
4. A *legitimate* repeat of the same action after the window (e.g. re-sending an approval link an hour later) → runs normally, not blocked.
5. File uploads / bulk imports / exports → unaffected (not deduped by body hash).
6. Redis down → writes still succeed (fail-open); no user-facing breakage.
7. A handler that errors (5xx) → not cached; user can immediately retry.
8. No measurable latency added to the happy path (one Redis `SET NX` + one `SET`).
9. Existing endpoints’ responses byte-identical on first call (middleware transparent when no replay).
10. Regression: the form-SLA duplicate scenario (shared policy + double-click) stays single even with all three domain guards reverted - proving the middleware alone suffices.

## Test strategy (Phase 2)

- **pytest:** middleware unit - first vs replay (done), replay-while-in-flight (409 after wait), TTL expiry → re-runs, 5xx not cached, excluded path passes through, Redis-down fail-open. Integration: hammer `set-pending-approval` twice with same fingerprint → one tracker (and as UAC #10, with domain guards reverted).
- **vitest:** `useAction` - same-tick double invoke → one call; stays disabled until invalidate resolves.
- **playwright:** the exact repro from this session (double-click on a slow refetch) → one POST, one tracker. Promote the scratchpad repro.

## Rollout (incremental, low-risk)

1. Middleware in **observe-only** mode first (compute key, log would-be-dupes, don't block) → measure real duplicate rate in prod for a few days.
2. Flip to **enforce** for a small allowlist of high-value endpoints (approvals, SLA, Respond sends).
3. Expand to all mutating methods with the exclusion allowlist.
4. FE primitive + migrate buttons in parallel (independent of BE).

## ⚠️ Internal grill verdicts (2026-06-30) - design revised

1. **Global auto body-hash on all POSTs corrupts creates - REJECTED as default.** `POST /collection` twice with identical body = two legitimate creates; body-hash can't distinguish a double-submit bug from a deliberate identical create, so it would silently return the first response and drop the second create (user sees "2 created", DB has 1). **Revision:** BE dedupe is an **opt-in allowlist of transition / side-effect endpoints** (approve, send-for-approval/set-pending, process, close, escalate, reject, Respond sends) - endpoints where re-execution is semantically a no-op and duplication is the harm. Creates are covered by the FE primitive (Layer 2) + existing DB unique constraints, NOT by BE body-hash. "Uniform" now = FE primitive everywhere + an explicit, easy-to-extend BE allowlist for the dangerous actions.
2. **Middleware has no `user_id` - key on the session token instead.** `get_current_user` is a route dependency resolved AFTER middleware, and it's DB-session-token based. Middleware can't cheaply resolve the user. Key component = `sha256(session_token)` from the Authorization bearer / session cookie. Same browser session → same token → same key. (X-API-Key principal: include the key value; acceptable.)
3. **Body-hash, not per-gesture keys, is what dedupes a double-click.** Two clicks = two gestures = (if explicit keys) two keys → not deduped. Only `(token, method, path, body)` collapses two gestures. Explicit `Idempotency-Key` only dedupes a *single* gesture's network/proxy retries - keep it as an optional add-on for high-value actions, not the primary mechanism.
4. **Two TTLs.** In-flight lock TTL must exceed max handler duration (else the lock expires mid-flight and a replay re-runs → duplicate) - set ~60s. Result/dedupe-window TTL is separate and short (~10s default). On handler completion, write the result record with the short TTL.
5. **Request body must be buffered to hash it** - reading the stream in middleware consumes it; re-inject via `request._body` so the handler still reads it. Cap buffered size (e.g. 256 KB); over-cap → skip dedupe (or require explicit header-key mode).
6. **Additional exclusions:** streaming/SSE endpoints (AI assistant) - responses uncacheable; auth endpoints (login/logout/token) - they set cookies, never cache `Set-Cookie`. Plus the originals (uploads/imports/exports/presign).
7. **In-flight wait must be async** (`asyncio.sleep`, never block the loop) and short (~2s) before returning 409 - a long wait under a double-submit storm ties up workers.
8. **Cache only safe response parts** - status + body + content-type. Never cache `Set-Cookie` or auth headers. Cap cached response size; over-cap replay → 409 rather than a wrong/empty body.
9. **Still fail-open on Redis down, still don't cache 5xx, still 2xx-only** - unchanged, confirmed sound.

**Net design change:** Layer 1 is no longer "global on all mutating methods." It is an **allowlist-driven dedupe for harmful-to-duplicate action endpoints, keyed on (session-token, method, path, body-hash), with a 60s lock TTL + ~10s result window.** Layer 2 (FE primitive) is the uniform layer that safely covers every action including creates.

## Open questions for the user-grill

1. **Auto fingerprint vs explicit header-key as the default?** Auto = zero client work, covers everything, but body-hash can't tell two *intentional* identical clicks apart inside the window (collapses them - usually desired for mutations). Explicit = precise but needs FE to mint/persist keys per gesture. Recommend: **auto by default + explicit for high-value**.
2. **Window length** for auto mode - 10s? 30s? Longer = safer against slow retries, but more risk of collapsing a deliberate quick re-submit.
3. **Replay-while-in-flight:** wait-then-return-cached vs immediate `409`? Wait is friendlier; 409 is simpler. Recommend bounded wait (~5s) then 409.
4. **Cache 4xx?** Caching deterministic validation 4xx avoids re-running, but risks masking a now-valid retry. Recommend: cache 2xx only; never cache 5xx; pass 4xx through (cheap, no side effect).
5. **Exclusion list** - confirm uploads/imports/exports/presign are the right skips; any others?
6. **Scope key by tenant** too (when multi-tenant lands) - include `tenant_id` in the key now or later?
7. Do we want an explicit response header (`Idempotent-Replay: true`) so the FE/observability can see when a replay was served?

## Files (anticipated)

- BE: `app/middleware/idempotency_middleware.py` (new), register in `app/main.py`; small Redis helper (reuse `queue_service` client or a new `decode_responses=True` one); config flags in `app/config.py` (`IDEMPOTENCY_ENABLED`, `_MODE`, `_TTL_SECONDS`, `_EXCLUDE_PREFIXES`). Tests in `tests/test_idempotency.py`.
- FE: `lib/useAction.ts` or `components/common/ActionButton.tsx` (new); `lib/api.ts` header injection; migrate the ~4 inline action buttons. Tests alongside.
