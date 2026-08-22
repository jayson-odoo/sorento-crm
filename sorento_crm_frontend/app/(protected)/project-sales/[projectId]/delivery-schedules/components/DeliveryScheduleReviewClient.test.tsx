/**
 * P6 - the reconciliation surface (AC-E1 to AC-E5, contract section 4).
 *
 * The measured spike is what these tests defend: roughly a fifth of columns came out wrong on
 * the real R1, so the screen is not an accept-or-reject. What has to hold is that all three
 * numbers are on screen per column, that a correction flips a column without a reload, that an
 * unidentified column is fixable in place, that a partial extraction never reads as success,
 * and that confirm is refused until somebody either fixes the columns or says why not.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  DeliveryScheduleVersion,
} from '../../../_shared/types/deliverySchedule.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

// The reconciliation section is the shared DataGrid, and under jsdom nothing answers the
// column-preferences fetch, so the grid would render skeletons instead of rows (CLAUDE.md).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

/**
 * The gear is rendered open, the way the dealer-kit gear tests do it: Radix opens its menu on
 * a pointer sequence into a portal, and what has to hold here is what the menu CONTAINS.
 */
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({
    children,
    ariaLabel,
  }: {
    children: React.ReactNode;
    ariaLabel?: string;
  }) => (
    <div data-testid="gear-menu" aria-label={ariaLabel}>
      {children}
    </div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: (props: React.ComponentProps<'div'> & { asChild?: boolean }) => {
    // `asChild` is a Radix concern and must not reach the DOM.
    const { children, asChild, ...rest } = props;
    void asChild;
    return (
      <div role="menuitem" {...rest}>
        {children}
      </div>
    );
  },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/delivery-schedules/v2',
  useSearchParams: () => new URLSearchParams(''),
}));

/**
 * The header's prev/next pager, which walks this schedule's own revisions. Mocked at the
 * shared hook so nothing is fetched and the arguments the feature hook passes can be read.
 */
const recordNeighbours = vi.fn((..._args: unknown[]) => ({
  prevId: 'v3',
  nextId: 'v1',
  index: 2,
  total: 3,
  isLoading: false,
}));
vi.mock('@/hooks/useRecordNeighbours', () => ({
  useRecordNeighbours: (...args: unknown[]) => recordNeighbours(...args),
}));

const getDeliveryScheduleVersion = vi.fn();
const saveDeliveryScheduleCells = vi.fn();
const resolveDeliveryScheduleProduct = vi.fn();
const confirmDeliveryScheduleVersion = vi.fn();
const listDeliveryScheduleVersions = vi.fn();
const acceptRevisionProposal = vi.fn();
const rejectRevisionProposal = vi.fn();
vi.mock('../../../_shared/services/deliveryScheduleService', () => ({
  DELIVERY_SCHEDULE_VERSION_NEIGHBOURS_PATH:
    '/api/v1/project-sales/delivery-schedule-versions/neighbours',
  listDeliverySchedules: vi.fn(),
  listDeliveryScheduleVersions: (...args: unknown[]) => listDeliveryScheduleVersions(...args),
  uploadDeliverySchedule: vi.fn(),
  getDeliveryScheduleVersion: (...args: unknown[]) => getDeliveryScheduleVersion(...args),
  saveDeliveryScheduleCells: (...args: unknown[]) => saveDeliveryScheduleCells(...args),
  resolveDeliveryScheduleProduct: (...args: unknown[]) =>
    resolveDeliveryScheduleProduct(...args),
  confirmDeliveryScheduleVersion: (...args: unknown[]) =>
    confirmDeliveryScheduleVersion(...args),
  acceptRevisionProposal: (...args: unknown[]) => acceptRevisionProposal(...args),
  rejectRevisionProposal: (...args: unknown[]) => rejectRevisionProposal(...args),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const getProject = vi.fn();
vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/projectService')>();
  return { ...actual, getProject: (...args: unknown[]) => getProject(...args) };
});

// The pickers offer the PO's own products, so the review screen reads the PO version the
// schedule was checked against. Mocked at the service, like every other network call here.
const getPOVersion = vi.fn();
vi.mock('../../../_shared/services/poIntakeService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../_shared/services/poIntakeService')>();
  return { ...actual, getPOVersion: (...args: unknown[]) => getPOVersion(...args) };
});

const getProductsForVariantSelect = vi.fn();
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: (...args: unknown[]) => getProductsForVariantSelect(...args),
}));

import { DeliveryScheduleReviewClient } from './DeliveryScheduleReviewClient';

