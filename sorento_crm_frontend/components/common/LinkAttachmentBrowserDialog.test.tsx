/**
 * The shared file browser, now with a pick-and-return escape hatch (S4/S5 of
 * PLAN-flyer-read-hardening.md).
 *
 * Two behaviours are the whole reason `onConfirm` exists and have to be
 * pinned precisely:
 *  - when it is given, NOTHING is linked - no `linkAttachment` call, no
 *    invalidation, no success toast - and a throw from it toasts instead of
 *    silently closing.
 *  - when it is absent, the original link flow (complaints/PR/SI/packing
 *    lists) is byte-for-byte unchanged: `linkAttachment` fires, the given
 *    query keys invalidate, a toast fires, and single-select still means
 *    single-select.
 *
 * `mimeTypes` is asserted to reach `getAttachments` as `mime_types` AND to be
 * part of the react-query key - the second half is the one a "just add a
 * prop" change silently drops, because a key that does not change means a
 * stale cached page never re-fetches for the new filter.
 */
import type { ComponentProps } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/app/(protected)/resource-management/attachments/services/directoryService', () => ({
  getDirectoryTree: vi.fn(),
}));

vi.mock('@/app/(protected)/resource-management/attachments/services/attachmentService', () => ({
  getAttachments: vi.fn(),
}));

import { toast } from 'sonner';
import { getDirectoryTree } from '@/app/(protected)/resource-management/attachments/services/directoryService';
import { getAttachments } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import type { Attachment } from '@/app/(protected)/resource-management/attachments/types/attachment.types';

import LinkAttachmentBrowserDialog from './LinkAttachmentBrowserDialog';

const mockTree = vi.mocked(getDirectoryTree);
const mockAttachments = vi.mocked(getAttachments);

function attachment(id: string, filename: string, overrides: Partial<Attachment> = {}): Attachment {
  return {
    id,
    original_filename: filename,
    stored_filename: filename,
    file_path: `general/${filename}`,
    file_size_bytes: 1024,
    mime_type: 'application/pdf',
    entity_type: null,
    entity_id: null,
    uploaded_at: new Date('2026-01-01T00:00:00Z'),
    created_at: new Date('2026-01-01T00:00:00Z'),
    is_deleted: false,
    ...overrides,
  };
}

const ATT_A = attachment('att-a', 'flyer-a.pdf');
const ATT_B = attachment('att-b', 'flyer-b.pdf');

function respond(items: Attachment[]) {
  return { data: items, empty: items.length === 0, pagination: { total: items.length, page: 1 } };
}

function renderDialog(props: Partial<ComponentProps<typeof LinkAttachmentBrowserDialog>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  const onOpenChange = vi.fn();

  const utils = render(
    <QueryClientProvider client={queryClient}>
      <LinkAttachmentBrowserDialog open onOpenChange={onOpenChange} {...props} />
    </QueryClientProvider>,
  );

  return { ...utils, queryClient, invalidateSpy, onOpenChange };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTree.mockResolvedValue([]);
  mockAttachments.mockResolvedValue(respond([ATT_A, ATT_B]));
});

async function selectByFilename(filename: string) {
  const row = await screen.findByText(filename);
  fireEvent.click(row);
}

describe('onConfirm (pick-and-return)', () => {
  it('hands back the selection, links nothing, invalidates nothing, toasts nothing, and closes', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const linkAttachment = vi.fn().mockResolvedValue(undefined);
    const { invalidateSpy, onOpenChange } = renderDialog({
      onConfirm,
      linkAttachment,
      invalidateQueryKeys: [['some-entity', '1']],
      maxSelections: 1,
    });

    await selectByFilename('flyer-a.pdf');
    fireEvent.click(screen.getByRole('button', { name: /link attachment/i }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm).toHaveBeenCalledWith([{ id: 'att-a', name: 'flyer-a.pdf' }]);

    expect(linkAttachment).not.toHaveBeenCalled();
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
    expect(vi.mocked(toast.error)).not.toHaveBeenCalled();

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('toasts the failure and leaves the dialog open when onConfirm throws', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('Could not use that file'));
    const { onOpenChange } = renderDialog({ onConfirm, maxSelections: 1 });

    await selectByFilename('flyer-a.pdf');
    fireEvent.click(screen.getByRole('button', { name: /link attachment/i }));

    await waitFor(() =>
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Could not use that file'),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('uses a custom title and confirm label when given', async () => {
    renderDialog({ onConfirm: vi.fn(), title: 'Choose a flyer', confirmLabel: 'Use this file' });

    expect(await screen.findByText('Choose a flyer')).toBeInTheDocument();
    await selectByFilename('flyer-a.pdf');
    expect(screen.getByRole('button', { name: 'Use this file' })).toBeInTheDocument();
  });
});

describe('display name precedence (stored_filename first)', () => {
  it('shows and returns stored_filename for a renamed library file', async () => {
    const renamed = attachment('att-r', 'uploaded-name.pdf', {
      stored_filename: 'Season Flyer 2026.pdf',
    });
    mockAttachments.mockResolvedValue(respond([renamed]));
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderDialog({ onConfirm, maxSelections: 1 });

    await selectByFilename('Season Flyer 2026.pdf');
    expect(screen.queryByText('uploaded-name.pdf')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /link attachment/i }));
    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith([{ id: 'att-r', name: 'Season Flyer 2026.pdf' }]),
    );
  });

  it('falls back to original_filename for a legacy row without stored_filename', async () => {
    const legacy = attachment('att-l', 'legacy-flyer.pdf', {
      stored_filename: null as unknown as string,
    });
    mockAttachments.mockResolvedValue(respond([legacy]));
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderDialog({ onConfirm, maxSelections: 1 });

    await selectByFilename('legacy-flyer.pdf');

    fireEvent.click(screen.getByRole('button', { name: /link attachment/i }));
    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith([{ id: 'att-l', name: 'legacy-flyer.pdf' }]),
    );
  });
});

