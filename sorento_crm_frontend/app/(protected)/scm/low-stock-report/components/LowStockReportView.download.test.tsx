/**
 * Review B2 (AC-14): Download sends the request the view ON SCREEN answers
 * (`useLowStockView().shownRequest`), never the page's live split and filters. The two only
 * differ while a change settles, and `LowStockReportView.test.tsx` pins that Download is held
 * back then; this file pins the other half on its own, with the hook fixed to a settled view
 * whose request differs from the page's opening state, so a Download that read the live state
 * would send the wrong file.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { LowStockRequest, LowStockView } from '../types/lowStockReport.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/low-stock-report/run-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, children }: { title: React.ReactNode; children?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      {children}
    </header>
  ),
}));

const RUN_ID = '0b6f3c8e-1d2a-4c5b-9e7f-123456789abc';

const shownRequest: LowStockRequest = {
  split: 'category',
  suppliers: ['Kohler'],
  categories: ['BASIN'],
};

const shownView: LowStockView = {
  run: { run_id: RUN_ID, as_of: '2026-09-26', generated_at: null },
  split: 'category',
  columns: ['Item code', 'Description', 'BRW on hand'],
  rows: [['A-1', 'Basin', 3]],
  sheets: [
    { title: 'BASIN - Low', row_indexes: [0], low: true },
    { title: 'BASIN', row_indexes: [0], low: false },
  ],
  facets: {
    suppliers: [{ key: 'Kohler', rows: 1, low: 1 }],
    categories: [{ key: 'BASIN', rows: 1, low: 1 }],
  },
  counts: { rows: 1, low: 1, sheets: 2 },
  over_cap: false,
  max_rows: 5000,
  filename: 'low-stock-26092026.xlsx',
};

vi.mock('../hooks/useLowStockView', () => ({
  useLowStockView: () => ({
    data: shownView,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    shownRequest,
    settling: false,
  }),
}));

const start = vi.fn();
vi.mock('../hooks/useLowStockDownload', () => ({
  useLowStockDownload: () => ({ start, preparing: false }),
}));

import { LowStockReportView } from './LowStockReportView';

describe('LowStockReportView Download', () => {
  it('sends the request the view on screen answers, not the live split and filters', async () => {
    render(<LowStockReportView runId={RUN_ID} />);

    await userEvent.click(screen.getByRole('button', { name: /Download/ }));

    expect(start).toHaveBeenCalledWith({
      split: 'category',
      suppliers: ['Kohler'],
      categories: ['BASIN'],
      runId: RUN_ID,
    });
  });
});