/**
 * The sentences `buildColumnStates` writes for this fixture, in full.
 *
 * Held here rather than inline because the same sentence has to be found in three places
 * (the list, the phone cards, the confirm dialog) and because what is being pinned is that
 * each one still ends in the thing to do next.
 */
/**
 * The flush valve asks for 8 of the 16 ordered, and that is a partial schedule - normal on a
 * live project, a WARNING rather than something to fix, and the same verdict the server
 * reaches. It used to be a blocker on this screen alone.
 */
const SHORTFALL_WARNING =
  'The schedule asks for 8 of the 16 on the purchase order; the remaining 8 is expected ' +
  'on a later schedule.';
const REPORTED_MISMATCH_MESSAGE =
  "The phases add up to 8 but the schedule's own TOTAL QTY row says 16. " +
  'One of the two was misread, so check the cells against the paper.';
const NOT_ON_PO_MESSAGE =
  'The PO version does not order this item, but the schedule asks for 927. ' +
  'Check the column is the right product, or amend the PO.';
const NEEDS_PRODUCT_MESSAGE =
  'BUI-HB-SRTWB7055 is not matched to a product. Pick the product this column means.';

function version(overrides: Partial<DeliveryScheduleVersion> = {}): DeliveryScheduleVersion {
  return {
    id: 'v2',
    delivery_schedule_id: 's1',
    version_no: 2,
    revision_label: 'REVISED 1 - 23/7/2026',
    issuer_party_label: 'SLG Construction Sdn Bhd',
    po_version_id: 'pv1',
    po_version_no: 1,
    purchase_order_id: 'po1',
    extraction_state: 'done',
    document_url: 'https://example.test/schedule.pdf',
    schedule_date: '2026-07-23',
    po_number: 'HQ/26/01/121',
    page_count: 7,
    pages_extracted: 7,
    phases: [
      {
        id: 'ph1',
        area_group: 'TOWER',
        sequence: 1,
        label: 'Level 2 & 7',
        delivery_date: '2026-07-01',
      },
      // No label at all, exactly as the COMMON AREA rows come off the document.
      { id: 'ph2', area_group: 'COMMON AREA', sequence: 3, label: null, delivery_date: '2027-06-01' },
    ],
    products: [
      {
        product_id: 'p1',
        product_code: 'SRTWC8613-RL',
        product_name: 'One-Piece WC',
        customer_code_raw: 'BUI-HB-SRTWC8613-RL',
        resolution_source: 'code',
        column_total: '927',
        reported_total: '927',
        po_qty: '927',
        reconciled: true,
        product_index: 0,
      },
      {
        product_id: 'p2',
        product_code: 'SRTFV1001',
        product_name: 'Sensor Urinal Flush Valve',
        customer_code_raw: 'BUI-HB-SRTFV1001',
        resolution_source: 'code',
        column_total: '8',
        reported_total: '16',
        po_qty: '16',
        reconciled: false,
        product_index: 1,
      },
      {
        product_id: null,
        product_code: null,
        product_name: null,
        customer_code_raw: 'BUI-HB-SRTWB7055',
        resolution_source: null,
        column_total: '927',
        reported_total: '927',
        po_qty: null,
        reconciled: false,
        product_index: 2,
      },
    ],
    cells: [
      { phase_id: 'ph1', product_id: 'p1', product_index: 0, qty: '927' },
      { phase_id: 'ph2', product_id: 'p2', product_index: 1, qty: '8' },
      { phase_id: 'ph1', product_id: null, product_index: 2, qty: '927' },
    ],
    reconciliation: { reconciled_columns: 1, total_columns: 3 },
    confirmed_at: null,
    ...overrides,
  };
}

function renderReview() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DeliveryScheduleReviewClient projectId="p1" versionId="v2" />
    </QueryClientProvider>,
  );
}

const matrix = () => within(screen.getByTestId('schedule-matrix'));

