/**
 * OI-WHOLE-SO-CANCEL v2 (crew decision 12 Nov), red: a waiting CANCELLED line matches BOTH the
 * "Line cancelled" and the "Waiting for CS" State-filter options (every shown value is
 * filterable); a date-waiting line matches "Waiting for CS" only. Harness from
 * `OrderInquiryLinesTab.stateFilter.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
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
    ack_state: 'awaiting',
    qty: '10',
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as OrderInquiryWorklistRow;
}

function renderTab(lines: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinesTab lines={lines} isLoading={false} rowSelection={{}} onRowSelectionChange={() => {}} />
    </QueryClientProvider>,
  );
}

const LINES = [
  line({ id: 'r-datew', item_code: 'ZZT-DATEWAIT', core_line_id: 'cl-1', line_no: 1, waiting_for_cs: true, waiting_change: { kind: 'date', was: '18/12/2026', now: '17/01/2027' } } as Partial<OrderInquiryWorklistRow>),
  line({ id: 'r-cancw', item_code: 'ZZT-CANCWAIT', core_line_id: 'cl-2', line_no: 2, line_cancelled: true, waiting_for_cs: true, waiting_change: { kind: 'line_removed', was: null, now: null } } as Partial<OrderInquiryWorklistRow>),
  line({ id: 'r-plain', item_code: 'ZZT-PLAIN', core_line_id: 'cl-3', line_no: 3 }),
];
const ALL = ['ZZT-DATEWAIT', 'ZZT-CANCWAIT', 'ZZT-PLAIN'];

async function pick(label: string) {
  renderTab(LINES);
  await screen.findByText('ZZT-PLAIN');
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]') as Element);
  const listbox = await screen.findByRole('listbox');
  fireEvent.click(within(listbox).getByRole('option', { name: label }));
}

describe('the State filter keeps both words for a waiting cancelled line', () => {
  it.each([
    ['Waiting for CS', ['ZZT-DATEWAIT', 'ZZT-CANCWAIT']],
    ['Line cancelled', ['ZZT-CANCWAIT']],
  ])('choosing "%s" shows exactly %j', async (label, expected) => {
    await pick(label);
    for (const code of ALL) {
      if (expected.includes(code)) expect(screen.getByText(code)).toBeInTheDocument();
      else expect(screen.queryByText(code)).not.toBeInTheDocument();
    }
  });
});
