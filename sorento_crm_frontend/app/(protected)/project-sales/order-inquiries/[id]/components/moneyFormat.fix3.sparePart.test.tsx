/**
 * SPARE-PART-ORDER-REQUEST fix round 3, B4 (browser pass): money reads the same everywhere.
 * - The unit price shows 2 decimals (SPARE-PART-OR-B U1.1 retired its "was" mark).
 * - The Lines tab and the Approve popup print money through the ONE shared formatter
 *   (`formatMoneyExact`, `_shared/lib/money.ts`): whatever it renders for MYR, the same string.
 *   That includes the popup's unit price change ("unit price RM 35.00 to RM 32.00").
 * The request form's half is `SparePartRequestForm.fix3.sparePart.test.tsx`.
 * Qty "was" marks stay plain quantities ("was 10"); this file asserts money only.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })),
}));
vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return { ...actual, getOrderInquiryPoDetail: vi.fn(), getOrderInquirySpoDetail: vi.fn() };
});
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import { SparePartRequestActions } from './SparePartRequestActions';
import { foldInquiryLines, toLineRows } from '../../../_shared/lib/orderInquiryLineFold';
import { formatMoneyExact } from '../../../_shared/lib/money';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

function titleOf(column: unknown): string | undefined {
  return (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;
}

function row(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-2',
    order_inquiry_id: 'oi-1',
    inquiry_type: 'spare_part_request',
    verb: 'REPLENISH',
    state: 'raised',
    ack_state: 'awaiting',
    item_code: 'ZZX-220',
    product_id: 'prod-2',
    stock_location: 'WH-SVC',
    qty: '6',
    unit_price: '32.0000',
    line_total: '192.0000',
    submitted_qty: '10',
    submitted_unit_price: '35.0000',
    photo_changes: { added: 0, removed: 0 },
    linked_qty: '0',
    bundled_qty: '0',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

function Grid({ rows, options }: { rows: OrderInquiryWorklistRow[]; options: Record<string, unknown> }) {
  const columns = useOrderInquiryHeaderLinesColumns(options as never);
  const data = React.useMemo(() => toLineRows(foldInquiryLines(rows)), [rows]);
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((r) => (
          <tr key={r.id} data-testid="line">
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

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function cell(title: string): HTMLElement {
  const found = screen.getByTestId('line').querySelector(`td[data-title="${title}"]`);
  expect(found, `a "${title}" cell`).not.toBeNull();
  return found as HTMLElement;
}

const RAISED = { inquiryType: 'spare_part_request', headerState: 'raised', canDecide: false, currency: 'MYR' };

describe('B4: the Lines tab prints money through the shared formatter', () => {
  // SPARE-PART-OR-B (U1.1, owner 14 Nov): no "was" mark on a spare part line any more; the
  // unit price prints alone, in 2 decimals.
  it('the unit price prints with 2 decimals and no "was" mark', () => {
    wrap(<Grid rows={[row()]} options={RAISED} />);
    const text = cell('Unit price').textContent ?? '';
    expect(text).toMatch(/32\.00\b/);
    expect(text).not.toMatch(/was /i);
  });

  it('unit price and total read exactly as formatMoneyExact renders them for MYR', () => {
    wrap(<Grid rows={[row()]} options={RAISED} />);
    expect(cell('Unit price')).toHaveTextContent(formatMoneyExact('32.0000', 'MYR'));
    expect(cell('Total')).toHaveTextContent(formatMoneyExact('192.0000', 'MYR'));
  });
});

describe('B4: the Approve popup prints the same strings', () => {
  const header = {
    id: 'oi-1',
    inquiry_no: 'OI-2611-0001',
    inquiry_type: 'spare_part_request',
    state: 'pending_approval',
    currency: 'MYR',
    can_decide: true,
    can_edit: false,
    can_revise: false,
    raise_history: [],
  } as unknown as OrderInquiryHeaderDetail;

  it('the amount and the unit price change use formatMoneyExact', () => {
    wrap(<SparePartRequestActions header={header} rows={[row({ state: 'draft' })]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent(formatMoneyExact('192.0000', 'MYR'));
    const priceChange = within(dialog)
      .getAllByRole('listitem')
      .map((li) => li.textContent ?? '')
      .find((t) => /unit price/i.test(t));
    expect(priceChange, 'the unit price change is listed').toBeDefined();
    expect(priceChange).toContain(formatMoneyExact('35.0000', 'MYR'));
    expect(priceChange).toContain(formatMoneyExact('32.0000', 'MYR'));
  });
});
