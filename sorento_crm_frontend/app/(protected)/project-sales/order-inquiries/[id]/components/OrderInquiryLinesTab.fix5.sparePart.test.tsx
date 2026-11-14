/**
 * SPARE-PART-ORDER-REQUEST fix round 5 (browser pass 2), red-first. OI page half.
 *
 * D1 The Lines tab leaves its loading state when a side call is refused. Measured cause of the
 *    browser pass's "skeleton forever": `useListingColumnPreferences` marks itself applied only
 *    when the column-config GET succeeds, so a 403 keeps `isLoading` true for good (the reserve
 *    requests read is a detail-page query and does not gate the tab). Here the column-config GET
 *    answers 403 and the reserve read is refused too: the rows must still render.
 * D5 The request total shows: the Lines footer's Total cell reads the sum of the live lines in the
 *    shared money format (cancelled lines excluded), and the General tab's Request card carries
 *    the header `total`.
 * D7 Superseded by SPARE-PART-OR-B U1.1 (owner 14 Nov): no "was" mark on a spare part line, so
 *    the Unit price cell reads its value alone.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));

const refused = (detail: string) =>
  new Response(JSON.stringify({ detail }), { status: 403, headers: { 'content-type': 'application/json' } });
const apiFetch = vi.fn(async (url: string) => {
  if (url.includes('/list-query/column-config/')) return refused('Permission denied');
  if (url.includes('reserve-requests'))
    return refused('One of these permissions required: projects.projects.view');
  return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string]) => apiFetch(...a) }));

import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import { OrderInquiryGeneralTab } from './OrderInquiryGeneralTab';
import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import { foldInquiryLines, toLineRows } from '../../../_shared/lib/orderInquiryLineFold';
import { formatMoneyExact } from '../../../_shared/lib/money';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function row(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    order_inquiry_id: 'oi-1',
    inquiry_type: 'spare_part_request',
    verb: 'REPLENISH',
    state: 'raised',
    ack_state: 'awaiting',
    item_code: 'ZZX-100',
    product_id: 'prod-1',
    stock_location: 'WH-MAIN',
    qty: '6',
    unit_price: '12.0000',
    line_total: '72.0000',
    submitted_qty: '10',
    submitted_unit_price: '12.0000',
    photo_changes: { added: 0, removed: 0 },
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function titleOf(column: unknown): string | undefined {
  return (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;
}

// =============================================================================
// D1
// =============================================================================

describe('D1: the Lines tab never hangs on a refused side call', () => {
  it('renders the rows when column-config and reserve-requests answer 403', async () => {
    wrap(
      <OrderInquiryLinesTab
        lines={[row()]}
        isLoading={false}
        rowSelection={{}}
        onRowSelectionChange={() => {}}
        {...({ inquiryType: 'spare_part_request', currency: 'MYR' } as Record<string, unknown>)}
      />,
    );
    await waitFor(
      () => expect(apiFetch.mock.calls.some(([u]) => String(u).includes('column-config'))).toBe(true),
    );
    expect(await screen.findByText('ZZX-100', {}, { timeout: 5000 })).toBeInTheDocument();
  });
});

// =============================================================================
// D5
// =============================================================================

const RAISED = { inquiryType: 'spare_part_request', headerState: 'raised', canDecide: false, currency: 'MYR' };

function Footer({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const columns = useOrderInquiryHeaderLinesColumns(RAISED as never);
  const data = React.useMemo(() => toLineRows(foldInquiryLines(rows)), [rows]);
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tfoot>
        <tr>
          {table.getFooterGroups().flatMap((group) =>
            group.headers.map((header) => (
              <td key={header.id} data-title={titleOf(header.column.columnDef) ?? header.column.id}>
                {header.column.columnDef.footer
                  ? flexRender(header.column.columnDef.footer, header.getContext())
                  : null}
              </td>
            )),
          )}
        </tr>
      </tfoot>
    </table>
  );
}

describe('D5: the request total shows on the OI page', () => {
  it('the Lines footer Total reads the live lines summed, in the shared money format', () => {
    const { container } = wrap(
      <Footer
        rows={[
          row({ id: 'r1', product_id: 'p1', item_code: 'ZZX-100', line_total: '72.0000' }),
          row({ id: 'r2', product_id: 'p2', item_code: 'ZZX-220', line_total: '128.0000' }),
          row({ id: 'r3', product_id: 'p3', item_code: 'ZZX-300', state: 'cancelled', qty: '0', line_total: '0.0000' }),
        ]}
      />,
    );
    const total = container.querySelector('td[data-title="Total"]');
    expect(total, 'a Total footer cell').not.toBeNull();
    expect(total).toHaveTextContent(formatMoneyExact('200.0000', 'MYR'));
  });

  it('the General tab Request card carries the request total', () => {
    render(
      <OrderInquiryGeneralTab
        header={
          {
            id: 'oi-1',
            inquiry_no: 'OI-2611-0001',
            inquiry_type: 'spare_part_request',
            state: 'pending_approval',
            currency: 'MYR',
            total: '260.0000',
            needed_by: '2026-11-30',
            default_location: 'WH-MAIN',
            reason: 'Service van',
            requested_by_name: 'Requester A',
            raise_history: [],
          } as never
        }
      />,
    );
    expect(document.body).toHaveTextContent(formatMoneyExact('260.0000', 'MYR'));
  });
});

// =============================================================================
// D7
// =============================================================================

const PENDING = { inquiryType: 'spare_part_request', headerState: 'pending_approval', canDecide: true, currency: 'MYR', onEditLine: vi.fn() };

function Grid({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const columns = useOrderInquiryHeaderLinesColumns(PENDING as never);
  const data = React.useMemo(() => toLineRows(foldInquiryLines(rows)), [rows]);
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((r) => (
          <tr key={r.id}>
            {r.getVisibleCells().map((cell) => (
              <td key={cell.id} data-title={titleOf(cell.column.columnDef) ?? cell.column.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// SPARE-PART-OR-B (U1.1, owner 14 Nov): the "was" mark is gone from spare part lines, so
// there is nothing left to clip; the unit price cell reads the value alone.
describe('D7: the unit price cell carries no "was" mark to clip', () => {
  it('reads the value without a "was" mark', () => {
    const { container } = wrap(
      <Grid rows={[row({ unit_price: '32.0000', submitted_unit_price: '35.0000', line_total: '192.0000' })]} />,
    );
    const cell = container.querySelector('td[data-title="Unit price"]') as HTMLElement;
    expect(cell).not.toBeNull();
    expect(cell.textContent ?? '').not.toMatch(/was /i);
  });
});

