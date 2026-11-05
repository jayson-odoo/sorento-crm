/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:15): the OI lines grid's search, State filter and
 * sort live in the URL (`view_q`, `view_state`, `view_sort`), so prev/next OI (which carries
 * `view_*`) and a reload open the next OI's lines filtered the same way.
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
  line({ id: 'r-pump', item_code: 'ZZT-PUMP', core_line_id: 'cl-3', line_no: 3, state: 'placed' }),
];

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinesTab lines={LINES} isLoading={false} rowSelection={{}} onRowSelectionChange={() => {}} />
    </QueryClientProvider>,
  );
}

const lastUrl = () => new URL(String(replaceSpy.mock.calls.at(-1)![0]), 'http://h');

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
});

describe('the lines view opens from the URL', () => {
  it('view_state applies the State filter (multi-select, comma-joined)', async () => {
    searchParamsValue = 'view_state=reserve%3Arequested%2Cplaced';
    renderTab();
    await screen.findByText('ZZT-REQUESTED');
    expect(screen.getByText('ZZT-PUMP')).toBeInTheDocument();
    expect(screen.queryByText('ZZT-PLAIN')).not.toBeInTheDocument();
  });

  it('view_q applies the search', async () => {
    searchParamsValue = 'view_q=pump';
    renderTab();
    await screen.findByText('ZZT-PUMP');
    expect(screen.queryByText('ZZT-PLAIN')).not.toBeInTheDocument();
    expect((screen.getByPlaceholderText('Search product...') as HTMLInputElement).value).toBe('pump');
  });

  it('view_sort applies the sort', async () => {
    searchParamsValue = 'view_sort=item_code%3Adesc';
    renderTab();
    await screen.findByText('ZZT-PUMP');
    const codes = screen
      .getAllByText(/^ZZT-/)
      .map((el) => el.textContent);
    expect(codes).toEqual(['ZZT-REQUESTED', 'ZZT-PUMP', 'ZZT-PLAIN']);
  });

  it('view_state wins over a ?reserve= preselect', async () => {
    searchParamsValue = 'reserve=needs_reserve&view_state=placed';
    renderTab();
    await screen.findByText('ZZT-PUMP');
    expect(screen.queryByText('ZZT-REQUESTED')).not.toBeInTheDocument();
  });
});

describe('changing the lines view writes the URL', () => {
  it('a State pick writes view_state and keeps the list params', async () => {
    searchParamsValue = 'page=2&limit=25&tab=lines';
    renderTab();
    await screen.findByText('ZZT-PLAIN');
    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]') as Element;
    fireEvent.click(trigger);
    const listbox = await screen.findByRole('listbox');
    fireEvent.click(within(listbox).getByRole('option', { name: 'Request to reserve' }));
    await waitFor(() => expect(lastUrl().searchParams.get('view_state')).toBe('reserve:requested'));
    expect(lastUrl().pathname).toBe('/project-sales/order-inquiries/oi-1');
    expect(lastUrl().searchParams.get('page')).toBe('2');
    expect(lastUrl().searchParams.get('tab')).toBe('lines');
  });

  it('a search writes view_q', async () => {
    renderTab();
    await screen.findByText('ZZT-PLAIN');
    fireEvent.change(screen.getByPlaceholderText('Search product...'), { target: { value: 'pump' } });
    await waitFor(() => expect(lastUrl().searchParams.get('view_q')).toBe('pump'));
  });

  it('a column header click writes view_sort and keeps the list params', async () => {
    // Review round (AC-1, sort): without this the sort silently stops surviving prev/next.
    searchParamsValue = 'page=2&tab=lines';
    renderTab();
    await screen.findByText('ZZT-PLAIN');
    // The header cell's drag handle is also role=button with the same text; the sort control
    // is the real <button> inside it.
    const header = screen
      .getAllByRole('button')
      .find((el) => el.tagName === 'BUTTON' && el.textContent?.trim() === 'Product');
    expect(header).toBeDefined();
    fireEvent.click(header!);
    await waitFor(() => expect(lastUrl().searchParams.get('view_sort')).toBe('item_code:asc'));
    expect(lastUrl().searchParams.get('page')).toBe('2');
    expect(lastUrl().searchParams.get('tab')).toBe('lines');
  });

  it('clearing the search drops view_q', async () => {
    searchParamsValue = 'view_q=pump&tab=lines';
    renderTab();
    await screen.findByText('ZZT-PUMP');
    fireEvent.change(screen.getByPlaceholderText('Search product...'), { target: { value: '' } });
    await waitFor(() => expect(replaceSpy).toHaveBeenCalled());
    expect(lastUrl().searchParams.has('view_q')).toBe(false);
    expect(lastUrl().searchParams.get('tab')).toBe('lines');
  });
});
