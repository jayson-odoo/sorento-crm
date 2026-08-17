/**
 * Guard: the Stage-2 LIVE-backend run service never imports a `*MockStore` module.
 *
 * `reorderRunService.ts` is Phase 2 - it is wired to the real
 * `/api/v1/scm/reorder-runs/*` endpoints and its whole job is to return the
 * backend's payload untouched (see `reorderRunService.test.ts`, "grain
 * pass-through"). The bug the code review caught: the Stage-2 Phase-1 mock
 * commit (`b8f2a1eff`) added `import { withChannelNeeds, withRunGrain } from
 * '../lib/frontPlanningMockStore'` into this file and used it to OVERLAY real
 * API responses with mock `decision_grain` / channel figures - so a live run
 * from the real backend silently had its grain and channel readings rewritten
 * by fixture logic. The overlay was removed once the backend endpoints shipped
 * (`43e5e1a07`), but nothing pinned it staying gone.
 *
 * This is deliberately NOT a blanket rule across every file in `services/`:
 * `summaryOrderService.ts`, `coverageService.ts`, `poWorklistService.ts`,
 * `explainerService.ts` and `decisionService.ts` are still Phase 1 and
 * legitimately import their own mock store behind an explicit
 * `USE_..._MOCKS` flag - that is the documented, intentional prototype path,
 * not the bug. Only `reorderRunService.ts`, which claims to be the live
 * Stage-2 wiring, is asserted clean here.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const SERVICE_DIR = join(__dirname, '.');

/** Matches `from '...someMockStore'` regardless of relative depth or quote style. */
const MOCK_STORE_IMPORT = /from\s+['"][^'"]*MockStore['"]/;

describe('reorderRunService.ts - no mock-store overlay on the live Stage-2 run service', () => {
  it('imports nothing from a *MockStore module', () => {
    const source = readFileSync(join(SERVICE_DIR, 'reorderRunService.ts'), 'utf-8');
    const match = source.match(MOCK_STORE_IMPORT);
    expect(match).toBeNull();
  });

  it('does not reference frontPlanningMockStore, coverageMockStore, summaryOrderMockStore or poWorklistMockStore by name', () => {
    const source = readFileSync(join(SERVICE_DIR, 'reorderRunService.ts'), 'utf-8');
    expect(source).not.toMatch(/frontPlanningMockStore/);
    expect(source).not.toMatch(/coverageMockStore/);
    expect(source).not.toMatch(/summaryOrderMockStore/);
    expect(source).not.toMatch(/poWorklistMockStore/);
  });

  it('the guard pattern itself actually catches the regressed import shape', () => {
    // Proves MOCK_STORE_IMPORT is not vacuously true - it matches the exact line the
    // review found, and would fail this suite if reintroduced.
    const regressed = `import { withChannelNeeds, withRunGrain } from '../lib/frontPlanningMockStore';`;
    expect(regressed).toMatch(MOCK_STORE_IMPORT);
  });
});
