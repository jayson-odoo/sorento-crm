/**
 * S8 / AC-8.1 - one file card, drawn once (`PLAN-scm-ui-feedback-14sep.md`, J6, ruling R8).
 *
 * TEST-FIRST: `components/common/AttachmentFileCard.tsx` does not exist when this file is
 * written, so the whole suite is expected to fail on the import until S8 lands.
 *
 * The packing list's Related Documents tab hand-rolls this card today (name, `type - KB`,
 * eye, download, unlink) and the proforma invoice's Source files block hand-rolls a poorer
 * version of it (name and date, no buttons at all). They are the same object on screen, so
 * they become the same component - and Unlink is the only part that is not: a PI source file
 * is evidence of what was uploaded, and detaching it there would be a claim nobody made.
 *
 * Both handlers are the ones the packing tab already calls, so they are mocked at the
 * service/hook boundary rather than at `fetch`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const { getAttachmentPreviewUrlMock, downloadMock } = vi.hoisted(() => ({
  getAttachmentPreviewUrlMock: vi.fn(),
  downloadMock: vi.fn(),
}));

vi.mock(
  '@/app/(protected)/resource-management/attachments/services/attachmentService',
  () => ({ getAttachmentPreviewUrl: getAttachmentPreviewUrlMock }),
);

vi.mock('@/app/(protected)/resource-management/attachments/hooks/useAttachments', () => ({
  useDownloadAttachment: () => ({ mutateAsync: downloadMock, isPending: false }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

import { AttachmentFileCard } from './AttachmentFileCard';

const PROPS = {
  attachmentId: 'att-1',
  name: 'Sorento PI 260801.xlsx',
  typeLabel: 'Proforma Invoice',
  sizeBytes: 18342,
};

beforeEach(() => {
  getAttachmentPreviewUrlMock.mockReset().mockResolvedValue('https://cdn.example/att-1');
  downloadMock.mockReset().mockResolvedValue(new Blob(['x']));
  vi.spyOn(window, 'open').mockImplementation(() => null);
});

describe('AttachmentFileCard (AC-8.1)', () => {
  it('names the file and states its type and size', () => {
    render(<AttachmentFileCard {...PROPS} />);

    expect(screen.getByText('Sorento PI 260801.xlsx')).toBeInTheDocument();
    expect(screen.getByText(/Proforma Invoice/)).toBeInTheDocument();
    expect(screen.getByText(/17\.91 KB/)).toBeInTheDocument();
  });

  it('says the type alone when the size is unknown, rather than "0 KB"', () => {
    render(<AttachmentFileCard {...PROPS} sizeBytes={null} />);

    expect(screen.getByText(/Proforma Invoice/)).toBeInTheDocument();
    expect(screen.queryByText(/0\.00 KB/)).toBeNull();
  });

  it('carries Preview and Download as named icon buttons', () => {
    render(<AttachmentFileCard {...PROPS} />);

    expect(screen.getByRole('button', { name: /preview/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
  });

  it('opens the preview URL the attachment service answers with', async () => {
    render(<AttachmentFileCard {...PROPS} />);

    fireEvent.click(screen.getByRole('button', { name: /preview/i }));

    await waitFor(() => expect(getAttachmentPreviewUrlMock).toHaveBeenCalledWith('att-1'));
    await waitFor(() =>
      expect(window.open).toHaveBeenCalledWith(
        'https://cdn.example/att-1',
        '_blank',
        'noopener,noreferrer',
      ),
    );
  });

  it('downloads through the attachments hook, by id', async () => {
    render(<AttachmentFileCard {...PROPS} />);

    fireEvent.click(screen.getByRole('button', { name: /download/i }));

    await waitFor(() => expect(downloadMock).toHaveBeenCalledWith('att-1'));
  });

  it('offers Unlink only when a caller passes one', () => {
    const { rerender } = render(<AttachmentFileCard {...PROPS} />);
    expect(screen.queryByRole('button', { name: /unlink/i })).toBeNull();

    const onUnlink = vi.fn();
    rerender(<AttachmentFileCard {...PROPS} onUnlink={onUnlink} />);
    const unlink = screen.getByRole('button', { name: /unlink/i });

    fireEvent.click(unlink);

    expect(onUnlink).toHaveBeenCalledTimes(1);
  });
});
