/**
 * SALES-INSIGHTS-P2 P3-1 (tester-first RED): Top selling items shows a "Product ranking" link back to the
 * leaderboard's Product view on Invoiced. The link is the strip the page passes to ReportPage as `belowHeader`.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/reports/ReportPage', () => ({
  ReportPage: ({ reportKey, belowHeader }: { reportKey: string; belowHeader?: React.ReactNode }) => (
    <div>
      <div data-testid="report-key">{reportKey}</div>
      {belowHeader}
    </div>
  ),
}));

import TopSellingItemsPage from './page';

describe('Top selling items page', () => {
  it('still renders the top_selling_items report', () => {
    render(<TopSellingItemsPage />);
    expect(screen.getByTestId('report-key').textContent).toBe('top_selling_items');
  });

  it('P3-1 offers a Product ranking link to the leaderboard Product view on Invoiced', () => {
    render(<TopSellingItemsPage />);
    const href = screen.getByRole('link', { name: 'Product ranking' }).getAttribute('href')!;
    const url = new URL(href, 'http://x');
    expect(url.pathname).toBe('/sales/leaderboard');
    expect(url.searchParams.get('basis')).toBe('invoiced');
    expect(url.searchParams.get('by')).toBe('product');
  });
});
