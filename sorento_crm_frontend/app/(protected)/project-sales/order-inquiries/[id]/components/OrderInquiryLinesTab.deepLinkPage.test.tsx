/**
 * SO-LINE-OI-STATUS-UNIFY crew pass (5 Nov 2026), fix (2): the SO line's OI link
 * (`?row=<id>`) into an OI with more than one page of lines (OI-2609-0016, 51 lines) lands
 * on page 1 or flashes the row then snaps back to page 1. The landing must open the page
 * holding the line, keep the highlight, and stay there when the lines refresh.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const nav = vi.hoisted(() => ({ params: 'row=row-40' }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(nav.params),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));

import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function lines(): OrderInquiryWorklistRow[] {
  return Array.from({ length: 60 }, (_, index) => {
    const no = index + 1;
    return {
      id: `row-${no}`,
      so_line_id: `sol-${no}`,
      so_line_no: no,
      item_code: `ITEM-${String(no).padStart(3, '0')}`,
      verb: 'ORDER',
      state: 'raised',
      ack_state: 'awaiting',
      qty: '4',
      linked_qty: '0',
      bundled_qty: '0',
      links: [],
    } as unknown as OrderInquiryWorklistRow;
  });
}

function tab(rows: OrderInquiryWorklistRow[]) {
  return (
    <OrderInquiryLinesTab
      lines={rows}
      isLoading={false}
      rowSelection={{}}
      onRowSelectionChange={() => {}}
    />
  );
}

describe('a deep link into a long OI opens the page holding the line', () => {
  it('lands on page 2 for line 40 of 60, highlighted, and stays there when the lines refetch', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>{tab(lines())}</QueryClientProvider>,
    );

    const target = await screen.findByText('ITEM-040');
    expect(target.closest('tr')).toHaveClass('deep-link-highlight');
    expect(screen.queryByText('ITEM-001')).toBeNull();

    // The query refetches (window focus, an action's invalidation): a NEW array, same rows.
    await act(async () => {
      rerender(<QueryClientProvider client={client}>{tab(lines())}</QueryClientProvider>);
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.getByText('ITEM-040')).toBeInTheDocument();
    expect(screen.queryByText('ITEM-001')).toBeNull();
  });

  it('crew pass: lands and stays under StrictMode with the lines already loaded on mount', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <React.StrictMode>
        <QueryClientProvider client={client}>{tab(lines())}</QueryClientProvider>
      </React.StrictMode>,
    );
    const target = await screen.findByText('ITEM-040');
    expect(target.closest('tr')).toHaveClass('deep-link-highlight');
    expect(screen.queryByText('ITEM-001')).toBeNull();
  });

  it('falls back to a page that exists when the lines shrink under it', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>{tab(lines())}</QueryClientProvider>,
    );
    await screen.findByText('ITEM-040');
    await act(async () => {
      rerender(
        <QueryClientProvider client={client}>{tab(lines().slice(0, 10))}</QueryClientProvider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.getByText('ITEM-001')).toBeInTheDocument();
  });
});
