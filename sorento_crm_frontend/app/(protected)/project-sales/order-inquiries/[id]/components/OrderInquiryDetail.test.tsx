/**
 * `PLAN-oi-header-list-detail.md`, AC-DP-05/06, security fix round S1 + UL, reviewer
 * fix round S5 (`oi-header-list-detail-acceptance-criteria.md`).
 *
 * Pinned here:
 *
 * 1. **S1 (never widen).** With nothing ticked, Confirm / Auto link send exactly
 *    `{ filter: { inquiry_id: <the page id> } }` - never a payload that could match
 *    outside this one OI. Real service functions are spied on through a PARTIAL mock
 *    of `orderInquiryService` (kept mostly real via `importOriginal`) rather than
 *    mocking the hooks, so the actual payload the hook builds is what gets asserted.
 * 2. **UL (deferred, not a dialog).** Gear > Unlink selected starts a server-deferred
 *    pending action (countdown + Cancel, AC-DP-06) instead of the retired `AlertDialog`
 *    confirm pattern - `@/services/pendingActionService` is mocked so the countdown
 *    `useDeferredBulkAction` builds is real, and Cancel is asserted to leave the ticked
 *    line ticked (AC-DP-06's own "Cancel leaves the ticked lines ticked").
 * 3. **AC-DP-05.** The Confirm label counts the ticked lines, and Confirm is disabled
 *    once nothing in scope still waits (a Completed header, nothing ticked).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  OrderInquiryHeaderDetail,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';

// STANDARD-HISTORY wave 1: a test may open the page on a tab (`?tab=history`).
const searchState = vi.hoisted(() => ({ query: '' }));
const getOrderInquiryHistorySpy = vi.hoisted(() =>
  vi.fn(async () => ({
    events: [
      {
        id: 'audit-unconfirm',
        kind: 'unconfirmed',
        at: '2026-11-09T09:15:53',
        actor: 'J*** (Purchasing)',
        title: 'Unconfirmed 9 lines',
        lines: [
          { row_id: 'r1', so_line_no: 1, item_code: 'SRTSP131', qty: 4, change: 'Confirmed -> To confirm' },
        ],
      },
    ],
  })),
);
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/oi-1',
  useSearchParams: () => new URLSearchParams(searchState.query),
}));

const permState = vi.hoisted(() => ({ denied: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => !permState.denied.has(slug),
}));

// OI-PO-LINK (document view gear): the shared dialog's hooks, mocked by module path as
// `OrderInquiriesClient.poLink.test.tsx` does.
const poLinkState = vi.hoisted(() => ({ switchOn: true, unlinkEnabled: true }));
const poOptionsSpy = vi.hoisted(() => vi.fn());
vi.mock('../../../_shared/po-link/usePoLink', () => ({
  usePoLinkSwitch: () => ({ data: poLinkState.switchOn, isLoading: false }),
  usePoLinkOptions: (...args: unknown[]) => {
    poOptionsSpy(...args);
    return {
      data: {
        capabilities: {
          split_link: { enabled: true, reason: null },
          link_row: { enabled: false, reason: null },
          unlink_row: {
            enabled: poLinkState.unlinkEnabled,
            reason: poLinkState.unlinkEnabled ? null : 'Waiting for AutoCount',
          },
          relink_row: { enabled: false, reason: null },
        },
        po_lines: [], so_books: {}, lines: [], skipped: [],
      },
      isLoading: false,
      error: null,
    };
  },
  usePoLinkMutations: () => ({
    link: { mutateAsync: vi.fn(), isPending: false },
    unlink: { mutateAsync: vi.fn(), isPending: false },
    change: { mutateAsync: vi.fn(), isPending: false },
    relink: { mutateAsync: vi.fn(), isPending: false },
    relocate: { mutateAsync: vi.fn(), isPending: false },
    resume: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

// OI-RESEND-PURCHASING: the single-OI entry point.
const previewHandoverResendSpy = vi.fn(async () => ({
  emails: [],
  inquiry_total: 0,
  unresolved: [],
  skipped: [],
  automation_enabled: true,
}));
vi.mock('../../../_shared/services/orderInquiryHandoverResendService', () => ({
  previewHandoverResend: (ids: string[]) => previewHandoverResendSpy(ids),
  sendHandoverResend: vi.fn(),
}));

// S1 (reviewer round): `OrderInquiryDetail` reads `useSession` directly now, to gate
// the reserve-request Cancel control on the actual signed-in user, not only a
// permission flag.
vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'test-current-user' } },
    status: 'authenticated',
  }),
}));

// Under jsdom nothing answers the column-preferences fetch `DataGrid` starts, so the
// Lines tab grid renders skeletons forever and no row is assertable
// (project_datagrid_jsdom_rows_mockable.md).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

const acknowledgeFilterSpy = vi.fn(async () => ({
  acknowledged: 0,
  results: [],
}));
const acknowledgeRowsSpy = vi.fn(async () => ({
  acknowledged: 0,
  results: [],
}));
const poCandidatesSpy = vi.hoisted(() => vi.fn());
const autoPlaceSpy = vi.fn(async () => ({ linked: 0, results: [] }));
const unacknowledgeSpy = vi.fn<
  (rowIds: unknown) => Promise<{ unacknowledged: number }>
>(async () => ({ unacknowledged: 0 }));
// Lane B (`PLAN-order-sheet-oi-reports-22sep.md`, AC-B1/AC-B5): Export Excel goes
// async (My Downloads), never a blob save - and the gear gets a "Download history" item.
const exportOrderInquiryXlsxSpy = vi.hoisted(() =>
  vi.fn(async () => ({
    id: 'dl-1',
    kind: 'order_inquiry_xlsx',
    status: 'pending',
    filename: 'OI-2609-0001.xlsx',
  })),
);

const exportOrderInquiryPdfSpy = vi.hoisted(() =>
  vi.fn<(inquiryId: string) => Promise<unknown>>(async () => ({
    id: 'dl-2',
    kind: 'order_inquiry_pdf',
    status: 'pending',
    filename: 'order-inquiry-OI-2609-0001.pdf',
  })),
);

const toastSpy = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  dismiss: vi.fn(),
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

vi.mock(
  '../../../_shared/services/orderInquiryService',
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import('../../../_shared/services/orderInquiryService')
      >();
    return {
      ...actual,
      getOrderInquiryHeader: vi.fn(async () => HEADER),
      getOrderInquiryHeaderLines: vi.fn(async () => [LINKED_LINE]),
      getOrderInquiryHeaderRelatedDocuments: vi.fn(async () => ({
        purchase_orders: [],
        spos: [],
      })),
      getOrderInquiryHistory: (...args: unknown[]) => getOrderInquiryHistorySpy(...(args as [])),
      listOrderInquiryHeaders: vi.fn(async () => ({
        data: [],
        total: 0,
        page: 1,
        limit: 25,
      })),
      exportOrderInquiryXlsx: (...args: unknown[]) =>
        exportOrderInquiryXlsxSpy(...(args as [string])),
      exportOrderInquiryPdf: (...args: unknown[]) =>
        exportOrderInquiryPdfSpy(...(args as [string])),
      acknowledgeOrderInquiryRowsByFilter: (...args: unknown[]) =>
        acknowledgeFilterSpy(...(args as [unknown])),
      acknowledgeOrderInquiryRows: (...args: unknown[]) =>
        acknowledgeRowsSpy(...(args as [unknown])),
      getOrderInquiryPoCandidates: (...args: unknown[]) => poCandidatesSpy(...args),
      autoPlaceOrderInquiryRows: (...args: unknown[]) =>
        autoPlaceSpy(...(args as [unknown])),
      unacknowledgeOrderInquiryRows: (...args: unknown[]) =>
        unacknowledgeSpy(...(args as [unknown])),
    };
  },
);

// UL: the deferred Unlink parks a real pending action through this service - mocked so
// the countdown `useDeferredBulkAction` builds is exercised for real, with a window long
// enough (10s) that a synchronous test never sees it lapse.
const createPendingActionSpy = vi.fn(
  async ({ entityId }: { entityId: string }) => ({
    id: `pa-${entityId}`,
    action_key: 'order_inquiry_row.unlink',
    entity_type: 'order_inquiry_row',
    entity_id: entityId,
    commit_at: new Date(Date.now() + 10_000).toISOString(),
    window_seconds: 10,
  }),
);
const cancelPendingActionSpy = vi.fn(async () => undefined);
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) =>
    createPendingActionSpy(...(args as [{ entityId: string }])),
  cancelPendingAction: (...args: unknown[]) =>
    cancelPendingActionSpy(...(args as [string])),
  getCurrentPendingAction: vi.fn(async () => ({
    pending: null,
    last_outcome: null,
  })),
}));

import { pendingEntityStore } from '@/lib/pending-entity-store';
import {
  getOrderInquiryHeader,
  getOrderInquiryHeaderLines,
} from '../../../_shared/services/orderInquiryService';
import { OrderInquiryDetail } from './OrderInquiryDetail';

const mockGetOrderInquiryHeader =
  getOrderInquiryHeader as unknown as ReturnType<typeof vi.fn>;

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
  permState.denied.clear();
  poLinkState.switchOn = true;
  poLinkState.unlinkEnabled = true;
  poOptionsSpy.mockClear();
  searchState.query = '';
  getOrderInquiryHistorySpy.mockClear();
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

describe('Confirm / Auto link never widen without a real page id (S1)', () => {
  it('with nothing ticked, Confirm sends exactly { filter: { inquiry_id: id } }', async () => {
    renderDetail('oi-1');
    const confirmButton = await screen.findByRole('button', {
      name: 'Confirm',
    });

    fireEvent.click(confirmButton);

    await waitFor(() => expect(acknowledgeFilterSpy).toHaveBeenCalledTimes(1));
    expect(acknowledgeFilterSpy.mock.calls[0][0]).toEqual({
      inquiry_id: 'oi-1',
    });
    expect(acknowledgeRowsSpy).not.toHaveBeenCalled();
  });

  it('with an empty page id, Confirm never fires an acknowledge call at all', async () => {
    renderDetail('');

    // The empty-id detail query is `enabled: Boolean(id)` = false, so the header never
    // loads and the "Could not load" state renders instead of the primary button - but
    // that is itself the guard this pins: nothing downstream may EVER reach a mutate
    // call with a widened/empty scope, whether by the button not rendering or by a
    // future change guarding the click. Both are asserted.
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: /confirm/i }),
      ).not.toBeInTheDocument(),
    );
    expect(acknowledgeFilterSpy).not.toHaveBeenCalled();
    expect(acknowledgeRowsSpy).not.toHaveBeenCalled();
  });

  it('Auto link with nothing ticked sends exactly { filter: { inquiry_id: id } }', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.pointerDown(
      screen.getByRole('button', { name: 'Order inquiry options' }),
      {
        button: 0,
      },
    );
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /auto link/i }),
    );

    await waitFor(() => expect(autoPlaceSpy).toHaveBeenCalledTimes(1));
    expect(autoPlaceSpy.mock.calls[0][0]).toEqual({
      filter: { inquiry_id: 'oi-1' },
    });
  });
});

describe('Confirm label / disabled follow the ticked scope (AC-DP-05, S5)', () => {
  it('ticking a line changes the label to Confirm (1)', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.click(
      await screen.findByLabelText(`Select ${LINKED_LINE.item_code}`),
    );

    expect(
      await screen.findByRole('button', { name: 'Confirm (1)' }),
    ).toBeInTheDocument();
  });

  // `PLAN-oi-no-double-count-25sep.md` AC-ND-12 + G6 (owner ruling 26 Sep 2026): the
  // grid ticks sales order LINES and Confirm (N) counts lines. S2 (AC-ND-24, AC-ND-27):
  // Confirm sends the ticked line's LIVE row ids only; the server takes on the line's
  // used rows in the same call, and a cancelled row from the history fetch is never sent.
  it('ticks a line, counts it once, and Confirm sends its live rows only', async () => {
    const lineRow = (over: Partial<OrderInquiryWorklistRow>) =>
      ({
        ...LINKED_LINE,
        item_code: 'ZZT-SPLIT',
        core_line_id: 'cl-1',
        line_no: 1,
        verb: 'ORDER',
        links: [],
        ...over,
      }) as OrderInquiryWorklistRow;
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValueOnce([
      lineRow({
        id: 'row-used',
        state: 'placed',
        redirected_to_pool: true,
        ack_state: 'changed',
      }),
      lineRow({ id: 'row-a', state: 'raised', ack_state: 'changed' }),
      lineRow({ id: 'row-b', state: 'raised', ack_state: 'awaiting' }),
      lineRow({ id: 'row-old', state: 'cancelled', ack_state: 'changed' }),
    ]);
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.click(await screen.findByLabelText('Select ZZT-SPLIT'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm (1)' }));

    await waitFor(() => expect(acknowledgeRowsSpy).toHaveBeenCalledTimes(1));
    const sent = (acknowledgeRowsSpy.mock.calls[0] as unknown[])[0] as string[];
    expect([...sent].sort()).toEqual(['row-a', 'row-b']);
  });

  // PR #1266 fix round W1 asked for a per-line check after Confirm; the owner and lead
  // later removed the Confirmed column (OI-AUTO-CONFIRM browser pass), so the line carries
  // no confirmed mark. Confirm still sends the ticked row and the lines refetch.
  it("W1: Confirm sends the ticked row and the line shows no Confirmed column", async () => {
    const rowAwaiting = {
      ...LINKED_LINE,
      id: 'row-w1',
      item_code: 'ZZT-W1',
      core_line_id: 'cl-w1',
      line_no: 1,
      ack_state: 'awaiting',
    } as OrderInquiryWorklistRow;
    const rowAcknowledged = {
      ...rowAwaiting,
      ack_state: 'acknowledged',
      acknowledged_by_name: 'Aisyah',
      acknowledged_at: '2026-09-26T11:20:00Z',
    } as OrderInquiryWorklistRow;
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValueOnce([rowAwaiting]);
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValueOnce([
      rowAcknowledged,
    ]);

    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.click(await screen.findByLabelText('Select ZZT-W1'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm (1)' }));

    await waitFor(() => expect(acknowledgeRowsSpy).toHaveBeenCalled());
    const sent = (acknowledgeRowsSpy.mock.calls.at(-1) as unknown[])[0] as string[];
    expect(sent).toEqual(['row-w1']);
    expect(screen.queryByTestId('line-confirmed-mark')).not.toBeInTheDocument();
  });

  it('is disabled on a Completed header with nothing ticked', async () => {
    mockGetOrderInquiryHeader.mockResolvedValue({
      ...HEADER,
      status: 'completed',
      lines_to_confirm: 0,
    });
    renderDetail('oi-1');

    const confirmButton = await screen.findByRole('button', {
      name: 'Confirm',
    });
    expect(confirmButton).toBeDisabled();
  });
});

/**
 * Review S2 (PR #1266 at a98e01cf; SF1 at d0d328d7f): the header must never sit
 * Outstanding on a used row that no tick can confirm (G6 rationale). A ticked line whose
 * only waiting row is a used row enables Confirm and sends that used row's id.
 */
