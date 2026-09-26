/**
 * P6 + S5 - the schedule review screen (AC-E1 to AC-E5; UAC S3-7, S5-1 to S5-6).
 *
 * The measured spike is what these tests defend: roughly a fifth of columns came out wrong on
 * the real R1, so the screen is not an accept-or-reject. S5 recomposed it per
 * mockups/delivery-schedule-review.html: one header with one primary button, two tabs
 * (Schedule, Documents), the reconciliation folded into the matrix as a Flag column, the
 * matrix opening on "Need attention" while unconfirmed, and History behind one button.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { toast } from '@/lib/toast';
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

const push = vi.fn();
let originParam: string | null = null;
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/delivery-schedules/v2',
  useSearchParams: () => new URLSearchParams(originParam ? { from: originParam } : ''),
}));

const getDeliveryScheduleVersion = vi.fn();
const saveDeliveryScheduleCells = vi.fn();
const resolveDeliveryScheduleProduct = vi.fn();
const confirmDeliveryScheduleVersion = vi.fn();
const listDeliveryScheduleVersions = vi.fn();
const acceptRevisionProposal = vi.fn();
const rejectRevisionProposal = vi.fn();
const dismissDeliveryScheduleColumn = vi.fn();
vi.mock('../../../_shared/services/deliveryScheduleService', () => ({
  // The pager walks the project's SCHEDULES now, each at its latest version.
  listDeliverySchedules: vi.fn(async () => [
    { id: 's0', latest_version_id: 'v-a' },
    { id: 's1', latest_version_id: 'v2' },
    { id: 's2', latest_version_id: 'v-c' },
  ]),
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
  dismissDeliveryScheduleColumn: (...args: unknown[]) => dismissDeliveryScheduleColumn(...args),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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
  "The areas add up to 8 but the schedule's own TOTAL QTY row says 16. " +
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
const phone = () => within(screen.getByTestId('schedule-columns-mobile'));

/** Every product the matrix is showing, top to bottom. */
function matrixRows(): string[] {
  return matrix()
    .getAllByRole('rowheader')
    .map((cell) => cell.textContent ?? '')
    .filter((text) => text !== 'Our total for the date');
}

/** One column that agrees with the PO, so "Need attention" has nothing to show. */
const ALL_AGREE: Partial<DeliveryScheduleVersion> = {
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
};

/** What the server answers once the flush valve's Area 3 cell is saved as 16: it adds up. */
function flushValveFixed() {
  return version({
    products: version().products.map((product) =>
      product.product_index === 1 ? { ...product, column_total: '16', reconciled: true } : product,
    ),
    cells: version().cells.map((cell) =>
      cell.product_index === 1 ? { ...cell, qty: '16' } : cell,
    ),
  });
}

async function openAllRows() {
  fireEvent.click(await screen.findByRole('radio', { name: /^All rows/ }));
}

async function openHistory() {
  fireEvent.click(await screen.findByRole('button', { name: 'History' }));
  return within(await screen.findByTestId('schedule-history'));
}

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
  originParam = null;
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
  dismissDeliveryScheduleColumn.mockImplementation(async () => version());
  (Element.prototype as unknown as { scrollIntoView: unknown }).scrollIntoView = vi.fn();
});

describe('DeliveryScheduleReviewClient, reading states', () => {
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
      version({ extraction_state: 'queued', pages_extracted: 0, phases: [], products: [], cells: [] }),
    );
    renderReview();

    expect(await screen.findByText('Queued')).toBeInTheDocument();
    expect(screen.getByText('7 pages waiting to be read.')).toBeInTheDocument();
    expect(screen.queryByTestId('schedule-matrix')).toBeNull();
  });

  it('reports honest progress while it reads', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({ extraction_state: 'running', pages_extracted: 3, phases: [], products: [], cells: [] }),
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

    expect(await screen.findByText('Only 5 of 7 pages were read')).toBeInTheDocument();
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

    expect(await screen.findByText('This document could not be read')).toBeInTheDocument();
    expect(screen.getByText('The file is not a readable PDF or image.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Upload it again/i })).toBeInTheDocument();
  });
});

