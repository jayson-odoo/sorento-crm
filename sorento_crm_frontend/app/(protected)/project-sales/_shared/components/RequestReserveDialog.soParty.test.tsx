/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:35): "Request CS to reserve" (opened from the OI page
 * and from the Stock Debt drills) names the sales order it is for, with its customer and
 * project, in the shared `CUSTOMER / project` line.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('../services/fulfilmentPlanningService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/fulfilmentPlanningService')>();
  return { ...actual, getStockDetail: vi.fn(async () => ({ locations: [] })) };
});

import { RequestReserveDialog } from './RequestReserveDialog';

const row = (over: Record<string, unknown> = {}) => ({
  id: 'row-1', item_code: 'ZZT-1', product_id: 'p1', location: 'BRW-BB', delivery_date: '2027-01-01',
  qty: '30', linked_qty: '0', reserved_qty: '0', bundled_qty: '0', verb: 'ORDER', state: 'raised',
  reserve_state: null, so_number: 'SO419208', customer_name: 'ACME SDN BHD (PROJECT)', project_title: 'TAMAN JAYA',
  ...over,
});

function renderDialog(rows: unknown[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RequestReserveDialog inquiryId="oi-1" open onOpenChange={vi.fn()} rows={rows as never} />
    </QueryClientProvider>,
  );
}

describe('Request CS to reserve names its order', () => {
  it('shows the SO number and CUSTOMER / project', async () => {
    renderDialog([row()]);
    expect(await screen.findByText('SO419208')).toBeInTheDocument();
    expect(screen.getByText('ACME SDN BHD (PROJECT) / TAMAN JAYA')).toBeInTheDocument();
  });

  it('prints nothing extra when the rows name no order', async () => {
    renderDialog([row({ so_number: null, customer_name: null, project_title: null })]);
    await screen.findByText('Request CS to reserve');
    expect(screen.queryByText(/ \/ /)).not.toBeInTheDocument();
  });
});
