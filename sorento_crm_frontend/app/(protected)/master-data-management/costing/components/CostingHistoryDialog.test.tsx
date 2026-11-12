/** The history dialog shows when a change happened, date and time, in Malaysia time (round 3). */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({ getCostingRowHistory: vi.fn() }));
vi.mock('../services/costingService', () => service);

import CostingHistoryDialog from './CostingHistoryDialog';

beforeEach(() => {
  vi.clearAllMocks();
  service.getCostingRowHistory.mockResolvedValue({
    data: [{ changed_at: '2026-11-11T05:26:00Z', user_name: 'Hana Tester', field: 'markup_pct', old: 8, new: 10 }],
  });
});

describe('history timestamps', () => {
  it('renders 05:26 UTC as 11/11/2026 and 1:26 pm Malaysia time', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <CostingHistoryDialog open onOpenChange={vi.fn()} productId="p1" productCode="CGB9032B" partyId={null} />
      </QueryClientProvider>,
    );
    const stamp = await screen.findByText(/11\/11\/2026/);
    expect(stamp.textContent).toMatch(/11\/11\/2026,? 1:26\s?pm/i);
  });
});
