/**
 * Purchasing's cross-project order inquiry (the screen), rewritten for
 * `PLAN-scm-oi-draft-links.md` and again for `PLAN-scm-reorder-oi-feedback-1sep.md` S1: the
 * toolbar is Actions + Start (item 12), the row Actions column, the State column/filter and
 * the Confirmed column are all gone (R8/item 11, S1 AC-1.5), the list opens on every row -
 * no default ack filter (S1, G5) - and the "Link up to" box moved off the toolbar into the
 * Auto link all dialog (item 12, tested on its own in `AutoLinkOrderInquiryDialog.test.tsx`).
 *
 * What is worth pinning here: every response shape renders explicitly, the columns read
 * in the sheet's own order with the renamed headers, the two menus carry the right counts
 * and disable at zero, an explicit ack filter and its clear round-trip through the URL,
 * and the handshake press that remains (Reject selected) sends what it says it sends.
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

// S3: the Schedule view reads its own endpoint now, never the list. Defaulted empty so
// no test here has to know the matrix's own fixture shape unless it is testing the
// matrix itself; the one test that cares about an EMPTY schedule overrides this
// directly rather than emptying the (unrelated) list mock.
const getOrderInquiryMatrix = vi.fn();
vi.mock('../../_shared/services/orderInquiryMatrixService', () => ({
  getOrderInquiryMatrix: (...args: unknown[]) => getOrderInquiryMatrix(...args),
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

vi.mock('@/lib/toast', () => ({
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

/**
 * Escape closes the menu - and, like every Radix modal layer, it stays
 * mounted (keeping `aria-hidden` over the rest of the page) for as long as
 * its own close animation runs (S8-01's shared spring actually ticks in
 * jsdom, unlike the CSS transition it replaced), so a caller has to await it
 * rather than assume Escape is synchronous.
 */
async function closeMenu() {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
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
  // S3: an empty matrix by default - the Schedule view is not what most tests here are
  // about, and this keeps them from depending on that endpoint's own fixture shape.
  getOrderInquiryMatrix.mockResolvedValue({ data: [] });
});