describe('Review S2: a line whose only waiting row is used confirms from the line', () => {
  const lineRow = (over: Partial<OrderInquiryWorklistRow>) =>
    ({
      ...LINKED_LINE,
      item_code: 'ZZT-USED',
      core_line_id: 'cl-u',
      line_no: 1,
      verb: 'ORDER',
      links: [],
      ...over,
    }) as OrderInquiryWorklistRow;

  it('shape a: live rows confirmed, the used row changed - Confirm (1) sends both', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValueOnce([
      lineRow({ id: 'row-live', state: 'placed', ack_state: 'acknowledged' }),
      lineRow({
        id: 'row-used',
        state: 'placed',
        redirected_to_pool: true,
        ack_state: 'changed',
      }),
    ]);
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.click(await screen.findByLabelText('Select ZZT-USED'));
    const confirm = await screen.findByRole('button', { name: 'Confirm (1)' });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);

    await waitFor(() => expect(acknowledgeRowsSpy).toHaveBeenCalledTimes(1));
    const sent = (acknowledgeRowsSpy.mock.calls[0] as unknown[])[0] as string[];
    expect([...sent].sort()).toEqual(['row-live', 'row-used']);
  });

  it('shape b re-pinned (OI-RESERVE-USED-ROW, owner 4 Nov): a line with only a used row is not rendered, so nothing ticks', async () => {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValueOnce([
      lineRow({
        id: 'row-used',
        state: 'placed',
        redirected_to_pool: true,
        ack_state: 'changed',
      }),
    ]);
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });
    expect(screen.queryByLabelText('Select ZZT-USED')).not.toBeInTheDocument();
  });
});

