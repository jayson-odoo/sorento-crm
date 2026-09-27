/**
 * SoLineAttachmentsButton - the paperclip + lightbox for a sales-order line's own
 * clarification files (#1312, PLAN-oi-line-attachments-27sep.md). AC-U1..U5.
 *
 * TEST-FIRST: written before the component exists, so a red here is
 * "Failed to resolve import ./SoLineAttachmentsButton" - never an import typo elsewhere.
 *
 * The upload goes through `useUploadSoLineAttachments` (`useSoLineAttachments.ts`), which
 * calls `uploadSoLineAttachments` - mocked at the service layer below, the same shape
 * `ShipmentLinePhotosCell.test.tsx` uses, so the hook's own dispatch is exercised for real.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// AttachmentPreviewModal's carousel (embla) reads both in jsdom.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const uploadSoLineAttachments = vi.fn().mockResolvedValue([]);
vi.mock('@/app/(protected)/project-sales/_shared/services/soLineAttachmentService', () => ({
  uploadSoLineAttachments: (...args: unknown[]) => uploadSoLineAttachments(...args),
  lookupSoLineAttachments: vi.fn().mockResolvedValue({}),
  deleteSoLineAttachment: vi.fn(),
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'sales_order_line_attachment.delete',
  entity_type: 'sales_order_line_attachment',
  entity_id: 'link-1',
  commit_at: '2026-09-27T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { SoLineAttachmentsButton } from './SoLineAttachmentsButton';
import type { SoLineAttachment } from '../services/soLineAttachmentService';

const LABEL = 'SO423136 L3 SRTWCY8605-PJ';

function attachment(over: Partial<SoLineAttachment> = {}): SoLineAttachment {
  return {
    id: 'link-1',
    attachment_id: 'att-1',
    filename: 'photo.png',
    size_bytes: 1024,
    content_type: 'image/png',
    url: 'https://cdn.example.com/photo.png',
    thumbnail_url: 'https://cdn.example.com/photo-thumb.png',
    ...over,
  };
}

function makeFile(name: string): File {
  return new File(['x'], name, { type: 'image/png' });
}

function renderButton(
  over: { attachments?: SoLineAttachment[]; canEdit?: boolean; lineId?: string } = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SoLineAttachmentsButton
        lineId={over.lineId ?? 'core-line-1'}
        label={LABEL}
        attachments={over.attachments ?? []}
        canEdit={over.canEdit ?? true}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  uploadSoLineAttachments.mockResolvedValue([]);
});

describe('SoLineAttachmentsButton', () => {
  it('renders the paperclip with an aria-label naming the line, no badge at zero (AC-U1/AC-U2)', () => {
    renderButton({ attachments: [] });

    expect(
      screen.getByRole('button', { name: `Attachments for ${LABEL}` }),
    ).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('shows the file count as a badge when above zero (AC-U2)', () => {
    renderButton({ attachments: [attachment(), attachment({ id: 'link-2' })] });

    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('opens the lightbox titled with the line on click, listing that line files (AC-U3)', () => {
    renderButton({ attachments: [attachment({ filename: 'clarification.png' })] });

    fireEvent.click(screen.getByRole('button', { name: `Attachments for ${LABEL}` }));

    expect(screen.getByText(LABEL)).toBeInTheDocument();
    expect(screen.getByText('clarification.png')).toBeInTheDocument();
  });

  it('offers a dropzone and Upload for a user with edit, and posts to THIS line only (AC-U3)', async () => {
    renderButton({ canEdit: true, lineId: 'core-line-1' });

    fireEvent.click(screen.getByRole('button', { name: `Attachments for ${LABEL}` }));

    const zone = screen.getByRole('button', { name: /drop|browse|choose/i });
    fireEvent.drop(zone, { dataTransfer: { files: [makeFile('clarification.png')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() =>
      expect(uploadSoLineAttachments).toHaveBeenCalledWith(
        'core-line-1',
        expect.arrayContaining([expect.objectContaining({ name: 'clarification.png' })]),
      ),
    );
  });

  it('shows no dropzone and no x for a user without edit (AC-U3)', () => {
    renderButton({ canEdit: false, attachments: [attachment({ filename: 'clarification.png' })] });

    fireEvent.click(screen.getByRole('button', { name: `Attachments for ${LABEL}` }));

    expect(screen.queryByRole('button', { name: 'Upload' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Delete/ })).not.toBeInTheDocument();
  });

  it('parks the delete on the x with no confirmation dialog in the way (AC-U5, D7)', async () => {
    renderButton({
      canEdit: true,
      attachments: [attachment({ id: 'link-1', filename: 'clarification.png' })],
    });

    fireEvent.click(screen.getByRole('button', { name: `Attachments for ${LABEL}` }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete clarification.png' }));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'sales_order_line_attachment.delete',
          entityType: 'sales_order_line_attachment',
          entityId: 'link-1',
        }),
      ),
    );
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();
  });
});