describe('OrderInquiriesClient: reading the page', () => {
  it('shows the rows purchasing has been told to buy', async () => {
    renderClient();

    expect(await screen.findByText('SO385126')).toBeInTheDocument();
    expect(screen.getByText('SRTWC8605-SC-RL')).toBeInTheDocument();
    expect(screen.getByText('Wall hung basin 5400')).toBeInTheDocument();
    expect(screen.getByText('DAFUYUAN')).toBeInTheDocument();
    // AC-R-26 (owner ruling 14 Sep 2026, superseding the 8 Sep cut): the PO column prints
    // the document NUMBER and that number is the lightbox trigger. The coverage headline
    // `35 of 35` moved to the lightbox's own subtitle, so it is not on the list any more.
    expect(screen.getByText('202601-S0015')).toBeInTheDocument();
    expect(screen.queryByText('35 of 35')).not.toBeInTheDocument();
  });

  it("reads the columns in the Excel's own order, renamed (AC-D15, Phase 2 round 2)", async () => {
    renderClient();
    await screen.findByText('SO385126');

    const headers = screen
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent ?? '');
    const order = [
      // The Excel's own column order (Phase 2 round 2): SO date through PO/SPO reads
      // the way the purchasing team already reads their sheet. Order inquiry is NOT in
      // this list any more (R5/AC-OH-01, one-header lane): it is hidden by default, so
      // it renders no `columnheader` cell at all until a reader ticks it back on -
      // asserted separately below, via the Columns menu.
      'SO date',
      'S/O no',
      'Item code',
      'Qty',
      'Delivery date',
      'Project / customer',
      'Supplier',
      // Two columns since 14 Sep, side by side, where "Outstanding PO/SPO" used to be
      // (AC-R-31). The id behind the first is still `po_number`, so a saved layout keeps
      // its place.
      'PO',
      'SPO',
      'Agent',
      'Location',
      'Taken by PO/SPO',
      'Remaining',
      'Instruction',
      'Raised by',
      'Raised at',
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
    // No row Actions column either (R8), and no Confirmed column any more (S1,
    // AC-1.5) - there is no manual confirm left to report on.
    expect(headers.some((text) => /^actions$/i.test(text))).toBe(false);
    expect(headers.some((text) => text === 'Confirmed')).toBe(false);

    // R5/AC-OH-01: Order inquiry is offered in the Columns menu, unticked - present, not
    // removed, so a reader who wants the number back can tick it on.
    fireEvent.pointerDown(screen.getByRole('button', { name: /^columns$/i }), {
      button: 0,
      ctrlKey: false,
    });
    const orderInquiryToggle = await screen.findByRole('menuitemcheckbox', {
      name: 'Order inquiry',
    });
    expect(orderInquiryToggle).toHaveAttribute('aria-checked', 'false');
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

describe('AC-1.5/G5: no default ack filter', () => {
  it('opens on every row, off no `?ack=` at all, and shows no active-filter chip', async () => {
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: undefined }),
      ),
    );
    expect(screen.queryByText(/^Confirmed:/)).not.toBeInTheDocument();
  });

  it('a URL naming an explicit ?ack= still narrows the list and shows its chip', async () => {
    currentSearchParams = new URLSearchParams('ack=rejected');
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'rejected' }),
      ),
    );
    expect(screen.getByText('Confirmed: Rejected')).toBeInTheDocument();
  });

  it('the Confirmed filter no longer offers To confirm (S3, review of PR #471)', async () => {
    // A row is born acknowledged now (G4) and a settle auto-acknowledges again, so
    // nothing purchasing still has to answer sits in `awaiting` any more - the FE stops
    // offering the option even though the backend still accepts an old bookmark's
    // `?ack=to_confirm` for compatibility.
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      ack: {
        awaiting: 0,
        acknowledged: 1,
        changed: 1,
        rejected: 0,
      },
    });
    renderClient();
    await screen.findByText('SO385126');

    openFilters();
    const select = (await screen.findByLabelText('Any')) as HTMLSelectElement;
    expect([...select.options].map((option) => option.textContent)).toEqual([
      'Any',
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

  it('Start is a single Upload purchase orders press, no Confirm and no history upload', async () => {
    // S1 (AC-1.5): a row is born acknowledged, so there is no second press left for
    // Start to hold - it is one button, not a dropdown.
    renderClient();
    await screen.findByText('SO385126');

    expect(
      screen.getByRole('button', { name: 'Upload purchase orders' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Confirm selected/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /history/i })).toBeNull();
  });

  it('AC-T5: Choose document (1) is enabled ONLY with exactly one row ticked', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openActionsMenu();
    let item = screen.getByRole('menuitem', { name: 'Choose document (1)' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
    await closeMenu();

    // A second tick drops it back to disabled - the manual dialog is a ONE-row override.
    fireEvent.click(screen.getByLabelText('Select SRTWT107 on SO363150'));
    openActionsMenu();
    item = screen.getByRole('menuitem', { name: 'Choose document (1)' });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).toHaveAttribute(
      'title',
      'Tick exactly one row to choose its document by hand.',
    );
  });

  it('AC-T5: opens the manual Link dialog for the one ticked row', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Choose document (1)' }),
    );

    expect(await screen.findByText('Link to a document')).toBeInTheDocument();
    expect(getOrderInquiryPoCandidates).toHaveBeenCalledWith('row-2');
  });

  it('AC-T4: Link selected posts auto-place with only the linkable ticked row ids', async () => {
    autoPlaceOrderInquiryRows.mockResolvedValue({
      placed_rows: 1,
      after_horizon: 0,
    });
    renderClient();
    await screen.findByText('SO385126');

    // row-2 (raised, unlinked) is linkable; row-1 (actioned, fully linked) is not.
    fireEvent.click(screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'));
    fireEvent.click(screen.getByLabelText('Select SRTWB5400 on SO385126'));
    openActionsMenu();
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Link selected (1 of 2)' }),
    );

    await waitFor(() =>
      expect(autoPlaceOrderInquiryRows).toHaveBeenCalledWith({ row_ids: ['row-2'] }),
    );
  });

  it('SF-4: a fully bundled row is not linkable - not counted, not posted', async () => {
    // Bundled entirely inside another row's own line (its whole unlinked remainder
    // rides along): `isLinkable` today reads only `qty - linked_qty`, so a row with
    // bundled_qty covering its whole unlinked remainder still counts as needing a
    // document, and "Link selected" would post an id `auto_place_for_rows` refuses
    // (nothing left FOR this row to place - it is not the row's own demand).
    const bundled: OrderInquiryWorklistRow = {
      ...MOCK_WORKLIST_ROWS[1],
      id: 'row-bundled',
      item_code: 'ZZT-BUNDLED',
      so_number: 'SO-BUNDLED',
      qty: '5',
      linked_qty: '0',
      bundled_qty: '5',
      bundled_with: {
        row_id: 'row-host',
        item_code: 'ZZT-HOST',
        item_codes: ['ZZT-HOST'],
        anchor_headline: '5 of 5',
      },
    };
    const plain: OrderInquiryWorklistRow = {
      ...MOCK_WORKLIST_ROWS[1],
      id: 'row-plain',
      item_code: 'ZZT-PLAIN',
      so_number: 'SO-PLAIN',
      qty: '5',
      linked_qty: '0',
      bundled_qty: '0',
      bundled_with: null,
    };
    listOrderInquiryWorklist.mockResolvedValue(envelope([bundled, plain]));
    autoPlaceOrderInquiryRows.mockResolvedValue({ placed_rows: 1, after_horizon: 0 });
    renderClient();
    await screen.findByText('SO-BUNDLED');

    fireEvent.click(screen.getByLabelText('Select ZZT-BUNDLED on SO-BUNDLED'));
    fireEvent.click(screen.getByLabelText('Select ZZT-PLAIN on SO-PLAIN'));
    openActionsMenu();
    expect(
      screen.getByRole('menuitem', { name: 'Link selected (1 of 2)' }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Link selected (1 of 2)' }));

    await waitFor(() =>
      expect(autoPlaceOrderInquiryRows).toHaveBeenCalledWith({ row_ids: ['row-plain'] }),
    );
  });

  it('Unlink selected counts only linked ticked rows, and disables at 0', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // row-2 is unlinked (raised, linked_qty 0); ticking it never enables Unlink. With
    // one row ticked and zero eligible, the label is "(0 of 1)" - `countLabel` only
    // drops the "of n" half when eligible equals ticked.
    fireEvent.click(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    );
    openActionsMenu();
    expect(
      screen.getByRole('menuitem', { name: 'Unlink selected (0 of 1)' }),
    ).toHaveAttribute('aria-disabled', 'true');
    await closeMenu();

    // row-5 IS linked (placed) - ticking it too takes it to "(1 of 2)", still disabled
    // because the OTHER ticked row (row-2) is still not.
    fireEvent.click(screen.getByLabelText('Select SRTWCY7405-PJ on SO381895'));
    openActionsMenu();
    expect(
      screen.getByRole('menuitem', { name: 'Unlink selected (1 of 2)' }),
    ).not.toHaveAttribute('aria-disabled', 'true');
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

  it('AC-T1: every row selectable except cancelled, fully linked and actioned included', async () => {
    // S4, R-A: "Every row except cancelled ticks." row-1 is `actioned` and fully
    // linked and now ticks too (Unlink selected reaches it); row-4 is `cancelled` and
    // is the only one that does not.
    renderClient();
    await screen.findByText('SO385126');

    expect(
      screen.getByLabelText('Select SRTWB5400 on SO385126'),
    ).toBeEnabled();
    expect(
      screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'),
    ).toBeEnabled();
    expect(
      screen.getByLabelText('Select BT012-CR on PSO-000412'),
    ).toBeDisabled();
  });

  it('AC-T2: three rows ticked - one fully linked, one partly linked, one unlinked - label the eligible count', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // row-1 actioned/fully linked, row-3 partly_linked, row-2 raised/unlinked.
    fireEvent.click(screen.getByLabelText('Select SRTWB5400 on SO385126'));
    fireEvent.click(screen.getByLabelText('Select SRTWT107 on SO363150'));
    fireEvent.click(screen.getByLabelText('Select SRTWC8605-SC-RL on SO386461'));
    openActionsMenu();

    // Link selected: row-3 (partly linked, remainder owed) and row-2 (raised) are
    // linkable, row-1 (actioned) is not -> 2 of 3.
    expect(
      screen.getByRole('menuitem', { name: 'Link selected (2 of 3)' }),
    ).toBeInTheDocument();
    // Reject selected: row-1 (actioned) has nothing left to refuse - only row-2 and
    // row-3 are still owed an answer -> 2 of 3.
    expect(
      screen.getByRole('menuitem', { name: 'Reject selected (2 of 3)' }),
    ).toBeInTheDocument();
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

describe('S2/R-H: the "Plan until" subtitle is retired from the page', () => {
  it('renders no "Plan until" text anywhere, with or without a plan horizon in force', async () => {
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      link_up_to_default: '2026-12-31',
    });
    renderClient();
    await screen.findByText('SO385126');

    // The date is not gone - it moved into the Auto link all dialog (item 12) - but the
    // page-level subtitle and its testid are.
    expect(screen.queryByTestId('oi-plan-until')).not.toBeInTheDocument();
    expect(screen.queryByText(/Plan until/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No Plan until in force/)).not.toBeInTheDocument();
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

describe('AC-H13: the uploaded book, offered from the Start button', () => {
  it('offers nothing while the worker is still reading the book', async () => {
    uploadSessions = [
      { session_id: 'job-1', import_job_id: 'job-1', status: 'processing' },
    ];
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(
      screen.getByRole('button', { name: 'Upload purchase orders' }),
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

    fireEvent.click(
      screen.getByRole('button', { name: 'Upload purchase orders' }),
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

  it('sees the rows, but no Upload button and no confirm/reject items', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // No Confirmed column any more (S1, AC-1.5) - and no upload/Start press either,
    // since that is purchasing's own grant.
    expect(
      screen.queryByRole('columnheader', { name: 'Confirmed' }),
    ).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'Upload purchase orders' }),
    ).toBeNull();

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
    // S3: Schedule reads its own matrix endpoint now, never the list - emptying
    // `listOrderInquiryWorklist` (as this test did before S3) no longer has any effect
    // on it. `getOrderInquiryMatrix` defaults to `{ data: [] }` in `beforeEach` already.
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
    // No default filter any more (S1, AC-1.5) - an explicit one, named in the URL,
    // still has to reach the export exactly as it reaches the list.
    currentSearchParams = new URLSearchParams('ack=rejected');
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'rejected' }),
      ),
    );

    openActionsMenu();
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /export excel/i }),
    );

    await waitFor(() =>
      expect(downloadOrderInquiryWorklistXlsx).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'rejected' }),
      ),
    );
    await waitFor(() => expect(saveBlobAs).toHaveBeenCalled());
  });
});