/**
 * Review S3 (PR #1266 at a98e01cf): since S2 the Lines fetch carries cancelled rows
 * (`include_history`), so the whole-OI Unconfirm must still read the LIVE rows only.
 */
describe('Review S3: whole-OI Unconfirm sends only live acknowledged rows', () => {
  it('with nothing ticked, Unconfirm skips the cancelled and the used acknowledged rows', async () => {
    const lineRow = (over: Partial<OrderInquiryWorklistRow>) =>
      ({
        ...LINKED_LINE,
        verb: 'ORDER',
        links: [],
        ...over,
      }) as OrderInquiryWorklistRow;
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValueOnce([
      lineRow({
        id: 'row-live',
        item_code: 'ZZT-A',
        core_line_id: 'cl-a',
        line_no: 1,
        ack_state: 'acknowledged',
      }),
      lineRow({
        id: 'row-old',
        item_code: 'ZZT-A',
        core_line_id: 'cl-a',
        line_no: 1,
        state: 'cancelled',
        ack_state: 'acknowledged',
      }),
      lineRow({
        id: 'row-used',
        item_code: 'ZZT-B',
        core_line_id: 'cl-b',
        line_no: 2,
        redirected_to_pool: true,
        ack_state: 'acknowledged',
      }),
    ]);
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });
    await screen.findByLabelText('Select ZZT-A');

    fireEvent.pointerDown(
      screen.getByRole('button', { name: 'Order inquiry options' }),
      {
        button: 0,
      },
    );
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /unconfirm/i }),
    );

    await waitFor(() => expect(unacknowledgeSpy).toHaveBeenCalledTimes(1));
    expect((unacknowledgeSpy.mock.calls[0] as unknown[])[0]).toEqual([
      'row-live',
    ]);
  });
});