/** S5-1: number and version, status pill, the meta line, record navigation, one button. */
describe('DeliveryScheduleReviewClient header (S5-1)', () => {
  it('heads the screen with the schedule, its status and the mockup meta line', async () => {
    renderReview();

    const heading = await screen.findByRole('heading', { name: /Schedule HQ\/26\/01\/121 v2/ });
    expect(within(heading).getByText('To confirm')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId('schedule-meta')).toHaveTextContent(
        'Tuju (PRJ-1) · Dated 23/07/2026 · Checked against PO v1',
      ),
    );
    // The PO opens in a new tab: leaving the page loses the cells being typed.
    const po = screen.getByRole('link', { name: 'Checked against PO v1' });
    expect(po).toHaveAttribute('href', '/project-sales/p1/pos/po1');
    expect(po).toHaveAttribute('target', '_blank');
  });

  it('renders `-` for a date it does not know (S5-6)', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(version({ schedule_date: null }));
    renderReview();
    await waitFor(() => expect(screen.getByTestId('schedule-meta')).toHaveTextContent('Dated -'));
  });

  it('carries one primary button and no sentence explaining the screen', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByRole('button', { name: 'Confirm schedule' })).toBeInTheDocument();
    // No gear, no second way to the same document, no instruction text.
    expect(screen.queryByRole('button', { name: /Schedule actions/ })).toBeNull();
    expect(screen.queryByText(/Every column has to agree with the PO/)).toBeNull();
    expect(screen.queryByText(/nothing here can be changed/i)).toBeNull();
    expect(screen.queryByText(/still to fix/)).toBeNull();
  });

  it('S3-03: walks the project schedules this review was opened from', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    await waitFor(() => expect(screen.getByText('2 / 3')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Next schedule' }));
    expect(push).toHaveBeenCalledWith('/project-sales/p1/delivery-schedules/v-c');
  });

  it('is read-only once confirmed, and says who confirmed it in the meta line', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({ confirmed_at: '2026-07-24T01:05:00', confirmed_by_name: 'Eling Tan' }),
    );
    renderReview();

    expect(await screen.findByTestId('schedule-meta')).toHaveTextContent(/Confirmed .* by Eling Tan/);
    expect(screen.getByRole('heading', { name: /Confirmed/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Confirm schedule$/ })).toBeNull();
    expect(matrix().getByLabelText('Area 3, SRTFV1001')).toBeDisabled();
  });
});

/** S5-2: two tabs, Schedule (default) and Documents; History holds the other three. */
describe('DeliveryScheduleReviewClient tabs (S5-2)', () => {
  it('has exactly two tabs, Schedule first and selected', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Schedule', 'Documents']);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    for (const name of ['Findings', 'Changes', 'Re-dating', 'Notes', 'Reconciliation']) {
      expect(screen.queryByRole('tab', { name })).toBeNull();
    }
  });

  it('opens History as one panel with the three sections in it', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        version_no: 1,
        notes: [{ page_no: 7, text: 'ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026' }],
      }),
    );
    renderReview();
    await screen.findByTestId('schedule-matrix');
    // Nothing of the three is on the page itself.
    expect(screen.queryByText('Notes on the document')).toBeNull();
    expect(screen.queryByText('Re-dating proposals')).toBeNull();

    const history = await openHistory();
    expect(history.getByText('Changes since the previous version')).toBeInTheDocument();
    expect(history.getByText('-')).toBeInTheDocument();
    expect(history.getByText('Re-dating proposals')).toBeInTheDocument();
    expect(history.getByText('No re-dating proposed')).toBeInTheDocument();
    expect(history.getByText('Notes on the document')).toBeInTheDocument();
    expect(
      history.getByText('Page 7: ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026'),
    ).toBeInTheDocument();
  });

  it('finds this version its predecessor and renders the was -> now diff inside History', async () => {
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
        { id: 'ph2', area_group: 'COMMON AREA', sequence: 3, label: null, delivery_date: '2027-06-01' },
      ],
    });
    const prior = version({
      id: 'v1',
      version_no: 1,
      phases: [
        { id: 'prior-ph1', area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7', delivery_date: '2026-01-01' },
        { id: 'prior-ph2', area_group: 'COMMON AREA', sequence: 3, label: null, delivery_date: '2027-06-01' },
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

    const history = await openHistory();
    expect(await history.findByText(/1 area moved/)).toBeInTheDocument();
    expect(history.getByText(/1 quantit(y|ies) changed/)).toBeInTheDocument();
  });

  it('accepts a re-dating proposal from History, through its confirm dialog', async () => {
    const proposal = {
      product_id: 'p2',
      item_code: 'SRTFV1001',
      note_text: 'note',
      page_no: 7,
      decided_by: null,
      decided_at: null,
      cells: [
        { phase_id: 'ph2', phase_label: 'Phase 3', qty: '8', old_date: '2027-06-01', new_date: '2026-07-23' },
      ],
    };
    getDeliveryScheduleVersion.mockResolvedValue(
      version({ revision_proposals: [{ ...proposal, state: 'proposed' }] }),
    );
    acceptRevisionProposal.mockResolvedValue(
      version({
        revision_proposals: [
          { ...proposal, state: 'accepted', decided_by: 'u1', decided_at: '2026-08-19T02:00:00' },
        ],
      }),
    );

    renderReview();
    await screen.findByTestId('schedule-matrix');
    const history = await openHistory();

    fireEvent.click(history.getByRole('button', { name: 'Accept' }));
    const dialogs = await screen.findAllByRole('dialog');
    fireEvent.click(
      within(dialogs[dialogs.length - 1]).getByRole('button', { name: 'Accept' }),
    );

    await waitFor(() => expect(acceptRevisionProposal).toHaveBeenCalledWith('v2', 0));
    expect(await screen.findByText(/^Accepted /)).toBeInTheDocument();
  });
});

