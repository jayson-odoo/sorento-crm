/**
 * AC-CONSIGN-CRM: the order document type (`sales_orders.doc_type` on the backend, carried to
 * the Order Inquiry, Fulfilment Planning and board rows as `so_doc_type`). Only a consignment
 * is marked; a plain sales order shows nothing, so the rest of the book reads as before.
 */
import { Badge } from '@/components/ui/badge';

/** True for a consignment order document (`so_doc_type`). */
export const isConsignment = (docType: string | null | undefined): boolean =>
  docType === 'consignment';

export function ConsignmentBadge({
  docType,
  size = 'sm',
}: {
  docType: string | null | undefined;
  size?: 'xs' | 'sm' | 'md';
}) {
  if (!isConsignment(docType)) return null;
  return (
    <Badge variant="info" appearance="light" size={size} className="w-fit">
      Consignment
    </Badge>
  );
}
