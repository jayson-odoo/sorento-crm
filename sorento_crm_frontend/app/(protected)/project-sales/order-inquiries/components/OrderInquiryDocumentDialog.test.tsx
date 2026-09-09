/**
 * The read-only document lightbox (R9, AC-D18/AC-D19/AC-D20, and slice B of
 * `PLAN-scm-oi-reserving-feedback-8sep.md`): one `Dialog` for both kinds, opened from the
 * document number the "Outstanding PO/SPO" column prints. Replaces the deleted
 * `OrderInquiryPoDetailPopover` - AC-D20 is asserted by the plain fact that this file
 * imports the dialog module, not the popover one, and nothing in the tree does.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  it('lists every allocated row - no Standing column any more (nit, review of PR #471)', async () => {
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

    expect(await screen.findByText('SO385126')).toBeInTheDocument();
    expect(screen.getByText('SO386461')).toBeInTheDocument();
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

  it('reads an explicit empty state when no allocations exist yet', async () => {
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

    expect(await screen.findByText('No allocations yet.')).toBeInTheDocument();
    expect(screen.getByText('This purchase order carries no lines.')).toBeInTheDocument();
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
});
