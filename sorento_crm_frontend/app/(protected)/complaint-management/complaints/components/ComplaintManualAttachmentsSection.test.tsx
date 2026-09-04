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
vi.mock('../hooks/useComplaints', () => ({
  useDeleteComplaintAttachment: () => noopMutation,
  useDeleteComplaintResponseAttachment: () => noopMutation,
}));

const ATTACHMENTS = [
  {
    id: 'a-1',
    complaint_id: 'c-1',
    attachment_id: 'att-1',
    file_name: 'photo.jpg',
    original_filename: 'photo.jpg',
    file_url: 'https://cdn.example.com/photo.jpg',
    file_size_bytes: 204800,
    uploaded_at: new Date('2026-01-05T00:00:00'),
    link_type: 'complaint_attachment' as const,
    uploaded_by_name: 'Alice Tan',
    uploaded_by_role: 'staff' as const,
  },
  {
    id: 'a-2',
    complaint_id: 'c-1',
    attachment_id: 'att-2',
    file_name: 'invoice.pdf',
    original_filename: 'invoice.pdf',
    file_url: 'https://cdn.example.com/invoice.pdf',
    file_size_bytes: 51200,
    uploaded_at: new Date('2026-01-06T00:00:00'),
    link_type: 'response_attachment' as const,
    uploaded_by_name: 'Bob Lee',
    uploaded_by_role: 'staff' as const,
  },
];

import ComplaintManualAttachmentsSection from './ComplaintManualAttachmentsSection';

describe('ComplaintManualAttachmentsSection - DataGrid', () => {
  it('renders the column headers and a real cell value for each attachment', () => {
    render(
      <ComplaintManualAttachmentsSection complaintId="c-1" attachments={ATTACHMENTS} />,
    );

    expect(screen.getByText('File Name')).toBeInTheDocument();
    expect(screen.getByText('Uploaded By')).toBeInTheDocument();
    expect(screen.getByText('File Size')).toBeInTheDocument();

    expect(screen.getByText('photo.jpg')).toBeInTheDocument();
    expect(screen.getByText('invoice.pdf')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Unlink/i })).toHaveLength(2);
  });
});
