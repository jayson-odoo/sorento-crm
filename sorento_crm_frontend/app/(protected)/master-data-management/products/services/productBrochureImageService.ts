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
 * PUT    /api/v1/master-data/product-attachments/brochure-images/{productId}  { attachment_id }
 * DELETE /api/v1/master-data/product-attachments/brochure-images/{productId}
 */
export async function setBrochureImage(productId: string, attachmentId: string): Promise<void> {
  const response = await apiFetch(
    `/api/master-data/product-attachments/brochure-images/${productId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attachment_id: attachmentId }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to set the brochure image'));
  }
}

export async function clearBrochureImage(productId: string): Promise<void> {
  const response = await apiFetch(
    `/api/master-data/product-attachments/brochure-images/${productId}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to clear the brochure image'));
  }
}
