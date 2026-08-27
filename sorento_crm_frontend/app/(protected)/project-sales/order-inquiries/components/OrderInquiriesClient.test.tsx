/**
 * Purchasing's cross-project order inquiry (the screen), rewritten for
 * `PLAN-scm-oi-draft-links.md`: the toolbar is Actions + Start (item 12), the row Actions
 * column and the State column/filter are gone (R8/item 11), the list opens on Confirmed =
 * To confirm (R3/AC-D12), and the "Link up to" box moved off the toolbar into the Auto
 * link all dialog (item 12, tested on its own in `AutoLinkOrderInquiryDialog.test.tsx`).
 *
 * What is worth pinning here: every response shape renders explicitly, the columns read
 * in the sheet's own order with the renamed headers, the two menus carry the right counts
 * and disable at zero, the default filter and its clear round-trip through the URL, and
 * the handshake presses (Confirm selected, Reject selected) send what they say they send.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MOCK_WORKLIST_ROWS,
  MOCK_WORKLIST_SUMMARY,
} from '../../_shared/__mocks__/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

// Every existing test here exercises a purchasing principal (both grants) unless a
// describe block says otherwise; CS's own view-only case gets its own describe block,
// toggling this down to the action grant alone.
let granted = new Set([
  'projects.order_inquiry.action',
  'projects.order_inquiries.acknowledge',
]);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) =>
    slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
  }),
}));

const routerReplace = vi.fn();
let currentSearchParams = new URLSearchParams('');

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: (...args: unknown[]) => routerReplace(...args),
  }),
  usePathname: () => '/project-sales/order-inquiries',
  useSearchParams: () => currentSearchParams,
}));

// Under jsdom nothing answers the preferences fetch, so the grid renders skeletons for
// ever and no row is assertable.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

const listOrderInquiryWorklist = vi.fn();
const getOrderInquiryWorklistSummary = vi.fn();
const downloadOrderInquiryWorklistXlsx = vi.fn();
const autoPlaceOrderInquiryRows = vi.fn();
const getUnplaceAllPreview = vi.fn();
const unplaceAllOrderInquiryRows = vi.fn();
const acknowledgeOrderInquiryRows = vi.fn();
const rejectOrderInquiryRows = vi.fn();
const linkNowOrderInquiryRows = vi.fn();
const getOrderInquiryPoCandidates = vi.fn();
const getOrderInquiryUploadJob = vi.fn();
const unplaceOrderInquiryRow = vi.fn();

vi.mock('../../_shared/services/orderInquiryService', () => ({
  listOrderInquiryWorklist: (...args: unknown[]) =>
    listOrderInquiryWorklist(...args),
  getOrderInquiryWorklistSummary: (...args: unknown[]) =>
    getOrderInquiryWorklistSummary(...args),
  downloadOrderInquiryWorklistXlsx: (...args: unknown[]) =>
    downloadOrderInquiryWorklistXlsx(...args),
  autoPlaceOrderInquiryRows: (...args: unknown[]) =>
    autoPlaceOrderInquiryRows(...args),
  getUnplaceAllPreview: (...args: unknown[]) => getUnplaceAllPreview(...args),
  unplaceAllOrderInquiryRows: (...args: unknown[]) =>
    unplaceAllOrderInquiryRows(...args),
  acknowledgeOrderInquiryRows: (...args: unknown[]) =>
    acknowledgeOrderInquiryRows(...args),
  rejectOrderInquiryRows: (...args: unknown[]) =>
    rejectOrderInquiryRows(...args),
  linkNowOrderInquiryRows: (...args: unknown[]) =>
    linkNowOrderInquiryRows(...args),
  getOrderInquiryPoCandidates: (...args: unknown[]) =>
    getOrderInquiryPoCandidates(...args),
  getOrderInquiryUploadJob: (...args: unknown[]) =>
    getOrderInquiryUploadJob(...args),
  unplaceOrderInquiryRow: (...args: unknown[]) =>
    unplaceOrderInquiryRow(...args),
}));

// The upload dialog is its own suite's subject (`OutstandingUploadDialog` under
// `scm/reorder`); what this file needs is only the `onQueued` seam that hands the queued
// job over, so the real dialog is replaced with a button that fires it directly.
vi.mock('../../../scm/reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: ({
    onQueued,
  }: {
    onQueued?: (queued: {
      job_id: string;
      id: string;
      message: string;
    }) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onQueued?.({ job_id: 'job-1', id: 'job-row-1', message: 'queued' })
      }
    >
      Upload (stub)
    </button>
  ),
}));

// The drawer's feed is what says whether the worker is done with that job (AC-H13).
let uploadSessions: {
  session_id: string;
  import_job_id: string | null;
  status: string;
}[] = [];
vi.mock('@/components/upload-activity/useUploadActivity', () => ({
  useUploadActivity: () => ({
    sessions: uploadSessions,
    badgeCount: 0,
    hasInFlight: false,
    refetch: vi.fn(),
    isLoading: false,
    dismissed: new Set<string>(),
  }),
}));

const saveBlobAs = vi.fn();
vi.mock('../../_shared/services/fileDownload', () => ({
  saveBlobAs: (...args: unknown[]) => saveBlobAs(...args),
  filenameFromContentDisposition: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
  }) => (
    <select
      aria-label={id ?? placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { OrderInquiriesClient } from './OrderInquiriesClient';

function envelope(rows: OrderInquiryWorklistRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiriesClient />
    </QueryClientProvider>,
  );
}

/** Radix opens its dropdown menus on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

function openActionsMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^actions$/i }), {
    button: 0,
    ctrlKey: false,
  });
}

function openStartMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^start$/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  granted = new Set([
    'projects.order_inquiry.action',
    'projects.order_inquiries.acknowledge',
  ]);
  uploadSessions = [];
  getOrderInquiryUploadJob.mockResolvedValue({
    job_id: 'job-1',
    status: 'finished',
    finished: true,
    product_ids: ['product-a', 'product-b'],
    documents: ['202607-S0039', '202607-S0070'],
    document_count: 2,
  });
  currentSearchParams = new URLSearchParams('');
  listOrderInquiryWorklist.mockResolvedValue(envelope(MOCK_WORKLIST_ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue(MOCK_WORKLIST_SUMMARY);
  downloadOrderInquiryWorklistXlsx.mockResolvedValue(new Blob(['x']));
  getUnplaceAllPreview.mockResolvedValue({
    count: 0,
    product_code: null,
    product_name: null,
  });
  getOrderInquiryPoCandidates.mockResolvedValue([]);
});

describe('OrderInquiriesClient: reading the page', () => {
  it('shows the rows purchasing has been told to buy', async () => {
    renderClient();

    expect(await screen.findByText('SO385126')).toBeInTheDocument();
    expect(screen.getByText('SRTWC8605-SC-RL')).toBeInTheDocument();
    expect(screen.getByText('Wall hung basin 5400')).toBeInTheDocument();
    expect(screen.getByText('DAFUYUAN')).toBeInTheDocument();
    expect(screen.getByText('202601-S0015')).toBeInTheDocument();
  });

  it("reads the columns in the sheet's own order, renamed (AC-D15)", async () => {
    renderClient();
    await screen.findByText('SO385126');

    const headers = screen
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent ?? '');
    const order = [
      'SO date',
      'S/O no',
      'Order inquiry',
      'Item code',
      'Qty',
      'Delivery date',
      'Project / customer',
      'Agent',
      'Location',
      'Supplier',
      'Outstanding PO/SPO',
      'Taken by PO/SPO',
      'Remaining',
      'Instruction',
      'Raised by',
      'Raised at',
      'Confirmed',
    ];
    let cursor = -1;
    for (const title of order) {
      const at = headers.findIndex(
        (text, index) => index > cursor && text.includes(title),
      );
      expect(at, `${title} out of order`).toBeGreaterThan(cursor);
      cursor = at;
    }
    // The State column and its header are gone entirely (item 11).
    expect(headers.some((text) => text === 'State')).toBe(false);
    // No row Actions column either (R8).
    expect(headers.some((text) => /^actions$/i.test(text))).toBe(false);
  });

  it('says nothing has been raised yet, and offers the screen that raises it', async () => {
    // The default filter itself counts as "filtered" (AC-D12), so this reads the
    // genuinely-empty state on ?ack=all - a company nothing has ever been raised in.
    currentSearchParams = new URLSearchParams('ack=all');
    listOrderInquiryWorklist.mockResolvedValue(envelope([]));
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      total_rows: 0,
      by_month: [],
    });
    renderClient();

    expect(
      await screen.findByText('Nothing has been raised yet'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /open fulfilment planning/i }),
    ).toHaveAttribute('href', '/project-sales/fulfilment-planning');
  });

  it('says the failure out loud rather than showing an empty table', async () => {
    listOrderInquiryWorklist.mockRejectedValue(new Error('Backend is down'));
    renderClient();

    expect(
      await screen.findByText('The order inquiry could not be loaded'),
    ).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });

  it('renders a loading state before the first answer arrives', async () => {
    listOrderInquiryWorklist.mockReturnValue(new Promise(() => {}));
    const { container } = renderClient();

    await waitFor(() =>
      expect(
        container.querySelectorAll('[data-slot="skeleton"]').length,
      ).toBeGreaterThan(0),
    );
  });

  it('sends the search box to the service', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.change(screen.getByLabelText('Search order inquiry rows'), {
      target: { value: 'SRTWT107' },
    });

    await waitFor(
      () =>
        expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
          expect.objectContaining({ query: 'SRTWT107' }),
        ),
      { timeout: 2000 },
    );
  });

  it('links an adopted row to the core sales order and a project row to its own', async () => {
    renderClient();

    expect(
      await screen.findByRole('link', { name: 'SO385126' }),
    ).toHaveAttribute('href', '/scm/sales-orders/so-385126');
    expect(screen.getByRole('link', { name: 'SO363150' })).toHaveAttribute(
      'href',
      '/project-sales/proj-9/sales-orders/pso-3',
    );
  });

  it('prints the location it was stamped with, and nothing when it has none', async () => {
    renderClient();

    const donor = (await screen.findByText('SO385126')).closest(
      'tr',
    ) as HTMLElement;
    expect(within(donor).getByText('BRW-BB')).toBeInTheDocument();

    const unlocated = screen.getByText('SO386461').closest('tr') as HTMLElement;
    expect(within(unlocated).queryByText('BRW-BB')).not.toBeInTheDocument();
  });
});

describe('AC-D12: the page opens on Confirmed = To confirm', () => {
  it('opens with the active-filter chip shown, off no `?ack=` at all', async () => {
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'to_confirm' }),
      ),
    );
    expect(screen.getByText('Confirmed: To confirm')).toBeInTheDocument();
  });

  it('clearing the chip requests ?ack=all (never absent) and drops the chip', async () => {
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        expect.stringContaining('ack=to_confirm'),
        expect.anything(),
      ),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Clear filter: Confirmed: To confirm',
      }),
    );

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenLastCalledWith(
        expect.objectContaining({ ack: undefined }),
      ),
    );
    expect(screen.queryByText('Confirmed: To confirm')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(routerReplace).toHaveBeenLastCalledWith(
        expect.stringContaining('ack=all'),
        expect.anything(),
      ),
    );
  });

  it('a URL naming ?ack=all opens on every row, not the default', async () => {
    currentSearchParams = new URLSearchParams('ack=all');
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: undefined }),
      ),
    );
    expect(screen.queryByText(/^Confirmed:/)).not.toBeInTheDocument();
  });

  it('the Confirmed filter offers To confirm first, with its own count', async () => {
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      ack: {
        awaiting: 3,
        acknowledged: 1,
        changed: 1,
        rejected: 0,
        to_confirm: 4,
      },
    });
    renderClient();
    await screen.findByText('SO385126');

    openFilters();
    const select = (await screen.findByLabelText('Any')) as HTMLSelectElement;
    expect([...select.options].map((option) => option.textContent)).toEqual([
      'Any',
      'To confirm (4)',
      'Confirmed (1)',
      'Changed (1)',
      'Rejected (0)',
    ]);
  });
});

describe('AC-D13/AC-D14: one toolbar row, Actions + Start, counts disabling at 0', () => {
  it('Actions holds Auto link all, Link selected, Unlink selected, Reject selected, Unlink all, Export Excel', async () => {
    renderClient();
    await screen.findByText('SO385126');

    openActionsMenu();
    for (const name of [
      /Auto link all/,
      /Link selected \(0\)/,
      /Unlink selected \(0\)/,
      /Reject selected \(0\)/,
      /Unlink all/,
      /Export Excel/,
    ]) {
      expect(screen.getByRole('menuitem', { name })).toBeInTheDocument();
    }
    // No "Acknowledge" wording survives anywhere in the menu (R7).
    expect(screen.queryByRole('menuitem', { name: /^Acknowledge/ })).toBeNull();
  });

  it('Start holds Upload purchase orders and Confirm selected, no history upload', async () => {
    renderClient();
    await screen.findByText('SO385126');

    openStartMenu();
    expect(
      screen.getByRole('menuitem', { name: 'Upload purchase orders' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('menuitem', { name: /Confirm selected \(0\)/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /history/i })).toBeNull();
  });

  it('Link selected is enabled ONLY with exactly one row ticked', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openActionsMenu();
    let item = screen.getByRole('menuitem', { name: 'Link selected (1)' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    });

    // A second tick drops it back to disabled - the manual dialog is a ONE-row override.
    fireEvent.click(screen.getByLabelText('Select SRTWT107 on SO363150'));
    openActionsMenu();
    item = screen.getByRole('menuitem', { name: 'Link selected (0)' });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).toHaveAttribute(
      'title',
      'Tick exactly one row to choose its document by hand.',
    );
  });

  it('opens the manual Link dialog for the one ticked row', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Link selected (1)' }),
    );

    expect(await screen.findByText('Link to a document')).toBeInTheDocument();
    expect(getOrderInquiryPoCandidates).toHaveBeenCalledWith('row-2');
  });

  it('Unlink selected counts only linked ticked rows, and disables at 0', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // row-2 is unlinked (raised, linked_qty 0); ticking it never enables Unlink.
    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openActionsMenu();
    expect(
      screen.getByRole('menuitem', { name: 'Unlink selected (0)' }),
    ).toHaveAttribute('aria-disabled', 'true');
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    });

    // row-5 IS linked (placed) - ticking it enables the count.
    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    const item = screen.getByRole('menuitem', { name: 'Unlink selected (1)' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('Reject selected counts every OWED row - draft-linked ones included (plan section 1)', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // row-5 is `placed` (drafted) and still owed - Reject must count it.
    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    const item = screen.getByRole('menuitem', { name: 'Reject selected (1)' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('Confirm selected disables at 0 with a reason, and counts only confirmable rows', async () => {
    renderClient();
    await screen.findByText('SO385126');

    openStartMenu();
    const empty = screen.getByRole('menuitem', {
      name: /Confirm selected \(0\)/,
    });
    expect(empty).toHaveAttribute('aria-disabled', 'true');
    expect(empty).toHaveAttribute('title', 'Tick the rows you are taking on.');
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    });

    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openStartMenu();
    expect(
      screen.getByRole('menuitem', { name: 'Confirm selected (1)' }),
    ).not.toHaveAttribute('aria-disabled', 'true');
  });
});

describe('Unlink selected asks first', () => {
  it('opens a confirmation rather than unlinking on the press itself', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // row-5 is `placed`, so it is the one Unlink selected counts.
    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Unlink selected (1)' }),
    );

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(unplaceOrderInquiryRow).not.toHaveBeenCalled();
  });

  it('unlinks the ticked rows once the confirmation is taken', async () => {
    unplaceOrderInquiryRow.mockResolvedValue({});
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Unlink selected (1)' }),
    );
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Unlink' }));

    await waitFor(() =>
      expect(unplaceOrderInquiryRow).toHaveBeenCalledWith('row-5'),
    );
  });

  it('changes nothing when the confirmation is cancelled', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Unlink selected (1)' }),
    );
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(unplaceOrderInquiryRow).not.toHaveBeenCalled();
  });
});

describe('AC-D5: Confirm selected', () => {
  it('sends exactly the ticked row ids, with no horizon of its own (R6)', async () => {
    acknowledgeOrderInquiryRows.mockResolvedValue({
      acknowledged: 2,
      linked_rows: 1,
      links: 1,
    });
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    fireEvent.click(screen.getByLabelText('Select SRTWT107 on SO363150'));
    openStartMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Confirm selected (2)' }),
    );

    await waitFor(() =>
      expect(acknowledgeOrderInquiryRows).toHaveBeenCalledWith(
        ['row-2', 'row-3'],
        undefined,
      ),
    );
  });

  it('clears the tick marks once the press succeeds', async () => {
    acknowledgeOrderInquiryRows.mockResolvedValue({
      acknowledged: 1,
      linked_rows: 0,
      links: 0,
    });
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openStartMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Confirm selected (1)' }),
    );

    // Wait for the press to land (and the Radix menu to finish closing) before reopening
    // it once - reopening it repeatedly inside the poll races the menu's own animation.
    await waitFor(() => expect(acknowledgeOrderInquiryRows).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole('menu')).not.toBeInTheDocument(),
    );
    openStartMenu();
    expect(
      await screen.findByRole('menuitem', { name: /Confirm selected \(0\)/ }),
    ).toBeInTheDocument();
  });

  it('offers no tickable checkbox for a row that cannot be acknowledged', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // row-1 is `actioned`, row-4 is `cancelled` - disabled rather than absent.
    expect(
      screen.getByLabelText('Select SRTWB5400 on SO385126'),
    ).toBeDisabled();
    expect(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    ).toBeEnabled();
  });
});

describe('AC-D6: Reject selected', () => {
  it('opens the batch dialog with exactly the rejectable ticked rows', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Reject selected (1)' }),
    );

    expect(await screen.findByText('Reject 1 row?')).toBeInTheDocument();
  });

  it('an empty reason is refused, and nothing is sent (validated in BulkRejectOrderInquiryDialog.test.tsx too)', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Reject selected (1)' }),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Reject row' }));

    expect(
      screen.getByText('A reason is required to reject.'),
    ).toBeInTheDocument();
    expect(rejectOrderInquiryRows).not.toHaveBeenCalled();
  });
});

describe('The plan horizon is stated in the header', () => {
  it('reads Plan until off the latest completed reorder plan', async () => {
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      link_up_to_default: '2026-12-31',
    });
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(screen.getByTestId('oi-plan-until')).toHaveTextContent(
        'Plan until 31/12/2026',
      ),
    );
  });

  it('says so when no plan is in force', async () => {
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      link_up_to_default: null,
    });
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(screen.getByTestId('oi-plan-until')).toHaveTextContent(
        'No reorder plan in force',
      ),
    );
  });
});

describe('AC-D9: Auto link all - the date lives in the dialog now', () => {
  it("seeds the dialog with the plan's own coverage date", async () => {
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      link_up_to_default: '2026-12-31',
    });
    renderClient();
    await screen.findByText('SO385126');

    openActionsMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: /Auto link all/ }));

    expect(
      await screen.findByText('Purchase order cut off'),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        (screen.getByTestId('auto-link-cut-off') as HTMLInputElement).value,
      ).toBe('2026-12-31'),
    );
  });

  it('runs the cascade on confirm', async () => {
    autoPlaceOrderInquiryRows.mockResolvedValue({
      placed_rows: 4,
      allocations: 5,
      products_touched: 3,
    });
    renderClient();
    await screen.findByText('SO385126');

    openActionsMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: /Auto link all/ }));
    fireEvent.click(
      await screen.findByRole('button', { name: 'Auto link all' }),
    );

    await waitFor(() => expect(autoPlaceOrderInquiryRows).toHaveBeenCalled());
  });
});

describe('AC-H13: the uploaded book, offered from the Start menu', () => {
  it('offers nothing while the worker is still reading the book', async () => {
    uploadSessions = [
      { session_id: 'job-1', import_job_id: 'job-1', status: 'processing' },
    ];
    renderClient();
    await screen.findByText('SO385126');

    openStartMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Upload purchase orders' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Upload (stub)' }));

    await waitFor(() =>
      expect(getOrderInquiryUploadJob).not.toHaveBeenCalled(),
    );
    expect(screen.queryByRole('button', { name: 'Link now' })).toBeNull();
  });

  it('once the job lands, Link now carries the products it wrote', async () => {
    uploadSessions = [
      { session_id: 'job-1', import_job_id: 'job-1', status: 'linked' },
    ];
    linkNowOrderInquiryRows.mockResolvedValue({
      placed_rows: 2,
      allocations: 3,
    });
    renderClient();
    await screen.findByText('SO385126');

    openStartMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Upload purchase orders' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Upload (stub)' }));

    expect(
      await screen.findByRole('button', { name: 'Link now' }),
    ).toBeInTheDocument();
    // The job's own scope (products/documents) is a separate query behind `landed`; wait
    // for it to answer before pressing, or the press captures an empty product list.
    await waitFor(() =>
      expect(getOrderInquiryUploadJob).toHaveBeenCalledWith('job-1'),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Link now' }));

    await waitFor(() =>
      expect(linkNowOrderInquiryRows).toHaveBeenCalledWith({
        product_ids: ['product-a', 'product-b'],
      }),
    );
  });
});

describe('AC-D8: a CS user (no acknowledge grant) sees the column, not the actions', () => {
  beforeEach(() => {
    granted = new Set(['projects.order_inquiry.action']);
  });

  it('sees the Confirmed column, but no Start menu and no confirm/reject items', async () => {
    renderClient();
    await screen.findByText('SO385126');

    expect(screen.getAllByText('To confirm').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /^start$/i })).toBeNull();

    openActionsMenu();
    expect(
      screen.queryByRole('menuitem', { name: /Reject selected/ }),
    ).toBeNull();
    expect(
      screen.queryByRole('menuitem', { name: /Link selected/ }),
    ).toBeNull();
    expect(
      screen.queryByRole('menuitem', { name: /Unlink selected/ }),
    ).toBeNull();
    // Auto link all and Unlink all/Export are still theirs - they read Found/Not found
    // and un-draft nothing that was confirmed.
    expect(
      screen.getByRole('menuitem', { name: /Auto link all/ }),
    ).toBeInTheDocument();
  });

  it("no row checkbox is offered at all - CS never ticks purchasing's to-do list", async () => {
    renderClient();
    await screen.findByText('SO385126');

    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('the handshake endpoints are never reached for a CS user', async () => {
    renderClient();
    await screen.findByText('SO385126');

    expect(acknowledgeOrderInquiryRows).not.toHaveBeenCalled();
    expect(rejectOrderInquiryRows).not.toHaveBeenCalled();
    expect(linkNowOrderInquiryRows).not.toHaveBeenCalled();
  });
});

describe('the schedule view (unaffected by the draft-links rework)', () => {
  it('switching to Schedule persists ?view=schedule in the URL', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(screen.getByRole('button', { name: 'Schedule' }));

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        expect.stringContaining('view=schedule'),
        expect.objectContaining({ scroll: false }),
      ),
    );
    expect(screen.queryByText('SO385126')).not.toBeInTheDocument();
  });

  it('says nothing is in this view when the filtered schedule is empty', async () => {
    listOrderInquiryWorklist.mockResolvedValue(envelope([]));
    currentSearchParams = new URLSearchParams('view=schedule');
    renderClient();

    expect(
      await screen.findByText('No inquiries in this view'),
    ).toBeInTheDocument();
  });
});

describe('Unlink all (S2/S3/N1, carried over unchanged from the handshake plan)', () => {
  it('names every linked row when no filter narrows the scope', async () => {
    getUnplaceAllPreview.mockResolvedValue({
      count: 5,
      product_code: null,
      product_name: null,
    });
    renderClient();
    await screen.findByText('SO385126');

    openActionsMenu();
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /Unlink all/ }),
    );

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog.textContent).toContain(
      '5 linked rows across the whole company',
    );
  });

  it('distinguishes "no permission" from "genuinely nothing to unplace" (N1)', async () => {
    granted = new Set(); // a view-only principal - no `projects.order_inquiry.action`
    renderClient();
    await screen.findByText('SO385126');

    openActionsMenu();
    const item = await screen.findByRole('menuitem', { name: /Unlink all/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).toHaveAttribute(
      'title',
      "You don't have permission to unlink rows",
    );
    expect(getUnplaceAllPreview).not.toHaveBeenCalled();
  });
});

describe('exports the set the screen is showing, not the whole book', () => {
  it('carries the active ack filter into the export request', async () => {
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'to_confirm' }),
      ),
    );

    openActionsMenu();
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /export excel/i }),
    );

    await waitFor(() =>
      expect(downloadOrderInquiryWorklistXlsx).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'to_confirm' }),
      ),
    );
    await waitFor(() => expect(saveBlobAs).toHaveBeenCalled());
  });
});
