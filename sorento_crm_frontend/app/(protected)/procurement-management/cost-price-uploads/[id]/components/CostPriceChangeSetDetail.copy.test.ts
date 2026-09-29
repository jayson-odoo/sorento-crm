/**
 * CostPriceChangeSetDetail header copy (#1288, Lane A): the header read "1 sheets, 3 rows"
 * on a one-sheet file (post-fix browser evidence, 23-applied-decisions-1280.png), the
 * same singular/plural defect "1 changes" had.
 */
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/cost-price-uploads/set-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { sheetsAndRowsLabel } from './CostPriceChangeSetDetail';

describe('sheetsAndRowsLabel', () => {
  it('is singular for one sheet and one row', () => {
    expect(sheetsAndRowsLabel(1, 1)).toBe('1 sheet, 1 row');
  });

  it('is plural otherwise', () => {
    expect(sheetsAndRowsLabel(1, 3)).toBe('1 sheet, 3 rows');
    expect(sheetsAndRowsLabel(5, 258)).toBe('5 sheets, 258 rows');
  });
});