describe('AC-F1: the five S1 filters travel in the URL', () => {
  const FACETS = {
    locations: [{ id: 'SRT-HQ', label: 'SRT-HQ', rows: 3 }],
    agents: [{ id: 'agent-1', label: 'AG01', rows: 2 }],
  };

  it('choosing a Location writes location= to the URL', async () => {
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      ...FACETS,
    });
    renderClient();
    await screen.findByText('SO385126');

    openFilters();
    fireEvent.change(await screen.findByLabelText('Every location'), {
      target: { value: 'SRT-HQ' },
    });

    // The PARAM, parsed - not a substring of the whole URL. `stringContaining` would
    // pass on `?relocation=SRT-HQ-2` and on a value that is merely a prefix of the one
    // that was chosen.
    await waitFor(() => expect(routerReplace).toHaveBeenCalled());
    const written = new URLSearchParams(
      String(routerReplace.mock.calls.at(-1)?.[0]).split('?')[1] ?? '',
    );
    expect(written.get('location')).toBe('SRT-HQ');
  });

  it('a URL carrying agent= seeds the Agent select and the request', async () => {
    currentSearchParams = new URLSearchParams('agent=agent-1');
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      ...FACETS,
    });
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ agent: 'agent-1' }),
      ),
    );
    openFilters();
    const select = (await screen.findByLabelText(
      'Every agent',
    )) as HTMLSelectElement;
    expect(select.value).toBe('agent-1');
  });
});

