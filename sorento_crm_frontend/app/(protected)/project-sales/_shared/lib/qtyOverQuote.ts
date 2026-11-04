import { codedError, type CodedError } from '@/lib/api-client';

/** PS-PROPOSAL-QUOTATION: the backend's soft stop on a PO save or confirm. */
export const QTY_OVER_QUOTED = 'po_qty_over_quoted';

export type QtyOverProduct = {
  product_code: string | null;
  description: string | null;
  /** Total over the project's live POs checked against the quotation. */
  ordered: string;
  /** What the quotation quotes now. */
  quoted: string;
};

export interface QtyOverError extends CodedError {
  products: QtyOverProduct[];
}

/**
 * `codedError` plus the products a 409 `po_qty_over_quoted` names, so the screen can ask for the
 * reason and send the save again. Any other refusal comes back with `products` empty.
 */
export async function qtyOverAwareError(
  response: Response,
  fallback: string,
): Promise<QtyOverError> {
  const clone = response.clone();
  const error = (await codedError(response, fallback)) as QtyOverError;
  error.products = [];
  if (error.code === QTY_OVER_QUOTED) {
    try {
      const body = (await clone.json()) as {
        details?: { products?: QtyOverProduct[] };
        detail?: { details?: { products?: QtyOverProduct[] } };
      };
      error.products = body?.details?.products ?? body?.detail?.details?.products ?? [];
    } catch {
      // No body: the dialog still asks for a reason, it just cannot list the products.
    }
  }
  return error;
}

export function isQtyOver(error: unknown): error is QtyOverError {
  return Boolean(error) && (error as QtyOverError).code === QTY_OVER_QUOTED;
}
