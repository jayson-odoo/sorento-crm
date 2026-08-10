import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import { AttachmentDropzone } from './AttachmentDropzone';
import type { PortalAttachment } from '../lib/portal-client';

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    uploadAttachment: vi.fn(),
    deleteAttachment: vi.fn(),
  };
});

import { uploadAttachment, deleteAttachment } from '../lib/portal-client';

// Mocked so the test asserts on the exact `open` / `items` props the dropzone
// hands the shared modal ("opens the preview in place") without pulling in the
// carousel engine (embla needs layout APIs jsdom lacks).
const previewPropsSpy = vi.fn();
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: (props: { open: boolean; items: { id: string; name: string }[]; startIndex?: number }) => {
    previewPropsSpy(props);
    if (!props.open) return null;
    return (
      <div data-testid="preview-modal">
        {props.items.map((it) => (
          <span key={it.id}>{it.name}</span>
        ))}
        <span data-testid="preview-start-index">{props.startIndex ?? 0}</span>
      </div>
    );
  },
}));

function contactUpload(over: Partial<PortalAttachment> = {}): PortalAttachment {
  return {
    link_id: 'link-1',
    attachment_id: 'att-1',
    filename: 'my-photo.jpg',
    size: 2048,
    url: 'https://cdn.example.com/my-photo.jpg',
    content_type: 'image/jpeg',
    uploader_kind: 'contact',
    can_unlink: true,
    ...over,
  };
}

function staffUpload(over: Partial<PortalAttachment> = {}): PortalAttachment {
  return {
    link_id: 'link-2',
    attachment_id: 'att-2',
    filename: 'purchasing-reply.pdf',
    size: 4096,
    url: 'https://cdn.example.com/purchasing-reply.pdf',
    content_type: 'application/pdf',
    uploader_kind: 'user',
    can_unlink: false,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AttachmentDropzone (portal)', () => {
  it('hides the unlink control when can_unlink is false (staff upload)', () => {
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[staffUpload()]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('purchasing-reply.pdf')).toBeInTheDocument();
    expect(screen.queryByLabelText('Remove attachment')).toBeNull();
    // View is still available - staff files stay previewable, only unlink is blocked.
    expect(screen.getByLabelText('View attachment')).toBeInTheDocument();
  });

  it('shows the unlink control when can_unlink is true (the contact’s own upload)', () => {
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[contactUpload()]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Remove attachment')).toBeInTheDocument();
  });

  it('requires the confirm dialog before deleting - no one-click unlink', async () => {
    (deleteAttachment as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const onChange = vi.fn();
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[contactUpload()]}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByLabelText('Remove attachment'));
    // Clicking Remove alone must not have deleted anything yet.
    expect(deleteAttachment).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();

    expect(screen.getByText('Remove this attachment?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^remove$/i }));

    await waitFor(() => expect(deleteAttachment).toHaveBeenCalledWith('link-1'));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([]));
  });

  it('cancelling the confirm dialog deletes nothing', () => {
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[contactUpload()]}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText('Remove attachment'));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(deleteAttachment).not.toHaveBeenCalled();
  });

  it('opens the preview in place when a row is clicked, scoped to the full attachment list', () => {
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[contactUpload(), staffUpload()]}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText('Preview purchasing-reply.pdf'));

    const modal = within(screen.getByTestId('preview-modal'));
    expect(screen.getByTestId('preview-modal')).toBeInTheDocument();
    expect(modal.getByText('my-photo.jpg')).toBeInTheDocument();
    expect(modal.getByText('purchasing-reply.pdf')).toBeInTheDocument();
    // Index 1 - the row that was clicked (staff upload is the 2nd attachment).
    expect(modal.getByTestId('preview-start-index').textContent).toBe('1');
  });

  it('hands the modal a portal byte reader and an attachment_id-keyed download route', () => {
    render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[contactUpload()]}
        onChange={vi.fn()}
      />,
    );
    const props = previewPropsSpy.mock.calls.at(-1)?.[0];
    // No NextAuth session on the portal, so the modal must not fall back to
    // its apiFetch default for Download / inline Excel.
    expect(typeof props.fetchBytes).toBe('function');
    // Keyed on attachment_id, never link_id (I2a).
    expect(props.items[0].downloadUrl).toBe(
      '/api/v1/public/portal/attachments/att-1/download',
    );
  });
});
