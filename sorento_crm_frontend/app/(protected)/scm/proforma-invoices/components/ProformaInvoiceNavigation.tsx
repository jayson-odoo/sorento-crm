'use client';

import { useMemo } from 'react';
import RecordNavigation from '@/components/common/RecordNavigation';
import { useProformaInvoices } from '../../hooks/useProformaInvoices';

/**
 * Prev/next over the proforma-invoice list (view/edit-structure ADR: every detail page carries
 * record navigation - see `components/common/RecordNavigation`, established by
 * `purchase-orders/components/PurchaseOrderNavigation.tsx`).
 *
 * Kept simpler than the purchase-order pager on purpose: PO's version reconstructs the exact
 * filtered/sorted/paged list the user was looking at from the URL the list handed the detail
 * page, because a buyer works down a specific worklist one row at a time. A proforma invoice
 * has no equivalent single worklist - it is opened from the plain list AND from other drills -
 * so the neighbours here are just the newest invoices, supplier-unfiltered, in the list
 * endpoint's own default order (`created_at DESC`, S9).
 *
 * 100, not the 200 the PO/SO pagers use (`GET .../proforma-invoices`'s own `limit` is
 * `Query(25, ge=1, le=100)` - PO/SO cap at 200). A higher value 422s the whole fetch
 * ("Input should be less than or equal to 100"), which `useProformaInvoices` surfaces as a
 * stray, unattributed toast AND leaves `data` undefined - so `items.length < 2` and this
 * component silently renders nothing instead of the pager. Found via browser evidence run
 * against the real backend (the mocked-hook component test never exercises the real cap).
 */
const NEIGHBOUR_LIMIT = 100;

export default function ProformaInvoiceNavigation({
  invoiceId,
  className,
}: {
  invoiceId: string;
  className?: string;
}) {
  const { data } = useProformaInvoices(null, { limit: NEIGHBOUR_LIMIT });
  const items = useMemo(() => (data?.data ?? []).map((row) => ({ id: row.id })), [data]);

  if (items.length < 2) return null;

  return (
    <RecordNavigation
      basePath="/scm/proforma-invoices"
      currentId={invoiceId}
      items={items}
      totalCount={data?.total}
      ariaLabel="proforma invoice"
      className={className}
    />
  );
}