/** The PO version 'pv1' is checked against: three lines, all resolved to a product. */
function poVersion() {
  return {
    id: 'pv1',
    lines: [
      {
        id: 'l1',
        line_no: 1,
        description_raw: 'ONE-PIECE WC',
        resolved_product_id: 'p1',
        resolved_product_code: 'SRTWC8613-RL',
      },
      {
        id: 'l2',
        line_no: 2,
        description_raw: 'SENSOR URINAL FLUSH VALVE',
        resolved_product_id: 'p2',
        resolved_product_code: 'SRTFV1001',
      },
      {
        id: 'l3',
        line_no: 3,
        description_raw: 'COUNTER-TOP BASIN',
        resolved_product_id: 'p6',
        resolved_product_code: 'SRTWB7055',
      },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getDeliveryScheduleVersion.mockResolvedValue(version());
  listDeliveryScheduleVersions.mockResolvedValue([]);
  getPOVersion.mockResolvedValue(poVersion());
  getProject.mockResolvedValue({ id: 'p1', project_code: 'PRJ-1', title: 'Tuju', can_edit: true });
  getProductsForVariantSelect.mockResolvedValue([
    { id: 'p6', product_code: 'SRTWB7055', product_name: 'Counter-Top Basin' },
  ]);
  saveDeliveryScheduleCells.mockImplementation(async () => version());
  resolveDeliveryScheduleProduct.mockImplementation(async () => version());
  confirmDeliveryScheduleVersion.mockImplementation(async () =>
    version({ confirmed_at: '2026-07-24T01:05:00' }),
  );
});

describe('DeliveryScheduleReviewClient', () => {
  it('shows a skeleton shaped like the page it becomes', () => {
    getDeliveryScheduleVersion.mockReturnValue(new Promise(() => {}));
    const { container } = renderReview();
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('schedule-matrix')).toBeNull();
  });

  it('states a load failure and offers the way back', async () => {
    getDeliveryScheduleVersion.mockRejectedValue(new Error('Nothing answered'));
    renderReview();

    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByText('Nothing answered')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /Back to delivery schedules/i }),
    ).toHaveAttribute('href', '/project-sales/p1?tab=schedules');
  });

  it('says the document is queued without inventing a percentage', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        extraction_state: 'queued',
        pages_extracted: 0,
        phases: [],
        products: [],
        cells: [],
      }),
    );
    renderReview();

    expect(await screen.findByText('Queued')).toBeInTheDocument();
    expect(screen.getByText('7 pages waiting to be read.')).toBeInTheDocument();
    expect(screen.queryByTestId('schedule-matrix')).toBeNull();
  });

  it('reports honest progress while it reads', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        extraction_state: 'running',
        pages_extracted: 3,
        phases: [],
        products: [],
        cells: [],
      }),
    );
    renderReview();

    expect(await screen.findByText('Reading the schedule')).toBeInTheDocument();
    expect(screen.getByText('Page 4 of 7.')).toBeInTheDocument();
  });

  it('does not let a partial extraction look like success', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        extraction_state: 'partial',
        pages_extracted: 5,
        extraction_error: 'Pages 6 and 7 could not be read.',
      }),
    );
    renderReview();

    expect(
      await screen.findByText('Only 5 of 7 pages were read'),
    ).toBeInTheDocument();
    expect(screen.getByText('Pages 6 and 7 could not be read.')).toBeInTheDocument();
    // The grid still renders: what WAS read is still worth reconciling.
    expect(screen.getByTestId('schedule-matrix')).toBeInTheDocument();
  });

  it('treats a done version carrying an extraction error as partial, not done', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({ extraction_state: 'done', extraction_error: 'Page 4 was unreadable.' }),
    );
    renderReview();

    expect(await screen.findByText('Page 4 was unreadable.')).toBeInTheDocument();
  });

  it('names a failed extraction and points at the retry', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        extraction_state: 'failed',
        extraction_error: 'The file is not a readable PDF or image.',
        phases: [],
        products: [],
        cells: [],
      }),
    );
    renderReview();

    expect(await screen.findByText(/could not be read/i)).toBeInTheDocument();
    expect(
      screen.getByText('The file is not a readable PDF or image.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Upload it again/i })).toBeInTheDocument();
  });

  it('heads the screen with the PO, the revision and the PO version it is checked against', async () => {
    renderReview();

    expect(
      await screen.findByRole('heading', { name: 'Delivery schedule for HQ/26/01/121' }),
    ).toBeInTheDocument();
    expect(screen.getByText('REVISED 1 - 23/7/2026')).toBeInTheDocument();
    expect(screen.getByText('Issued by SLG Construction Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Checked against PO version 1')).toBeInTheDocument();
  });

  it('puts all three numbers on every column and marks the ones that disagree', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const grid = matrix();
    expect(grid.getByText('Our total')).toBeInTheDocument();
    expect(grid.getByText('Schedule TOTAL QTY')).toBeInTheDocument();
    expect(grid.getByText('PO quantity')).toBeInTheDocument();

    // The reconciled column and the misread ones read differently at a glance. The flush
    // valve has ONE thing to fix (its own TOTAL QTY row), the unmatched column two.
    expect(grid.getAllByText('Reconciled')).toHaveLength(1);
    expect(grid.getByText('1 to fix')).toBeInTheDocument();
    expect(grid.getByText('2 to fix')).toBeInTheDocument();

    // The column the PO never ordered says so where the number would be.
    expect(grid.getByText('Not on the PO')).toBeInTheDocument();
    expect(screen.getByText('1 of 3 columns reconciled')).toBeInTheDocument();
  });

  it('names the blocking columns in the grid AND in the summary', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByText(REPORTED_MISMATCH_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText(NEEDS_PRODUCT_MESSAGE)).toBeInTheDocument();
    // In the grid too, not only in the message.
    expect(matrix().getAllByText('BUI-HB-SRTWB7055').length).toBeGreaterThan(0);
  });

  it('says what the section is for before it lists a single problem', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(
      screen.getByText(
        'Every column has to agree with the PO before this schedule can be confirmed.',
      ),
    ).toBeInTheDocument();
  });

  it('tables the reconciliation, one row per column, every finding in it', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const list = within(screen.getByTestId('reconciliation-list'));
    // Two blocked columns and the shortfall warning, one row each. The reconciled column
    // with nothing to say is not listed.
    const rows = list
      .getAllByRole('row')
      .filter((node) => node.querySelector('td') !== null);
    expect(rows).toHaveLength(2);

    // Every sentence the check wrote, in the Problem column, whichever row it belongs to.
    expect(list.getByText(REPORTED_MISMATCH_MESSAGE)).toBeInTheDocument();
    expect(list.getByText(NOT_ON_PO_MESSAGE)).toBeInTheDocument();
    expect(list.getByText(NEEDS_PRODUCT_MESSAGE)).toBeInTheDocument();
    // The shortfall is stated as a warning rather than as something to fix. This row is
    // blocked all the same, by its own TOTAL QTY row, and the pill says the worst of the two.
    expect(list.getByTestId('reconciliation-warning')).toHaveTextContent(SHORTFALL_WARNING);
    expect(list.getAllByText('Blocked')).toHaveLength(2);

    // Truncated with the whole sentence on `title`: the numbers it quotes are in their own
    // columns beside it, so what is cut is the wording rather than the facts.
    const details = list.getAllByTestId('reconciliation-detail');
    expect(details).toHaveLength(3);
    details.forEach((node) => {
      expect(String(node.className)).toContain('truncate');
      expect(node).toHaveAttribute('title', node.textContent);
    });
  });

  /**
   * "You just need a gear button at top right, with view PO as one of the dropdown."
   *
   * The header used to carry a button per destination and a PO link on every reconciliation
   * row - three links to the same page, next to sentences they do not answer.
   */
  it('puts the ways out behind one gear, and opens the PO in a new tab', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    // Nothing standing in the header but Confirm: no button per destination.
    expect(screen.queryByRole('button', { name: /View document/ })).toBeNull();

    const gear = within(screen.getByTestId('gear-menu'));
    expect(screen.getByTestId('gear-menu')).toHaveAttribute('aria-label', 'Schedule actions');

    const po = gear.getByRole('link', { name: /View PO/ });
    // The PO RECORD, not the document confirm screen: amending the PO is what the reviewer
    // comes here to do. New tab, because leaving loses the cells they have typed.
    expect(po).toHaveAttribute('href', '/project-sales/p1/pos/po1');
    expect(po).toHaveAttribute('target', '_blank');
    expect(po).toHaveAttribute('rel', expect.stringContaining('noopener'));

    const document = gear.getByRole('link', { name: /View document/ });
    expect(document).toHaveAttribute('href', 'https://example.test/schedule.pdf');
    expect(document).toHaveAttribute('target', '_blank');
  });

  it('offers no gear when there is nothing behind it', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({ purchase_order_id: null, po_version_id: null, document_url: null }),
    );
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.queryByTestId('gear-menu')).toBeNull();
  });

  it('takes a reconciliation row to its column in the grid', async () => {
    const scrollIntoView = vi.fn();
    // jsdom implements none, and the component calls it optionally for that reason.
    (Element.prototype as unknown as { scrollIntoView: unknown }).scrollIntoView =
      scrollIntoView;

    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(
      within(screen.getByTestId('reconciliation-list')).getByRole('button', {
        name: 'Go to SRTFV1001 in the schedule',
      }),
    );

    expect(scrollIntoView).toHaveBeenCalled();
  });

  it('lands a quantity fix IN the cell to be typed into, not merely near it', async () => {
    (Element.prototype as unknown as { scrollIntoView: unknown }).scrollIntoView = vi.fn();
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(
      within(screen.getByTestId('reconciliation-list')).getAllByRole('button', {
        name: 'Fix the quantities',
      })[0],
    );

    // The flush valve takes nothing at Level 2 & 7 and 8 at Phase 3, and BOTH are typeable,
    // so the first cell of the column is where the cursor belongs.
    await waitFor(() =>
      expect(matrix().getByLabelText('Level 2 & 7, SRTFV1001')).toHaveFocus(),
    );
  });

  it('counts what is left to fix, and counts down as a column is corrected', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByTestId('reconciliation-remaining')).toHaveTextContent(
      '2 columns still to fix.',
    );

    fireEvent.change(matrix().getByLabelText('Phase 3, SRTFV1001'), {
      target: { value: '16' },
    });

    await waitFor(() =>
      expect(screen.getByTestId('reconciliation-remaining')).toHaveTextContent(
        '1 column still to fix.',
      ),
    );
  });

  it('offers no fix in the list to a reviewer who cannot edit, only the jump', async () => {
    getProject.mockResolvedValue({
      id: 'p1',
      project_code: 'PRJ-1',
      title: 'Tuju',
      can_edit: false,
    });
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const list = within(screen.getByTestId('reconciliation-list'));
    expect(list.queryByLabelText(/Pick the product/)).toBeNull();
    expect(list.queryByLabelText(/Pick a different product/)).toBeNull();
    expect(list.queryByRole('button', { name: 'Fix the quantities' })).toBeNull();
    expect(list.queryByRole('link', { name: /Open the PO/ })).toBeNull();
    expect(
      list.getByRole('button', { name: 'Go to SRTFV1001 in the schedule' }),
    ).toBeInTheDocument();
  });

  it('reports rather than instructs when the schedule can no longer be changed', async () => {
    // A confirmed schedule still lists what disagreed, and that is worth keeping. But
    // "2 columns still to fix" on a screen that accepts no fix is asking for work it
    // will refuse, which is the same confusion in a new place.
    getProject.mockResolvedValue({
      id: 'p1',
      project_code: 'PRJ-1',
      title: 'Tuju',
      can_edit: false,
    });
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByTestId('reconciliation-remaining')).toHaveTextContent(
      '2 columns did not agree.',
    );
    expect(screen.getByTestId('reconciliation-remaining')).not.toHaveTextContent(
      'to fix',
    );
    expect(screen.getByText(/confirmed, so nothing here can be changed/i)).toBeInTheDocument();
  });

  it('lets a column that resolved to the WRONG product be changed, in both views', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    // SRTFV1001 is matched already and still does not reconcile, which used to mean the
    // picker was withheld and the only way out was deleting something.
    expect(
      matrix().getByLabelText('Change the product for BUI-HB-SRTFV1001'),
    ).toBeInTheDocument();

    const phone = within(screen.getByTestId('schedule-columns-mobile'));
    fireEvent.click(phone.getAllByRole('button', { expanded: false })[1]);
    expect(
      phone.getByLabelText('Change the product for BUI-HB-SRTFV1001'),
    ).toBeInTheDocument();
  });

  it('renders a blank cell blank, because a blank is not a zero', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    // Level 2 & 7 does not take the flush valve at all.
    const untouched = matrix().getByLabelText('Level 2 & 7, SRTFV1001');
    expect(untouched).toHaveValue('');
  });

  it('flips a column to reconciled as the correction is typed, and saves it', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const cell = matrix().getByLabelText('Phase 3, SRTFV1001');
    expect(cell).toHaveValue('8');

    fireEvent.change(cell, { target: { value: '16' } });

    // No reload, no round trip: the column agrees the moment the number does.
    await waitFor(() =>
      expect(screen.getByText('2 of 3 columns reconciled')).toBeInTheDocument(),
    );

    fireEvent.blur(cell);
    await waitFor(() =>
      expect(saveDeliveryScheduleCells).toHaveBeenCalledWith('v2', [
        { phase_id: 'ph2', product_id: 'p2', qty: '16' },
      ]),
    );
  });

  it('writes a cleared cell back as the delete the API expects', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const cell = matrix().getByLabelText('Phase 3, SRTFV1001');
    fireEvent.change(cell, { target: { value: '' } });
    fireEvent.blur(cell);

    await waitFor(() =>
      expect(saveDeliveryScheduleCells).toHaveBeenCalledWith('v2', [
        { phase_id: 'ph2', product_id: 'p2', qty: '0' },
      ]),
    );
  });

  it('saves nothing when the value comes back unchanged', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const cell = matrix().getByLabelText('Phase 3, SRTFV1001');
    fireEvent.change(cell, { target: { value: '8' } });
    fireEvent.blur(cell);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(saveDeliveryScheduleCells).not.toHaveBeenCalled();
  });

  it('locks the cells of a column with no product, and offers the picker instead', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const grid = matrix();
    expect(grid.getByLabelText('Level 2 & 7, BUI-HB-SRTWB7055')).toBeDisabled();
    expect(
      grid.getByLabelText('Pick the product for BUI-HB-SRTWB7055'),
    ).toBeInTheDocument();
  });

  it('resolves an unidentified column and says the code is remembered, once', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(matrix().getByLabelText('Pick the product for BUI-HB-SRTWB7055'));
    const option = await screen.findByText('SRTWB7055');
    fireEvent.click(option);

    await waitFor(() =>
      expect(resolveDeliveryScheduleProduct).toHaveBeenCalledWith('v2', 2, 'p6'),
    );
    expect(
      await screen.findByText(
        /BUI-HB-SRTWB7055 will resolve to .* on this customer's next schedule\./,
      ),
    ).toBeInTheDocument();
  });

  it('refuses to confirm while a column is unreconciled, then allows it with a reason', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm$/ }));

    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText('2 columns do not add up yet.')).toBeInTheDocument();
    // Named in the dialog, with the numbers, so the decision is informed.
    expect(dialog.getByText('SRTFV1001')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: /^Confirm$/ })).toBeDisabled();

    fireEvent.click(dialog.getByRole('checkbox'));
    expect(dialog.getByRole('button', { name: /^Confirm$/ })).toBeDisabled();

    fireEvent.change(dialog.getByLabelText(/Reason/i), {
      target: { value: 'Customer confirmed the valve quantity by email.' },
    });
    expect(dialog.getByRole('button', { name: /^Confirm$/ })).toBeEnabled();

    fireEvent.click(dialog.getByRole('button', { name: /^Confirm$/ }));
    await waitFor(() =>
      expect(confirmDeliveryScheduleVersion).toHaveBeenCalledWith('v2', {
        acknowledge_unreconciled: true,
        reason: 'Customer confirmed the valve quantity by email.',
      }),
    );
  });

  it('confirms with no acknowledgement once every column agrees', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        products: [
          {
            product_id: 'p1',
            product_code: 'SRTWC8613-RL',
            product_name: 'One-Piece WC',
            customer_code_raw: 'BUI-HB-SRTWC8613-RL',
            resolution_source: 'code',
            column_total: '927',
            reported_total: '927',
            po_qty: '927',
            reconciled: true,
            product_index: 0,
          },
        ],
        cells: [{ phase_id: 'ph1', product_id: 'p1', product_index: 0, qty: '927' }],
        reconciliation: { reconciled_columns: 1, total_columns: 1 },
      }),
    );
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText(/Every column agrees with the PO/i)).toBeInTheDocument();
    expect(dialog.queryByRole('checkbox')).toBeNull();

    fireEvent.click(dialog.getByRole('button', { name: /^Confirm$/ }));
    await waitFor(() =>
      expect(confirmDeliveryScheduleVersion).toHaveBeenCalledWith('v2', {}),
    );
  });

  it('is read-only once confirmed', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({ confirmed_at: '2026-07-24T01:05:00', confirmed_by_name: 'Eling Tan' }),
    );
    renderReview();

    expect(await screen.findByText(/Confirmed .* by Eling Tan/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Confirm$/ })).toBeNull();
    expect(matrix().getByLabelText('Phase 3, SRTFV1001')).toBeDisabled();
  });

  it('renders a phone view of the same columns alongside the matrix', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const phone = within(screen.getByTestId('schedule-columns-mobile'));
    // One card per column, each carrying its three numbers as labels rather than a wide row.
    expect(phone.getAllByRole('button', { expanded: false })).toHaveLength(3);
    expect(phone.getAllByText('Our total')).toHaveLength(3);
    expect(phone.getAllByText('Schedule')).toHaveLength(3);
    expect(phone.getAllByText('PO')).toHaveLength(3);
  });

  it('opens one phone card at a time, and only then mounts its quantity fields', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const phone = within(screen.getByTestId('schedule-columns-mobile'));
    expect(phone.queryByLabelText('Phase 3, SRTFV1001')).toBeNull();

    fireEvent.click(phone.getAllByRole('button', { expanded: false })[1]);
    expect(phone.getByLabelText('Phase 3, SRTFV1001')).toHaveValue('8');
    expect(phone.getByText(REPORTED_MISMATCH_MESSAGE)).toBeInTheDocument();
  });
});

