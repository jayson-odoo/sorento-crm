/**
 * Brochure image control on the product's own attachments tab (surface 2).
 *
 * The tile a catalogue renders picks the photo flagged `is_primary`, and no row
 * behind the 2025-2026 flyer carries that flag, so a tile currently shows
 * whichever file happened to be linked first (for SRTWC286-SH that is one of 31,
 * including a blank page and two other products' photographs). Only a human can
 * say which picture is the product, so these tests pin the affordance that lets
 * them: one mark, moved by a click, never two at once, never offered for a PDF.
 *
 * The tab is rendered whole rather than the control in isolation, because "the
 * mark moves" is only observable across rows.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { ProductAttachment } from '../../product-attachments/types/productAttachment.types';

const PRODUCT_ID = 'prod-1';

const getProductAttachmentsByProduct = vi.fn();
const setBrochureImage = vi.fn();
const clearBrochureImage = vi.fn();

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
  deleteProductAttachment: vi.fn(),
}));

vi.mock('../services/productBrochureImageService', () => ({
  setBrochureImage: (...a: unknown[]) => setBrochureImage(...a),
  clearBrochureImage: (...a: unknown[]) => clearBrochureImage(...a),
}));

// Peripheral panels of the tab; none of them touch the brochure mark.
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

function row(
  id: string,
  attachmentId: string,
  filename: string,
  mimeType: string | null,
  isPrimary = false,
): ProductAttachment {
  return {
    id,
    product_id: PRODUCT_ID,
    attachment_id: attachmentId,
    is_primary: isPrimary,
    attachment: {
      id: attachmentId,
      original_filename: filename,
      stored_filename: filename,
      file_path: `product-photo/${attachmentId}/${filename}`,
      mime_type: mimeType,
      file_size_bytes: 120_000,
      full_directory_path: 'SORENTO --> Product Photo',
      directory_id: 'dir-1',
      uploaded_at: '2026-03-10T00:00:00Z',
      is_deleted: false,
    },
  };
}

const PHOTO_A = row('pa-a', 'att-a', 'SRTWC286-SH-front.jpg', 'image/jpeg', true);
const PHOTO_B = row('pa-b', 'att-b', 'SRTWC286-SH-angle.jpg', 'image/jpeg');
const SPEC_PDF = row('pa-c', 'att-c', 'SRTWC286-SH-spec.pdf', 'application/pdf');

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

beforeEach(() => {
  vi.clearAllMocks();
  getProductAttachmentsByProduct.mockResolvedValue([PHOTO_A, PHOTO_B, SPEC_PDF]);
  setBrochureImage.mockResolvedValue(undefined);
  clearBrochureImage.mockResolvedValue(undefined);
});

afterEach(() => cleanup());

describe('ProductAttachmentsTab brochure image control', () => {
  it('marks exactly one attachment and its control reads as already chosen', async () => {
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-a')).toBeInTheDocument());

    expect(screen.getAllByText('Brochure image')).toHaveLength(1);
    expect(within(attachmentRow('pa-a')).getByText('Brochure image')).toBeInTheDocument();

    const chosen = within(attachmentRow('pa-a')).getByRole('button', {
      name: 'Already the brochure image',
    });
    expect(chosen).toBeDisabled();
    expect(
      within(attachmentRow('pa-a')).queryByRole('button', { name: 'Use as brochure image' }),
    ).not.toBeInTheDocument();

    // Idempotent: the chosen row can never be clicked back into "nothing chosen".
    fireEvent.click(chosen);
    expect(setBrochureImage).not.toHaveBeenCalled();
    expect(clearBrochureImage).not.toHaveBeenCalled();
  });

  it('offers no brochure control on a non-image attachment', async () => {
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-c')).toBeInTheDocument());

    const pdfRow = within(attachmentRow('pa-c'));
    expect(pdfRow.queryByRole('button', { name: 'Use as brochure image' })).not.toBeInTheDocument();
    expect(
      pdfRow.queryByRole('button', { name: 'Already the brochure image' }),
    ).not.toBeInTheDocument();
    expect(pdfRow.queryByText('Brochure image')).not.toBeInTheDocument();
  });

  it('moves the mark when another image is chosen, never showing two', async () => {
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-b')).toBeInTheDocument());

    // The refetch that follows the save reports the moved flag.
    getProductAttachmentsByProduct.mockResolvedValue([
      { ...PHOTO_A, is_primary: false },
      { ...PHOTO_B, is_primary: true },
      SPEC_PDF,
    ]);

    fireEvent.click(
      within(attachmentRow('pa-b')).getByRole('button', { name: 'Use as brochure image' }),
    );

    await waitFor(() => expect(setBrochureImage).toHaveBeenCalledWith(PRODUCT_ID, 'att-b'));
    await waitFor(() =>
      expect(within(attachmentRow('pa-b')).getByText('Brochure image')).toBeInTheDocument(),
    );
    expect(screen.getAllByText('Brochure image')).toHaveLength(1);
    expect(
      within(attachmentRow('pa-a')).getByRole('button', { name: 'Use as brochure image' }),
    ).toBeInTheDocument();
  });

  it('shows one mark even when the API reports two flagged rows', async () => {
    // Legacy rows were flagged by an importer that never enforced the invariant,
    // and two marks would put the tile back to depending on row order.
    getProductAttachmentsByProduct.mockResolvedValue([
      PHOTO_A,
      { ...PHOTO_B, is_primary: true },
      SPEC_PDF,
    ]);
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-a')).toBeInTheDocument());

    expect(screen.getAllByText('Brochure image')).toHaveLength(1);
  });

  it('shows and lets you clear a flag that landed on a non-image', async () => {
    // A flagged PDF must not be silently invisible: "marked but not shown" is the
    // same class of bug as "two marks", so the row gets the mark and a way out,
    // but still no way to choose a spec sheet as the photo.
    getProductAttachmentsByProduct.mockResolvedValue([
      { ...PHOTO_A, is_primary: false },
      PHOTO_B,
      { ...SPEC_PDF, is_primary: true },
    ]);
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-c')).toBeInTheDocument());

    const pdfRow = within(attachmentRow('pa-c'));
    expect(pdfRow.getByText('Brochure image')).toBeInTheDocument();
    expect(pdfRow.queryByRole('button', { name: 'Use as brochure image' })).not.toBeInTheDocument();
    expect(pdfRow.getByRole('button', { name: 'Clear brochure image' })).toBeInTheDocument();
  });

  it('confirms before clearing the brochure image', async () => {
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-a')).toBeInTheDocument());

    fireEvent.click(
      within(attachmentRow('pa-a')).getByRole('button', { name: 'Clear brochure image' }),
    );

    // Detaching is destructive-shaped: nothing leaves until the dialog is answered.
    expect(clearBrochureImage).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Clear brochure image?')).toBeInTheDocument();
    // What happens next, not how the tile picks a photo when nothing is chosen.
    expect(within(dialog).queryByText(/linked first/i)).toBeNull();
    expect(within(dialog).queryByText(/catalogue tile/i)).toBeNull();
    expect(within(dialog).getByText(/stays attached/i)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(clearBrochureImage).toHaveBeenCalledWith(PRODUCT_ID));
  });

  it('keeps the mark and toasts the extracted message when the save fails', async () => {
    setBrochureImage.mockRejectedValue(new Error('Attachment is not linked to this product'));
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-b')).toBeInTheDocument());

    fireEvent.click(
      within(attachmentRow('pa-b')).getByRole('button', { name: 'Use as brochure image' }),
    );

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith('Attachment is not linked to this product'),
    );
    expect(within(attachmentRow('pa-a')).getByText('Brochure image')).toBeInTheDocument();
    expect(screen.getAllByText('Brochure image')).toHaveLength(1);
  });

  it('keeps the mark when clearing fails', async () => {
    // Same lie in the other direction: a row that reads as cleared while the
    // flag is still set sends the user off to choose a replacement they do not
    // need, and the tile keeps the photo they thought they had removed.
    clearBrochureImage.mockRejectedValue(new Error('Product not found'));
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-a')).toBeInTheDocument());

    fireEvent.click(
      within(attachmentRow('pa-a')).getByRole('button', { name: 'Clear brochure image' }),
    );
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Clear' }));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Product not found'));
    expect(within(attachmentRow('pa-a')).getByText('Brochure image')).toBeInTheDocument();
    expect(screen.getAllByText('Brochure image')).toHaveLength(1);
  });

  it('stays at nothing chosen when the first save on a product fails', async () => {
    // Nothing was flagged before, so the roll-back target is "no mark at all".
    // A mark left behind here is the worst version of the lie: the product reads
    // as answered on a screen whose entire job is recording that answer.
    getProductAttachmentsByProduct.mockResolvedValue([
      { ...PHOTO_A, is_primary: false },
      PHOTO_B,
      SPEC_PDF,
    ]);
    setBrochureImage.mockRejectedValue(new Error('Attachment is not an image'));
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-b')).toBeInTheDocument());

    fireEvent.click(
      within(attachmentRow('pa-b')).getByRole('button', { name: 'Use as brochure image' }),
    );

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith('Attachment is not an image'),
    );
    expect(screen.queryByText('Brochure image')).not.toBeInTheDocument();
    // Still offered, because the product genuinely has no brochure image and the
    // user has to be able to try again.
    expect(
      within(attachmentRow('pa-b')).getByRole('button', { name: 'Use as brochure image' }),
    ).toBeInTheDocument();
  });

  it('keeps a successful choice marked when a later save fails', async () => {
    // The roll-back target is what the server last accepted, not what the page
    // was first rendered with.
    getProductAttachmentsByProduct.mockResolvedValue([
      { ...PHOTO_A, is_primary: false },
      PHOTO_B,
      SPEC_PDF,
    ]);
    renderTab();

    await waitFor(() => expect(attachmentRow('pa-b')).toBeInTheDocument());

    fireEvent.click(
      within(attachmentRow('pa-b')).getByRole('button', { name: 'Use as brochure image' }),
    );
    await waitFor(() =>
      expect(within(attachmentRow('pa-b')).getByText('Brochure image')).toBeInTheDocument(),
    );

    setBrochureImage.mockRejectedValue(new Error('Product not found'));
    fireEvent.click(
      within(attachmentRow('pa-a')).getByRole('button', { name: 'Use as brochure image' }),
    );

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Product not found'));
    expect(within(attachmentRow('pa-b')).getByText('Brochure image')).toBeInTheDocument();
    expect(screen.getAllByText('Brochure image')).toHaveLength(1);
  });
});
