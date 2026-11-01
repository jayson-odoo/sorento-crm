/**
 * AC-RF-80, 81, 83: `?reserve=` on the detail page holds a list status (written by the
 * list) or a request id (written by the one-OI email link). The Lines tab preselects
 * "Request to reserve" for a request id and for the statuses whose lines still need an
 * answer, never for the answered ones; changing the line filter keeps a list status in the
 * URL (so the pager asks about the same list) and drops only a request id.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let searchParamsValue = '';
const replaceSpy = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: (...args: unknown[]) => replaceSpy(...args) }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function line(over: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as OrderInquiryWorklistRow;
}

const LINES = [
  line({ id: 'r-req', item_code: 'ZZT-REQUESTED', core_line_id: 'cl-1', line_no: 1, reserve_state: 'requested' }),
  line({ id: 'r-plain', item_code: 'ZZT-PLAIN', core_line_id: 'cl-2', line_no: 2 }),
];

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinesTab
        lines={LINES}
        isLoading={false}
        rowSelection={{}}
        onRowSelectionChange={() => {}}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
});

describe('AC-RF-80 / AC-RF-83 what ?reserve= preselects', () => {
  it.each([
    ['a request id', '0b7f7a52-3c1e-4f0a-9d55-6f1c2a9e8b11'],
    ['needs_reserve', 'needs_reserve'],
    ['parked', 'parked'],
  ])('%s preselects Request to reserve', async (_name, value) => {
    searchParamsValue = `reserve=${value}`;
    renderTab();
    await screen.findByText('ZZT-REQUESTED');
    await waitFor(() => expect(screen.queryByText('ZZT-PLAIN')).not.toBeInTheDocument());
  });

  it.each(['reserved', 'notice_parked'])(
    '%s does not preselect it (those lines are already answered)',
    async (value) => {
      searchParamsValue = `reserve=${value}`;
      renderTab();
      await screen.findByText('ZZT-REQUESTED');
      expect(screen.getByText('ZZT-PLAIN')).toBeInTheDocument();
      expect(screen.queryByText('No line matches the filter.')).not.toBeInTheDocument();
    },
  );
});

describe('AC-RF-81 changing the line filter', () => {
  async function changeLineFilter() {
    await screen.findByText('ZZT-REQUESTED');
    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]') as Element;
    fireEvent.click(trigger);
    const listbox = await screen.findByRole('listbox');
    fireEvent.click(within(listbox).getByRole('option', { name: 'Done' }));
    // The choice has landed once the trigger names it.
    await waitFor(() => expect(trigger.textContent).toMatch(/Done/));
  }

  it('keeps reserve=needs_reserve and the list params in the URL', async () => {
    searchParamsValue = 'page=2&limit=25&reserve=needs_reserve';
    renderTab();
    await changeLineFilter();
    for (const [url] of replaceSpy.mock.calls) {
      expect(String(url)).toContain('reserve=needs_reserve');
      expect(String(url)).toContain('page=2');
    }
  });

  it('drops only a request id, and keeps the other params', async () => {
    searchParamsValue = 'page=2&limit=25&reserve=0b7f7a52-3c1e-4f0a-9d55-6f1c2a9e8b11';
    renderTab();
    await changeLineFilter();
    await waitFor(() => expect(replaceSpy).toHaveBeenCalled());
    const url = String(replaceSpy.mock.calls[replaceSpy.mock.calls.length - 1][0]);
    expect(url).not.toContain('reserve=');
    expect(url).toContain('page=2');
    expect(url).toContain('limit=25');
  });
});
