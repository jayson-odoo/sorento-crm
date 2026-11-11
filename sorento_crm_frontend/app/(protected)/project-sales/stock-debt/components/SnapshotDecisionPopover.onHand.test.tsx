/**
 * RESERVE-DIALOG-ON-HAND (owner 11 Nov 2026, crew ruling (a)): the snapshot's Decide >
 * Reserve > From picker states the same plain on hand as every other reserve picker. The
 * REAL `useReserveRowOptions` runs here; only the stock-detail read and the save are mocked.
 * The fixture is 171 on hand with 6 owed on a non-transferable SO and 4 incoming, so the old
 * `available_qty` (169) differs from on hand.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/api', () => ({
  apiFetch: async () => ({ ok: false, json: async () => ({}) }),
}));

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: async () => ({
    product_id: 'prod-1',
    group: 'pools',
    locations: [
      {
        warehouse_id: 'wh-brw',
        location: 'BRW',
        qty_on_hand: '171',
        so_qty: '6',
        spo_qty: '4',
        available_qty: '169',
      },
    ],
  }),
}));

vi.mock('../hooks/useStockDebtSnapshots', () => ({
  useSetSnapshotDecision: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string;
    onChange: (value: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    'aria-label'?: string;
  }) => (
    <select
      aria-label={props['aria-label']}
      value={props.value ?? ''}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { SnapshotDecisionPopover } from './SnapshotDecisionPopover';
import type { SnapshotRow } from '../types/stockDebtSnapshot.types';

describe('SnapshotDecisionPopover: Reserve From states plain on hand', () => {
  it('offers BRW with its on hand, never on hand less SO plus SPO', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const row = {
      row_id: 'row-1',
      product_id: 'prod-1',
      decision: null,
      decision_warehouse_id: null,
      decision_warehouse_code: null,
      decision_note: null,
    } as unknown as SnapshotRow;
    render(
      <QueryClientProvider client={client}>
        <SnapshotDecisionPopover snapshotId="snap-1" row={row} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Decide' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Reserve' }));
    const from = screen.getByRole('combobox', { name: /from/i });
    expect(
      await within(from).findByRole('option', { name: /BRW\s+on hand 171/ }),
    ).toBeInTheDocument();
    expect(within(from).queryByRole('option', { name: /169/ })).not.toBeInTheDocument();
  });
});
