/**
 * S21 (CHO-3) - choosing which photograph IS the product, on the product.
 *
 * This is the other end of the quotation line's "No photo chosen" link, and the reason that link
 * is worth having. The flag it writes - `product_attachments.is_primary` - is the SAME one the
 * brochure and 3D-model generation read, so this is not "the quotation's picture": it is the
 * product's, answered once.
 *
 * Two rules are pinned. A PDF can never be the product photo (the live data holds 532 of them
 * linked to products, and a spec sheet rendered as the product is worse than no photo at all),
 * and the row that already holds the choice is not offered it again.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mutate = vi.fn();

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>(
    '@tanstack/react-query',
  );
  return { ...actual, useQueryClient: () => ({ setQueryData: vi.fn(), invalidateQueries: vi.fn() }) };
});

const attachments = [
  {
    id: 'link-photo',
    product_id: 'product-1',
    attachment_id: 'att-photo',
    is_primary: false,
    attachment: {
      id: 'att-photo',
      original_filename: 'CWC604-RL front.jpg',
      mime_type: 'image/jpeg',
      full_directory_path: 'Products',
    },
  },
  {
    id: 'link-chosen',
    product_id: 'product-1',
    attachment_id: 'att-chosen',
    is_primary: true,
    attachment: {
      id: 'att-chosen',
      original_filename: 'CWC604-RL angle.jpg',
      mime_type: 'image/jpeg',
      full_directory_path: 'Products',
    },
  },
  {
    id: 'link-spec',
    product_id: 'product-1',
    attachment_id: 'att-spec',
    is_primary: false,
    attachment: {
      id: 'att-spec',
      original_filename: 'CWC604-RL spec.pdf',
      mime_type: 'application/pdf',
      full_directory_path: 'Products',
    },
  },
];

vi.mock('../../product-attachments/hooks/useProductAttachments', () => ({
  useProductAttachmentsByProduct: () => ({ data: attachments, isLoading: false }),
  useDeleteProductAttachment: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateProductAttachment: () => ({ mutate, isPending: false }),
}));

vi.mock('../hooks/useProducts', () => ({ useProduct: () => ({ data: null }) }));
vi.mock('../hooks/useFieldLinkageSchema', () => ({
  useFieldLinkageSchema: () => ({ data: { fields: [] } }),
}));
vi.mock(
  '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes',
  () => ({ useContactAccessTypes: () => ({ data: [] }) }),
);
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
vi.mock(
  '@/app/(protected)/resource-management/attachments/components/ManageFieldLinksDialog',
  () => ({ default: () => null }),
);

import ProductAttachmentsTab from './ProductAttachmentsTab';

describe('ProductAttachmentsTab - choosing the product photo', () => {
  beforeEach(() => {
    mutate.mockClear();
  });

  it('offers the choice on an image that is not chosen, and on nothing else', () => {
    render(<ProductAttachmentsTab productId="product-1" isEditMode />);

    expect(screen.getByTestId('choose-product-photo-link-photo')).toBeInTheDocument();
    // Already the product's photo: nothing to do, and re-offering it reads as if it were not.
    expect(screen.queryByTestId('choose-product-photo-link-chosen')).not.toBeInTheDocument();
    // A spec sheet is not a photograph of the product.
    expect(screen.queryByTestId('choose-product-photo-link-spec')).not.toBeInTheDocument();
    expect(screen.getByText('Product photo')).toBeInTheDocument();
  });

  it('writes the ONE flag, and never a second concept', () => {
    render(<ProductAttachmentsTab productId="product-1" isEditMode />);

    screen.getByTestId('choose-product-photo-link-photo').click();

    expect(mutate).toHaveBeenCalledWith({ id: 'link-photo', data: { is_primary: true } });
  });

  it('offers nothing to change while the tab is only being read', () => {
    render(<ProductAttachmentsTab productId="product-1" isEditMode={false} />);

    expect(screen.queryByTestId('choose-product-photo-link-photo')).not.toBeInTheDocument();
    // The badge still says which one was picked: a read should still answer the question.
    expect(screen.getByText('Product photo')).toBeInTheDocument();
  });
});
