/**
 * AttachmentBulkDeleteDialog - mixed folder + file bulk delete (Fix 1).
 *
 * The unified Drive selection can contain folders AND files. Selecting a folder
 * and choosing Action -> "Delete selected" must delete BOTH: files via the bulk
 * archive/delete path, folders via the directory delete (cascades subtree). The
 * count copy must reflect the real breakdown.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import AttachmentBulkDeleteDialog from './AttachmentBulkDeleteDialog';
import {
  useBulkDeleteAttachments,
  useBulkArchiveAttachments,
  useDeleteDirectory,
  usePermanentDeleteDirectory,
} from '../hooks/useAttachments';

vi.mock('../hooks/useAttachments', () => ({
  useBulkDeleteAttachments: vi.fn(),
  useBulkArchiveAttachments: vi.fn(),
  useDeleteDirectory: vi.fn(),
  usePermanentDeleteDirectory: vi.fn(),
}));

const bulkDelete = vi.fn();
const bulkArchive = vi.fn();
const deleteDir = vi.fn();
const permDeleteDir = vi.fn();

function mutationStub(mutateAsync: ReturnType<typeof vi.fn>) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return { mutateAsync, isPending: false } as any;
}

beforeEach(() => {
  vi.clearAllMocks();
  bulkDelete.mockResolvedValue({ deleted_count: 0 });
  bulkArchive.mockResolvedValue({ archived_count: 0 });
  deleteDir.mockResolvedValue(undefined);
  permDeleteDir.mockResolvedValue({ directories_deleted: 1, attachments_deleted: 0 });
  vi.mocked(useBulkDeleteAttachments).mockReturnValue(mutationStub(bulkDelete));
  vi.mocked(useBulkArchiveAttachments).mockReturnValue(mutationStub(bulkArchive));
  vi.mocked(useDeleteDirectory).mockReturnValue(mutationStub(deleteDir));
  vi.mocked(usePermanentDeleteDirectory).mockReturnValue(mutationStub(permDeleteDir));
});

describe('AttachmentBulkDeleteDialog', () => {
  it('mixed selection: deletes both files and folders on confirm', async () => {
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    render(
      <AttachmentBulkDeleteDialog
        open
        onOpenChange={onOpenChange}
        attachmentIds={['f1', 'f2']}
        folderIds={['d1']}
        onSuccess={onSuccess}
      />
    );

    // Count breakdown: "3 items (1 folder, 2 files)" appears in both the
    // description and the confirm button.
    expect(screen.getAllByText(/3 items \(1 folder, 2 files\)/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /move to trash 3 items/i }));

    await waitFor(() => {
      expect(bulkArchive).toHaveBeenCalledWith(['f1', 'f2']);
      expect(deleteDir).toHaveBeenCalledWith('d1');
      expect(onSuccess).toHaveBeenCalled();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('folder-only selection: deletes the folder, never the file path', async () => {
    const onSuccess = vi.fn();
    render(
      <AttachmentBulkDeleteDialog
        open
        onOpenChange={vi.fn()}
        attachmentIds={[]}
        folderIds={['d1', 'd2']}
        onSuccess={onSuccess}
      />
    );

    // No breakdown parenthetical when only one kind is selected.
    expect(screen.getAllByText(/2 items/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/folder,/i)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /move to trash 2 items/i }));

    await waitFor(() => {
      expect(deleteDir).toHaveBeenCalledWith('d1');
      expect(deleteDir).toHaveBeenCalledWith('d2');
      expect(bulkArchive).not.toHaveBeenCalled();
      expect(onSuccess).toHaveBeenCalled();
    });
  });

  it('file-only selection: uses the bulk file path with singular copy', async () => {
    render(
      <AttachmentBulkDeleteDialog
        open
        onOpenChange={vi.fn()}
        attachmentIds={['f1']}
        folderIds={[]}
        onSuccess={vi.fn()}
      />
    );

    expect(screen.getAllByText(/1 item/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /move to trash 1 item/i }));

    await waitFor(() => {
      expect(bulkArchive).toHaveBeenCalledWith(['f1']);
      expect(deleteDir).not.toHaveBeenCalled();
    });
  });

  it('permanent (trash) mode: folders use the permanent directory delete', async () => {
    render(
      <AttachmentBulkDeleteDialog
        open
        onOpenChange={vi.fn()}
        attachmentIds={['f1']}
        folderIds={['d1']}
        permanent
        onSuccess={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /permanently delete 2 items/i }));

    await waitFor(() => {
      expect(bulkDelete).toHaveBeenCalledWith(['f1']);
      expect(permDeleteDir).toHaveBeenCalledWith('d1');
      expect(deleteDir).not.toHaveBeenCalled();
    });
  });

  it('empty selection: confirm is a no-op and the button is disabled', () => {
    render(
      <AttachmentBulkDeleteDialog
        open
        onOpenChange={vi.fn()}
        attachmentIds={[]}
        folderIds={[]}
        onSuccess={vi.fn()}
      />
    );
    const btn = screen.getByRole('button', { name: /move to trash 0 items/i });
    expect(btn).toBeDisabled();
  });
});
