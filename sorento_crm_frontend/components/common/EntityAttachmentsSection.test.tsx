/**
 * The shared record attachments section (new product application, order change notice), owner
 * rules of round 5: "Link Attachment" is an outline button, there is no action column or row
 * button, Unlink is in the file row's right-click menu, and a record that takes direct uploads
 * shows a drop zone whose chosen files go straight up. The deferred-unlink hook and the library
 * dialog are the seams.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mock = vi.hoisted(() => ({
  unlinkRun: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: mock.success, error: mock.error } }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: mock.unlinkRun, targetId: null, isPending: false, countdown: null }),
}));
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({
  __esModule: true,
  default: () => null,
}));

import { EntityAttachmentsSection, type EntityAttachmentRow } from './EntityAttachmentsSection';

const FILE: EntityAttachmentRow = {
  link_id: 'k-1',
  attachment_id: 'at-1',
  filename: 'revised-po.pdf',
  size: 2048,
  url: '/files/1',
  content_type: 'application/pdf',
};

function mount(props: { editable: boolean; uploadFile?: (id: string, f: File) => Promise<unknown> }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EntityAttachmentsSection
        entityId="ocn-1"
        attachments={[FILE]}
        editable={props.editable}
        linkAttachment={vi.fn()}
        unlinkActionKey="order_change_notice_attachment.unlink"
        unlinkEntityType="order_change_notice_attachment"
        invalidateKeys={[['order-change-notice', 'ocn-1']]}
        entityLabel="notice"
        uploadFile={props.uploadFile}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mock.unlinkRun.mockReset();
  mock.success.mockReset();
  mock.error.mockReset();
});

describe('EntityAttachmentsSection', () => {
  it('shows Link Attachment as an outline button, never the filled main one', () => {
    mount({ editable: true });
    const link = screen.getByRole('button', { name: /link attachment/i });
    expect(link.className).not.toMatch(/\bbg-primary\b/);
    expect(link.className).toMatch(/\bborder\b/);
  });

  it('has no Actions column and no Unlink row button', () => {
    mount({ editable: true });
    expect(screen.queryByRole('button', { name: /unlink/i })).toBeNull();
    expect(screen.queryByText('Actions')).toBeNull();
  });

  it('unlinks from the file row right-click menu through the deferred action', async () => {
    mount({ editable: true });
    fireEvent.contextMenu(screen.getByText('revised-po.pdf'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Unlink' }));
    expect(mock.unlinkRun).toHaveBeenCalledWith({ id: 'k-1', subject: 'revised-po.pdf' });
  });

  it('opens no menu on a read-only list', () => {
    mount({ editable: false });
    fireEvent.contextMenu(screen.getByText('revised-po.pdf'));
    expect(screen.queryByRole('menuitem', { name: 'Unlink' })).toBeNull();
    expect(screen.queryByRole('button', { name: /link attachment/i })).toBeNull();
  });

  it('uploads a chosen file straight onto the record', async () => {
    const uploadFile = vi.fn(async () => ({}));
    const { container } = mount({ editable: true, uploadFile });
    expect(screen.getByRole('button', { name: /choose file/i })).toBeInTheDocument();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['%PDF-1.4'], 'site-photo.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(uploadFile).toHaveBeenCalledWith('ocn-1', file));
    await waitFor(() => expect(mock.success).toHaveBeenCalledWith('site-photo.pdf attached'));
  });

  it('says plainly when an upload is refused', async () => {
    const uploadFile = vi.fn(async () => {
      throw new Error('This file type is not allowed');
    });
    const { container } = mount({ editable: true, uploadFile });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.pdf', { type: 'application/pdf' })] } });
    await waitFor(() => expect(mock.error).toHaveBeenCalledWith('This file type is not allowed'));
  });

  it('shows no drop zone without an upload route or on a read-only list', () => {
    mount({ editable: true });
    expect(screen.queryByRole('button', { name: /choose file/i })).toBeNull();
  });

  it('shows no drop zone to a reader even when the record takes uploads', () => {
    mount({ editable: false, uploadFile: vi.fn() });
    expect(screen.queryByRole('button', { name: /choose file/i })).toBeNull();
  });
});
