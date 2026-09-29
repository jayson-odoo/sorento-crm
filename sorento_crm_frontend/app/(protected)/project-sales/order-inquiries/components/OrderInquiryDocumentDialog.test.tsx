/**
 * The read-only document lightbox (R9, AC-D18/AC-D19/AC-D20, and slice B of
 * `PLAN-scm-oi-reserving-feedback-8sep.md`): one `Dialog` for both kinds, opened from the
 * document number the "Outstanding PO/SPO" column prints. Replaces the deleted
 * `OrderInquiryPoDetailPopover` - AC-D20 is asserted by the plain fact that this file
 * imports the dialog module, not the popover one, and nothing in the tree does.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getOrderInquiryPoDetail = vi.fn();
const getOrderInquirySpoDetail = vi.fn();

vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoDetail: (...args: unknown[]) => getOrderInquiryPoDetail(...args),
    getOrderInquirySpoDetail: (...args: unknown[]) => getOrderInquirySpoDetail(...args),
  };
});

// The lines are a `PanelDataGrid` now (slice B), which reads per-user column preferences
// through this hook - the same mock every other `PanelDataGrid` test file uses (see
// `OrderLinesCard.test.tsx`), or the grid never resolves under jsdom.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import {
  OrderInquiryDocumentDialog,
  OrderInquiryDocumentLink,
} from './OrderInquiryDocumentDialog';

function renderNode(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('OrderInquiryDocumentLink: opens from either kind of document (AC-D18/AC-D19)', () => {
  it('opens the lightbox for a PO number', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [],
      allocations: [],
    });
    renderNode(<OrderInquiryDocumentLink kind="po" document="202607-S0105" poId="po-1" />);

    fireEvent.click(screen.getByTestId('document-detail-trigger-202607-S0105'));

    expect(await screen.findByText('DAFUYUAN')).toBeInTheDocument();
    expect(getOrderInquiryPoDetail).toHaveBeenCalledWith('po-1');
    expect(getOrderInquirySpoDetail).not.toHaveBeenCalled();
    expect(screen.getByText('Purchase order')).toBeInTheDocument();
  });

  it('opens the lightbox for an SPO number, addressed by NUMBER not id', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/08-0015',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      lines: [],
      allocations: [],
    });
    renderNode(<OrderInquiryDocumentLink kind="spo" document="SPO-2026/08-0015" />);

    fireEvent.click(screen.getByTestId('document-detail-trigger-SPO-2026/08-0015'));

    expect(await screen.findByText('CHAOSHENG')).toBeInTheDocument();
    expect(getOrderInquirySpoDetail).toHaveBeenCalledWith('SPO-2026/08-0015');
    expect(getOrderInquiryPoDetail).not.toHaveBeenCalled();
    expect(screen.getByText('Shipping order')).toBeInTheDocument();
  });
});

describe('PO lightbox body', () => {
  it('R13 (owner rulings, 24 Sep 2026): no "Allocated to" panel under the lines grid - the grid\'s own Allocated column is the whole answer', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [
        {
          sku: 'SRTWB5400',
          product_name: 'Wall hung basin 5400',
          qty_ordered: '35',
          qty_received: '0',
          remaining: '35',
          location: 'BRW-BB',
        },
      ],
      allocations: [
        { inquiry_no: 'OI-000101', so_number: 'SO385126', item_code: 'SRTWB5400', qty: '20', ack_state: 'acknowledged' },
        { inquiry_no: 'OI-000102', so_number: 'SO386461', item_code: 'SRTWB5400', qty: '15', ack_state: 'acknowledged' },
      ],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    await screen.findByText('BRW-BB');
    expect(screen.queryByText('Allocated to')).not.toBeInTheDocument();
    expect(screen.queryByText('SO385126')).not.toBeInTheDocument();
    expect(screen.queryByText('SO386461')).not.toBeInTheDocument();
    expect(screen.queryByText('Standing')).not.toBeInTheDocument();
    expect(screen.queryByText('Proposed')).not.toBeInTheDocument();
    expect(screen.queryByText('Confirmed')).not.toBeInTheDocument();

    // The lines table too.
    expect(screen.getByText('BRW-BB')).toBeInTheDocument();
    const openLink = screen.getByText('Open document');
    expect(openLink).toHaveAttribute('href', '/scm/purchase-orders/po-1');
    // AC-B5: a NEW tab, so the lightbox and the list behind it are still there on return.
    expect(openLink).toHaveAttribute('target', '_blank');
    expect(openLink).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('AC-B1: a PO with many lines renders a fixed-layout, resizable DataGrid, not a bare table', async () => {
    const lines = Array.from({ length: 12 }, (_, index) => ({
      sku: `SRTWCX8605-S-RL-PJ-${index}`,
      product_name: 'Wall hung WC',
      qty_ordered: '10',
      qty_received: '0',
      remaining: '10',
      location: 'BRW-IB',
    }));
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-89',
      po_number: '202405-S0045',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines,
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202405-S0045" poId="po-89" open onOpenChange={vi.fn()} />,
    );

    expect(await screen.findByText('SRTWCX8605-S-RL-PJ-0')).toBeInTheDocument();
    const table = document.querySelector('table[data-slot="data-grid-table"]');
    expect(table).toBeTruthy();
    expect(table).toHaveClass('table-fixed');
    // AC-B4: paginates at 10 by default and states the total (12 lines here).
    expect(screen.getByText(/1 - 10 of 12/)).toBeInTheDocument();
    // Resizable columns leave a resize handle per header.
    expect(document.querySelectorAll('.cursor-col-resize').length).toBeGreaterThan(0);
  });

  it('AC-B2/AC-B3: one search input narrows by product code AND by location', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-89',
      po_number: '202405-S0045',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: null,
      lines: [
        {
          sku: 'SRTWCX8605-S-RL-PJ',
          product_name: 'Wall hung WC 8605',
          qty_ordered: '52',
          qty_received: '0',
          remaining: '52',
          location: 'BRW-IB',
        },
        {
          sku: 'SRTWCX8605-S-RL-PJ',
          product_name: 'Wall hung WC 8605',
          qty_ordered: '2',
          qty_received: '0',
          remaining: '2',
          location: 'BRW-IB',
        },
        {
          sku: 'SRTWB5400',
          product_name: 'Wall hung basin 5400',
          qty_ordered: '10',
          qty_received: '0',
          remaining: '10',
          location: 'BRW',
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202405-S0045" poId="po-89" open onOpenChange={vi.fn()} />,
    );

    expect(await screen.findByText('SRTWB5400')).toBeInTheDocument();

    const search = screen.getByPlaceholderText('Search product or location...');
    fireEvent.change(search, { target: { value: 'SRTWCX8605-S-RL-PJ' } });
    expect(screen.getAllByText('SRTWCX8605-S-RL-PJ')).toHaveLength(2);
    expect(screen.queryByText('SRTWB5400')).not.toBeInTheDocument();

    // AC-B3: narrowing further by location, without paging (the two open lines).
    fireEvent.change(search, { target: { value: 'BRW-IB' } });
    expect(screen.getAllByText('SRTWCX8605-S-RL-PJ')).toHaveLength(2);
    expect(screen.getByText(/1 - 2 of 2/)).toBeInTheDocument();
  });

  it('reads an explicit empty state when the purchase order carries no lines', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-2',
      po_number: '202607-S0200',
      supplier_name: null,
      status: 'draft',
      expected_date: null,
      lines: [],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0200" poId="po-2" open onOpenChange={vi.fn()} />,
    );

    expect(await screen.findByText('This purchase order carries no lines.')).toBeInTheDocument();
    expect(screen.getAllByText('Not stated').length).toBeGreaterThan(0);
  });

  it('says the link reaches no purchase order when poId is null', () => {
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0200" poId={null} open onOpenChange={vi.fn()} />,
    );
    expect(
      screen.getByText('This link does not reach a purchase order in the system.'),
    ).toBeInTheDocument();
    expect(getOrderInquiryPoDetail).not.toHaveBeenCalled();
  });
});

describe('PO lightbox lines - the book\'s own S/O linkage, a third surface for slice A', () => {
  const detailWithLine = (extra: Record<string, unknown>) => ({
    id: 'po-1',
    po_number: '202607-S0105',
    supplier_name: 'DAFUYUAN',
    status: 'confirmed',
    expected_date: '2026-09-01',
    lines: [
      {
        sku: 'SRTWB5400',
        product_name: 'Wall hung basin 5400',
        qty_ordered: '35',
        qty_received: '0',
        remaining: '35',
        location: 'BRW-BB',
        ...extra,
      },
    ],
    allocations: [],
  });

  it('prints the sales order the book names on the line', async () => {
    getOrderInquiryPoDetail.mockResolvedValue(
      detailWithLine({ book_so_number: 'SO391853', book_so_unresolved: false }),
    );
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    const row = (await screen.findByText('SRTWB5400')).closest('tr') as HTMLElement;
    expect(within(row).getByText('SO391853')).toBeInTheDocument();
  });

  it('reads a muted dash when the book names no sales order, never a guess', async () => {
    getOrderInquiryPoDetail.mockResolvedValue(
      detailWithLine({ book_so_number: null, book_so_unresolved: false }),
    );
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    const row = (await screen.findByText('SRTWB5400')).closest('tr') as HTMLElement;
    expect(within(row).getByText('-')).toBeInTheDocument();
    expect(within(row).queryByText('Linked, not held')).not.toBeInTheDocument();
  });

  it('distinguishes a linkage this system does not hold from no linkage at all', async () => {
    getOrderInquiryPoDetail.mockResolvedValue(
      detailWithLine({ book_so_number: null, book_so_unresolved: true }),
    );
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    const row = (await screen.findByText('SRTWB5400')).closest('tr') as HTMLElement;
    expect(within(row).getByText('Linked, not held')).toBeInTheDocument();
    expect(within(row).queryByText('-')).not.toBeInTheDocument();
  });

  it('never renders the raw AutoCount ref, which is a machine key', async () => {
    const { container } = renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );
    getOrderInquiryPoDetail.mockResolvedValue(
      detailWithLine({
        book_so_number: null,
        book_so_unresolved: true,
        from_so_line_ref: 'AED_SORENTO:45322312:45322332',
      }),
    );

    await screen.findByText('SRTWB5400');
    expect(container.textContent).not.toContain('AED_SORENTO');
    expect(container.textContent).not.toContain('45322312');
    expect(document.body.textContent).not.toContain('AED_SORENTO');
  });

  it('has no "+N more" overflow, because a line carries ONE sales order', async () => {
    getOrderInquiryPoDetail.mockResolvedValue(
      detailWithLine({ book_so_number: 'SO391853', book_so_unresolved: false }),
    );
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    await screen.findByText('SRTWB5400');
    expect(document.body.textContent).not.toMatch(/\+\d+ more/);
  });

  it('renders the three states exactly as the purchase-order detail does', async () => {
    // One fact, one presentation: both surfaces render through `BookSoCell`, so this
    // pins the SHARED wording rather than a second copy of it drifting.
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [
        {
          sku: 'RESOLVED',
          product_name: 'Resolved',
          qty_ordered: '1',
          qty_received: '0',
          remaining: '1',
          location: 'BRW-BB',
          book_so_number: 'SO391853',
          book_so_unresolved: false,
        },
        {
          sku: 'UNRESOLVED',
          product_name: 'Unresolved',
          qty_ordered: '1',
          qty_received: '0',
          remaining: '1',
          location: 'BRW-BB',
          book_so_number: null,
          book_so_unresolved: true,
        },
        {
          sku: 'UNLINKED',
          product_name: 'Unlinked',
          qty_ordered: '1',
          qty_received: '0',
          remaining: '1',
          location: 'BRW-BB',
          book_so_number: null,
          book_so_unresolved: false,
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    const resolved = (await screen.findByText('RESOLVED')).closest('tr') as HTMLElement;
    const unresolved = screen.getByText('UNRESOLVED').closest('tr') as HTMLElement;
    const unlinked = screen.getByText('UNLINKED').closest('tr') as HTMLElement;

    expect(within(resolved).getByText('SO391853')).toBeInTheDocument();
    expect(within(unresolved).getByText('Linked, not held')).toBeInTheDocument();
    expect(within(unlinked).getByText('-')).toBeInTheDocument();
  });
});

describe('PO lightbox lines - Allocated + the linked line highlight (issue #1215 point 2)', () => {
  it('renders the Allocated column, summed from the links this line holds', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [
        {
          id: 'line-taken',
          sku: 'TPE-9204',
          product_name: 'Basin',
          qty_ordered: '20000',
          qty_received: '13550',
          remaining: '6450',
          location: 'BRW',
          allocated: '2',
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    const row = (await screen.findByText('TPE-9204')).closest('tr') as HTMLElement;
    expect(within(row).getByText('2')).toBeInTheDocument();
  });

  it('highlights only the line the opening row own link sits on, when poLineId is given - same SKU on both lines (nit 8, review of PR #1220)', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [
        {
          id: 'line-taken',
          sku: 'TPE-9204',
          product_name: 'Basin',
          qty_ordered: '20000',
          qty_received: '13550',
          remaining: '6450',
          location: 'BRW',
          allocated: '2',
        },
        {
          // Same SKU as the row above (the exact case a PO with two lines of the same
          // item makes ambiguous) - the highlight must key off `id`, never `sku`.
          id: 'line-other',
          sku: 'TPE-9204',
          product_name: 'Basin',
          qty_ordered: '10000',
          qty_received: '1500',
          remaining: '8500',
          location: 'BRW',
          allocated: '0',
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="po"
        document="202607-S0105"
        poId="po-1"
        poLineId="line-taken"
        open
        onOpenChange={vi.fn()}
      />,
    );

    const rows = (await screen.findAllByText('TPE-9204')).map(
      (cell) => cell.closest('tr') as HTMLElement,
    );
    expect(rows).toHaveLength(2);
    const [takenRow, otherRow] = rows;
    expect(takenRow).toHaveAttribute('data-linked-line', 'true');
    expect(otherRow).not.toHaveAttribute('data-linked-line');
  });

  it('R11 (owner rulings, 24 Sep 2026): highlights the suggested line, the same idiom as a linked line', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [
        {
          id: 'line-taken',
          sku: 'TPE-9204',
          product_name: 'Basin',
          qty_ordered: '20000',
          qty_received: '13550',
          remaining: '6450',
          location: 'BRW',
          allocated: '2',
        },
        {
          id: 'line-suggested',
          sku: 'TPE-9203',
          product_name: 'Basin (other line)',
          qty_ordered: '10000',
          qty_received: '1500',
          remaining: '8500',
          location: 'BRW',
          allocated: '0',
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="po"
        document="202607-S0105"
        poId="po-1"
        suggestedLineId="line-suggested"
        open
        onOpenChange={vi.fn()}
      />,
    );

    const takenRow = (await screen.findByText('TPE-9204')).closest('tr') as HTMLElement;
    const suggestedRow = screen.getByText('TPE-9203').closest('tr') as HTMLElement;
    expect(suggestedRow).toHaveAttribute('data-suggested-line', 'true');
    expect(suggestedRow).not.toHaveAttribute('data-linked-line');
    expect(takenRow).not.toHaveAttribute('data-suggested-line');
    expect(takenRow).not.toHaveAttribute('data-linked-line');
  });

  it('R11: a linked line and a suggested line highlight at once, on different lines', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [
        {
          id: 'line-taken',
          sku: 'TPE-9204',
          product_name: 'Basin',
          qty_ordered: '20000',
          qty_received: '13550',
          remaining: '6450',
          location: 'BRW',
          allocated: '2',
        },
        {
          id: 'line-suggested',
          sku: 'TPE-9203',
          product_name: 'Basin (other line)',
          qty_ordered: '10000',
          qty_received: '1500',
          remaining: '8500',
          location: 'BRW',
          allocated: '0',
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="po"
        document="202607-S0105"
        poId="po-1"
        poLineId="line-taken"
        suggestedLineId="line-suggested"
        open
        onOpenChange={vi.fn()}
      />,
    );

    const takenRow = (await screen.findByText('TPE-9204')).closest('tr') as HTMLElement;
    const suggestedRow = screen.getByText('TPE-9203').closest('tr') as HTMLElement;
    expect(takenRow).toHaveAttribute('data-linked-line', 'true');
    expect(suggestedRow).toHaveAttribute('data-suggested-line', 'true');
  });

  it('highlights nothing when no poLineId is given', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [
        {
          id: 'line-taken',
          sku: 'TPE-9204',
          product_name: 'Basin',
          qty_ordered: '20000',
          qty_received: '13550',
          remaining: '6450',
          location: 'BRW',
          allocated: '2',
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    const row = (await screen.findByText('TPE-9204')).closest('tr') as HTMLElement;
    expect(row).not.toHaveAttribute('data-linked-line');
  });
});

describe('SPO lightbox body (AC-D19)', () => {
  it('reads the shipment / container when an inbound shipment exists', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/08-0015',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      shipment_ref: 'SHP-0042',
      container_no: 'MSKU1234567',
      lines: [
        {
          sku: 'SRTWCY7405-PJ',
          product_name: 'Wall hung WC 7405',
          allocated: '10',
          received: '0',
          remaining: '10',
          location: 'BRW',
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="spo" document="SPO-2026/08-0015" open onOpenChange={vi.fn()} />,
    );

    expect(await screen.findByText('SHP-0042')).toBeInTheDocument();
    expect(screen.getByText('MSKU1234567')).toBeInTheDocument();
    expect(screen.getByText('BRW')).toBeInTheDocument();
  });

  it('reads "no location in the book" gracefully - a 404 becomes a friendly empty state', async () => {
    getOrderInquirySpoDetail.mockRejectedValue(new Error('not found'));
    renderNode(
      <OrderInquiryDocumentDialog kind="spo" document="SPO-2026/08-9999" open onOpenChange={vi.fn()} />,
    );

    expect(await screen.findByText('This shipping order could not be found.')).toBeInTheDocument();
  });

  it('a line with no location in the book reads "no location"', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/08-0031',
      supplier_name: null,
      eta: null,
      lines: [
        {
          sku: 'ZZT-0001',
          product_name: null,
          allocated: '5',
          received: '0',
          remaining: '5',
          location: null,
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="spo" document="SPO-2026/08-0031" open onOpenChange={vi.fn()} />,
    );

    expect(await waitFor(() => screen.getByText('no location'))).toBeInTheDocument();
  });

  it('AC-B6: the SPO lightbox gets the same fixed-layout DataGrid, search and pagination', async () => {
    const lines = Array.from({ length: 11 }, (_, index) => ({
      sku: index === 0 ? 'SRTWCY7405-PJ' : `ZZT-${index}`,
      product_name: 'Wall hung WC 7405',
      allocated: '10',
      received: '0',
      remaining: '10',
      location: index === 0 ? 'BRW-IB' : 'BRW',
    }));
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/08-0061',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      lines,
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="spo" document="SPO-2026/08-0061" open onOpenChange={vi.fn()} />,
    );

    expect(await screen.findByText('SRTWCY7405-PJ')).toBeInTheDocument();
    const table = document.querySelector('table[data-slot="data-grid-table"]');
    expect(table).toHaveClass('table-fixed');
    expect(screen.getByText(/1 - 10 of 11/)).toBeInTheDocument();

    const search = screen.getByPlaceholderText('Search product or location...');
    fireEvent.change(search, { target: { value: 'BRW-IB' } });
    expect(screen.getByText('SRTWCY7405-PJ')).toBeInTheDocument();
    expect(screen.queryByText('ZZT-1')).not.toBeInTheDocument();
  });

  it('AC-A13/AC-A14: the SPO grid names each line\'s source PO, and a muted dash when it has none', async () => {
    // Owner's 9 Sep feedback, surface 2: the document lightbox is the other place a
    // buyer meets an SPO, so it carries the same fact the backing-documents dialog does.
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/09-0036',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      lines: [
        {
          sku: 'SRTWCX8605-S-RL-PJ',
          product_name: 'Wall hung WC 8605',
          allocated: '52',
          received: '0',
          remaining: '52',
          location: 'BRW-IB',
          source_po_number: '202606-S0110',
        },
        {
          sku: 'ZZT-0002',
          product_name: null,
          allocated: '10',
          received: '0',
          remaining: '10',
          location: 'BRW',
          source_po_number: null,
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="spo" document="SPO-2026/09-0036" open onOpenChange={vi.fn()} />,
    );

    expect(await screen.findByText('202606-S0110')).toBeInTheDocument();
    // The sourceless line reads a muted dash, never an empty cell or a guess.
    const rows = document.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    expect(within(rows[1] as HTMLElement).getByText('-')).toBeInTheDocument();
  });

  it('R31b: marks the line named in highlightLines with a Linked badge, and offers a jump', async () => {
    // RED today: `OrderInquiryDocumentDialog` takes no `highlightLines` prop at all - it
    // is dropped as an unknown prop, so neither a "Linked" badge nor the header's own
    // jump button exists.
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/06-0131',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      lines: [
        {
          sku: 'SRTWB242', product_name: 'Sorento basin 242', allocated: '100',
          received: '0', remaining: '100', location: 'BRW-BB', spo_line_number: 4,
        },
        {
          sku: 'ZZT-OTHER', product_name: 'Other item', allocated: '10',
          received: '0', remaining: '10', location: 'BRW', spo_line_number: 5,
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="spo"
        document="SPO-2026/06-0131"
        open
        onOpenChange={vi.fn()}
        {...({ highlightLines: [4] } as Record<string, unknown>)}
      />,
    );

    const linkedRow = (await screen.findByText('SRTWB242')).closest('tr') as HTMLElement;
    expect(within(linkedRow).getByText('Linked')).toBeInTheDocument();
    const otherRow = screen.getByText('ZZT-OTHER').closest('tr') as HTMLElement;
    expect(within(otherRow).queryByText('Linked')).not.toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'Go to linked line' })).toBeInTheDocument();
  });

  it('R31b: the jump button pages the highlighted line into view when it starts off the current page', async () => {
    // Same 11-line/pageSize-10 shape AC-B6 above already proves pages with - line 11
    // (index 10) carries `spo_line_number: 808` and starts on page 2, invisible until
    // the jump runs. RED today for the same reason as the test above: no prop, no jump.
    const lines = Array.from({ length: 11 }, (_, index) => ({
      sku: index === 10 ? 'SRTWB242-LINKED' : `ZZT-${index}`,
      product_name: 'Wall hung WC 7405',
      allocated: '10',
      received: '0',
      remaining: '10',
      location: 'BRW',
      spo_line_number: index === 10 ? 808 : index + 1,
    }));
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/06-0131',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      lines,
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="spo"
        document="SPO-2026/06-0131"
        open
        onOpenChange={vi.fn()}
        {...({ highlightLines: [808] } as Record<string, unknown>)}
      />,
    );

    await screen.findByText('ZZT-0');
    expect(screen.queryByText('SRTWB242-LINKED')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Go to linked line' }));

    expect(await screen.findByText('SRTWB242-LINKED')).toBeInTheDocument();
    const linkedRow = screen.getByText('SRTWB242-LINKED').closest('tr') as HTMLElement;
    expect(within(linkedRow).getByText('Linked')).toBeInTheDocument();
  });

  it('R31b: renders nothing new without highlightLines', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/06-0131',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      lines: [
        {
          sku: 'SRTWB242', product_name: 'Sorento basin 242', allocated: '100',
          received: '0', remaining: '100', location: 'BRW-BB', spo_line_number: 4,
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="spo" document="SPO-2026/06-0131" open onOpenChange={vi.fn()} />,
    );

    await screen.findByText('SRTWB242');
    expect(screen.queryByText('Linked')).not.toBeInTheDocument();
    // R16: the header's "Go to linked line" button is shared by both lightboxes and
    // always renders - it merely stays disabled when nothing is highlighted.
    expect(screen.getByRole('button', { name: 'Go to linked line' })).toBeDisabled();
  });

  it('Should fix 4 (review round 3): disables Go to when highlightLines names a line no row on the document carries', async () => {
    // RED before the fix: `highlightedLineId` fell back to the placeholder
    // `'__highlighted__'` the moment `highlightLines` was non-empty, whether or not
    // `SpoBody` ever resolved a matching row - stock debt could open this lightbox
    // with an ENABLED Go to that scrolled to nothing, since `highlightLineRowId`
    // (and so `effectiveGoToLineId`) stayed null. Main's own #1165 rendered no
    // button at all in that case; this lightbox must at least disable it rather
    // than answer nothing on a press.
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/06-0131',
      supplier_name: 'CHAOSHENG',
      eta: '2026-09-15',
      lines: [
        {
          sku: 'SRTWB242', product_name: 'Sorento basin 242', allocated: '100',
          received: '0', remaining: '100', location: 'BRW-BB', spo_line_number: 4,
        },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="spo"
        document="SPO-2026/06-0131"
        open
        onOpenChange={vi.fn()}
        {...({ highlightLines: [99] } as Record<string, unknown>)}
      />,
    );

    await screen.findByText('SRTWB242');
    expect(screen.queryByText('Linked')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Go to linked line' })).toBeDisabled();
    });
  });
});

describe('SPO lightbox lines - the linked line highlight (R15, owner rulings 25 Sep 2026)', () => {
  const detailWithLines = (lines: Record<string, unknown>[]) => ({
    spo_number: 'SPO-2026/09-0051',
    supplier_name: 'CHAOSHENG',
    eta: '2026-09-15',
    lines,
    allocations: [],
  });

  it('R15: "why the SPO doesn\'t show the highlight like PO does" - highlights only the line the opening row\'s own real link sits on, same SKU on both lines, keyed by id never product', async () => {
    getOrderInquirySpoDetail.mockResolvedValue(
      detailWithLines([
        {
          id: 'spo-line-taken',
          sku: 'TPE-9204',
          product_name: 'Basin',
          allocated: '10',
          received: '0',
          remaining: '10',
          location: 'BRW',
        },
        {
          id: 'spo-line-other',
          sku: 'TPE-9204',
          product_name: 'Basin',
          allocated: '5',
          received: '0',
          remaining: '5',
          location: 'BRW-B',
        },
      ]),
    );
    renderNode(
      <OrderInquiryDocumentDialog
        kind="spo"
        document="SPO-2026/09-0051"
        spoLineId="spo-line-taken"
        open
        onOpenChange={vi.fn()}
      />,
    );

    const rows = (await screen.findAllByText('TPE-9204')).map(
      (cell) => cell.closest('tr') as HTMLElement,
    );
    expect(rows).toHaveLength(2);
    const [takenRow, otherRow] = rows;
    expect(takenRow).toHaveAttribute('data-linked-line', 'true');
    expect(otherRow).not.toHaveAttribute('data-linked-line');
  });

  it('R11/R15: a suggested SPO line highlights the same idiom, and both a linked and a suggested line can show at once', async () => {
    getOrderInquirySpoDetail.mockResolvedValue(
      detailWithLines([
        { id: 'spo-line-taken', sku: 'TPE-9204', allocated: '10', received: '0', remaining: '10' },
        {
          id: 'spo-line-suggested',
          sku: 'TPE-9203',
          allocated: '5',
          received: '0',
          remaining: '5',
        },
      ]),
    );
    renderNode(
      <OrderInquiryDocumentDialog
        kind="spo"
        document="SPO-2026/09-0051"
        spoLineId="spo-line-taken"
        suggestedLineId="spo-line-suggested"
        open
        onOpenChange={vi.fn()}
      />,
    );

    const takenRow = (await screen.findByText('TPE-9204')).closest('tr') as HTMLElement;
    const suggestedRow = screen.getByText('TPE-9203').closest('tr') as HTMLElement;
    expect(takenRow).toHaveAttribute('data-linked-line', 'true');
    expect(suggestedRow).toHaveAttribute('data-suggested-line', 'true');
  });

  it('highlights nothing when no spoLineId or suggestedLineId is given', async () => {
    getOrderInquirySpoDetail.mockResolvedValue(
      detailWithLines([
        { id: 'spo-line-1', sku: 'TPE-9204', allocated: '10', received: '0', remaining: '10' },
      ]),
    );
    renderNode(
      <OrderInquiryDocumentDialog kind="spo" document="SPO-2026/09-0051" open onOpenChange={vi.fn()} />,
    );

    const row = (await screen.findByText('TPE-9204')).closest('tr') as HTMLElement;
    expect(row).not.toHaveAttribute('data-linked-line');
    expect(row).not.toHaveAttribute('data-suggested-line');
  });
});

describe('R16 (owner rulings, 25 Sep 2026): "1 button to quickly jump to the linked line" in both lightbox headers', () => {
  it('is disabled with a tooltip reason when nothing is highlighted, on the PO lightbox', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [{ id: 'line-1', sku: 'SKU-1', qty_ordered: '10', qty_received: '0', remaining: '10' }],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog kind="po" document="202607-S0105" poId="po-1" open onOpenChange={vi.fn()} />,
    );

    await screen.findByText('SKU-1');
    const button = screen.getByTestId('document-detail-go-to-line');
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Go to linked line');
  });

  it('reads "Go to linked line" and jumps the PO lines grid to the page holding it, scrolling it into view', async () => {
    const lines = Array.from({ length: 25 }, (_, index) => ({
      id: `line-${index}`,
      sku: `SKU-${index}`,
      qty_ordered: '10',
      qty_received: '0',
      remaining: '10',
    }));
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines,
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="po"
        document="202607-S0105"
        poId="po-1"
        poLineId="line-22"
        open
        onOpenChange={vi.fn()}
      />,
    );

    await screen.findByText('SKU-0');
    // The linked line sits on page 3 (10 rows/page) - not visible yet.
    expect(screen.queryByText('SKU-22')).not.toBeInTheDocument();

    const button = screen.getByTestId('document-detail-go-to-line');
    expect(button).not.toBeDisabled();
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    fireEvent.click(button);

    await waitFor(() => expect(screen.getByText('SKU-22')).toBeInTheDocument());
    const linkedRow = screen.getByText('SKU-22').closest('tr') as HTMLElement;
    expect(linkedRow).toHaveAttribute('data-linked-line', 'true');
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });

  it('Should fix 1 (review round 2): jumps again on a second Go to press after the reader has paged away', async () => {
    const lines = Array.from({ length: 25 }, (_, index) => ({
      id: `line-${index}`,
      sku: `SKU-${index}`,
      qty_ordered: '10',
      qty_received: '0',
      remaining: '10',
    }));
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines,
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="po"
        document="202607-S0105"
        poId="po-1"
        poLineId="line-22"
        open
        onOpenChange={vi.fn()}
      />,
    );

    await screen.findByText('SKU-0');
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    // First press: jumps to page 3, where the linked line sits.
    fireEvent.click(screen.getByTestId('document-detail-go-to-line'));
    await waitFor(() => expect(screen.getByText('SKU-22')).toBeInTheDocument());

    // The reader pages away, back to page 1 - `goToLineId` never changes, only
    // the grid's own page does.
    fireEvent.click(screen.getByRole('button', { name: '1' }));
    await waitFor(() => expect(screen.queryByText('SKU-22')).not.toBeInTheDocument());
    scrollIntoView.mockClear();

    // A second press must jump back to the linked line, not read as a no-op
    // because `goToLineId` is unchanged from the first press.
    fireEvent.click(screen.getByTestId('document-detail-go-to-line'));
    await waitFor(() => expect(screen.getByText('SKU-22')).toBeInTheDocument());
    const linkedRowAgain = screen.getByText('SKU-22').closest('tr') as HTMLElement;
    expect(linkedRowAgain).toHaveAttribute('data-linked-line', 'true');
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });

  it('reads "Go to suggested line" when opened from a Suggested cell (no real link highlighted)', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/09-0051',
      supplier_name: 'CHAOSHENG',
      lines: [
        { id: 'spo-line-1', sku: 'SKU-1', allocated: '10', received: '0', remaining: '10' },
      ],
      allocations: [],
    });
    renderNode(
      <OrderInquiryDocumentDialog
        kind="spo"
        document="SPO-2026/09-0051"
        suggestedLineId="spo-line-1"
        open
        onOpenChange={vi.fn()}
      />,
    );

    await screen.findByText('SKU-1');
    const button = screen.getByTestId('document-detail-go-to-line');
    expect(button).not.toBeDisabled();
    expect(button).toHaveTextContent('Go to suggested line');
  });
});
