/**
 * OI-WHOLE-SO-CANCEL v2 (F1, owner: "this not tallied"), red: the Lines tab's State filter must
 * offer the words the State column prints (the shared line status pill: To order, Waiting for
 * CS, Done, Rejected, SO cancelled, Line cancelled, Nothing to buy, the reserve words) and
 * choosing one must show exactly the lines that read that word. Today it offers the retired
 * row-state words (To buy, Partly on PO/SPO, On PO/SPO) and nothing for Waiting for CS.
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

const PRINTABLE_WORDS = [
  'To order', 'Waiting for CS', 'Done', 'Rejected', 'SO cancelled', 'Line cancelled',
  'Nothing to buy', 'Request to reserve', 'Reserved', 'Not reserved',
];

const LINES = [
  line({ id: 'r-wait', item_code: 'ZZT-WAITING', core_line_id: 'cl-1', line_no: 1, waiting_for_cs: true } as Partial<OrderInquiryWorklistRow>),
  line({ id: 'r-order', item_code: 'ZZT-TOORDER', core_line_id: 'cl-2', line_no: 2 }),
  line({ id: 'r-done', item_code: 'ZZT-DONE', core_line_id: 'cl-3', line_no: 3, ack_state: 'acknowledged' }),
  line({ id: 'r-res', item_code: 'ZZT-RESERVE', core_line_id: 'cl-4', line_no: 4, reserve_state: 'requested', requested_qty: '4' } as Partial<OrderInquiryWorklistRow>),
];
const ALL_CODES = ['ZZT-WAITING', 'ZZT-TOORDER', 'ZZT-DONE', 'ZZT-RESERVE'];

function openOptions() {
  const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]') as Element;
  fireEvent.click(trigger);
  return screen.findByRole('listbox');
}

describe('F1: the State filter tallies with the State column', () => {
  it('(a) offers only words the column can print, including Waiting for CS and To order', async () => {
    renderTab(LINES);
    await screen.findByText('ZZT-WAITING');
    const listbox = await openOptions();
    const labels = within(listbox).getAllByRole('option').map((o) => o.textContent?.trim() ?? '');

    for (const label of labels) {
      expect(PRINTABLE_WORDS, `"${label}" is not a word the State column prints`).toContain(label);
    }
    expect(labels).toContain('Waiting for CS');
    expect(labels).toContain('To order');
    expect(labels).toContain('Done');
  });

  it('the fixture reads as expected in the State column', async () => {
    renderTab(LINES);
    await screen.findByText('ZZT-WAITING');
    expect(screen.getAllByText('Waiting for CS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('To order').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Done').length).toBeGreaterThan(0);
  });

  it.each([
    ['Waiting for CS', ['ZZT-WAITING']],
    ['To order', ['ZZT-TOORDER']],
    ['Done', ['ZZT-DONE']],
    ['Request to reserve', ['ZZT-RESERVE']],
  ])('(b) choosing "%s" shows exactly the lines that read it', async (label, expected) => {
    renderTab(LINES);
    await screen.findByText('ZZT-WAITING');
    const listbox = await openOptions();
    fireEvent.click(within(listbox).getByRole('option', { name: label }));

    for (const code of ALL_CODES) {
      if (expected.includes(code)) {
        expect(screen.getByText(code)).toBeInTheDocument();
      } else {
        expect(screen.queryByText(code)).not.toBeInTheDocument();
      }
    }
  });
});
