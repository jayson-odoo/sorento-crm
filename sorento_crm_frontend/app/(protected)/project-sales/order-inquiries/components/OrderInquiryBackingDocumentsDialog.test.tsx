/**
 * Blocking 1 (PR #1220 review, reviewer pass at 9ba33a37): the worklist's own
 * backing-documents dialog renders each link's document through `OrderInquiryDocumentLink`
 * but never passed `poLineId` through - so opening a PO from HERE (as opposed to the OI
 * detail page's Lines tab, `orderInquiryHeaderLinesColumns.tsx`, which already does) always
 * highlighted nothing, even when the link named an exact line. This pins the fix
 * (`OrderInquiryBackingDocumentsDialog.tsx`): the field already exists on the wire
 * (`link.po_line_id`, `schemas/project_order_inquiry.py`), it is now threaded through.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { OrderInquiryBackingDocumentsDialog } from './OrderInquiryBackingDocumentsDialog';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

function renderNode(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

function rowWithPoLink(): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    linked_qty: '10',
    links: [
      {
        id: 'link-1',
        kind: 'po',
        document: '202607-S0105',
        po_id: 'po-1',
        po_line_id: 'line-taken',
        qty: '10',
        location: 'BRW',
      },
    ],
  } as unknown as OrderInquiryWorklistRow;
}

describe('issue #1215 point 2 (Blocking 1): the backing-documents dialog threads poLineId through', () => {
  it('highlights the exact PO line the opening link names, not nothing', async () => {
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
          id: 'line-other',
          sku: 'TPE-9204',
          product_name: 'Basin',
          qty_ordered: '10000',
          qty_received: '1500',
          remaining: '8500',
          location: 'BRW-B',
          allocated: '0',
        },
      ],
      allocations: [],
    });

    renderNode(
      <OrderInquiryBackingDocumentsDialog row={rowWithPoLink()} open onOpenChange={vi.fn()} />,
    );

    fireEvent.click(screen.getByTestId('document-detail-trigger-202607-S0105'));

    const skuCells = await screen.findAllByText('TPE-9204');
    expect(skuCells).toHaveLength(2);
    const lineRows = skuCells.map((cell) => cell.closest('tr') as HTMLElement);
    const takenRow = lineRows.find((r) => within(r).queryByText('BRW'));
    const otherRow = lineRows.find((r) => within(r).queryByText('BRW-B'));
    expect(takenRow).toBeTruthy();
    expect(otherRow).toBeTruthy();

    expect(takenRow).toHaveAttribute('data-linked-line', 'true');
    expect(otherRow).not.toHaveAttribute('data-linked-line');
  });
});

function rowWithSpoLink(): OrderInquiryWorklistRow {
  return {
    id: 'row-2',
    qty: '10',
    linked_qty: '10',
    links: [
      {
        id: 'link-2',
        kind: 'spo',
        document: 'SPO-2026/09-0051',
        spo_allocation_id: 'spo-line-taken',
        qty: '10',
        location: 'BRW',
      },
    ],
  } as unknown as OrderInquiryWorklistRow;
}

describe('R15 (owner rulings, 25 Sep 2026): the backing-documents dialog threads spo_allocation_id through', () => {
  it('highlights the exact SPO line the opening link names, not nothing', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/09-0051',
      supplier_name: 'CHAOSHENG',
      lines: [
        { id: 'spo-line-taken', sku: 'TPE-9204', allocated: '10', received: '0', remaining: '10' },
        { id: 'spo-line-other', sku: 'TPE-9204', allocated: '5', received: '0', remaining: '5' },
      ],
      allocations: [],
    });

    renderNode(
      <OrderInquiryBackingDocumentsDialog row={rowWithSpoLink()} open onOpenChange={vi.fn()} />,
    );

    fireEvent.click(screen.getByTestId('document-detail-trigger-SPO-2026/09-0051'));

    const rows = (await screen.findAllByText('TPE-9204')).map(
      (cell) => cell.closest('tr') as HTMLElement,
    );
    expect(rows).toHaveLength(2);
    const takenRow = rows.find((r) => r.getAttribute('data-linked-line') === 'true');
    expect(takenRow).toBeTruthy();
    const otherRow = rows.find((r) => r !== takenRow);
    expect(otherRow).not.toHaveAttribute('data-linked-line');
  });
});

function rowWithViaSpoPoLink(purchaseOrderId: string | null): OrderInquiryWorklistRow {
  return {
    id: 'row-3',
    qty: '6',
    linked_qty: '6',
    links: [
      {
        id: 'link-3',
        kind: 'spo',
        document: 'SPO-2026/09-0080',
        source_po_number: '202607-S0105',
        derived_po: true,
        purchase_order_id: purchaseOrderId,
        qty: '6',
        location: 'BRW',
      },
    ],
  } as unknown as OrderInquiryWorklistRow;
}

describe('R17 (owner rulings, 25 Sep 2026): "from PO X" is clickable, never dead text', () => {
  it('opens the PO lightbox by purchase_order_id when the payload carries it', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/09-0080',
      supplier_name: 'CHAOSHENG',
      lines: [],
      allocations: [],
    });
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-source-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [],
      allocations: [],
    });

    renderNode(
      <OrderInquiryBackingDocumentsDialog
        row={rowWithViaSpoPoLink('po-source-1')}
        open
        onOpenChange={vi.fn()}
      />,
    );

    expect(await screen.findByText('from PO')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('document-detail-trigger-202607-S0105'));

    expect(await screen.findByText('DAFUYUAN')).toBeInTheDocument();
    expect(getOrderInquiryPoDetail).toHaveBeenCalledWith('po-source-1');
  });

  it('Should fix 3 (review round 2): purchase_order_id is resolved on the SERVER now, never a client scan of the worklist - a payload carrying none reads the dead-lightbox message', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/09-0080',
      supplier_name: 'CHAOSHENG',
      lines: [],
      allocations: [],
    });

    renderNode(
      <OrderInquiryBackingDocumentsDialog
        row={rowWithViaSpoPoLink(null)}
        open
        onOpenChange={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByTestId('document-detail-trigger-202607-S0105'));

    expect(
      await screen.findByText('This link does not reach a purchase order in the system.'),
    ).toBeInTheDocument();
    expect(getOrderInquiryPoDetail).not.toHaveBeenCalled();
  });
});
