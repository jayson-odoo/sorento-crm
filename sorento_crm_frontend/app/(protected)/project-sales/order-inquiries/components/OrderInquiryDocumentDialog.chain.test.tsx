/**
 * LINKAGE-UNIFY U4 (PLAN section 12): the PO and SPO popups read the chain.
 *
 *  - F1 the PO table's figure column is headed "Transferred" (never "Received"), each line's
 *    SPO cells draw the shared pills ("Received 486 at BRW-BB", red "SPO withdrawn"), and
 *    "In transit" appears nowhere (owner ruling: no such tag);
 *
 * `spos`, `receipts` and `dead_reason` are not on the app's types yet: the fixtures
 * are plain objects handed to the mocked service.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
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

import { OrderInquiryDocumentDialog } from './OrderInquiryDocumentDialog';

function renderNode(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => vi.clearAllMocks());

const PO_DETAIL = {
  id: 'po-1',
  po_number: '202607-S0100',
  supplier_name: 'DAFUYUAN',
  status: 'confirmed',
  expected_date: '2026-09-01',
  lines: [
    {
      id: 'pl-1',
      sku: 'SRTSS3170',
      product_name: 'Basin',
      qty_ordered: '780',
      qty_received: '780',
      remaining: '0',
      allocated: '780',
      location: 'BRW-BB',
      spos: [
        {
          spo_number: 'SPO-2026/09-0107', line_label: 'L9',
          receipts: [{ qty: '486', bin: 'BRW-BB' }], dead_reason: null,
        },
        { spo_number: 'SPO-2026/09-0107', line_label: 'L7', receipts: [], dead_reason: 'spo_withdrawn' },
      ],
    },
  ],
  allocations: [],
};

describe('F1 the PO popup', () => {
  it('seed: renders the PO and its line', async () => {
    getOrderInquiryPoDetail.mockResolvedValue(PO_DETAIL);
    renderNode(<OrderInquiryDocumentDialog kind="po" document="202607-S0100" poId="po-1" open onOpenChange={vi.fn()} />);
    expect(await screen.findByText('DAFUYUAN')).toBeInTheDocument();
    expect(screen.getByText('BRW-BB')).toBeInTheDocument();
  });

  it('heads the figure column "Transferred", not "Received"', async () => {
    getOrderInquiryPoDetail.mockResolvedValue(PO_DETAIL);
    renderNode(<OrderInquiryDocumentDialog kind="po" document="202607-S0100" poId="po-1" open onOpenChange={vi.fn()} />);
    await screen.findByText('DAFUYUAN');
    expect(screen.getByText('Transferred')).toBeInTheDocument();
    expect(screen.queryByText('Received')).not.toBeInTheDocument();
  });

  it('draws the line\'s SPO cells with the shared pills and no "In transit" tag', async () => {
    getOrderInquiryPoDetail.mockResolvedValue(PO_DETAIL);
    renderNode(<OrderInquiryDocumentDialog kind="po" document="202607-S0100" poId="po-1" open onOpenChange={vi.fn()} />);
    await screen.findByText('DAFUYUAN');
    expect(screen.getByText('Received 486 at BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('SPO withdrawn')).toBeInTheDocument();
    expect(screen.queryByText(/in transit/i)).not.toBeInTheDocument();
  });
});
