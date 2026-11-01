/**
 * DEALER-PLANNING PR 2, R12: the stock pop-up on a line at a pool states figures that agree
 * with the suggestion, for both classes. Today a line's own pool row says "Available for
 * Project 30" while the Site pool subtotal under it, re-derived from the pool's net, says a
 * smaller figure, with nothing explaining the gap. The rows carry what the walk obeyed
 * (`available_for_project`, the line's own demand already added back), so the subtotal of a
 * section whose rows state it must print the same figure, and a row and its subtotal can no
 * longer disagree.
 *
 * Derivation: one pool row, on hand 30 and nothing owed but the line's own 15, so the walk's
 * figure for the line is 30 (its 15 added back to the true net of 15). The subtotal of a
 * single row is that row's figure. Written test-first; the subtotal still shows the share of
 * the NET (7) today.
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
    so_qty: '15',
    spo_qty: '0',
    available_qty: '15',
    incoming: [],
    where: 'site_pool',
    net: '15',
    net_of: 'pools',
    available_for_project: '30',
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

describe('R12: a line at its own pool reads one set of figures', () => {
  it('the pool subtotal states the same Available for Project as the row above it', () => {
    renderTable([ownPool()]);

    expect(screen.getByRole('table').textContent).toContain('30');
    expect(screen.getByTestId('stock-subtotal-available-for-project-pools').textContent).toBe('30');
  });

  it('a pool whose rows state different figures sums them in its subtotal', () => {
    renderTable([
      ownPool(),
      ownPool({ location: 'MWH', warehouse_id: 'wh-mwh', available_for_project: '10' }),
    ]);

    expect(screen.getByTestId('stock-subtotal-available-for-project-pools').textContent).toBe('40');
  });
});
