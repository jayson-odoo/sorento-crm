/** PM-SIMPLIFY AC-L2 / AC-L3: per line ordered, scheduled, delivered, outstanding. */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { POProgress, POProgressLine } from '../../_shared/types/poProgress.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

import { POLinesProgressGrid, describeScheduleGap } from './POLinesProgressGrid';

function line(overrides: Partial<POProgressLine>): POProgressLine {
  return {
    key: 'k',
    po_line_id: 'pl',
    line_no: 1,
    product_id: 'p',
    product_code: 'SRTWC86',
    description: 'One piece WC',
    uom: 'SETS',
    ordered: '927',
    scheduled: '927',
    schedule_gap: '0',
    delivered: '0',
    outstanding: '927',
    next_delivery_date: '2027-01-07',
    deliveries: [],
    ...overrides,
  };
}

const progress: POProgress = {
  purchase_order_id: 'po1',
  schedule_version_id: 'sv',
  lines: [
    line({ key: 'a', line_no: 1, delivered: '100', outstanding: '827' }),
    line({
      key: 'b',
      line_no: 2,
      product_code: 'SRTWC8608-RL',
      description: 'Close coupled WC',
      ordered: '894',
      scheduled: '0',
      schedule_gap: '-894',
      outstanding: '894',
      next_delivery_date: null,
    }),
    line({
      key: 'c',
      line_no: 3,
      product_code: 'SRTFH12',
      description: 'Flexible hose',
      ordered: '10',
      scheduled: '10',
      delivered: '10',
      outstanding: '0',
      next_delivery_date: null,
      deliveries: [
        {
          phase_id: 'ph1',
          area_group: 'Tower',
          label: 'Level 2 & 7',
          delivery_date: '2027-01-07',
          units: '10',
          delivered: '10',
          sales_order_id: 'so1',
          provisional_ref: 'PSO-000002',
          sales_order_status: 'published',
        },
      ],
    }),
  ],
  areas: [],
  totals: {
    ordered: '1831',
    scheduled: '937',
    delivered: '110',
    outstanding: '1721',
    next_delivery_date: '2027-01-07',
    schedule_short_lines: 1,
    schedule_over_lines: 0,
  },
};

describe('POLinesProgressGrid', () => {
  it('shows the four figures, and says how much is not scheduled', () => {
    render(<POLinesProgressGrid progress={progress} isLoading={false} />);

    const row = screen.getAllByText('SRTWC8608-RL')[0].closest('tr') as HTMLElement;
    expect(within(row).getByText('894 not scheduled')).toBeInTheDocument();
    expect(row.className).toMatch(/bg-amber/);
    expect(describeScheduleGap(line({ schedule_gap: '1835' }))).toBe('1,835 more than ordered');
  });

  it('filters to what is still to deliver and to where the schedule differs', () => {
    render(<POLinesProgressGrid progress={progress} isLoading={false} />);
    const grid = screen.getAllByRole('table')[0];

    fireEvent.click(screen.getAllByRole('button', { name: 'Still to deliver (2)' })[0]);
    expect(within(grid).queryByText('SRTFH12')).toBeNull();

    fireEvent.click(screen.getAllByRole('button', { name: 'Schedule differs (1)' })[0]);
    expect(within(screen.getAllByRole('table')[0]).getByText('SRTWC8608-RL')).toBeInTheDocument();
    expect(within(screen.getAllByRole('table')[0]).queryByText('SRTWC86')).toBeNull();
  });

  it('expands a line to its deliveries', () => {
    render(<POLinesProgressGrid progress={progress} isLoading={false} />);

    fireEvent.click(screen.getByRole('button', { name: 'Show the deliveries of line 3' }));

    const deliveries = screen.getByTestId('line-deliveries-3');
    expect(within(deliveries).getByText('Tower, Level 2 & 7')).toBeInTheDocument();
    expect(within(deliveries).getByText('PSO-000002')).toBeInTheDocument();
  });
});