describe('Unlink selected is a server-deferred pending action, not a confirm dialog (AC-DP-06, UL)', () => {
  it('does not open an AlertDialog - a countdown with Cancel appears instead', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.click(
      await screen.findByLabelText(`Select ${LINKED_LINE.item_code}`),
    );
    fireEvent.pointerDown(
      screen.getByRole('button', { name: 'Order inquiry options' }),
      {
        button: 0,
      },
    );
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /^remove link in crm/i }),
    );

    // Target behaviour: no confirmation dialog at all, a deferred countdown instead.
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(await screen.findByText(/cancel/i)).toBeInTheDocument();
  });

  it('Cancel leaves the ticked line ticked (AC-DP-06)', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    const checkbox = await screen.findByLabelText(
      `Select ${LINKED_LINE.item_code}`,
    );
    fireEvent.click(checkbox);
    expect(checkbox).toHaveAttribute('aria-checked', 'true');

    fireEvent.pointerDown(
      screen.getByRole('button', { name: 'Order inquiry options' }),
      {
        button: 0,
      },
    );
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /^remove link in crm/i }),
    );
    await waitFor(() =>
      expect(createPendingActionSpy).toHaveBeenCalledTimes(1),
    );

    fireEvent.click(await screen.findByRole('button', { name: /cancel/i }));

    await waitFor(() =>
      expect(cancelPendingActionSpy).toHaveBeenCalledTimes(1),
    );
    // The selection is untouched by Cancel - only a commit clears it.
    expect(checkbox).toHaveAttribute('aria-checked', 'true');
  });
});

