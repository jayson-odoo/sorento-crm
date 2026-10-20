/**
 * OI-SPLIT-VIEW (UAC D1): the Order Inquiry page gear "Order inquiry options" has "View splits":
 * one popup titled "<OI number>: splits" with the SO number under it, "<n> split lines", a group
 * per split line in line number order, and an empty state. Scaffolding copied from
 * `OrderInquiryDetail.consignment.test.tsx`. Red until the build.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryHeaderDetail, OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

// S1 (reviewer round): `OrderInquiryDetail` reads `useSession` directly now, to gate
// the reserve-request Cancel control on the actual signed-in user, not only a
// permission flag.
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'test-current-user' } }, status: 'authenticated' }),
}));

// Under jsdom nothing answers the column-preferences fetch `DataGrid` starts, so the
// Lines tab grid renders skeletons forever and no row is assertable
// (project_datagrid_jsdom_rows_mockable.md).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const acknowledgeFilterSpy = vi.fn(async () => ({ acknowledged: 0, results: [] }));
const acknowledgeRowsSpy = vi.fn(async () => ({ acknowledged: 0, results: [] }));
const autoPlaceSpy = vi.fn(async () => ({ linked: 0, results: [] }));
const unacknowledgeSpy = vi.fn<(rowIds: unknown) => Promise<{ unacknowledged: number }>>(
  async () => ({ unacknowledged: 0 }),
);
// Lane B (`PLAN-order-sheet-oi-reports-22sep.md`, AC-B1/AC-B5): Export Excel goes
// async (My Downloads), never a blob save - and the gear gets a "Download history" item.
const exportOrderInquiryXlsxSpy = vi.hoisted(() => vi.fn(async () => ({
  id: 'dl-1', kind: 'order_inquiry_xlsx', status: 'pending', filename: 'OI-2609-0001.xlsx',
})));

const toastSpy = vi.hoisted(() => ({
  success: vi.fn(), error: vi.fn(), warning: vi.fn(), dismiss: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: toastSpy }));

const saveBlobAsSpy = vi.hoisted(() => vi.fn());
vi.mock('../../../_shared/services/fileDownload', () => ({
  saveBlobAs: (...args: unknown[]) => saveBlobAsSpy(...args),
  filenameFromContentDisposition: vi.fn(),
}));

const entityDownloadsButtonSpy = vi.hoisted(() => vi.fn());
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: (props: {
    entityType: string;
    entityId: string;
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
  }) => {
    entityDownloadsButtonSpy(props);
    return props.open ? (
      <div data-testid="entity-downloads-dialog">
        Downloads for {props.entityType}:{props.entityId}
      </div>
    ) : null;
  },
}));

let linesNow: () => OrderInquiryWorklistRow[] = () => [];

const HEADER: OrderInquiryHeaderDetail = {
  id: 'oi-1',
  inquiry_no: 'OI-2609-0001',
  legacy_inquiry_no: null,
  raised_at: '2026-09-05T08:00:00',
  raised_by_name: 'Eling',
  sales_order_id: 'so-1',
  project_sales_order_id: 'pso-1',
  so_number: 'SO123456',
  so_date: '2026-09-01',
  customer_name: 'Optad',
  customer_code: 'CUST-1',
  project_id: null,
  project_title: null,
  agent_name: null,
  lines_total: 3,
  lines_to_confirm: 3,
  qty_total: '30',
  status: 'outstanding',
  order_type: null,
  raise_history: [],
};

const LINKED_LINE: OrderInquiryWorklistRow = {
  id: 'row-linked',
  order_inquiry_id: 'oi-1',
  item_code: `ZZT-${'LINK'}`,
  qty: '10',
  delivery_date: null,
  supplier: null,
  po_number: null,
  location: null,
  verb: 'order',
  note: null,
  state: 'placed',
  ack_state: 'awaiting',
  links: [{ kind: 'po', document: 'PO-1', po_id: 'po-1', qty: '10' }],
} as unknown as OrderInquiryWorklistRow;

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryHeader: vi.fn(async () => HEADER),
    getOrderInquiryHeaderLines: vi.fn(async () => linesNow()),
    getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({
      purchase_orders: [],
      spos: [],
    })),
    listOrderInquiryHeaders: vi.fn(async () => ({ data: [], total: 0, page: 1, limit: 25 })),
    exportOrderInquiryXlsx: (...args: unknown[]) =>
      exportOrderInquiryXlsxSpy(...(args as [string])),
    acknowledgeOrderInquiryRowsByFilter: (...args: unknown[]) =>
      acknowledgeFilterSpy(...(args as [unknown])),
    acknowledgeOrderInquiryRows: (...args: unknown[]) =>
      acknowledgeRowsSpy(...(args as [unknown])),
    autoPlaceOrderInquiryRows: (...args: unknown[]) => autoPlaceSpy(...(args as [unknown])),
    unacknowledgeOrderInquiryRows: (...args: unknown[]) =>
      unacknowledgeSpy(...(args as [unknown])),
  };
});

// UL: the deferred Unlink parks a real pending action through this service - mocked so
// the countdown `useDeferredBulkAction` builds is exercised for real, with a window long
// enough (10s) that a synchronous test never sees it lapse.
const createPendingActionSpy = vi.fn(async ({ entityId }: { entityId: string }) => ({
  id: `pa-${entityId}`,
  action_key: 'order_inquiry_row.unlink',
  entity_type: 'order_inquiry_row',
  entity_id: entityId,
  commit_at: new Date(Date.now() + 10_000).toISOString(),
  window_seconds: 10,
}));
const cancelPendingActionSpy = vi.fn(async () => undefined);
// UAC E5: the OI gear's whole-inquiry popup reads the sheet payload, as the board does.
let splitsPayload: unknown = null;
vi.mock('../../../_shared/services/lineSplitService', () => ({
  getLineSplits: () => Promise.resolve(splitsPayload),
  saveLineSplits: vi.fn(),
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) =>
    createPendingActionSpy(...(args as [{ entityId: string }])),
  cancelPendingAction: (...args: unknown[]) => cancelPendingActionSpy(...(args as [string])),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));

import { pendingEntityStore } from '@/lib/pending-entity-store';
import { getOrderInquiryHeader } from '../../../_shared/services/orderInquiryService';
import { OrderInquiryDetail } from './OrderInquiryDetail';
import { ownerSavedCase } from '@/test-mocks/lineSplitSheetKit';

const mockGetOrderInquiryHeader = getOrderInquiryHeader as unknown as ReturnType<typeof vi.fn>;

function renderDetail(id: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryDetail id={id} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  acknowledgeFilterSpy.mockClear();
  acknowledgeRowsSpy.mockClear();
  autoPlaceSpy.mockClear();
  unacknowledgeSpy.mockClear();
  createPendingActionSpy.mockClear();
  cancelPendingActionSpy.mockClear();
  exportOrderInquiryXlsxSpy.mockClear();
  saveBlobAsSpy.mockClear();
  entityDownloadsButtonSpy.mockClear();
  toastSpy.success.mockClear();
  toastSpy.error.mockClear();
  mockGetOrderInquiryHeader.mockReset();
  mockGetOrderInquiryHeader.mockResolvedValue(HEADER);
});

afterEach(() => {
  pendingEntityStore.reset();
});


const view = (qty: string) => ({
  status: 'confirmed', revision_no: 3, confirmed_on: '2026-10-19',
  base_qty: '417', base_date: '2026-10-20', now_qty: '14', now_date: '2026-09-20',
  total_qty: '417',
  rows: [{
    qty, delivery_date: '2026-09-20', change: 'ADVANCE', sits_on: 'own', sits_on_line_no: 480,
    remark: '', is_cancel: false, changed: false, was_qty: null, was_date: null,
  }],
});

function oiLine(id: string, no: number, splitView: unknown) {
  return {
    ...LINKED_LINE,
    id,
    item_code: 'CSK14B',
    so_line_no: no,
    line_no: no,
    so_line_id: `sol-${no}`,
    split_view: splitView,
  } as unknown as OrderInquiryWorklistRow;
}

async function openViewSplits() {
  await screen.findByRole('button', { name: 'Order inquiry options' });
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), { button: 0 });
  fireEvent.click(await screen.findByRole('menuitem', { name: 'View splits' }));
  return screen.findByRole('dialog');
}

describe('OI gear: View splits (D1)', () => {
  it('opens "OI-2609-0001: splits" with the SO number and one group per split line', async () => {
    linesNow = () => [oiLine('r-752', 752, view('37')), oiLine('r-480', 480, view('14')), oiLine('r-608', 608, null)];
    splitsPayload = ownerSavedCase();
    renderDetail('oi-1');
    const dialog = await openViewSplits();
    expect(within(dialog).getByText('OI-2609-0001: splits')).toBeInTheDocument();
    expect(dialog.textContent).toContain('SO123456');
    expect(dialog.textContent).toContain('2 split lines');
    // UAC E3: the read-only sheet, only the lines with saved splits.
    const blocks = await within(dialog).findAllByTestId(/^split-line-/);
    expect(blocks.map((el) => el.getAttribute('data-testid'))).toEqual([
      'split-line-480', 'split-line-752',
    ]);
    expect(within(dialog).queryByTestId('split-line-608')).not.toBeInTheDocument();
  });

  it('shows "No split lines" when no line is split', async () => {
    linesNow = () => [oiLine('r-608', 608, null)];
    splitsPayload = { ...ownerSavedCase(), lines: ownerSavedCase().lines.map((l) => ({ ...l, splits: [], extra_qty: null })) };
    renderDetail('oi-1');
    const dialog = await openViewSplits();
    expect(await within(dialog).findByText('No split lines')).toBeInTheDocument();
    expect(within(dialog).getByText('Every line ships as AutoCount has it.')).toBeInTheDocument();
  });
});
