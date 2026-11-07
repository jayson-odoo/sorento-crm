'use client';

import Link from 'next/link';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { NewProductApplicationLineageRow } from '@/types/newProductApplication';
import { useProductLineageQuery } from '@/app/(protected)/procurement-management/new-product-applications/hooks/useNewProductApplications';

const TH = 'px-3 py-2 text-left font-medium';
const TD = 'px-3 py-2 align-top';

const codes = (row: NewProductApplicationLineageRow) =>
  row.current_products.map((p) => p.product_code).join(', ');

function LineageTable({
  title,
  rows,
  showNewCode,
}: {
  title: string;
  rows: NewProductApplicationLineageRow[];
  /** "New codes made from this product" names the code each row created. */
  showNewCode?: boolean;
}) {
  const showWho = rows.some((r) => r.customer_name || r.project_name);
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">None</p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[720px] table-fixed text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                {showNewCode && <th className={`${TH} w-40`}>New code</th>}
                <th className={`${TH} w-44`}>From product codes</th>
                <th className={TH}>Why</th>
                <th className={`${TH} w-36`}>Application</th>
                {showWho && (
                  <th className={`${TH} w-48`}>Customer / project</th>
                )}
                <th className={`${TH} w-20`}>Qty</th>
                <th className={`${TH} w-28`}>Created</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.line_id} className="border-t">
                  {showNewCode && (
                    <td className={TD}>
                      <Link
                        href={`/master-data-management/products/${row.product_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {row.product_code}
                      </Link>
                    </td>
                  )}
                  <td className={`${TD} break-words`}>{codes(row) || '-'}</td>
                  <td className={`${TD} break-words`}>
                    {row.description || '-'}
                  </td>
                  <td className={TD}>
                    {row.application_id && row.application_no ? (
                      <Link
                        href={`/procurement-management/new-product-applications/${row.application_id}`}
                        className="text-primary hover:underline"
                      >
                        {row.application_no}
                      </Link>
                    ) : (
                      row.application_no || '-'
                    )}
                  </td>
                  {showWho && (
                    <td className={`${TD} break-words`}>
                      {[row.customer_name, row.project_name]
                        .filter(Boolean)
                        .join(' / ') || '-'}
                    </td>
                  )}
                  <td className={TD}>{row.expected_qty ?? '-'}</td>
                  <td className={TD}>
                    {row.created_at
                      ? formatDateInMalaysia(row.created_at)
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Read-only: what this code was created from, and the codes made from it. */
export default function ProductLineageTab({
  productId,
}: {
  productId: string;
}) {
  const { data, isLoading, isError } = useProductLineageQuery(productId);
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const created = data?.created_from ?? [];
  const made = data?.made_from_this ?? [];
  // A refusal (no permission) reads the same as nothing to show.
  if (isError || (created.length === 0 && made.length === 0)) {
    return (
      <div className="rounded-lg border border-dashed px-6 py-10 text-center">
        <h3 className="text-base font-semibold">No lineage</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Codes created through a New Product Application show here.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <LineageTable title="Created from" rows={created} />
      <LineageTable
        title="New codes made from this product"
        rows={made}
        showNewCode
      />
    </div>
  );
}
