/**
 * DEALER-PLANNING PR 2, R12: the stock pop-up on a line at a pool states figures that agree
 * with the suggestion, for both classes. Today a line's own pool row says "Available for
 * Project 30" while the Site pool subtotal under it, re-derived from the pool's net, says a
 * smaller figure, with nothing explaining the gap.
 *
 * Captain's ruling, 1 Nov 2026: on a line STANDING ON ITS OWN POOL the own row and the subtotal
 * agree and follow the class: a project-class line shows the share, a retail line at its own
 * location shows Available. Everywhere else AC-2.6b stands (`CellStockTable.test.tsx`).
 *
 * Derivation: on hand 30, nothing owed but the line's own 15. The server states the walk's
 * figure on the row it stands on and on the subtotal: a project line's share is 15, a retail
 * line's Available is 30.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: vi.fn(() => new Promise(() => {})),
}));

import { CellStockTable } from './CellStockTable';
import type { BoardCellLocation } from '../../_shared/types/fulfilmentPlanning.types';

function ownPool(over: Partial<BoardCellLocation> = {}): BoardCellLocation {
  return {
    location: 'BRW',
    product_id: 'prod-1',
    warehouse_id: 'wh-brw',
    qty: '15',
    qty_demand: '15',
    qty_on_hand: '30',
    qty_reserved: '0',
    qty_free: '30',
    so_qty: '0',
    spo_qty: '0',
    available_qty: '30',
    incoming: [],
    // A line at its own pool reads that pool's row as `own`.
    where: 'own',
    net: '30',
    net_of: 'pools',
    stands_on_pool: true,
    ...over,
  } as BoardCellLocation;
}

function renderTable(rows: BoardCellLocation[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <CellStockTable locations={rows} />
    </QueryClientProvider>,
  );
}

function ownRowFigure() {
  const row = screen.getAllByRole('row').find((entry) => entry.textContent?.includes('BRW'));
  return row?.textContent ?? '';
}

describe('R12: a line at its own pool reads one set of figures', () => {
  it('a project-class line: the row and the subtotal state the share', () => {
    renderTable([ownPool({ available_for_project: '15', pool_subtotal_for_project: '15' })]);

    expect(ownRowFigure()).toContain('15');
    expect(screen.getByTestId('stock-subtotal-available-for-project-pools').textContent).toBe('15');
    expect(screen.getByRole('columnheader', { name: 'Available for Project' })).toBeTruthy();
  });

  it('a retail line at its own location: the row and the subtotal state Available', () => {
    renderTable([
      ownPool({
        available_for_project: '30',
        pool_subtotal_for_project: '30',
        own_pool_no_share: true,
      }),
    ]);

    expect(ownRowFigure()).toContain('30');
    expect(screen.getByTestId('stock-subtotal-available-for-project-pools').textContent).toBe('30');
    expect(screen.getByRole('columnheader', { name: 'Available for this line' })).toBeTruthy();
  });

  it('another pool beside the own one adds what the server states for the pools', () => {
    renderTable([
      ownPool({ available_for_project: '30', pool_subtotal_for_project: '40' }),
      ownPool({
        location: 'MWH',
        warehouse_id: 'wh-mwh',
        where: 'site_pool',
        stands_on_pool: false,
        available_for_project: '10',
      }),
    ]);

    expect(screen.getByTestId('stock-subtotal-available-for-project-pools').textContent).toBe('40');
  });

  it('a line not standing on a pool keeps AC-2.6b: the subtotal is the share of the net', () => {
    renderTable([
      ownPool({
        where: 'site_pool',
        stands_on_pool: false,
        net: '50',
        available_for_project: '50',
      }),
    ]);

    expect(screen.getByTestId('stock-subtotal-available-for-project-pools').textContent).toBe('25');
  });
});
