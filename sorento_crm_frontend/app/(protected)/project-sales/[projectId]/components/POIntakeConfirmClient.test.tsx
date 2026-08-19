/**
 * P4 - the confirm screen end to end, one state per test.
 *
 * The states are the point. A queued extraction, a failed one, a SHORT one, an empty read and
 * a clean read all look different, and the short read is the one that must never be mistaken
 * for success. The confirm gate is tested where it lives: on the screen, beside the button,
 * rather than in a toast that disappears.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POVersion, POVersionLine } from '../../_shared/types/poIntake.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/purchase-orders/v1',
  useSearchParams: () => ({ get: () => null }),
}));

// The shared DataGrid holds its skeleton rows until the column-preferences query settles, and
// under jsdom it never does.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

const getPOVersion = vi.fn();
const confirmPOVersion = vi.fn();
const approvePurchaseOrder = vi.fn();
const countersignPurchaseOrder = vi.fn();

vi.mock('../../_shared/services/poIntakeService', () => ({
  getPOVersion: (versionId: string) => getPOVersion(versionId),
  listPOVersions: vi.fn(async () => null),
  uploadPurchaseOrderDocument: vi.fn(),
  updatePOVersionLine: vi.fn(async () => null),
  updatePOVersionHeader: vi.fn(async () => null),
  confirmPOVersion: (versionId: string) => confirmPOVersion(versionId),
  approvePurchaseOrder: (poId: string) => approvePurchaseOrder(poId),
  countersignPurchaseOrder: (poId: string) => countersignPurchaseOrder(poId),
  acceptPOAnnotation: vi.fn(async () => {}),
  editPOAnnotation: vi.fn(async () => {}),
  rejectPOAnnotation: vi.fn(async () => {}),
}));

const getProject = vi.fn(async () => ({
  id: 'p1',
  project_code: 'PRJ-000001',
  title: 'Tuju Residences',
  outcome: 'open',
  can_edit: true,
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../_shared/services/projectService')>();
  return { ...actual, getProject: () => getProject() };
});

import { POIntakeConfirmClient } from './POIntakeConfirmClient';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function line(overrides: Partial<POVersionLine> = {}): POVersionLine {
  return {
    id: 'l1',
    line_no: 1,
    stock_code_raw: 'SRTWC8613-RL',
    description_raw: 'RIMLESS CLOSE COUPLED WC',
    qty: '927',
    uom_raw: 'SETS',
    unit_price: '392.85',
    amount: '364171.95',
    arithmetic_ok: true,
    is_cancelled: false,
    resolved_product_id: 'prod-1',
    resolved_product_code: 'SRTWC8613-RL',
    resolution_source: 'code',
    page_no: 1,
    ...overrides,
  };
}

function version(overrides: Partial<POVersion> = {}): POVersion {
  return {
    id: 'v1',
    purchase_order_id: 'po1',
    version_no: 1,
    extraction_state: 'done',
    extraction_error: null,
    extraction_model: 'gemini-2.5-flash',
    page_count: 10,
    document_url: 'https://example.test/po.pdf',
    header: {
      po_number: 'HQ/26/01/041',
      po_date: '2026-01-19',
      term_days: 60,
      sales_person: 'Ali Hassan',
      customer_order_ref: 'BUI/TR/2026/0114',
      admin_ref: 'PS26-0143',
      remark: null,
    },
    totals: {
      extracted_total: '364171.95',
      lines_total: '364171.95',
      arithmetic_passed: 1,
      arithmetic_total: 1,
    },
    lines: [line()],
    annotations: [],
    confirmed_at: null,
    ...overrides,
  };
}

function annotation(overrides = {}) {
  return {
    id: 'a1',
    page_no: 4,
    crop_url: null,
    raw_text: 'cancel item (7), refer to new P/O HQ/26/05/087',
    written_date: '15/5/26',
    refers_to_lines: [1],
    interpretation: 'cancel_line' as const,
    interpretation_json: { line_nos: [1] },
    state: 'proposed' as const,
    actioned_by_name: null,
    actioned_at: null,
    action_note: null,
    ...overrides,
  };
}

function renderConfirm() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <POIntakeConfirmClient projectId="p1" versionId="v1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getProject.mockResolvedValue({
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Tuju Residences',
    outcome: 'open',
    can_edit: true,
  } as never);
});

describe('POIntakeConfirmClient', () => {
  it('shows a skeleton shaped like the screen it becomes', () => {
    getPOVersion.mockReturnValue(new Promise(() => {}));

    renderConfirm();

    expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Lines/)).toBeNull();
  });

  it('says the document could not be loaded, with a way back', async () => {
    getPOVersion.mockRejectedValue(new Error('You do not have access to this project'));

    renderConfirm();

    expect(
      await screen.findByText(/This PO document could not be loaded/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText('You do not have access to this project'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Back to the project/i })).toHaveAttribute(
      'href',
      '/project-sales/p1',
    );
  });

  it('reports a queued extraction honestly instead of blocking the screen', async () => {
    getPOVersion.mockResolvedValue(
      version({
        extraction_state: 'queued',
        lines: [],
        totals: {
          extracted_total: null,
          lines_total: '0.00',
          arithmetic_passed: 0,
          arithmetic_total: 0,
        },
      }),
    );

    renderConfirm();

    // Twice on purpose: as a pill in the header, and where the lines will be.
    expect(await screen.findAllByText('Waiting to be read')).toHaveLength(2);
    expect(screen.getByText(/This page updates itself/i)).toBeInTheDocument();
  });

  it('names the reason when extraction failed, and offers another upload', async () => {
    getPOVersion.mockResolvedValue(
      version({
        extraction_state: 'failed',
        extraction_error: 'Page 1 came back blank at 300 dpi.',
        lines: [],
      }),
    );

    renderConfirm();

    expect(
      await screen.findByText('This document could not be read'),
    ).toBeInTheDocument();
    expect(screen.getByText('Page 1 came back blank at 300 dpi.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload it again/i })).toBeInTheDocument();
  });

  it('does not let a SHORT read look like a finished one', async () => {
    getPOVersion.mockResolvedValue(
      version({
        pages_extracted: 7,
        failed_pages: [8, 9, 10],
        extraction_error: 'Pages 8, 9 and 10 could not be read (scan too dark).',
        totals: {
          extracted_total: '1810640.62',
          lines_total: '364171.95',
          arithmetic_passed: 1,
          arithmetic_total: 1,
        },
      }),
    );

    renderConfirm();

    expect(await screen.findByText('Only 7 of 10 pages were read')).toBeInTheDocument();
    expect(screen.getByText(/Pages 8, 9, 10 produced nothing/i)).toBeInTheDocument();
    // The money gap is still stated on its own, because that is what a person can act on.
    expect(
      screen.getByText(/RM 1,446,468\.67 below the total printed on the document/i),
    ).toBeInTheDocument();
  });

  it('says nothing can be confirmed from an empty read', async () => {
    getPOVersion.mockResolvedValue(
      version({
        lines: [],
        totals: {
          extracted_total: null,
          lines_total: '0.00',
          arithmetic_passed: 0,
          arithmetic_total: 0,
        },
      }),
    );

    renderConfirm();

    expect(
      await screen.findByText(/No lines came back from this document/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm this PO/i })).toBeDisabled();
  });

  it('puts the header, the lines and the handwriting on one screen', async () => {
    getPOVersion.mockResolvedValue(version({ annotations: [annotation()] }));

    renderConfirm();

    expect(await screen.findByText('PO HQ/26/01/041')).toBeInTheDocument();
    expect(screen.getByLabelText('PO number')).toHaveValue('HQ/26/01/041');
    expect(screen.getByLabelText('Filing reference')).toHaveValue('PS26-0143');
    expect(screen.getByLabelText('Quantity on line 1')).toHaveValue('927');
    expect(
      screen.getByText('Handwriting', { selector: '[data-slot="card-title"]' }),
    ).toBeInTheDocument();
    expect(screen.getByTitle('Purchase order page 1')).toBeInTheDocument();
  });

  it('moves the scan to the page a note was written on', async () => {
    getPOVersion.mockResolvedValue(version({ annotations: [annotation()] }));

    renderConfirm();

    // The viewer is on page 1 until a note asks for its own page.
    expect(await screen.findByTitle('Purchase order page 1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Page 4' }));

    expect(screen.getByTitle('Purchase order page 4')).toBeInTheDocument();
    expect(screen.getByText('Page 4 of 10')).toBeInTheDocument();
  });

  /**
   * The read takes minutes and the person waiting deserves to be told how long it took, but
   * the version response carries no elapsed time yet (nothing on `GET /api/v1/project-sales`
   * returns it). Until it does, the screen says nothing rather than inventing a number, and
   * the spinner is never accompanied by a duration.
   */
  it('never shows a duration beside the spinner while the document is still being read', async () => {
    getPOVersion.mockResolvedValue(
      version({ extraction_state: 'running', lines: [], annotations: [] }),
    );

    renderConfirm();

    expect(await screen.findByText('Reading the document')).toBeInTheDocument();
    expect(screen.getByText('Being read')).toBeInTheDocument();
    expect(screen.queryByText(/read in/i)).toBeNull();
  });

  /**
   * B3 (19 Aug follow-up): pages land as they finish rather than all at once at the
   * end, so the progress card counts up instead of sitting on a static page total for
   * the whole read.
   */
  it('shows which page is being read as pages land, not just the total', async () => {
    getPOVersion.mockResolvedValue(
      version({
        extraction_state: 'running',
        pages_extracted: 3,
        lines: [],
        annotations: [],
      }),
    );

    renderConfirm();

    expect(await screen.findByText('Reading the document')).toBeInTheDocument();
    expect(screen.getByText('Page 4 of 10')).toBeInTheDocument();
  });

  it('counts the exceptions once, on the lines card, and still reaches them', async () => {
    getPOVersion.mockResolvedValue(
      version({
        lines: [line(), line({ id: 'l2', line_no: 2, amount: '1.00', arithmetic_ok: false })],
        totals: {
          extracted_total: '728343.90',
          lines_total: '364172.95',
          arithmetic_passed: 1,
          arithmetic_total: 2,
        },
      }),
    );

    renderConfirm();

    expect(await screen.findByText('1 of 2 lines need attention')).toBeInTheDocument();
    // The old count in the card header is gone: two numbers on one card teaches people to
    // read neither.
    expect(screen.queryByText('1 of 2 multiply out')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /first problem line/i }));
    expect(screen.getByLabelText('Amount on line 2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Show only these 1/ }));
    expect(screen.getByLabelText('Amount on line 2')).toBeInTheDocument();
    expect(screen.queryByLabelText('Amount on line 1')).toBeNull();
  });

  it('refuses to confirm while a note is unreviewed, and says so beside the button', async () => {
    getPOVersion.mockResolvedValue(version({ annotations: [annotation()] }));

    renderConfirm();

    expect(await screen.findByRole('button', { name: /Confirm this PO/i })).toBeDisabled();
    expect(
      screen.getByText('1 handwritten note still unreviewed'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Review them/i })).toBeInTheDocument();
    expect(screen.getByText('1 to review')).toBeInTheDocument();
  });

  it('confirms once every note has been looked at', async () => {
    getPOVersion.mockResolvedValue(
      version({
        annotations: [
          annotation({ state: 'accepted', actioned_by_name: 'Yana Abdullah' }),
        ],
      }),
    );

    renderConfirm();

    const confirmButton = await screen.findByRole('button', { name: /Confirm this PO/i });
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);
    await waitFor(() => expect(confirmPOVersion).toHaveBeenCalledWith('v1'));
  });

  it('shows confirm, approve and countersign as three stamps, absent ones included', async () => {
    getPOVersion.mockResolvedValue(
      version({
        confirmed_at: '2026-05-15T03:02:00',
        confirmed_by_name: 'Yana Abdullah',
      }),
    );

    renderConfirm();

    expect(await screen.findByText(/Yana Abdullah/)).toBeInTheDocument();
    // Approved and Countersigned are still rendered, as "Not yet" rather than hidden.
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.getByText('Countersigned')).toBeInTheDocument();
    expect(screen.getAllByText('Not yet')).toHaveLength(2);
    expect(screen.getByRole('button', { name: /^Approve$/ })).toBeInTheDocument();
  });

  it('offers countersign only once the PO is approved, and stops editing after confirm', async () => {
    getPOVersion.mockResolvedValue(
      version({
        confirmed_at: '2026-05-15T03:02:00',
        confirmed_by_name: 'Yana Abdullah',
        purchase_order: {
          po_number: 'HQ/26/01/041',
          status: 'approved',
          approved_by_name: 'Yana Abdullah',
          approved_at: '2026-05-15T03:05:00',
          countersigned_by_name: null,
          countersigned_at: null,
        },
      }),
    );

    renderConfirm();

    const countersign = await screen.findByRole('button', { name: /Countersign/i });
    fireEvent.click(countersign);
    await waitFor(() => expect(countersignPurchaseOrder).toHaveBeenCalledWith('po1'));

    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
    expect(screen.queryByRole('button', { name: /Confirm this PO/i })).toBeNull();
  });

  it('offers a reader no write affordance at all', async () => {
    getProject.mockResolvedValue({
      id: 'p1',
      project_code: 'PRJ-000001',
      title: 'Tuju Residences',
      outcome: 'open',
      can_edit: false,
    } as never);
    getPOVersion.mockResolvedValue(version({ annotations: [annotation()] }));

    renderConfirm();

    expect(await screen.findByText('Read only')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Confirm this PO/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Accept$/ })).toBeNull();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
  });
});
