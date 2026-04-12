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