describe('Print / Download PDF, tied to this OI (OI-DOWNLOAD)', () => {
  it('calls exportOrderInquiryPdf(id) and toasts My Downloads', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), {
      button: 0,
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: /print \/ download pdf/i }));

    await waitFor(() => expect(exportOrderInquiryPdfSpy).toHaveBeenCalledWith('oi-1'));
    expect(exportOrderInquiryXlsxSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(toastSpy.success).toHaveBeenCalled());
    expect(toastSpy.success.mock.calls.at(-1)?.[0]).toMatch(/my downloads/i);
    expect(saveBlobAsSpy).not.toHaveBeenCalled();
  });
});

describe('Export Excel goes async, tied to this OI (Lane B, AC-B1/AC-B5)', () => {
  function openGear() {
    fireEvent.pointerDown(
      screen.getByRole('button', { name: 'Order inquiry options' }),
      {
        button: 0,
      },
    );
  }

  it('Export Excel calls exportOrderInquiryXlsx(id) and toasts My Downloads, never saveBlobAs', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    openGear();
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /export excel/i }),
    );

    await waitFor(() =>
      expect(exportOrderInquiryXlsxSpy).toHaveBeenCalledWith('oi-1'),
    );
    await waitFor(() => expect(toastSpy.success).toHaveBeenCalled());
    expect(toastSpy.success.mock.calls[0][0]).toMatch(/my downloads/i);
    expect(saveBlobAsSpy).not.toHaveBeenCalled();
  });

  it('disables Export Excel while the export is pending', async () => {
    let resolveExport: (v: unknown) => void = () => {};
    exportOrderInquiryXlsxSpy.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveExport = resolve;
        }),
    );
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    openGear();
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /export excel/i }),
    );

    await waitFor(() => expect(exportOrderInquiryXlsxSpy).toHaveBeenCalled());
    openGear();
    const item = await screen.findByRole('menuitem', { name: /export excel/i });
    expect(item).toHaveAttribute('aria-disabled', 'true');

    resolveExport({
      id: 'dl-1',
      kind: 'order_inquiry_xlsx',
      status: 'pending',
      filename: 'x.xlsx',
    });
    await waitFor(() => expect(toastSpy.success).toHaveBeenCalled());
  });

  it('shows an error toast when the export fails to start', async () => {
    exportOrderInquiryXlsxSpy.mockRejectedValueOnce(
      new Error('An export is already queued'),
    );
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    openGear();
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /export excel/i }),
    );

    await waitFor(() => expect(toastSpy.error).toHaveBeenCalled());
    expect(toastSpy.error.mock.calls[0][0]).toMatch(/already queued/i);
  });

  it('the gear offers "Download history", opening EntityDownloadsButton for this OI', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });

    openGear();
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /download history/i }),
    );

    await waitFor(() =>
      expect(entityDownloadsButtonSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          entityType: 'order_inquiry',
          entityId: 'oi-1',
          open: true,
        }),
      ),
    );
    expect(
      await screen.findByTestId('entity-downloads-dialog'),
    ).toBeInTheDocument();
  });
});