/** S5-5: the Documents tab is the file, or a plain not-available state; nothing under it. */
describe('DeliveryScheduleReviewClient Documents (S5-5)', () => {
  it('renders the schedule file and nothing else', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Documents' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Documents' }));
    const panel = await screen.findByRole('tabpanel');
    expect(panel.querySelector('iframe, img, object, embed')).not.toBeNull();
    expect(within(panel).queryByRole('table')).toBeNull();
    expect(within(panel).queryByRole('grid')).toBeNull();
  });

  it('shows a plain not-available state with an upload action, never an error code', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(version({ document_url: null }));
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Documents' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Documents' }));
    const panel = await screen.findByRole('tabpanel');
    expect(within(panel).getByText('This PDF is not available yet')).toBeInTheDocument();
    expect(
      within(panel).getByRole('button', { name: 'Upload the schedule again' }),
    ).toBeInTheDocument();
    expect(panel.textContent).not.toMatch(/404|NoSuchKey|not found/i);
  });
});

/** S5-3, S3-7: the reconciliation is a Flag column on the matrix, not a table of its own. */
describe('DeliveryScheduleReviewClient Flag column (S5-3, S3-7)', () => {
  it('has no separate reconciliation table: the Flag is on the matrix row', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.queryByTestId('reconciliation-list')).toBeNull();
    expect(screen.queryByText('Reconciliation')).toBeNull();
    expect(matrix().getByRole('columnheader', { name: 'Flag' })).toBeInTheDocument();
    expect(
      matrix().getByRole('button', { name: 'Blocks publish, 2 on SRTFV1001' }),
    ).toBeInTheDocument();
  });

  it('shows the full customer code on a flagged row, and its sentences behind the pill', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const row = matrix().getByRole('rowheader', { name: /BUI-HB-SRTWB7055/ });
    expect(within(row).getByText('BUI-HB-SRTWB7055').className).not.toContain('truncate');
    expect(screen.queryByText(NEEDS_PRODUCT_MESSAGE)).toBeNull();

    fireEvent.click(matrix().getByRole('button', { name: 'Blocks publish, 2 on BUI-HB-SRTWB7055' }));
    expect(await screen.findByText(NEEDS_PRODUCT_MESSAGE)).toBeInTheDocument();
    expect(screen.getByText(NOT_ON_PO_MESSAGE)).toBeInTheDocument();
  });

  it('dismisses a flagged row with a reason, from its own Flag', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(matrix().getByRole('button', { name: 'Blocks publish, 2 on SRTFV1001' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss with a reason' }));
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'The printed total is a typo' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss 1' }));

    await waitFor(() =>
      expect(dismissDeliveryScheduleColumn).toHaveBeenCalledWith(
        'v2',
        1,
        true,
        'The printed total is a typo',
      ),
    );
  });

  it('uses the product picker as the fix for an unidentified row', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(matrix().getByLabelText('Level 2 & 7, BUI-HB-SRTWB7055')).toBeDisabled();
    fireEvent.click(matrix().getByRole('button', { name: 'Blocks publish, 2 on BUI-HB-SRTWB7055' }));
    fireEvent.click(await screen.findByLabelText('Pick the product for BUI-HB-SRTWB7055'));
    fireEvent.click(await screen.findByText('SRTWB7055'));

    await waitFor(() =>
      expect(resolveDeliveryScheduleProduct).toHaveBeenCalledWith('v2', 2, 'p6'),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "BUI-HB-SRTWB7055 will resolve to this product on this customer's next schedule.",
      ),
    );
  });

  it('lands a quantity fix IN the cell to be typed into, from the Flag', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(matrix().getByRole('button', { name: 'Blocks publish, 2 on SRTFV1001' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Fix the quantities' }));

    await waitFor(() =>
      expect(matrix().getByLabelText('Level 2 & 7, SRTFV1001')).toHaveFocus(),
    );
  });

  it('offers no fix and no dismiss to a reviewer who cannot edit', async () => {
    getProject.mockResolvedValue({ id: 'p1', project_code: 'PRJ-1', title: 'Tuju', can_edit: false });
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(matrix().getByRole('button', { name: 'Blocks publish, 2 on SRTFV1001' }));
    await screen.findByText(REPORTED_MISMATCH_MESSAGE);
    expect(screen.queryByRole('button', { name: 'Dismiss with a reason' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Fix the quantities' })).toBeNull();
    expect(screen.queryByLabelText(/the product for/)).toBeNull();
  });

  it('never says "Dismiss as false signal" (S3-2)', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');
    fireEvent.click(matrix().getByRole('button', { name: 'Blocks publish, 2 on SRTFV1001' }));
    await screen.findByRole('button', { name: 'Dismiss with a reason' });
    expect(screen.queryByText(/false signal/)).toBeNull();
  });
});

/** S5-4 and owner lesson (c): "Need attention" / "All rows", and the one blocking rule. */
describe('DeliveryScheduleReviewClient Need attention (S5-4)', () => {
  it('opens on Need attention while unconfirmed, with both counts', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByRole('radio', { name: 'Need attention (2)' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('radio', { name: 'All rows (3)' })).toBeInTheDocument();
    expect(screen.queryByText(/Only rows with a flag/)).toBeNull();
    // The agreeing WC is not shown; the two that block Confirm are.
    expect(matrixRows()).toEqual([
      expect.stringContaining('SRTFV1001'),
      expect.stringContaining('BUI-HB-SRTWB7055'),
    ]);

    await openAllRows();
    expect(matrixRows()).toHaveLength(3);
  });

  it('opens on All rows once confirmed', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(version({ confirmed_at: '2026-07-24T01:05:00' }));
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByRole('radio', { name: 'All rows (3)' })).toHaveAttribute('aria-checked', 'true');
    expect(matrixRows()).toHaveLength(3);
  });

  it('puts every row the confirm dialog names in Need attention, and nothing else', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');
    const shown = matrixRows();

    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText('2 columns do not add up yet.')).toBeInTheDocument();
    expect(dialog.getByText('SRTFV1001')).toBeInTheDocument();
    expect(dialog.getByText('BUI-HB-SRTWB7055')).toBeInTheDocument();
    expect(shown).toHaveLength(2);
  });

  it('drops a row from Need attention the moment its correction is typed', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');
    await openAllRows();

    fireEvent.change(matrix().getByLabelText('Area 3, SRTFV1001'), { target: { value: '16' } });

    await waitFor(() =>
      expect(screen.getByRole('radio', { name: 'Need attention (1)' })).toBeInTheDocument(),
    );
    fireEvent.blur(matrix().getByLabelText('Area 3, SRTFV1001'));
    await waitFor(() =>
      expect(saveDeliveryScheduleCells).toHaveBeenCalledWith('v2', [
        { phase_id: 'ph2', product_id: 'p2', qty: '16' },
      ]),
    );
  });

  it('counts a dismissed row as not blocking, same as the server', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({
        products: version().products.map((product) =>
          product.product_index === 1
            ? { ...product, dismissed: true, dismissed_reason: 'Typo', dismissed_by_name: 'Aina' }
            : product,
        ),
      }),
    );
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(screen.getByRole('radio', { name: 'Need attention (1)' })).toBeInTheDocument();
    // The default view's ROWS follow the same rule as its count: the dismissed row is not in it.
    expect(matrixRows()).toEqual([expect.stringContaining('BUI-HB-SRTWB7055')]);
    await openAllRows();
    expect(matrix().getByRole('button', { name: /^Dismissed, 2 on SRTFV1001/ })).toBeInTheDocument();
  });

  /**
   * B1 (review of #1265): the default view used to rebuild its rows from the drafts on every
   * keystroke, so the keystroke that made a row add up unmounted the input being typed into.
   * An unmounted input never blurs, the save never went out, and the Confirm dialog then
   * listed fewer columns than the server's confirm refuses.
   */
  it('keeps a row being typed into in the default Need attention view, and saves it', async () => {
    saveDeliveryScheduleCells.mockImplementation(async () => flushValveFixed());
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const cell = matrix().getByLabelText('Area 3, SRTFV1001');
    cell.focus();
    fireEvent.change(cell, { target: { value: '16' } });

    expect(cell).toBeInTheDocument();
    expect(cell).toHaveFocus();
    expect(matrixRows()).toEqual([
      expect.stringContaining('SRTFV1001'),
      expect.stringContaining('BUI-HB-SRTWB7055'),
    ]);

    fireEvent.blur(cell);
    await waitFor(() =>
      expect(saveDeliveryScheduleCells).toHaveBeenCalledWith('v2', [
        { phase_id: 'ph2', product_id: 'p2', qty: '16' },
      ]),
    );

    // The screen matches the server once the save lands: one column blocks, and the dialog
    // names exactly that one.
    await waitFor(() =>
      expect(screen.getByRole('radio', { name: 'Need attention (1)' })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText('1 column does not add up yet.')).toBeInTheDocument();
    expect(dialog.getByText('BUI-HB-SRTWB7055')).toBeInTheDocument();
  });

  it('keeps a row in Need attention when a keystroke turns its blocker into a warning', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    // First Backspace on 8: the column now totals nothing, a shortfall, which blocks nothing.
    const cell = matrix().getByLabelText('Area 3, SRTFV1001');
    fireEvent.change(cell, { target: { value: '' } });

    expect(matrix().getByLabelText('Area 3, SRTFV1001')).toBe(cell);
    fireEvent.change(cell, { target: { value: '16' } });
    fireEvent.blur(cell);
    await waitFor(() =>
      expect(saveDeliveryScheduleCells).toHaveBeenCalledWith('v2', [
        { phase_id: 'ph2', product_id: 'p2', qty: '16' },
      ]),
    );
  });

  it('lets a row that was fixed leave Need attention when the view is chosen again', async () => {
    saveDeliveryScheduleCells.mockImplementation(async () => flushValveFixed());
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.change(matrix().getByLabelText('Area 3, SRTFV1001'), { target: { value: '16' } });
    fireEvent.blur(matrix().getByLabelText('Area 3, SRTFV1001'));
    await openAllRows();
    fireEvent.click(screen.getByRole('radio', { name: /^Need attention/ }));

    expect(matrixRows()).toEqual([expect.stringContaining('BUI-HB-SRTWB7055')]);
  });

  it('says plainly when nothing needs attention (S5-6)', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(version(ALL_AGREE));
    renderReview();

    expect(await screen.findByTestId('schedule-all-clear')).toHaveTextContent(
      'Nothing needs attention',
    );
    await openAllRows();
    expect(await screen.findByTestId('schedule-matrix')).toBeInTheDocument();
  });

  it('keeps By area / By date working as before', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');
    expect(screen.queryByTestId('schedule-by-date-matrix')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: 'By date' }));
    expect(await screen.findByTestId('schedule-by-date-matrix')).toBeInTheDocument();
    expect(screen.queryByTestId('schedule-matrix')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: 'By area' }));
    expect(await screen.findByTestId('schedule-matrix')).toBeInTheDocument();
  });
});

