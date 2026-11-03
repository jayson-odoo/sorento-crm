/**
 * The free-text changes-requested strip. PS-QUOTE-MATRIX retired the suggested changes it used to
 * stand down for (Accept / Reject / Apply became feedback notes on their own tab), so the strip
 * follows the document alone. Values invented.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';
import { QuotationChangesRequestedPanel } from './QuotationChangesRequestedPanel';

const DOCUMENT = {
  id: 'd1',
  customer_decision: 'changes_requested',
  changes_requested_at: '2026-10-30T06:05:00',
  changes_requested_note: 'Please deliver in two batches.',
  changes_requested_by_name: 'Buyer A',
} as unknown as QuotationDocument;

describe('QuotationChangesRequestedPanel', () => {
  it('names who asked, quotes the words and offers the revise', () => {
    render(
      <QuotationChangesRequestedPanel
        document={DOCUMENT}
        reviseLabel="Revise this quotation"
        onRevise={vi.fn()}
      />,
    );
    expect(screen.getByText(/Buyer A asked for changes/)).toBeInTheDocument();
    expect(screen.getByText('Please deliver in two batches.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Revise this quotation' })).toBeInTheDocument();
  });

  it('renders nothing when the customer asked for nothing', () => {
    const { container } = render(
      <QuotationChangesRequestedPanel
        document={{ ...DOCUMENT, customer_decision: null, changes_requested_at: null } as unknown as QuotationDocument}
        reviseLabel="Revise this quotation"
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