describe('Send to purchasing from the detail page (OI-RESEND-PURCHASING)', () => {
  it('the options menu opens the preview for this one order inquiry', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });
    fireEvent.pointerDown(
      screen.getByRole('button', { name: 'Order inquiry options' }),
      {
        button: 0,
      },
    );
    fireEvent.click(
      await screen.findByRole('menuitem', { name: 'Send to purchasing' }),
    );
    await waitFor(() =>
      expect(previewHandoverResendSpy).toHaveBeenCalledWith(['oi-1']),
    );
    expect(
      await screen.findByRole('dialog', { name: 'Send to purchasing' }),
    ).toBeInTheDocument();
  });
});

describe('owner hand test (5 Nov 2026): the sales order is named in the header card', () => {
  it('shows the SO number beside "Raised by", linking to the sales order', async () => {
    renderDetail('oi-1');
    const link = await screen.findByTestId('oi-header-so-link');
    expect(link).toHaveTextContent('SO123456');
    expect(link).toHaveAttribute('href', '/scm/sales-orders/so-1');
  });

  it('prints the SO number as plain text when the sales order has no id to link to', async () => {
    mockGetOrderInquiryHeader.mockResolvedValue({ ...HEADER, sales_order_id: undefined });
    renderDetail('oi-1');
    const plain = await screen.findByTestId('oi-header-so');
    expect(plain).toHaveTextContent('SO123456');
    expect(screen.queryByTestId('oi-header-so-link')).toBeNull();
  });
});

describe('STANDARD-HISTORY: the History tab (AC-SH-B8, v2)', () => {
  it('is the last tab, after Related SPO', async () => {
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });
    const tabs = screen.getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabs.slice(-2)).toEqual(['Related SPO', 'History']);
    // Not opened: nothing is read for it.
    expect(getOrderInquiryHistorySpy).not.toHaveBeenCalled();
  });

  it("opened, reads this OI's history and shows a batch press as one event", async () => {
    searchState.query = 'tab=history';
    renderDetail('oi-1');
    // STANDARD-HISTORY v2: the Audit Trail list - one sentence, then when and who.
    const event = (await screen.findByText('Unconfirmed 9 lines')).closest('[data-audit-entry]');
    expect(getOrderInquiryHistorySpy).toHaveBeenCalledWith('oi-1');
    expect(event).toHaveTextContent('by J*** (Purchasing)');
    expect(screen.queryByRole('combobox', { name: 'Product' })).not.toBeInTheDocument();
  });
});

