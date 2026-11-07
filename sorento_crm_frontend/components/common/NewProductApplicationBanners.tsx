'use client';

import { Badge } from '@/components/ui/badge';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { NewProductApplicationCreatedCode } from '@/types/newProductApplication';

/** The slice of an application the stock inquiry banners and tabs read. */
export interface InquiryApplicationRow {
  id: string;
  application_no: string;
  status: string;
  status_label: string;
  created_at: string | null;
  created_codes?: NewProductApplicationCreatedCode[];
}

/** Live = still in play: not cancelled and not rejected. */
export const isLiveApplication = (a: Pick<InquiryApplicationRow, 'status'>) =>
  a.status !== 'cancelled' && a.status !== 'rejected';

/** Purchasing asked for an application and nobody has a live one yet. */
export const npaStillToCreate = (
  requested: boolean | null | undefined,
  applications: Pick<InquiryApplicationRow, 'status'>[],
) => Boolean(requested) && !applications.some(isLiveApplication);

/**
 * The next-step banner (blue) and the code-created banners (green) of a stock inquiry. Staff and
 * portal share it; `audience` only changes who is asked.
 */
export function NewProductApplicationBanners({
  requested,
  applications,
  audience,
}: {
  requested: boolean | null | undefined;
  applications: InquiryApplicationRow[];
  audience: 'staff' | 'portal';
}) {
  const created = applications.filter((a) => (a.created_codes ?? []).length > 0);
  const ask = npaStillToCreate(requested, applications);
  if (!ask && created.length === 0) return null;
  return (
    <div className="space-y-2">
      {ask && (
        <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
          {audience === 'portal'
            ? 'Purchasing asks you to create a New Product Application.'
            : 'Purchasing asks the salesperson to create a New Product Application.'}
        </div>
      )}
      {created.map((a) => {
        const codes = a.created_codes ?? [];
        const when = codes[0]?.created_at;
        return (
          <div
            key={a.id}
            className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900"
          >
            New code {codes.map((c) => c.product_code).join(', ')} created
            {when ? ` on ${formatDateInMalaysia(when)}` : ''} ({a.application_no}).
          </div>
        );
      })}
    </div>
  );
}

/** The "New product applications" tab body: number, status, current codes -> new code, date. */
export function InquiryApplicationsList({
  applications,
  renderNumber,
}: {
  applications: InquiryApplicationRow[];
  renderNumber: (a: InquiryApplicationRow) => React.ReactNode;
}) {
  if (applications.length === 0) {
    return (
      <div className="rounded-lg border border-dashed px-6 py-10 text-center">
        <h3 className="text-base font-semibold">No new product applications</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Applications created from this inquiry show here.
        </p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full min-w-[560px] table-fixed text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="w-36 px-3 py-2 text-left font-medium">Application</th>
            <th className="w-32 px-3 py-2 text-left font-medium">Status</th>
            <th className="px-3 py-2 text-left font-medium">New code</th>
            <th className="w-28 px-3 py-2 text-left font-medium">Date</th>
          </tr>
        </thead>
        <tbody>
          {applications.map((a) => (
            <tr key={a.id} className="border-t">
              <td className="px-3 py-2 align-top font-medium">{renderNumber(a)}</td>
              <td className="px-3 py-2 align-top"><Badge status={a.status}>{a.status_label}</Badge></td>
              <td className="break-words px-3 py-2 align-top">
                {(a.created_codes ?? []).length > 0
                  ? (a.created_codes ?? [])
                      .map(
                        (c) =>
                          `${c.current_codes.length ? `${c.current_codes.join(', ')} -> ` : ''}${c.product_code}`,
                      )
                      .join('; ')
                  : '-'}
              </td>
              <td className="px-3 py-2 align-top">
                {a.created_at ? formatDateInMalaysia(a.created_at) : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
