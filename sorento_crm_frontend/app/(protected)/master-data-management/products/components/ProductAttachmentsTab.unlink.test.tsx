/**
 * Unlink confirmation on the product's attachments tab.
 *
 * Detaching is destructive-shaped: the link is the only record that this file
 * belongs to this product, and a mis-click on a row of near-identical filenames
 * (SRTWC286-SH has 31 of them) is unrecoverable without hunting the file back
 * down in Resource Management. PRINCIPLES.md therefore treats Unlink exactly
 * like Delete: a dialog, never one click, and never the browser's confirm().
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { ProductAttachment } from '../../product-attachments/types/productAttachment.types';

const PRODUCT_ID = 'prod-1';

const getProductAttachmentsByProduct = vi.fn();
const deleteProductAttachment = vi.fn();

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  custom: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({ toast: toastMock }));

vi.mock('../../product-attachments/services/productAttachmentService', () => ({
  getProductAttachmentsByProduct: (...a: unknown[]) => getProductAttachmentsByProduct(...a),
  getProductAttachments: vi.fn(),
  getProductAttachment: vi.fn(),
  createProductAttachment: vi.fn(),
  updateProductAttachment: vi.fn(),
  deleteProductAttachment: (...a: unknown[]) => deleteProductAttachment(...a),
}));

vi.mock('../services/productBrochureImageService', () => ({
  setBrochureImage: vi.fn(),
  clearBrochureImage: vi.fn(),
}));

// Peripheral panels of the tab; none of them touch the link.
vi.mock('../hooks/useProducts', () => ({ useProduct: () => ({ data: undefined }) }));
vi.mock('../hooks/useFieldLinkageSchema', () => ({
  useFieldLinkageSchema: () => ({ data: { fields: [] } }),
}));
vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));
vi.mock('@/app/(protected)/resource-management/attachments/hooks/useAttachments', () => ({
  useDownloadAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/app/(protected)/resource-management/attachments/services/attachmentService', () => ({
  getAttachmentPreviewUrl: vi.fn(),
}));
vi.mock('./LinkAttachmentBrowserDialog', () => ({ default: () => null }));
vi.mock('@/app/(protected)/resource-management/attachments/components/AttachmentDetailModal', () => ({
  default: () => null,
}));
vi.mock('@/app/(protected)/resource-management/attachments/components/ManageFieldLinksDialog', () => ({
  default: () => null,
}));

import ProductAttachmentsTab from './ProductAttachmentsTab';

function row(id: string, attachmentId: string, filename: string): ProductAttachment {
  return {
    id,
    product_id: PRODUCT_ID,
    attachment_id: attachmentId,
    is_primary: false,
    attachment: {
      id: attachmentId,
      original_filename: filename,
      stored_filename: filename,
      file_path: `product-photo/${attachmentId}/${filename}`,
      mime_type: 'image/jpeg',
      file_size_bytes: 120_000,
      full_directory_path: 'SORENTO --> Product Photo',
      directory_id: 'dir-1',
      uploaded_at: '2026-03-10T00:00:00Z',
      is_deleted: false,
    },
  };
}

const PHOTO_A = row('pa-a', 'att-a', 'SRTWC286-SH-front.jpg');
const PHOTO_B = row('pa-b', 'att-b', 'SRTWC286-SH-angle.jpg');

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductAttachmentsTab productId={PRODUCT_ID} isEditMode />
    </QueryClientProvider>,
  );
}

function attachmentRow(productAttachmentId: string) {
  return screen.getByTestId(`product-attachment-row-${productAttachmentId}`);
}

async function openUnlinkDialogFor(productAttachmentId: string) {
  renderTab();
  await waitFor(() => expect(attachmentRow(productAttachmentId)).toBeInTheDocument());
  fireEvent.click(
    within(attachmentRow(productAttachmentId)).getByRole('button', { name: 'Unlink attachment' }),
  );
  return screen.findByRole('alertdialog');
}

beforeEach(() => {
  vi.clearAllMocks();
  getProductAttachmentsByProduct.mockResolvedValue([PHOTO_A, PHOTO_B]);
  deleteProductAttachment.mockResolvedValue(undefined);
});

afterEach(() => cleanup());

describe('ProductAttachmentsTab unlink confirmation', () => {
  it('asks first and sends nothing, naming the file so a wrong row is obvious', async () => {
    const dialog = await openUnlinkDialogFor('pa-b');

    expect(deleteProductAttachment).not.toHaveBeenCalled();
    expect(within(dialog).getByText('Unlink attachment?')).toBeInTheDocument();
    expect(dialog).toHaveTextContent('SRTWC286-SH-angle.jpg');
    expect(dialog).toHaveTextContent(/cannot be undone/i);
  });

  it('unlinks exactly the confirmed row, once', async () => {
    const dialog = await openUnlinkDialogFor('pa-b');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Unlink' }));

    await waitFor(() => expect(deleteProductAttachment).toHaveBeenCalledWith('pa-b'));
    expect(deleteProductAttachment).toHaveBeenCalledTimes(1);
  });

  it('leaves the attachment linked and fires nothing when cancelled', async () => {
    const dialog = await openUnlinkDialogFor('pa-b');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(deleteProductAttachment).not.toHaveBeenCalled();
    expect(attachmentRow('pa-b')).toBeInTheDocument();
  });

  it('keeps its buttons reachable on a phone-width screen', async () => {
    const dialog = await openUnlinkDialogFor('pa-b');

    // A dialog taller than the viewport hides its own footer at 375px, which
    // leaves the user unable to cancel; capped height plus scroll is the fix.
    expect(dialog.className).toMatch(/max-h-/);
    expect(dialog.className).toMatch(/overflow-y-auto/);
  });

  it('uses the destructive styling required for a confirm action', async () => {
    const dialog = await openUnlinkDialogFor('pa-b');

    expect(within(dialog).getByRole('button', { name: 'Unlink' }).className).toContain(
      'bg-destructive text-destructive-foreground hover:bg-destructive/90',
    );
  });
});