describe('Gear menu: Link selected is gone, Auto link with ticks stays (owner round, 13 Nov)', () => {
  async function openGearWithTick() {
    const lineRow = (over: Partial<OrderInquiryWorklistRow>) =>
      ({
        ...LINKED_LINE,
        item_code: 'ZZT-TICK',
        core_line_id: 'cl-t',
        line_no: 1,
        verb: 'ORDER',
        links: [],
        ...over,
      }) as OrderInquiryWorklistRow;
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValueOnce([
      lineRow({ id: 'row-a', state: 'raised', ack_state: 'changed' }),
      lineRow({ id: 'row-b', state: 'raised', ack_state: 'awaiting' }),
    ]);
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });
    fireEvent.click(await screen.findByLabelText('Select ZZT-TICK'));
    await screen.findByRole('button', { name: 'Confirm (1)' });
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), { button: 0 });
  }

  it('has no Link selected item', async () => {
    await openGearWithTick();
    await screen.findByRole('menuitem', { name: /auto link/i });
    expect(screen.queryByRole('menuitem', { name: /^link selected/i })).toBeNull();
  });

  it('Auto link with ticked lines still sends exactly those row ids', async () => {
    await openGearWithTick();
    fireEvent.click(await screen.findByRole('menuitem', { name: /auto link/i }));
    await waitFor(() => expect(autoPlaceSpy).toHaveBeenCalledTimes(1));
    const sent = autoPlaceSpy.mock.calls[0][0] as { row_ids?: string[]; filter?: unknown };
    expect(sent.filter).toBeUndefined();
    expect([...(sent.row_ids ?? [])].sort()).toEqual(['row-a', 'row-b']);
  });
});


// OI-PO-LINK, document view gear. Owner, 13 Nov 18:55: "1 button is like link po then they can link
// or change link or unlink in the popup". The gear carries Auto link, Link PO... (n) and Remove link
// in CRM (n) (the CRM-only countdown unlink); never Link to PO / Change PO / Unlink...
// ASSUMPTION: the line carries a new boolean `in_autocount_link` (AutoCount ties a PO line to it);
// `doc` below is the one place to rename it.
describe('Document view gear: one Link PO... item and Remove link in CRM', () => {
  const LINK_PO = 'projects.stock_debt.link_po';
  const doc = (id: string, code: string, inAutocountLink: boolean, over: Record<string, unknown> = {}) =>
    ({
      ...LINKED_LINE, id, item_code: code, product_id: 'prod-1', core_line_id: `cl-${id}`, line_no: 1,
      verb: 'ORDER', state: 'placed', in_autocount: true, in_autocount_link: inAutocountLink,
      links: [{ id: `l-${id}`, kind: inAutocountLink ? 'po' : 'spo', document: 'X-1', qty: '10' }],
      ...over,
    }) as unknown as OrderInquiryWorklistRow;
  const A = doc('row-a', 'ZZT-AAA', true);
  const B = doc('row-b', 'ZZT-BBB', true);
  const C = doc('row-c', 'ZZT-CCC', false);

  async function gear(rows: OrderInquiryWorklistRow[], ticks: string[]) {
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue(rows);
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });
    for (const code of ticks) fireEvent.click(await screen.findByLabelText(`Select ${code}`));
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), { button: 0 });
    await screen.findByRole('menuitem', { name: /auto link/i });
  }
  const optionsKey = () => JSON.stringify((poOptionsSpy.mock.calls[0]?.[0] as { key?: unknown })?.key ?? '');
  afterEach(() => vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([LINKED_LINE]));

  it('shows Auto link, Link PO... (n), Remove link in CRM (n), and none of Link to PO / Change PO / Unlink... / Choose document', async () => {
    await gear([A, B, C], ['ZZT-CCC']);
    expect(screen.getByRole('menuitem', { name: /auto link/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Link PO\.\.\. \(1\)$/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Remove link in CRM \(1\)$/ })).toBeInTheDocument();
    for (const gone of [/^Link to PO/, /^Change PO/, /^Unlink\.\.\./, /^Unlink selected/, /choose document/i]) {
      expect(screen.queryByRole('menuitem', { name: gone })).toBeNull();
    }
  });

  it('two products ticked: Link PO... is disabled', async () => {
    await gear([A, doc('row-d', 'ZZT-DDD', true, { product_id: 'prod-2' })], ['ZZT-AAA', 'ZZT-DDD']);
    expect(screen.getByRole('menuitem', { name: /^Link PO\.\.\./ })).toHaveAttribute('aria-disabled', 'true');
  });

  it('Link PO... opens the shared popup titled Link PO for exactly the ticked row ids', async () => {
    await gear([A, B, C], ['ZZT-AAA', 'ZZT-BBB']);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Link PO\.\.\./ }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Link PO');
    await waitFor(() => expect(poOptionsSpy).toHaveBeenCalled());
    expect(optionsKey()).toContain('row-a');
    expect(optionsKey()).toContain('row-b');
    expect(optionsKey()).not.toContain('row-c');
  });

  it('Remove link in CRM runs the countdown for exactly the ticked CRM-only line, no popup', async () => {
    await gear([A, C], ['ZZT-CCC']);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Remove link in CRM/ }));
    await waitFor(() => expect(createPendingActionSpy).toHaveBeenCalledTimes(1));
    expect(createPendingActionSpy.mock.calls[0][0].entityId).toBe('row-c');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it.each([
    ['the switch is off', () => { poLinkState.switchOn = false; }],
    ['the grant is missing', () => { permState.denied.add(LINK_PO); }],
  ])('%s: Remove link in CRM also takes an AutoCount-tied line through the countdown', async (_n, setup) => {
    setup();
    await gear([A, C], ['ZZT-AAA']);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Remove link in CRM/ }));
    await waitFor(() => expect(createPendingActionSpy).toHaveBeenCalledTimes(1));
    expect(createPendingActionSpy.mock.calls[0][0].entityId).toBe('row-a');
  });
});

