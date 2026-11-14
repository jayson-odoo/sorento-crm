/**
 * SPARE-PART-OR-B (slice 2 of #2381), red-first (Phase 2). U3.1: ONE shared link cell.
 * Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md.
 *
 * `SoLineOrderInquiryCell`'s entry view is lifted to
 * `app/(protected)/project-sales/_shared/components/OrderInquiryLinkCell.tsx`, exporting
 * `OrderInquiryLinkCell` and `orderInquiryLinkEntries`. Red today: the module does not exist
 * (the one import failure the brief allows).
 *
 * NAMED CONTRACT CHOICES:
 * 1. `OrderInquiryLinkCell({ rows, lineId })`: the same props as `SoLineOrderInquiryCell`.
 * 2. `orderInquiryLinkEntries(rows)` returns `soLineInquiryEntries`'s shape
 *    (`{ inquiryId, inquiryNo, line }`), where `inquiryNo` is the row's `oi_no` when set
 *    (a spare part request past approval) and else its `inquiry_no` (a sales-order OI).
 * 3. The link: text = that number, href `/project-sales/order-inquiries/<inquiry id>?row=<row id>`.
 * The existing `scm/sales-orders/[id]/components/SoLineOrderInquiryCell.test.tsx` stays the
 * regression guard that SO line rendering is unchanged.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/app/(protected)/project-sales/_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/app/(protected)/project-sales/_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoDetail: vi.fn(() => new Promise(() => {})),
    getOrderInquirySpoDetail: vi.fn(() => new Promise(() => {})),
  };
});

import { OrderInquiryLinkCell, orderInquiryLinkEntries } from './OrderInquiryLinkCell';
import type { OrderInquiryWorklistRow } from '../types/orderInquiry.types';

function soRow(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-so-1',
    order_inquiry_id: 'oi-so-1',
    inquiry_no: 'OI-2611-0048',
    inquiry_type: 'sales_order',
    so_line_id: 'mirror-32',
    core_line_id: 'core-32',
    so_line_no: 32,
    item_code: 'ZZX-SW-15',
    qty: '4',
    verb: 'ORDER',
    state: 'raised',
    ack_state: 'awaiting',
    redirected_to_pool: false,
    links: [],
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

function spareRow(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return soRow({
    id: 'row-sp-1',
    order_inquiry_id: 'oi-sp-1',
    inquiry_no: 'OR-2611-0003',
    oi_no: 'OI-2611-0009',
    inquiry_type: 'spare_part_request',
    so_line_id: null,
    core_line_id: null,
    so_line_no: null,
    verb: 'REPLENISH',
    ...over,
  });
}

function renderCell(rows: OrderInquiryWorklistRow[], lineId = 'l-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryLinkCell rows={rows} lineId={lineId} />
    </QueryClientProvider>,
  );
}

describe('U3.1: orderInquiryLinkEntries', () => {
  it('a sales-order OI entry is numbered by its inquiry_no', () => {
    const [entry] = orderInquiryLinkEntries([soRow()]);
    expect(entry.inquiryId).toBe('oi-so-1');
    expect(entry.inquiryNo).toBe('OI-2611-0048');
  });

  it('a spare part request entry is numbered by its oi_no', () => {
    const [entry] = orderInquiryLinkEntries([spareRow()]);
    expect(entry.inquiryId).toBe('oi-sp-1');
    expect(entry.inquiryNo).toBe('OI-2611-0009');
  });

  it('no rows: no entries', () => {
    expect(orderInquiryLinkEntries([])).toEqual([]);
    expect(orderInquiryLinkEntries(null)).toEqual([]);
  });
});

describe('U3.1: OrderInquiryLinkCell', () => {
  it('links a sales-order OI to the OI page at the row', () => {
    renderCell([soRow()]);
    const link = screen.getByRole('link', { name: 'OI-2611-0048' });
    expect(link).toHaveAttribute('href', '/project-sales/order-inquiries/oi-so-1?row=row-so-1');
  });

  it('links a spare part request by its OI number to the OI page at the row', () => {
    renderCell([spareRow()]);
    const link = screen.getByRole('link', { name: 'OI-2611-0009' });
    expect(link).toHaveAttribute('href', '/project-sales/order-inquiries/oi-sp-1?row=row-sp-1');
  });

  it('no rows reads "-"', () => {
    renderCell([]);
    expect(screen.getByText('-')).toBeInTheDocument();
  });
});

describe('U3.1: SoLineOrderInquiryCell is a thin caller of the shared cell', () => {
  it('renders the same link as the shared cell for an SO line', async () => {
    const { SoLineOrderInquiryCell } = await import(
      '@/app/(protected)/scm/sales-orders/[id]/components/SoLineOrderInquiryCell'
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SoLineOrderInquiryCell rows={[soRow()]} lineId="l-2" />
      </QueryClientProvider>,
    );
    expect(screen.getByRole('link', { name: 'OI-2611-0048' })).toHaveAttribute(
      'href',
      '/project-sales/order-inquiries/oi-so-1?row=row-so-1',
    );
  });
});
