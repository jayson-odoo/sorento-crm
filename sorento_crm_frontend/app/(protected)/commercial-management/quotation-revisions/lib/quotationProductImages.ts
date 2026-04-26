import type { ProductAttachment } from '@/app/(protected)/master-data-management/product-attachments/types/productAttachment.types';

/** Attachment type label configured in master data — product imagery for quotation lines. */
const PRODUCT_IMAGE_TYPE_NAMES = new Set(['product image', 'product_image', 'productimage']);
const TECHNICAL_SPEC_TYPE_NAMES = new Set([
  'technical spec',
  'technical specs',
  'technical_spec',
  'technical specification',
  'technical specifications',
]);

function attachmentTypeName(pa: ProductAttachment): string {
  return pa.attachment?.attachment_type?.type_name?.trim().toLowerCase() ?? '';
}

export function isProductImageAttachment(pa: ProductAttachment): boolean {
  const name = attachmentTypeName(pa);
  if (!name) return false;
  return PRODUCT_IMAGE_TYPE_NAMES.has(name);
}

export function isTechnicalSpecAttachment(pa: ProductAttachment): boolean {
  const name = attachmentTypeName(pa);
  if (!name) return false;
  return TECHNICAL_SPEC_TYPE_NAMES.has(name);
}

/** Stable order: primary first, then sort_order, then filename. */
export function sortProductImageAttachments(rows: ProductAttachment[]): ProductAttachment[] {
  return [...rows].sort((a, b) => {
    const pa = a.is_primary ? 1 : 0;
    const pb = b.is_primary ? 1 : 0;
    if (pb !== pa) return pb - pa;
    const sa = a.sort_order ?? 0;
    const sb = b.sort_order ?? 0;
    if (sa !== sb) return sa - sb;
    const fa = a.attachment?.original_filename ?? '';
    const fb = b.attachment?.original_filename ?? '';
    return fa.localeCompare(fb);
  });
}

export function filterProductImageAttachments(all: ProductAttachment[]): ProductAttachment[] {
  const imgs = all.filter(isProductImageAttachment);
  return sortProductImageAttachments(imgs);
}

export function filterTechnicalSpecAttachments(all: ProductAttachment[]): ProductAttachment[] {
  const specs = all.filter(isTechnicalSpecAttachment);
  return sortProductImageAttachments(specs);
}
