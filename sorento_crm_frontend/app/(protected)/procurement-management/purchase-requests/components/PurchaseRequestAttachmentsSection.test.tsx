/**
 * M5-06 - the linked-attachments table renders on DataGrid instead of a raw
 * `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const noopMutation = { mutate: vi.fn(), isPending: false };
vi.mock('../hooks/usePurchaseRequests', () => ({
  useDeletePurchaseRequestAttachment: () => noopMutation,
}));

const ATTACHMENTS = [
  {
    id: 'a-1',
    purchase_request_id: 'pr-1',
    attachment_id: 'att-1',
    file_name: 'quote.pdf',
    original_filename: 'quote.pdf',
    file_url: 'https://cdn.example.com/quote.pdf',
    file_size_bytes: 102400,
    uploaded_at: '2026-01-05T00:00:00',
    uploaded_by_name: 'Alice Tan',
    uploaded_by_role: 'staff' as const,
  },
  {
    id: 'a-2',
    purchase_request_id: 'pr-1',
    attachment_id: 'att-2',
    file_name: 'spec.pdf',
    original_filename: 'spec.pdf',
    file_url: 'https://cdn.example.com/spec.pdf',
    file_size_bytes: 51200,
    uploaded_at: '2026-01-06T00:00:00',
    uploaded_by_name: 'Bob Lee',
    uploaded_by_role: 'staff' as const,
  },
];

import PurchaseRequestAttachmentsSection from './PurchaseRequestAttachmentsSection';

describe('PurchaseRequestAttachmentsSection - DataGrid', () => {
  it('renders the column headers and a real cell value for each attachment', () => {
    render(
      <PurchaseRequestAttachmentsSection requestId="pr-1" attachments={ATTACHMENTS} />,
    );

    expect(screen.getByText('File Name')).toBeInTheDocument();
    expect(screen.getByText('Uploaded By')).toBeInTheDocument();

    expect(screen.getByText('quote.pdf')).toBeInTheDocument();
    expect(screen.getByText('spec.pdf')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Unlink/i })).toHaveLength(2);
  });
});
