/**
 * ATTACH-DELETE-PERM: the record action set offers "Permanently delete" on a trashed file
 * only to a caller holding `resource.attachments.delete`, the slug the server checks.
 * "Move to trash" (archive) is not gated by it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const hasPermission = vi.fn<(slug: string) => boolean>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock('./hooks/useAttachments', () => {
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
  return {
    useDownloadAttachment: idle,
    useUpdateAttachment: idle,
    useResubmitAttachmentWebhook: idle,
    useRestoreAttachment: idle,
  };
});

vi.mock('./components/attachment-delete-dialog', () => ({ default: () => null }));

import { useAttachmentActions } from './actions';
import type { Attachment } from './types/attachment.types';

function attachment(isDeleted: boolean): Attachment {
  return {
    id: 'att-1',
    original_filename: 'brief.pdf',
    stored_filename: 'brief.pdf',
    is_deleted: isDeleted,
  } as Attachment;
}

function labels(isDeleted: boolean): string[] {
  const { result } = renderHook(() => useAttachmentActions(attachment(isDeleted)));
  return result.current.actions.map((a) => String(a.label));
}

describe('useAttachmentActions delete gating', () => {
  beforeEach(() => hasPermission.mockReset());

  it('a trashed file offers Permanently delete with the permission', () => {
    hasPermission.mockImplementation((slug) => slug === 'resource.attachments.delete');
    expect(labels(true)).toContain('Permanently delete');
  });

  it('a trashed file offers no Permanently delete without the permission', () => {
    hasPermission.mockReturnValue(false);
    const l = labels(true);
    expect(l).not.toContain('Permanently delete');
    expect(l).toContain('Restore');
  });

  it('a live file still offers Move to trash without the permission', () => {
    hasPermission.mockReturnValue(false);
    expect(labels(false)).toContain('Move to trash');
  });
});