describe('mimeTypes', () => {
  it('is forwarded to getAttachments as mime_types', async () => {
    renderDialog({ mimeTypes: ['application/pdf'] });

    await waitFor(() =>
      expect(mockAttachments).toHaveBeenCalledWith(
        expect.objectContaining({ mime_types: ['application/pdf'] }),
      ),
    );
  });

  it('changes the react-query key, so a different filter re-fetches', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const onOpenChange = vi.fn();

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <LinkAttachmentBrowserDialog
          open
          onOpenChange={onOpenChange}
          mimeTypes={['application/pdf']}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mockAttachments).toHaveBeenCalledTimes(1));

    // Same props, same key: react-query's `staleTime: Infinity` means this
    // must NOT trigger a second fetch.
    rerender(
      <QueryClientProvider client={queryClient}>
        <LinkAttachmentBrowserDialog
          open
          onOpenChange={onOpenChange}
          mimeTypes={['application/pdf']}
        />
      </QueryClientProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockAttachments).toHaveBeenCalledTimes(1);

    // A different filter is a different key and must re-fetch.
    rerender(
      <QueryClientProvider client={queryClient}>
        <LinkAttachmentBrowserDialog open onOpenChange={onOpenChange} mimeTypes={['image/png']} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mockAttachments).toHaveBeenCalledTimes(2));
    expect(mockAttachments).toHaveBeenLastCalledWith(
      expect.objectContaining({ mime_types: ['image/png'] }),
    );
  });
});

describe('the original link flow (unchanged without onConfirm)', () => {
  it('links the selection, invalidates the given keys, toasts success, and closes', async () => {
    const linkAttachment = vi.fn().mockResolvedValue(undefined);
    const { invalidateSpy, onOpenChange } = renderDialog({
      entityId: 'complaint-1',
      linkAttachment,
      invalidateQueryKeys: [['complaint', 'complaint-1'], ['complaints']],
      successEntityLabel: 'complaint',
    });

    await selectByFilename('flyer-a.pdf');
    fireEvent.click(screen.getByRole('button', { name: /link 1 attachment/i }));

    await waitFor(() => expect(linkAttachment).toHaveBeenCalledWith('complaint-1', 'att-a'));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['complaint', 'complaint-1'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['complaints'] });
    await waitFor(() =>
      expect(vi.mocked(toast.success)).toHaveBeenCalledWith('1 attachment(s) linked to complaint.'),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('maxSelections=1 keeps only the most recently clicked row selected', async () => {
    const linkAttachment = vi.fn().mockResolvedValue(undefined);
    renderDialog({ entityId: 'e-1', linkAttachment, maxSelections: 1 });

    await selectByFilename('flyer-a.pdf');
    await selectByFilename('flyer-b.pdf');

    fireEvent.click(screen.getByRole('button', { name: /link attachment/i }));

    await waitFor(() => expect(linkAttachment).toHaveBeenCalledTimes(1));
    expect(linkAttachment).toHaveBeenCalledWith('e-1', 'att-b');
  });

  it('disables the confirm button when there is no entityId and no onConfirm', async () => {
    renderDialog({});

    await selectByFilename('flyer-a.pdf');

    const confirmButton = screen.getByRole('button', { name: /link 1 attachment/i });
    expect(confirmButton).toBeDisabled();
  });
});