/**
 * The header standard, shared with the sales order and the customer PO: ONE call to action
 * (Confirm, which is what this screen is for), everything else behind the gear, and a pager
 * so a reviewer can walk the revisions without going back to the project tab.
 */
describe('DeliveryScheduleReviewClient header', () => {
  it('walks this schedule own revisions', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(recordNeighbours).toHaveBeenCalledWith(
      '/api/v1/project-sales/delivery-schedule-versions/neighbours',
      'v2',
    );
    expect(screen.getByText('2 / 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next schedule version' }));

    expect(push).toHaveBeenCalledWith('/project-sales/p1/delivery-schedules/v1');
  });

  it('keeps Confirm as the one call to action beside the pager', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    // The pager is chevrons, not a third and fourth thing to read.
    expect(screen.getByRole('button', { name: 'Previous schedule version' })).toBeInTheDocument();
  });
});

/** Section 9.1/9.2 of PLAN-so-book-diff-replanning: was -> now, and confirm's amendment notice. */
describe('DeliveryScheduleReviewClient revision diff and amendment banner', () => {
  it('finds this version its predecessor and renders the was -> now diff', async () => {
    listDeliveryScheduleVersions.mockResolvedValue([
      {
        id: 'v1',
        delivery_schedule_id: 's1',
        version_no: 1,
        revision_label: 'R1',
        issuer_party_label: null,
        schedule_date: null,
        extraction_state: 'done',
        reconciled_columns: 1,
        total_columns: 1,
        confirmed_at: '2026-01-20T00:00:00',
        created_at: null,
      },
    ]);

    const current = version({
      phases: [
        {
          id: 'ph1',
          area_group: 'TOWER',
          sequence: 1,
          label: 'Level 2 & 7',
          delivery_date: '2026-07-01',
          promoted_delivery_date: '2026-01-01',
        },
        {
          id: 'ph2',
          area_group: 'COMMON AREA',
          sequence: 3,
          label: null,
          delivery_date: '2027-06-01',
        },
      ],
    });
    const prior = version({
      id: 'v1',
      version_no: 1,
      phases: [
        {
          id: 'prior-ph1',
          area_group: 'TOWER',
          sequence: 1,
          label: 'Level 2 & 7',
          delivery_date: '2026-01-01',
        },
        {
          id: 'prior-ph2',
          area_group: 'COMMON AREA',
          sequence: 3,
          label: null,
          delivery_date: '2027-06-01',
        },
      ],
      cells: [
        { phase_id: 'prior-ph1', product_id: 'p1', product_index: 0, qty: '900' },
        { phase_id: 'prior-ph2', product_id: 'p2', product_index: 1, qty: '8' },
      ],
    });

    getDeliveryScheduleVersion.mockImplementation((id: string) =>
      Promise.resolve(id === 'v1' ? prior : current),
    );

    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(await screen.findByText('Changes since the previous version')).toBeInTheDocument();
    // The phase moved (01/01/2026 -> 01/07/2026) and the WC's quantity grew (900 -> 927).
    expect(await screen.findByText(/1 phase moved/)).toBeInTheDocument();
    expect(screen.getByText(/1 quantit(y|ies) changed/)).toBeInTheDocument();
  });

  it('shows the amendment-needed banner and a toast whose action goes to it, once confirm answers a preview url', async () => {
    const reconciled = version({
      products: [
        {
          product_id: 'p1',
          product_code: 'SRTWC8613-RL',
          product_name: 'One-Piece WC',
          customer_code_raw: 'BUI-HB-SRTWC8613-RL',
          resolution_source: 'code',
          column_total: '927',
          reported_total: '927',
          po_qty: '927',
          reconciled: true,
          product_index: 0,
        },
      ],
      cells: [{ phase_id: 'ph1', product_id: 'p1', product_index: 0, qty: '927' }],
      reconciliation: { reconciled_columns: 1, total_columns: 1 },
    });
    getDeliveryScheduleVersion.mockResolvedValue(reconciled);
    confirmDeliveryScheduleVersion.mockResolvedValue({
      ...reconciled,
      confirmed_at: '2026-07-24T01:05:00',
      amendment_preview_url: '/project-sales/p1/sales-orders/so-1/revisions',
    });

    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    fireEvent.click(dialog.getByRole('button', { name: /^Confirm$/ }));

    await waitFor(() => expect(confirmDeliveryScheduleVersion).toHaveBeenCalled());

    expect(await screen.findByTestId('amendment-needed-banner')).toHaveTextContent(
      'the linked sales order has not been amended yet',
    );
    expect(screen.getByRole('link', { name: 'Review the amendment' })).toHaveAttribute(
      'href',
      '/project-sales/p1/sales-orders/so-1/revisions',
    );

    expect(toast.success).toHaveBeenCalledWith(
      'Schedule confirmed - the linked sales order needs an amendment.',
      expect.objectContaining({
        action: expect.objectContaining({ label: 'Review the amendment' }),
      }),
    );
    const [, options] = (toast.success as ReturnType<typeof vi.fn>).mock.calls.find(
      ([message]) => message === 'Schedule confirmed - the linked sales order needs an amendment.',
    ) as [string, { action: { onClick: () => void } }];
    options.action.onClick();
    expect(push).toHaveBeenCalledWith('/project-sales/p1/sales-orders/so-1/revisions');
  });
});

