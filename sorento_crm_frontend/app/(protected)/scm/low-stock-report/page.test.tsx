/**
 * W5 (owner hand test, 26 Sep): the low stock report is reached from a plan (Reorder planning
 * > Actions), never from the sidebar. The bare `/scm/low-stock-report` names no plan, so an
 * old bookmark goes to Reorder planning to pick one; `/scm/low-stock-report/<run>` (the daily
 * email's link) is unchanged.
 */
import { describe, it, expect, vi } from 'vitest';

const redirect = vi.fn((to: string) => {
  throw new Error(`NEXT_REDIRECT ${to}`);
});
vi.mock('next/navigation', () => ({ redirect: (to: string) => redirect(to) }));

import LowStockReportPage from './page';

describe('/scm/low-stock-report with no plan', () => {
  it('W5: redirects to Reorder planning', () => {
    expect(() => LowStockReportPage()).toThrow('NEXT_REDIRECT /scm/reorder');
    expect(redirect).toHaveBeenCalledWith('/scm/reorder');
  });
});
