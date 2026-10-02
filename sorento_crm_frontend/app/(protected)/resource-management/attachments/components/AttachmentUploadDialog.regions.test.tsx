/**
 * AttachmentUploadDialog - Regions (REGION-PACKING-LIST, AC-RPL-2).
 *
 * A required Regions multi-select shows ONLY when the picked type's code is
 * `packing_list`, with West Malaysia preselected, and the chosen regions ride the upload
 * request as `regions` (lowercase codes). Other types show no Regions control and send
 * no `regions`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
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

const TYPE_OTHER = {
  id: 'type-cert',
  code: 'certificate',
  type_name: 'Certificate',
  description: null,
  allowed_extensions: 'pdf',
  max_file_size_mb: 10,
  supports_field_linkage: false,
  default_directory_id: null,
};
const TYPE_PACKING_LIST = {
  id: 'type-pl',
  code: 'packing_list',
  type_name: 'Packing List',
  description: null,
  allowed_extensions: 'pdf',
  max_file_size_mb: 10,
  supports_field_linkage: false,
  default_directory_id: null,
};

const mutateAsync = vi.fn(async () => ({ id: 'att-1' }));
const startSession = vi.fn();

vi.mock('../hooks/useAttachments', () => ({
  useUploadAttachment: () => ({ mutateAsync, isPending: false }),
  useAttachmentTypesList: () => ({ data: [TYPE_OTHER, TYPE_PACKING_LIST], isLoading: false }),
  useDirectoryTree: () => ({ data: [], isLoading: false }),
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
  useUploadManager: () => ({ startSession }),
}));

import AttachmentUploadDialog from './AttachmentUploadDialog';

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AttachmentUploadDialog open onOpenChange={() => {}} defaultDirectoryId="dir-1" />
    </QueryClientProvider>,
  );
}

function pickType(name: string) {
  fireEvent.click(screen.getByLabelText(/Attachment Type/i));
  fireEvent.click(screen.getByRole('option', { name }));
}

function attachFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['%PDF-1.4'], 'pl.pdf', { type: 'application/pdf' });
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AttachmentUploadDialog - Regions control (AC-RPL-2)', () => {
  it('shows a Regions control for the Packing List type with West Malaysia preselected', () => {
    renderDialog();
    pickType('Packing List');

    const regions = screen.getByLabelText('Regions');
    expect(regions).toBeInTheDocument();
    expect(regions).toHaveTextContent('West Malaysia');
    expect(regions).not.toHaveTextContent('East Malaysia');
  });

  it('shows no Regions control before a type is picked', () => {
    renderDialog();
    expect(screen.queryByLabelText('Regions')).not.toBeInTheDocument();
  });

  it('hides the Regions control for any other type', () => {
    renderDialog();
    pickType('Certificate');
    expect(screen.queryByLabelText('Regions')).not.toBeInTheDocument();
  });

  it('hides the Regions control again when the type switches away from Packing List', () => {
    renderDialog();
    pickType('Packing List');
    expect(screen.getByLabelText('Regions')).toBeInTheDocument();
    pickType('Certificate');
    expect(screen.queryByLabelText('Regions')).not.toBeInTheDocument();
  });
});

describe('AttachmentUploadDialog - regions reach the upload request (AC-RPL-2)', () => {
  async function submitAndRunUploader() {
    fireEvent.click(screen.getByRole('button', { name: /^Upload 1 Attachment$/ }));
    await waitFor(() => expect(startSession).toHaveBeenCalled());
    const { uploader } = startSession.mock.calls[0][0] as {
      uploader: (file: File) => Promise<unknown>;
    };
    await uploader(new File(['x'], 'pl.pdf', { type: 'application/pdf' }));
    return mutateAsync.mock.calls[0][0] as Record<string, unknown>;
  }

  it('sends West only for a Packing List upload by default', async () => {
    renderDialog();
    pickType('Packing List');
    attachFile();

    const request = await submitAndRunUploader();
    expect(request.regions).toEqual(['west']);
  });

  it('sends the regions the user ticked (West and East)', async () => {
    renderDialog();
    pickType('Packing List');
    fireEvent.click(screen.getByLabelText('Regions'));
    fireEvent.click(screen.getByRole('option', { name: 'East Malaysia' }));
    attachFile();

    const request = await submitAndRunUploader();
    expect([...(request.regions as string[])].sort()).toEqual(['east', 'west']);
  });

  it('sends no regions for another type', async () => {
    renderDialog();
    pickType('Certificate');
    attachFile();

    const request = await submitAndRunUploader();
    expect(request.regions == null || (request.regions as string[]).length === 0).toBe(true);
  });
});
