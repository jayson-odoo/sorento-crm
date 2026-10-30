/**
 * QUOTE-CUSTOMER-AMEND fix round 2 (item 5): the free-text changes-requested strip stands down
 * while the customer's suggested changes are on the Lines tab (open, or applied with rows), so
 * its Revise cannot walk the salesperson into the hand-made draft that blocks Apply. A request
 * from before suggestions existed keeps the strip. Values invented.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';
import type { QuotationAmendmentRequest } from '../../../../_shared/types/project.types';
import { QuotationChangesRequestedPanel } from './QuotationChangesRequestedPanel';

const DOCUMENT = {
  id: 'd1',
  customer_decision: 'changes_requested',
  changes_requested_at: '2026-10-30T06:05:00',
  changes_requested_note: 'Please deliver in two batches.',
  changes_requested_by_name: 'Buyer A',
} as unknown as QuotationDocument;

const AMENDMENT: QuotationAmendmentRequest = {
  id: 'req-1',
  status: 'open',
  submitted_at: '2026-10-30T06:05:00',
  requester_name: 'Buyer A',
  note: 'Please deliver in two batches.',
  applied_at: null,
  rows: [],
  total_issued: '100.00',
  total_after: '100.00',
  blocked_scopes: [],
};

function renderPanel(amendment: QuotationAmendmentRequest | null) {
  return render(
    <QuotationChangesRequestedPanel
      document={DOCUMENT}
      reviseLabel="Revise this quotation"
      onRevise={vi.fn()}
      amendment={amendment}
    />,
  );
}

describe('QuotationChangesRequestedPanel beside suggested changes', () => {
  it('renders nothing while a suggestion request is open', () => {
    renderPanel(AMENDMENT);
    expect(screen.queryByText(/asked for changes/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Revise this quotation' })).toBeNull();
  });

  it('keeps the strip for a free-text request with no suggestion request', () => {
    renderPanel(null);
    expect(screen.getByText(/Buyer A asked for changes/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Revise this quotation' })).toBeInTheDocument();
  });
});
