/**
 * poLinesOnly (owner, 13 Nov). Header mirrors LinkDocumentDialog.test.tsx.
 * "Place on PO" (section G, reworked G2, PLAN-demo-followups-19aug-ladder-v2.md): the
 * candidates table loads from `GET .../po-candidates`, opens already showing the
 * cascade's own preview (`default_take`) per line, lets the take be edited, and confirms
 * by posting the whole allocation in one call (`POST .../place-on-po { allocations }`).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryPoCandidate } from '../types/orderInquiry.types';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const getOrderInquiryPoCandidates = vi.fn();
const placeOrderInquiryRowOnPoAllocations = vi.fn();

vi.mock('../services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoCandidates: (...args: unknown[]) => getOrderInquiryPoCandidates(...args),
    placeOrderInquiryRowOnPoAllocations: (...args: unknown[]) =>
      placeOrderInquiryRowOnPoAllocations(...args),
  };
});

import { LinkDocumentDialog } from './LinkDocumentDialog';

const EARLY: OrderInquiryPoCandidate = {
  kind: 'po',
  po_line_id: 'po-line-early',
  tier: 1,
  location: 'BRW-IB',
  issue_date: '2026-08-01',
  cited: false,
  po_number: 'ZZT-PO-0001',
  supplier_name: 'Dafuyuan',
  expected_date: '2026-09-01',
  qty_ordered: '15',
  qty_received: '0',
  already_tagged: '0',
  remaining: '15',
  covers: false,
  recommended: false,
  default_take: '15',
  claims: [],
};

const LATER: OrderInquiryPoCandidate = {
  kind: 'po',
  po_line_id: 'po-line-later',
  tier: 3,
  location: 'BRW',
  issue_date: '2026-08-05',
  cited: false,
  po_number: 'ZZT-PO-0002',
  supplier_name: 'Another Factory',
  expected_date: '2026-09-15',
  qty_ordered: '20',
  qty_received: '0',
  already_tagged: '0',
  remaining: '20',
  covers: true,
  recommended: false,
  default_take: '10',
  claims: [],
};


// ASSUMPTION: no candidate field says "AutoCount ties this PO line to another SO line" today
// (the type has `covers`, `cited`, `claims`, `already_tagged`, not that), so the tests use a new
// boolean `tied_elsewhere` on the candidate. The coder may name it differently.
const TIED_ELSEWHERE = {
  ...LATER,
  po_line_id: 'po-line-tied',
  po_number: 'ZZT-PO-0003',
  tied_elsewhere: true,
} as OrderInquiryPoCandidate;

function renderDialog(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const onDone = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  getOrderInquiryPoCandidates.mockReset();
  getOrderInquiryPoCandidates.mockResolvedValue({ candidates: [EARLY, TIED_ELSEWHERE], still_to_link: '25' });
});

describe('LinkDocumentDialog poLinesOnly (the Link to PO... fallback)', () => {
  it('does not offer a PO line AutoCount ties to another sales order line', async () => {
    renderDialog(<LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" poLinesOnly onDone={onDone} />);
    await screen.findByLabelText('Take off ZZT-PO-0001');
    expect(screen.queryByLabelText('Take off ZZT-PO-0003')).toBeNull();
  });

  it('pre-fills no take: every qty input starts empty and Link is disabled until a qty is typed', async () => {
    renderDialog(<LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" poLinesOnly onDone={onDone} />);
    const input = (await screen.findByLabelText('Take off ZZT-PO-0001')) as HTMLInputElement;
    expect(input.value).toBe('');
    expect(screen.getByRole('button', { name: 'Link' })).toBeDisabled();
    fireEvent.change(input, { target: { value: '5' } });
    expect(screen.getByRole('button', { name: 'Link' })).toBeEnabled();
  });

  it('without poLinesOnly the dialog is as today: takes pre-filled, the tied line still offered', async () => {
    renderDialog(<LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />);
    const input = (await screen.findByLabelText('Take off ZZT-PO-0001')) as HTMLInputElement;
    expect(input.value).toBe('15');
    expect(screen.getByRole('button', { name: 'Link' })).toBeEnabled();
    expect(screen.getByLabelText('Take off ZZT-PO-0003')).toBeInTheDocument();
  });
});