/** Section 9.7 - the notes callout and the re-dating proposals, above the grid. */
describe('DeliveryScheduleReviewClient notes and revision proposals', () => {
  it('renders the notes callout and a proposal card straight off the version', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        notes: [
          {
            page_no: 7,
            text: 'ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026',
          },
        ],
        revision_proposals: [
          {
            product_id: 'p2',
            item_code: 'SRTFV1001',
            note_text: 'ONLY FOR FLOOR TRAP...',
            page_no: 7,
            state: 'proposed',
            decided_by: null,
            decided_at: null,
            cells: [
              {
                phase_id: 'ph2',
                phase_label: 'Phase 3',
                qty: '8',
                old_date: '2027-06-01',
                new_date: '2026-07-23',
              },
            ],
          },
        ],
      }),
    );
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByText('Notes on the document')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Page 7: ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026',
      ),
    ).toBeInTheDocument();

    expect(screen.getByText('Re-dating proposals')).toBeInTheDocument();
    expect(
      screen.getByText(/SRTFV1001 - re-date 1 phase from 23\/07\/2026/),
    ).toBeInTheDocument();
  });

  it('says nothing was proposed, and no notes, without hiding either section', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByText('No notes on the document')).toBeInTheDocument();
    expect(screen.getByText('No re-dating proposed')).toBeInTheDocument();
  });

  it('accepts a proposal through the confirm dialog, and writes it to the version query', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        revision_proposals: [
          {
            product_id: 'p2',
            item_code: 'SRTFV1001',
            note_text: 'note',
            page_no: 7,
            state: 'proposed',
            decided_by: null,
            decided_at: null,
            cells: [
              {
                phase_id: 'ph2',
                phase_label: 'Phase 3',
                qty: '8',
                old_date: '2027-06-01',
                new_date: '2026-07-23',
              },
            ],
          },
        ],
      }),
    );
    acceptRevisionProposal.mockResolvedValue(
      version({
        revision_proposals: [
          {
            product_id: 'p2',
            item_code: 'SRTFV1001',
            note_text: 'note',
            page_no: 7,
            state: 'accepted',
            decided_by: 'u1',
            decided_at: '2026-08-19T02:00:00',
            cells: [
              {
                phase_id: 'ph2',
                phase_label: 'Phase 3',
                qty: '8',
                old_date: '2027-06-01',
                new_date: '2026-07-23',
              },
            ],
          },
        ],
      }),
    );

    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Accept' }));

    await waitFor(() => expect(acceptRevisionProposal).toHaveBeenCalledWith('v2', 0));
    expect(await screen.findByText(/^Accepted /)).toBeInTheDocument();
  });
});

