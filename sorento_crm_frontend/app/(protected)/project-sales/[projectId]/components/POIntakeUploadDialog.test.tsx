/**
 * P4 - the upload (AC-D1).
 *
 * The upload returns as soon as the document is stored, so the dialog's job ends at "the
 * scan is on the server": it hands over to the confirm screen, which reports extraction. A
 * modal that waited for a queue would be a worse lie than showing the queue.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => ({ get: () => null }),
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
    warning: vi.fn(),
  },
}));

const uploadPurchaseOrderDocument = vi.fn();
vi.mock('../../_shared/services/poIntakeService', () => ({
  uploadPurchaseOrderDocument: (...args: unknown[]) => uploadPurchaseOrderDocument(...args),
  getPOVersion: vi.fn(),
  listPOVersions: vi.fn(),
  updatePOVersionLine: vi.fn(),
  updatePOVersionHeader: vi.fn(),
  confirmPOVersion: vi.fn(),
  approvePurchaseOrder: vi.fn(),
  countersignPurchaseOrder: vi.fn(),
  acceptPOAnnotation: vi.fn(),
  editPOAnnotation: vi.fn(),
  rejectPOAnnotation: vi.fn(),
}));

const listProjects = vi.fn();
const listEditableProjectOptions = vi.fn();
vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    listProjects: (...args: unknown[]) => listProjects(...args),
    listEditableProjectOptions: (...args: unknown[]) => listEditableProjectOptions(...args),
  };
});

import { POIntakeUploadDialog } from './POIntakeUploadDialog';

function renderDialog(
  props: {
    projectId?: string;
    purchaseOrderId?: string | null;
    originHref?: string;
    pipelineListQuery?: string;
  } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <POIntakeUploadDialog
        projectId={'projectId' in props ? props.projectId : 'p1'}
        purchaseOrderId={props.purchaseOrderId ?? null}
        purchaseOrderNumber={props.purchaseOrderId ? 'HQ/26/01/041' : null}
        onDone={() => {}}
        originHref={props.originHref}
        pipelineListQuery={props.pipelineListQuery}
      />
    </QueryClientProvider>,
  );
}

function pdf(name = 'customer-po-buimaco-r1.pdf') {
  return new File(['%PDF-1.4'], name, { type: 'application/pdf' });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POIntakeUploadDialog', () => {
  it('will not upload nothing', () => {
    renderDialog();

    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
    expect(screen.getByText('Drop the PO here')).toBeInTheDocument();
  });

  it('refuses a file that is neither a PDF nor a photo', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('PO document'), {
      target: { files: [new File(['x'], 'schedule.xlsx')] },
    });

    // The wording moved with the shared dropzone; what is pinned is that the file is
    // named in the refusal and that the dialog cannot be submitted with it.
    expect(toastError).toHaveBeenCalledWith('schedule.xlsx is not a PDF or a photo.');
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
  });

  it('goes straight to the confirm screen and says how many pages are being read', async () => {
    uploadPurchaseOrderDocument.mockResolvedValue({
      purchase_order_id: 'po1',
      po_version_id: 'v9',
      version_no: 1,
      extraction_state: 'queued',
      page_count: 10,
    });

    renderDialog();

    fireEvent.change(screen.getByLabelText('PO document'), { target: { files: [pdf()] } });
    expect(screen.getByTitle('customer-po-buimaco-r1.pdf')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('PO number'), {
      target: { value: 'HQ/26/01/041' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() =>
      expect(uploadPurchaseOrderDocument).toHaveBeenCalledWith('p1', {
        file: expect.any(File),
        po_number: 'HQ/26/01/041',
        purchase_order_id: null,
      }),
    );
    expect(toastSuccess).toHaveBeenCalledWith('Uploaded. Reading 10 pages.');
    expect(push).toHaveBeenCalledWith('/project-sales/p1/purchase-orders/v9');
  });

  it('adds a version to an existing PO instead of asking for its number again', async () => {
    uploadPurchaseOrderDocument.mockResolvedValue({
      purchase_order_id: 'po1',
      po_version_id: 'v2',
      version_no: 2,
      extraction_state: 'queued',
      page_count: null,
    });

    renderDialog({ purchaseOrderId: 'po1' });

    expect(
      screen.getByText('Upload a new document for HQ/26/01/041'),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('PO number')).toBeNull();

    fireEvent.change(screen.getByLabelText('PO document'), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() =>
      expect(uploadPurchaseOrderDocument).toHaveBeenCalledWith('p1', {
        file: expect.any(File),
        po_number: null,
        purchase_order_id: 'po1',
      }),
    );
    expect(toastSuccess).toHaveBeenCalledWith('Uploaded. Reading the document.');
  });

  it('stays put when the upload is refused', async () => {
    uploadPurchaseOrderDocument.mockRejectedValue(new Error('File is too large'));

    renderDialog();

    fireEvent.change(screen.getByLabelText('PO document'), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('File is too large'));
    expect(push).not.toHaveBeenCalled();
  });

  it('renders no project field when opened for a known project (S2-4)', () => {
    renderDialog();

    expect(screen.queryByLabelText(/^Project/)).toBeNull();
  });

  it('renders a required project field, and refuses the upload without one, when opened with no project (S2-4)', async () => {
    renderDialog({ projectId: undefined });

    expect(screen.getByLabelText(/^Project/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('PO document'), { target: { files: [pdf()] } });
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
  });

  it('routes to the review page under the project PICKED from Start, never a blank segment (S2-7)', async () => {
    listEditableProjectOptions.mockResolvedValue([
      { value: 'p-setia-alam', label: 'Setia Alam', description: 'PRJ-000009 · SP Setia' },
    ]);
    uploadPurchaseOrderDocument.mockResolvedValue({
      purchase_order_id: 'po1',
      po_version_id: 'v9',
      version_no: 1,
      extraction_state: 'queued',
      page_count: 3,
    });

    renderDialog({ projectId: undefined });

    fireEvent.click(screen.getByLabelText(/^Project/));
    fireEvent.click(await screen.findByText('Setia Alam'));

    fireEvent.change(screen.getByLabelText('PO document'), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() =>
      expect(uploadPurchaseOrderDocument).toHaveBeenCalledWith('p-setia-alam', expect.any(Object)),
    );
    // S4-5: a Start-driven upload's review page always carries the Pipeline list as its origin.
    const [pushedUrl] = push.mock.calls[0];
    expect(pushedUrl).toMatch(/^\/project-sales\/p-setia-alam\/purchase-orders\/v9\?from=/);
    expect(new URLSearchParams(pushedUrl.split('?')[1]).get('from')).toBe(
      '/project-sales/pipeline?from=p-setia-alam',
    );
    expect(push).not.toHaveBeenCalledWith(expect.stringContaining('/project-sales//'));
  });

  it('carries the Pipeline grid\'s own list state alongside the picked project (S4-1)', async () => {
    listEditableProjectOptions.mockResolvedValue([
      { value: 'p-setia-alam', label: 'Setia Alam', description: 'PRJ-000009 · SP Setia' },
    ]);
    uploadPurchaseOrderDocument.mockResolvedValue({
      purchase_order_id: 'po1',
      po_version_id: 'v9',
      version_no: 1,
      extraction_state: 'queued',
      page_count: 3,
    });

    renderDialog({ projectId: undefined, pipelineListQuery: 'page=2&sort=created_at&dir=desc' });

    fireEvent.click(screen.getByLabelText(/^Project/));
    fireEvent.click(await screen.findByText('Setia Alam'));
    fireEvent.change(screen.getByLabelText('PO document'), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    const [pushedUrl] = push.mock.calls[0];
    expect(new URLSearchParams(pushedUrl.split('?')[1]).get('from')).toBe(
      '/project-sales/pipeline?page=2&sort=created_at&dir=desc&from=p-setia-alam',
    );
  });

  it('forwards the given originHref when opened from a project tab with a fixed project (S4-1)', async () => {
    uploadPurchaseOrderDocument.mockResolvedValue({
      purchase_order_id: 'po1',
      po_version_id: 'v9',
      version_no: 1,
      extraction_state: 'queued',
      page_count: 3,
    });

    renderDialog({ originHref: '/project-sales/p1?tab=pos' });

    fireEvent.change(screen.getByLabelText('PO document'), { target: { files: [pdf()] } });
    fireEvent.change(screen.getByLabelText('PO number'), { target: { value: 'HQ/26/01/041' } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    const [pushedUrl] = push.mock.calls[0];
    expect(new URLSearchParams(pushedUrl.split('?')[1]).get('from')).toBe(
      '/project-sales/p1?tab=pos',
    );
  });
});
