/**
 * AC-RF-81, AC-6..AC-9 (OI-RESERVE-ROUND): `?reserve=` on the detail page holds a list status
 * (written by the list) or request ids (written by the one-OI email link). A list status
 * keeps today's State preselect; request ids tick the Request dropdown and narrow the lines to
 * what those requests asked, in every state. Changing a filter keeps a list status in the URL
 * and drops only request ids.
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
import type { OrderInquiryReserveRequest } from '../../../../_shared/services/orderInquiryReserveService';

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
  line({ id: 'r-a', item_code: 'ZZT-FULL', core_line_id: 'cl-1', line_no: 1, reserve_state: 'reserved' }),
  line({ id: 'r-b', item_code: 'ZZT-REJECTED', core_line_id: 'cl-2', line_no: 2, reserve_state: 'declined' }),
  line({ id: 'r-c', item_code: 'ZZT-OPEN', core_line_id: 'cl-3', line_no: 3, reserve_state: 'requested' }),
  line({ id: 'r-d', item_code: 'ZZT-PLAIN', core_line_id: 'cl-4', line_no: 4 }),
];

const REQUESTS = [
  { id: 'req-2', ordinal: 2, rows: [{ row_id: 'r-c' }] },
  { id: 'req-1', ordinal: 1, rows: [{ row_id: 'r-a' }, { row_id: 'r-b' }] },
] as unknown as OrderInquiryReserveRequest[];

function renderTab(reserveRequests: OrderInquiryReserveRequest[] = REQUESTS) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinesTab
        lines={LINES}
        isLoading={false}
        rowSelection={{}}
        onRowSelectionChange={() => {}}
        reserveRequests={reserveRequests}
      />
    </QueryClientProvider>,
  );
}

const shown = (code: string) => screen.queryByText(code);

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
});

describe('AC-6 / AC-7 a request id in ?reserve= opens that request\'s lines', () => {
  it('shows only that request\'s lines in every state, Request #1 ticked, State empty', async () => {
    searchParamsValue = 'reserve=req-1';
    renderTab();
    await screen.findByText('ZZT-FULL');
    expect(shown('ZZT-REJECTED')).toBeInTheDocument();
    expect(shown('ZZT-OPEN')).not.toBeInTheDocument();
    expect(shown('ZZT-PLAIN')).not.toBeInTheDocument();
    const trigger = document.querySelector('#oi-lines-request-filter') as Element;
    expect(trigger.textContent).toMatch(/Request #1/);
    const state = document.querySelector('#oi-lines-state-filter') as Element;
    expect(state.textContent).not.toMatch(/Request to reserve/);
  });

  it('two ids tick both requests', async () => {
    searchParamsValue = 'reserve=req-1,req-2';
    renderTab();
    await screen.findByText('ZZT-FULL');
    expect(shown('ZZT-OPEN')).toBeInTheDocument();
    expect(shown('ZZT-REJECTED')).toBeInTheDocument();
    expect(shown('ZZT-PLAIN')).not.toBeInTheDocument();
  });

  it('clearing the dropdown shows every line', async () => {
    searchParamsValue = 'reserve=req-1';
    renderTab();
    await screen.findByText('ZZT-FULL');
    const trigger = document.querySelector('#oi-lines-request-filter') as Element;
    fireEvent.click(trigger);
    const listbox = await screen.findByRole('listbox');
    fireEvent.click(within(listbox).getByRole('option', { name: 'Request #1' }));
    await waitFor(() => expect(shown('ZZT-PLAIN')).toBeInTheDocument());
    expect(shown('ZZT-OPEN')).toBeInTheDocument();
  });
});

describe('AC-8 list statuses and unknown ids', () => {
  it.each(['needs_reserve', 'parked'])('%s still preselects Request to reserve', async (value) => {
    searchParamsValue = `reserve=${value}`;
    renderTab();
    await screen.findByText('ZZT-OPEN');
    await waitFor(() => expect(shown('ZZT-PLAIN')).not.toBeInTheDocument());
    expect(shown('ZZT-FULL')).not.toBeInTheDocument();
  });

  it.each(['reserved', 'notice_parked'])('%s preselects nothing', async (value) => {
    searchParamsValue = `reserve=${value}`;
    renderTab();
    await screen.findByText('ZZT-FULL');
    expect(shown('ZZT-PLAIN')).toBeInTheDocument();
    expect(screen.queryByText('No line matches the filter.')).not.toBeInTheDocument();
  });

  it('an id that is not one of this OI\'s requests narrows nothing', async () => {
    searchParamsValue = 'reserve=0b7f7a52-3c1e-4f0a-9d55-6f1c2a9e8b11';
    renderTab();
    await screen.findByText('ZZT-FULL');
    expect(shown('ZZT-PLAIN')).toBeInTheDocument();
    expect(shown('ZZT-OPEN')).toBeInTheDocument();
  });

  it('requests arriving after the first render still seed the filter', async () => {
    searchParamsValue = 'reserve=req-1';
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const tab = (requests: OrderInquiryReserveRequest[]) => (
      <QueryClientProvider client={client}>
        <OrderInquiryLinesTab
          lines={LINES}
          isLoading={false}
          rowSelection={{}}
          onRowSelectionChange={() => {}}
          reserveRequests={requests}
        />
      </QueryClientProvider>
    );
    const view = render(tab([]));
    await screen.findByText('ZZT-FULL');
    view.rerender(tab(REQUESTS));
    await waitFor(() => expect(shown('ZZT-PLAIN')).not.toBeInTheDocument());
    expect(shown('ZZT-REJECTED')).toBeInTheDocument();
  });
});

describe('AC-9 the Request dropdown', () => {
  it('is absent when the OI has no reserve request', async () => {
    renderTab([]);
    await screen.findByText('ZZT-FULL');
    expect(document.querySelector('#oi-lines-request-filter')).toBeNull();
  });

  it('is present, with Request #<ordinal> options sorted, when it has some', async () => {
    renderTab();
    await screen.findByText('ZZT-FULL');
    fireEvent.click(document.querySelector('#oi-lines-request-filter') as Element);
    const listbox = await screen.findByRole('listbox');
    const names = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(names).toEqual(['Request #1', 'Request #2']);
  });
});

describe('AC-RF-81 changing the line filter', () => {
  async function changeLineFilter() {
    await screen.findByRole('table');
    const trigger = document.querySelector('#oi-lines-state-filter') as Element;
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
    searchParamsValue = 'page=2&limit=25&reserve=req-1';
    renderTab();
    await changeLineFilter();
    await waitFor(() => expect(replaceSpy).toHaveBeenCalled());
    const url = String(replaceSpy.mock.calls[replaceSpy.mock.calls.length - 1][0]);
    expect(url).not.toContain('reserve=');
    expect(url).toContain('page=2');
    expect(url).toContain('limit=25');
  });
});
