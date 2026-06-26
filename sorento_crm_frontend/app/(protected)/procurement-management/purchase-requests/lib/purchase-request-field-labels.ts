/** Title-case entity label for a request_type — the single source of truth so
 *  sponsorship forms never surface "Purchase Request" to the user, and vice
 *  versa. Replaces the per-component REQUEST_TYPE_LABELS copies. */
export function requestTypeLabel(requestType: string | null | undefined): string {
  if (requestType === 'sponsorship_form') return 'Sponsorship Form';
  if (requestType === 'purchase_request') return 'Purchase Request';
  return 'Request';
}

/** Lowercase entity label for mid-sentence use (toasts, errors, aria-labels). */
export function requestTypeLabelLower(requestType: string | null | undefined): string {
  if (requestType === 'sponsorship_form') return 'sponsorship form';
  if (requestType === 'purchase_request') return 'purchase request';
  return 'request';
}

/** User-visible label for the request_number field (lists, forms, detail). */
export function purchaseRequestNumberFieldLabel(
  requestType: string | null | undefined,
): string {
  if (requestType === 'sponsorship_form') return 'Sponsorship form number';
  if (requestType === 'purchase_request') return 'Purchase request number';
  return 'Request number';
}

/** Phrase for chat / reply templates (lowercase phrase + number). */
export function purchaseRequestNumberReplyPhrase(
  requestType: string | null | undefined,
  requestNumber: string | null | undefined,
): string {
  const n = (requestNumber ?? '').trim();
  if (requestType === 'sponsorship_form') {
    return n ? `sponsorship form number ${n}` : 'sponsorship form number';
  }
  return n ? `purchase request number ${n}` : 'purchase request number';
}
