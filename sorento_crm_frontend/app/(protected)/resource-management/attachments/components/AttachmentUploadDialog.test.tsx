/**
 * AttachmentUploadDialog - the reachable Folder picker (review round 1, B3/S3).
 *
 * `showFolderPicker = defaultDirectoryId === undefined` was never true: both real callers
 * (`AttachmentBrowser.tsx`, `AttachmentsInFolderPanel.tsx`) pass `directoryId ?? null`, so at
 * the root ("All attachments") the prop arrives as explicit `null`, never `undefined`. The
 * picker showed only when a caller passed neither prop at all (no production caller does).
 * Fixed to `defaultDirectoryId == null` - root reaches this either way, a real folder id is
 * the only value that still skips the picker (B3). A manual folder pick must also survive a
 * later attachment-type switch instead of being clobbered by that type's own default (S3).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = vi.fn();

const TYPE_NO_DEFAULT = {
  id: 'type-cert',
  type_name: 'Certificate',
  description: null,
  allowed_extensions: 'pdf',
  max_file_size_mb: 10,
  supports_field_linkage: false,
  default_directory_id: null,
};
const TYPE_WITH_DEFAULT = {
  id: 'type-pl',
  type_name: 'Packing List',
  description: null,
  allowed_extensions: 'xlsx,xls',
  max_file_size_mb: 10,
  supports_field_linkage: false,
  default_directory_id: 'dir-pl',
};

vi.mock('../hooks/useAttachments', () => ({
  useUploadAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAttachmentTypesList: () => ({
    data: [TYPE_NO_DEFAULT, TYPE_WITH_DEFAULT],
    isLoading: false,
  }),
  useDirectoryTree: (_deleted?: boolean, options?: { enabled?: boolean }) => ({
    data:
      options?.enabled === false
        ? []
        : [
            { id: 'dir-pl', name: 'Packing Lists', parent_id: null, sort_order: null, created_at: '', children: [] },
            { id: 'dir-other', name: 'Other Folder', parent_id: null, sort_order: null, created_at: '', children: [] },
          ],
    isLoading: false,
  }),
}));

vi.mock('@/hooks/use-upload-conflict', () => ({
  useUploadConflict: () => ({ ConflictDialog: null, confirmConflict: vi.fn() }),
}));

vi.mock('../services/attachmentService', () => ({
  checkAttachmentCollision: vi.fn(async () => ({ collides: false })),
}));

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));

vi.mock('@/components/upload-activity', () => ({
  useUploadManager: () => ({ startSession: vi.fn() }),
}));

import AttachmentUploadDialog from './AttachmentUploadDialog';

function renderDialog(defaultDirectoryId?: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const props =
    defaultDirectoryId === undefined ? {} : { defaultDirectoryId };
  return render(
    <QueryClientProvider client={qc}>
      <AttachmentUploadDialog open onOpenChange={() => {}} {...props} />
    </QueryClientProvider>,
  );
}

// `id`/`htmlFor` association survives a selection (unlike matching on the trigger's OWN
// text, which becomes the picked label the moment something is chosen).
function pickType(name: string) {
  fireEvent.click(screen.getByLabelText(/Attachment Type/i));
  fireEvent.click(screen.getByRole('option', { name }));
}

function folderSelect(): HTMLElement | null {
  return screen.queryByLabelText('Folder');
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AttachmentUploadDialog - Folder picker reachability (B3)', () => {
  it('shows the picker when no defaultDirectoryId prop is passed at all', () => {
    renderDialog(undefined);
    expect(screen.getByLabelText('Folder')).toBeInTheDocument();
  });

  it('shows the picker at root, where callers pass explicit null (the actual bug)', () => {
    renderDialog(null);
    expect(screen.getByLabelText('Folder')).toBeInTheDocument();
  });

  it('hides the picker when a real folder id is passed - the caller already decided', () => {
    renderDialog('dir-other');
    expect(screen.queryByLabelText('Folder')).not.toBeInTheDocument();
  });
});

describe('AttachmentUploadDialog - type pick pre-selects the folder (R4)', () => {
  it('seeds the folder select with the picked type\'s own default', () => {
    renderDialog(null);
    pickType('Packing List');

    const select = folderSelect()!;
    expect(within(select).getByText('Packing Lists')).toBeInTheDocument();
  });

  it('leaves the folder empty for a type with no default', () => {
    renderDialog(null);
    pickType('Certificate');

    const select = folderSelect()!;
    expect(within(select).getByText(/No folder/)).toBeInTheDocument();
  });
});

describe('AttachmentUploadDialog - a manual folder choice survives a type switch (S3)', () => {
  it('does not overwrite the user\'s own pick with the next type\'s default', () => {
    renderDialog(null);
    pickType('Certificate'); // no default - folder stays empty

    // User picks a folder by hand.
    fireEvent.click(folderSelect()!);
    fireEvent.click(screen.getByRole('option', { name: 'Other Folder' }));
    expect(within(folderSelect()!).getByText('Other Folder')).toBeInTheDocument();

    // Switching to a type WITH a default must not clobber the manual choice.
    pickType('Packing List');
    expect(within(folderSelect()!).getByText('Other Folder')).toBeInTheDocument();
  });
});
