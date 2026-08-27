'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useProformaInvoices } from '../../hooks/useProformaInvoices';
import type { ProformaPlacement } from '../../services/proformaInvoiceService';

/**
 * Prev/next over the proforma-invoice list, the twin of `PurchaseOrderNavigation`.
 *
 * The neighbours come from the SAME filtered, searched page the reader was looking at,
 * rebuilt from the query the list carried into the detail URL. It used to fetch the newest
 * 100 invoices unfiltered instead, so the row after the one you opened was not the row under
 * it in the list - which is the whole promise a pager makes.
 *
 * **The walk is that page, and it stops at both ends**, the same as the purchase-order
 * pager: the counter says where the reader is within the page they chose to look at, and a
 * chevron that silently jumped from the last row back to the first would read as a broken
 * step rather than as a feature.
 *
 * The list endpoint pages by `limit`/`offset` rather than `page`, and caps `limit` at 100
 * (`Query(25, ge=1, le=100)`). A higher value 422s the whole fetch, which surfaces as a
 * stray unattributed toast AND leaves `data` undefined - so the pager silently renders
 * nothing. The page size is clamped here rather than trusted from the URL.
 */
const MAX_LIMIT = 100;

export default function ProformaInvoiceNavigation({
  invoiceId,
  className,
}: {
  invoiceId: string;
  className?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(new URLSearchParams(searchParams?.toString() ?? ''));
    const pageSize = Math.min(parsed.pageSize, MAX_LIMIT);
    return {
      supplierId: parsed.filters.supplier_id || null,
      placement: (parsed.filters.placement as ProformaPlacement) || null,
      query: parsed.searchQuery || null,
      limit: pageSize,
      offset: parsed.pageIndex * pageSize,
    };
  }, [searchParams]);

  const { data } = useProformaInvoices(listParams.supplierId, {
    placement: listParams.placement,
    query: listParams.query,
    limit: listParams.limit,
    offset: listParams.offset,
  });
  const items = useMemo(() => (data?.data ?? []).map((row) => ({ id: row.id })), [data]);

  // Keep the list query on the URL as the reader steps, or the second hop would lose the set.
  const handleSelect = (id: string) => {
    const qs = searchParams?.toString() ?? '';
    router.push(`/scm/proforma-invoices/${id}${qs ? `?${qs}` : ''}`);
  };

  if (items.length < 2) return null;

  return (
    <RecordNavigation
      basePath="/scm/proforma-invoices"
      currentId={invoiceId}
      items={items}
      circular={false}
      onSelect={handleSelect}
      ariaLabel="proforma invoice"
      className={className}
    />
  );
}