describe('DeliveryScheduleReviewClient cells', () => {
  it('renders a blank cell blank, because a blank is not a zero', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');
    expect(matrix().getByLabelText('Level 2 & 7, SRTFV1001')).toHaveValue('');
  });

  it('writes a cleared cell back as the delete the API expects', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    const cell = matrix().getByLabelText('Area 3, SRTFV1001');
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

    const cell = matrix().getByLabelText('Area 3, SRTFV1001');
    fireEvent.change(cell, { target: { value: '8' } });
    fireEvent.blur(cell);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(saveDeliveryScheduleCells).not.toHaveBeenCalled();
  });

  it('renders the phone cards of the same rows, one Flag each', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    expect(phone().getAllByText('Schedule')).toHaveLength(2);
    expect(phone().getByRole('button', { name: 'Blocks publish, 2 on SRTFV1001' })).toBeInTheDocument();
    expect(phone().queryByLabelText('Area 3, SRTFV1001')).toBeNull();
  });
});

describe('DeliveryScheduleReviewClient Confirm schedule', () => {
  it('refuses to confirm while a column is unreconciled, then allows it with a reason', async () => {
    renderReview();
    await screen.findByTestId('schedule-matrix');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: /^Confirm schedule$/ })).toBeDisabled();

    fireEvent.click(dialog.getByRole('checkbox'));
    fireEvent.change(dialog.getByLabelText(/Reason/i), {
      target: { value: 'Customer confirmed the valve quantity by email.' },
    });
    fireEvent.click(dialog.getByRole('button', { name: /^Confirm schedule$/ }));
    await waitFor(() =>
      expect(confirmDeliveryScheduleVersion).toHaveBeenCalledWith('v2', {
        acknowledge_unreconciled: true,
        reason: 'Customer confirmed the valve quantity by email.',
      }),
    );
  });

  it('confirms with no acknowledgement once every column agrees', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(version(ALL_AGREE));
    renderReview();
    await screen.findByTestId('schedule-all-clear');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText(/Every column agrees with the PO/i)).toBeInTheDocument();
    expect(dialog.queryByRole('checkbox')).toBeNull();

    fireEvent.click(dialog.getByRole('button', { name: /^Confirm schedule$/ }));
    await waitFor(() => expect(confirmDeliveryScheduleVersion).toHaveBeenCalledWith('v2', {}));
  });

  it('asks for the acknowledgement the server wants on a partial read, even with every column agreeing', async () => {
    getDeliveryScheduleVersion.mockResolvedValue(
      version({ ...ALL_AGREE, extraction_state: 'partial', pages_extracted: 5 }),
    );
    renderReview();
    await screen.findByTestId('schedule-all-clear');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText('Part of this schedule could not be read.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: /^Confirm schedule$/ })).toBeDisabled();

    fireEvent.click(dialog.getByRole('checkbox'));
    fireEvent.change(dialog.getByLabelText(/Reason/i), { target: { value: 'Pages 6-7 are blank' } });
    fireEvent.click(dialog.getByRole('button', { name: /^Confirm schedule$/ }));
    await waitFor(() =>
      expect(confirmDeliveryScheduleVersion).toHaveBeenCalledWith('v2', {
        acknowledge_unreconciled: true,
        reason: 'Pages 6-7 are blank',
      }),
    );
  });

  it('returns to the origin after a successful Confirm schedule, when it carries one (S4-2)', async () => {
    originParam = '/project-sales/p1?tab=schedules';
    getDeliveryScheduleVersion.mockResolvedValue(version(ALL_AGREE));
    renderReview();
    await screen.findByTestId('schedule-all-clear');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    fireEvent.click(dialog.getByRole('button', { name: /^Confirm schedule$/ }));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/p1?tab=schedules'));
  });

  it('stays on the page after Confirm schedule with no origin (S4-3)', async () => {
    originParam = null;
    getDeliveryScheduleVersion.mockResolvedValue(version(ALL_AGREE));
    renderReview();
    await screen.findByTestId('schedule-all-clear');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    fireEvent.click(dialog.getByRole('button', { name: /^Confirm schedule$/ }));

    await waitFor(() => expect(confirmDeliveryScheduleVersion).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });

  it('makes the amendment the one primary button once confirm answers a preview url', async () => {
    const reconciled = version(ALL_AGREE);
    getDeliveryScheduleVersion.mockResolvedValue(reconciled);
    confirmDeliveryScheduleVersion.mockResolvedValue({
      ...reconciled,
      confirmed_at: '2026-07-24T01:05:00',
      amendment_preview_url: '/project-sales/p1/sales-orders/so-1/revisions',
    });

    renderReview();
    await screen.findByTestId('schedule-all-clear');

    fireEvent.click(screen.getByRole('button', { name: /^Confirm schedule$/ }));
    const dialog = within(await screen.findByRole('dialog'));
    fireEvent.click(dialog.getByRole('button', { name: /^Confirm schedule$/ }));

    await waitFor(() => expect(confirmDeliveryScheduleVersion).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    expect(await screen.findByRole('link', { name: 'Review the amendment' })).toHaveAttribute(
      'href',
      '/project-sales/p1/sales-orders/so-1/revisions',
    );
    expect(screen.queryByRole('button', { name: /^Confirm schedule$/ })).toBeNull();
    expect(toast.success).toHaveBeenCalledWith(
      'Schedule confirmed - the linked sales order needs an amendment.',
      expect.objectContaining({
        action: expect.objectContaining({ label: 'Review the amendment' }),
      }),
    );
  });
});