/** Section 9.8 - By phase / By date, and the hint chip that offers the switch. */
describe('DeliveryScheduleReviewClient, By phase / By date', () => {
  it('defaults to By phase, and switches renderer when the toggle is pressed', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');
    expect(screen.queryByTestId('schedule-by-date-matrix')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: 'By date' }));

    expect(await screen.findByTestId('schedule-by-date-matrix')).toBeInTheDocument();
    expect(screen.queryByTestId('schedule-matrix')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: 'By phase' }));
    expect(await screen.findByTestId('schedule-matrix')).toBeInTheDocument();
  });

  it('shows no hint chip while nothing has been re-dated', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');
    expect(screen.queryByText(/re-dated - view by date/)).toBeNull();
  });

  it('offers the hint chip once a cell carries an accepted override, and switches on click', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        cells: [
          {
            phase_id: 'ph1',
            product_id: 'p1',
            product_index: 0,
            qty: '927',
            delivery_date_override: '2026-07-23',
          },
          { phase_id: 'ph2', product_id: 'p2', product_index: 1, qty: '8' },
          { phase_id: 'ph1', product_id: null, product_index: 2, qty: '927' },
        ],
      }),
    );
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const chip = screen.getByText('1 cell re-dated - view by date');
    fireEvent.click(chip);

    expect(await screen.findByTestId('schedule-by-date-matrix')).toBeInTheDocument();
    // Once switched to By date, the hint (a By phase affordance) is gone.
    expect(screen.queryByText(/re-dated - view by date/)).toBeNull();
  });
});