// Where AutoCount cannot be written (switch off, or the line is not in AutoCount), Link PO...
// opens the existing CRM placement dialog, PO lines only.
describe('Document view gear: Link PO... without AutoCount falls back to the CRM placement dialog', () => {
  const PO_CANDIDATE = {
    kind: 'po', po_line_id: 'pol-1', tier: 1, location: 'BRW', issue_date: '2026-08-01', cited: false,
    po_number: 'ZZT-PO-0001', supplier_name: 'Dafuyuan', expected_date: '2026-09-01', qty_ordered: '15',
    qty_received: '0', already_tagged: '0', remaining: '15', covers: true, recommended: false,
    default_take: '10', claims: [],
  };
  const SPO_CANDIDATE = {
    ...PO_CANDIDATE, kind: 'spo', po_line_id: null, spo_allocation_id: 'spo-1', po_number: 'ZZT-SPO-0009',
  };
  const line = (over: Record<string, unknown> = {}) =>
    ({ ...LINKED_LINE, id: 'row-q', item_code: 'ZZT-QQQ', product_id: 'prod-1', state: 'raised',
       links: [], core_line_id: 'cl-q', line_no: 1, verb: 'ORDER', ...over }) as unknown as OrderInquiryWorklistRow;
  afterEach(() => vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([LINKED_LINE]));

  it.each([
    ['the switch is off', () => { poLinkState.switchOn = false; }, { in_autocount: true }],
    ['the line is not in AutoCount', () => undefined, { in_autocount: false }],
  ])('%s: Link PO... opens the CRM dialog with PO lines only', async (_n, setup, rowOver) => {
    setup();
    poCandidatesSpy.mockResolvedValue({ candidates: [PO_CANDIDATE, SPO_CANDIDATE], still_to_link: '10' });
    vi.mocked(getOrderInquiryHeaderLines).mockResolvedValue([line(rowOver)]);
    renderDetail('oi-1');
    await screen.findByRole('button', { name: 'Confirm' });
    fireEvent.click(await screen.findByLabelText('Select ZZT-QQQ'));
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Order inquiry options' }), { button: 0 });
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Link PO\.\.\./ }));
    expect(await screen.findByText('Link to a document')).toBeInTheDocument();
    expect(await screen.findByText('ZZT-PO-0001')).toBeInTheDocument();
    expect(screen.queryByText('ZZT-SPO-0009')).toBeNull();
  });
});
