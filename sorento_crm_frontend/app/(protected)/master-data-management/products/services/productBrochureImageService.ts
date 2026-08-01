import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The brochure image is the one photo a catalogue tile shows for a product.
 * It is stored as `product_attachments.is_primary`, which the tile renderer
 * already orders by, so no new column and no renderer change.
 *
 * The backend owns the "exactly one per product" invariant: setting a new one
 * clears the previous in the same transaction, because two flagged rows would
 * put the tile back to depending on row order.
 *
 * This is the ONLY place the flag is written. The Dealer Kit picker is the
 * second surface that sets it and imports from here rather than keeping its
 * own copy: the two copies that existed briefly drifted in URL spelling and in
 * failure message, and neither drift could fail because both spellings resolve
 * through the api rewrite table.
 *
 * PUT    /api/v1/master-data/product-attachments/brochure-images/{productId}  { attachment_id }
 * DELETE /api/v1/master-data/product-attachments/brochure-images/{productId}
 */
const BASE = '/api/v1/master-data/product-attachments/brochure-images';

export interface BrochureImageChoice {
  productId: string;
  chosenAttachmentId: string | null;
}

export async function setBrochureImage(
  productId: string,
  attachmentId: string,
): Promise<BrochureImageChoice> {
  const response = await apiFetch(`${BASE}/${productId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attachment_id: attachmentId }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to set the brochure image'));
  }
  return (await response.json()) as BrochureImageChoice;
}

export async function clearBrochureImage(productId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${productId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to clear the brochure image'));
  }
}
