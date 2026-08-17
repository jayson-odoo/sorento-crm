/**
 * ============================================================================
 * PLAN-GRAIN POLICY SETTING - MOCK STORE (Phase 1 only)
 * ============================================================================
 * The admin plan-grain policy field (plan section 5.1, AC-F01) rides the EXISTING
 * settings blob: `GET /api/v1/user-management/settings/` returns `plan_grain` and
 * `POST /settings/general` accepts it. No new route and no new gated GET.
 *
 * Until slice S2-BE-2 adds the column, the blob carries no `plan_grain`, so while
 * `USE_PLAN_GRAIN_MOCKS` is true this store answers for it: the read falls back to
 * the value chosen in this browser session (or the rollout default, Product), and
 * the write remembers it here instead of being sent to a server that would ignore
 * the field. Phase 2 flips the flag to false and DELETES this file; the settings
 * page keeps reading `settings.planGrain` and keeps posting `plan_grain`, so
 * nothing about the form changes.
 *
 * What this setting does NOT do, and must never grow into: it is not a per-run
 * selector. It applies to runs created AFTER it is saved, and an existing run keeps
 * the grain it was stamped with at creation (AC-F10).
 * ============================================================================
 */
export type PlanGrainSetting = 'product' | 'location';

/** Phase-1 flag. Phase 2 sets this false and deletes the file. */
export const USE_PLAN_GRAIN_MOCKS = true;

/** The rollout default, per plan section 5.1. */
export const DEFAULT_PLAN_GRAIN: PlanGrainSetting = 'product';

/** Chosen in this browser session. Dies with the tab, the honest limit of a mock. */
let sessionPlanGrain: PlanGrainSetting | null = null;

/** What the settings form should show. */
export function mockPlanGrain(saved: string | null | undefined): PlanGrainSetting {
  if (saved === 'product' || saved === 'location') return saved;
  return sessionPlanGrain ?? DEFAULT_PLAN_GRAIN;
}

/** Remember what was saved, so the form comes back showing it. */
export function rememberPlanGrain(next: PlanGrainSetting): void {
  sessionPlanGrain = next;
}

/** Drop the session value. Used by tests to keep cases independent. */
export function resetMockPlanGrain(): void {
  sessionPlanGrain = null;
}
