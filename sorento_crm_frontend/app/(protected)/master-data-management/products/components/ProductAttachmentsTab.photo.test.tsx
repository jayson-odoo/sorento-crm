/**
 * S21 (CHO-3) - choosing which photograph IS the product, on the product.
 *
 * This is the other end of the quotation line's "No photo chosen" link, and the reason that link
 * is worth having. The flag it writes - `product_attachments.is_primary` - is the SAME one the
 * brochure and 3D-model generation read, so this is not "the quotation's picture": it is the
 * product's, answered once.
 *
 * The rules pinned here came from the project-sales branch, which shipped its own star button on
 * this tab. They survive the merge; the control does not. `ProductBrochureImageControl` (main)
 * answers the same question and does more of it - it can also CLEAR the choice, behind a
 * confirmation - so the two were folded into one rather than left as two ways to say the same
 * thing on the same row.
 *
 * Two rules from the original are unchanged. A PDF can never be the product photo (the live data
 * holds 532 of them linked to products, and a spec sheet rendered as the product is worse than
 * no photo at all), and the row that already holds the choice is not offered it again. One
 * changed deliberately: the chosen row still renders a disabled mark plus a Clear action, where
 * the star button rendered nothing, because a choice you cannot see is a choice you cannot undo.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { ProductAttachment } from '../../product-attachments/types/productAttachment.types';

const PRODUCT_ID = 'product-1';

const getProductAttachmentsByProduct = vi.fn();
const setBrochureImage = vi.fn();
const clearBrochureImage = vi.fn();

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  custom: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: toastMock }));

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

// Peripheral panels of the tab; none of them touch the choice.
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
  mimeType: string,
  isPrimary: boolean,
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

const PHOTO = row('link-photo', 'att-photo', 'CWC604-RL front.jpg', 'image/jpeg', false);
const CHOSEN = row('link-chosen', 'att-chosen', 'CWC604-RL angle.jpg', 'image/jpeg', true);
const SPEC = row('link-spec', 'att-spec', 'CWC604-RL spec.pdf', 'application/pdf', false);

function renderTab(isEditMode = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductAttachmentsTab productId={PRODUCT_ID} isEditMode={isEditMode} />
    </QueryClientProvider>,
  );
}

function attachmentRow(productAttachmentId: string) {
  return screen.getByTestId(`product-attachment-row-${productAttachmentId}`);
}

beforeEach(() => {
  vi.clearAllMocks();
  getProductAttachmentsByProduct.mockResolvedValue([PHOTO, CHOSEN, SPEC]);
  setBrochureImage.mockResolvedValue(undefined);
  clearBrochureImage.mockResolvedValue(undefined);
});

afterEach(() => cleanup());

describe('ProductAttachmentsTab - choosing the product photo', () => {
  it('offers the choice on an image that is not chosen, and on nothing else', async () => {
    renderTab();
    await waitFor(() => expect(attachmentRow('link-photo')).toBeInTheDocument());

    expect(
      within(attachmentRow('link-photo')).getByRole('button', { name: 'Use as brochure image' }),
    ).toBeInTheDocument();
    // Already the product's photo: offering it again reads as if it were not chosen. It shows
    // the mark and a way out instead.
    expect(
      within(attachmentRow('link-chosen')).queryByRole('button', {
        name: 'Use as brochure image',
      }),
    ).not.toBeInTheDocument();
    expect(
      within(attachmentRow('link-chosen')).getByRole('button', {
        name: 'Already the brochure image',
      }),
    ).toBeDisabled();
    // A spec sheet is not a photograph of the product.
    expect(
      within(attachmentRow('link-spec')).queryByRole('button', { name: 'Use as brochure image' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('Brochure image')).toBeInTheDocument();
  });

  it('writes the ONE decision, and never a second concept', async () => {
    renderTab();
    await waitFor(() => expect(attachmentRow('link-photo')).toBeInTheDocument());

    fireEvent.click(
      within(attachmentRow('link-photo')).getByRole('button', { name: 'Use as brochure image' }),
    );

    await waitFor(() => expect(setBrochureImage).toHaveBeenCalledWith(PRODUCT_ID, 'att-photo'));
    expect(setBrochureImage).toHaveBeenCalledTimes(1);
  });

  it('confirms before clearing the choice, and sends nothing until it is confirmed', async () => {
    renderTab();
    await waitFor(() => expect(attachmentRow('link-chosen')).toBeInTheDocument());

    fireEvent.click(
      within(attachmentRow('link-chosen')).getByRole('button', { name: 'Clear brochure image' }),
    );

    const dialog = await screen.findByRole('alertdialog');
    expect(clearBrochureImage).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Clear' }));

    await waitFor(() => expect(clearBrochureImage).toHaveBeenCalledWith(PRODUCT_ID));
  });

  it('offers nothing to change while the tab is only being read', async () => {
    renderTab(false);
    await waitFor(() => expect(attachmentRow('link-photo')).toBeInTheDocument());

    expect(
      screen.queryByRole('button', { name: 'Use as brochure image' }),
    ).not.toBeInTheDocument();
    // The badge still says which one was picked: a read should still answer the question.
    expect(screen.getByText('Brochure image')).toBeInTheDocument();
  });
});
