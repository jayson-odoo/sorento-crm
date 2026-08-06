import type { QuotationDocument } from '../services/quotationDocumentService';

/**
 * Where a quotation stands, in the one word a row or a badge has space for.
 *
 * The backend resolves `customer_decision` (acceptance beats a request when both stamps are set,
 * because a customer who asked for a lower price and then signed has accepted). This turns that
 * answer into a label and a tone, in ONE place, so the project's quotation list and the document
 * itself cannot end up telling a salesperson two different things about the same record.
 *
 * The customer's decision REPLACES Issued rather than sitting beside it: an issued quotation the
 * customer has answered is not still waiting, and a row carrying both reads as neither.
 */
export type QuotationStanding = {
  label: string;
  variant: 'success' | 'warning' | 'secondary';
};

export function quotationStanding(document: QuotationDocument): QuotationStanding {
  if (document.customer_decision === 'accepted') {
    return { label: 'Accepted', variant: 'success' };
  }
  if (document.customer_decision === 'changes_requested') {
    return { label: 'Changes requested', variant: 'warning' };
  }
  return document.is_issued
    ? { label: 'Issued', variant: 'success' }
    : { label: 'Draft', variant: 'secondary' };
}

/**
 * Whether the customer is currently waiting on a revision.
 *
 * Read off the resolved decision and never off `changes_requested_at`: those words stay on the
 * row as history after an acceptance, and a banner that read the raw stamp would go on asking
 * somebody to revise a quotation that is already won.
 */
export function hasOpenChangeRequest(document: QuotationDocument): boolean {
  return document.customer_decision === 'changes_requested';
}
