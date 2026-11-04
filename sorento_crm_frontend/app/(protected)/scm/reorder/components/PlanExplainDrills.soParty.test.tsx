/**
 * OI-UX-FILTER-SNAPSHOT: the Net drill names each open sales order with its customer and
 * project, in the one `CUSTOMER / project` line.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const useExplainNet = vi.fn();
vi.mock('../hooks/useDrills', () => ({
  useExplainNet: (...a: unknown[]) => useExplainNet(...a),
  useExplainDemand: () => ({ data: undefined, isLoading: false, isError: false }),
}));

import { NetDrill } from './PlanExplainDrills';
import type { M8PlanRow } from '../lib/planRow';

const net = (sos: unknown[]) => ({
  on_hand: 10,
  on_order: 0,
  po_ordered: 0,
  committed: 17,
  net: -7,
  committed_sos: sos,
});

describe('NetDrill open sales orders', () => {
  it('prints customer and project beside each order', () => {
    useExplainNet.mockReturnValue({
      data: net([
        {
          so_number: 'SO-M8-001',
          qty: 12,
          customer_name: 'Alpha Debtor',
          project_label: 'Tuju Residences',
          order_date: '2026-07-02',
        },
        { so_number: 'SO-M8-002', qty: 5, customer_name: 'Beta Trading', order_date: null },
      ]),
      isLoading: false,
      isError: false,
    });
    render(<NetDrill row={{ id: 'r1' } as unknown as M8PlanRow} />);

    expect(screen.getByText('Alpha Debtor / Tuju Residences')).toBeInTheDocument();
    expect(screen.getByText('Beta Trading / -')).toBeInTheDocument();
  });
});
