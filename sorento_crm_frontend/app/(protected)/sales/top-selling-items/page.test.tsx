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

import { ReportParamsContext } from '@/components/reports/reportParamsContext';
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

  it('the Product ranking link carries the report\'s period, brand, category and company', () => {
    const params = {
      period: { kind: 'custom', from: '2026-10-01', to: '2026-10-31' },
      brand: ['b1', 'b2'],
      category: ['c1'],
      company: ['SOR', 'MCH'],
      channel: ['dealer'],
    };
    render(
      <ReportParamsContext.Provider value={params as never}>
        <TopSellingItemsPage />
      </ReportParamsContext.Provider>,
    );
    const url = new URL(screen.getByRole('link', { name: 'Product ranking' }).getAttribute('href')!, 'http://x');
    const sp = url.searchParams;
    expect([sp.get('basis'), sp.get('by'), sp.get('period'), sp.get('from'), sp.get('to')]).toEqual([
      'invoiced', 'product', 'custom', '2026-10-01', '2026-10-31',
    ]);
    expect(sp.getAll('brand')).toEqual(['b1', 'b2']);
    expect(sp.getAll('category')).toEqual(['c1']);
    expect(sp.getAll('company')).toEqual(['SOR', 'MCH']);
  });

  it('a year and a month range read as their dates', () => {
    const href = (period: unknown) => {
      const view = render(
        <ReportParamsContext.Provider value={{ period } as never}>
          <TopSellingItemsPage />
        </ReportParamsContext.Provider>,
      );
      const url = new URL(screen.getByRole('link', { name: 'Product ranking' }).getAttribute('href')!, 'http://x');
      view.unmount();
      return [url.searchParams.get('from'), url.searchParams.get('to')];
    };
    expect(href({ kind: 'year', year: 2026 })).toEqual(['2026-01-01', '2026-12-31']);
    expect(href({ kind: 'month_range', year: 2026, from_month: 2, to_month: 3 })).toEqual(['2026-02-01', '2026-03-31']);
  });
});