describe('AC-OH-70: the Filters popover scrolls (`oi-worklist-one-header-acceptance-criteria.md` S7)', () => {
  /**
   * TEST-FIRST: today `filtersContent` in `OrderInquiriesClient.tsx` is a plain
   * `<div className="space-y-3">` with no height bound at all, so this fails on a null
   * scroll-container ancestor until the coder wraps it (or the `DropdownMenuContent` it
   * renders into) with `overflow-y-auto` + a `max-h-` class - "a class on the content",
   * per the plan, since the shared `data-grid-list-toolbar.tsx` primitive has no
   * max-height prop of its own.
   *
   * Selector asserted on: the nearest ancestor of the "Confirmed" label (the popover's
   * OWN last field, AC-OH-70's own wording) whose class list contains
   * `overflow-y-auto`, found via `closest('[class*="overflow-y-auto"]')` - and that
   * same element's className also matching `/max-h-/`. Reported to the captain as the
   * exact contract this test pins; the coder may add the classes to a new wrapper div
   * or to an existing one, as long as some ancestor between "Confirmed" and the popover
   * carries both.
   */
  it('bounds the Filters content to the viewport and scrolls it, so Confirmed is reachable', async () => {
    renderClient();
    await screen.findByText('SO385126');

    openFilters();
    // "Confirmed" also names the toolbar's own active-filter chip once one is set
    // (`activeSummary`, e.g. "Confirmed: Rejected") - the popover's own FIELD label is
    // the plain `<label>` element among the matches.
    const confirmedLabel = (await screen.findAllByText('Confirmed')).find(
      (node) => node.tagName === 'LABEL',
    );
    expect(confirmedLabel).toBeDefined();

    const scrollContainer = confirmedLabel!.closest('[class*="overflow-y-auto"]');
    expect(scrollContainer).not.toBeNull();
    expect(scrollContainer?.className ?? '').toMatch(/max-h-/);
  });
});
